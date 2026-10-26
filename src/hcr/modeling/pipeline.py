"""The scikit-learn Pipeline that keeps every transform inside the fold.

This is the technical constraint the whole training design rests on: every
data-dependent transform lives inside a Pipeline and is fitted within each fold,
never once over the full matrix beforehand. It applies to imputation, scaling,
encoding and any feature selection step.

Three of the five leakage sources are defeated here rather than by discipline.
Target encoding computed outside the fold shows up as very high cross-validated
AUC and a sharp holdout drop. Imputation from full-matrix statistics leaks a
little, systematically. Scaling fitted on the full matrix leaks a little. All three
disappear when the transform is a Pipeline step.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Final

import polars as pl
from lightgbm import LGBMClassifier
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ID_COLUMN: Final = "SK_ID_CURR"
LABEL_COLUMN: Final = "TARGET"

PREPROCESS_STEP: Final = "preprocess"
ESTIMATOR_STEP: Final = "estimator"
NUMERIC_BRANCH: Final = "numeric"
CATEGORICAL_BRANCH: Final = "categorical"
LOGISTIC_MAX_ITER: Final = 1000
MISSING_CATEGORY_LABEL: Final = "MISSING"
MEDIAN_IMPUTE: Final = "median"
CONSTANT_IMPUTE: Final = "constant"

_CATEGORICAL_DTYPES: Final = (pl.String, pl.Categorical)


def numeric_columns(schema: pl.Schema) -> tuple[str, ...]:
    """Return the numeric feature columns, excluding the id and the label.

    Booleans count as numeric because the models read them as 0 and 1. A column of any
    other dtype stops the pipeline, since guessing how to encode it would be a silent
    choice.

    Raises:
        ValueError: If a feature column is neither numeric, boolean nor categorical.
    """
    numeric, _ = _partition_feature_columns(schema)
    return numeric


def categorical_columns(schema: pl.Schema) -> tuple[str, ...]:
    """Return the categorical feature columns, identified by dtype.

    Raises:
        ValueError: If a feature column is neither numeric, boolean nor categorical.
    """
    _, categorical = _partition_feature_columns(schema)
    return categorical


def build_lightgbm_pipeline(params: dict[str, Any]) -> Pipeline:
    """Build the LightGBM pipeline, which deliberately imputes nothing.

    LightGBM handles nulls natively and learns which direction the missing branch
    should take. That is the reason it is the primary model here: EXT_SOURCE_1 is
    absent for 56 percent of applicants and OWN_CAR_AGE for 66 percent, and in both
    cases the absence is informative. An imputer in front of this estimator would
    destroy exactly the signal the choice of estimator was made to capture.

    Args:
        params: Hyperparameters from configs/model.yml.

    Returns:
        A Pipeline whose only step is the estimator.

    TODO:
        - Pass categorical features to LightGBM as native categoricals rather than
          one-hot encoding them, when train.py needs it. One-hot over ORGANIZATION_TYPE
          at 59 levels fragments the splits.
        - Set scale_pos_weight per fold with scale_pos_weight_from_labels, from the fold's
          training labels only, never from the full matrix.
    """
    return Pipeline([(ESTIMATOR_STEP, LGBMClassifier(**params))])


def build_logistic_pipeline(
    numeric: tuple[str, ...],
    categorical: tuple[str, ...],
) -> Pipeline:
    """Build the logistic regression baseline pipeline, which must impute.

    Unlike the tree, logistic regression cannot consume a null, so it needs an
    imputer, and that imputer must be a Pipeline step so it fits inside the fold.
    This difference is itself the argument for the tree being the primary model: the
    baseline is forced to fill a value and lose the information that absence
    carries. The median imputer adds an indicator column, so the fact of absence
    survives the fill.

    Args:
        numeric: Numeric column names.
        categorical: Categorical column names.

    Returns:
        A ColumnTransformer-based Pipeline ending in the estimator.
    """
    preprocess = ColumnTransformer(
        [
            (NUMERIC_BRANCH, _numeric_branch(), list(numeric)),
            (CATEGORICAL_BRANCH, _categorical_branch(), list(categorical)),
        ],
        remainder="drop",
    )
    return Pipeline(
        [
            (PREPROCESS_STEP, preprocess),
            (
                ESTIMATOR_STEP,
                LogisticRegression(class_weight="balanced", max_iter=LOGISTIC_MAX_ITER),
            ),
        ]
    )


def scale_pos_weight_from_labels(labels: pl.Series) -> float:
    """Return the negative-to-positive ratio that balances the LightGBM loss.

    Called per fold on that fold's training labels, so the holdout class balance never
    reaches the model.

    Raises:
        ValueError: If the labels hold no positive case, since the ratio is undefined.
    """
    positives = int(labels.sum())
    if positives == 0:
        raise ValueError("Cannot derive scale_pos_weight from labels with no positive case")
    return (labels.len() - positives) / positives


def assert_no_transform_outside_pipeline(pipeline: Pipeline) -> None:
    """Assert the pipeline contains every data-dependent step it should.

    A guard against the habit this design exists to prevent: fitting an imputer or
    an encoder before cross-validation and passing the transformed matrix in. The
    logistic pipeline must carry its imputer and scaler; the LightGBM pipeline must
    carry no imputer, since filling nulls would erase the signal it was chosen for.

    Raises:
        ValueError: If a required step is absent, a forbidden step is present, or the
            estimator is not one this project trains.
    """
    estimator = pipeline.steps[-1][1]
    transformer_types = {type(step) for step in _leaf_steps(pipeline)}
    if isinstance(estimator, LogisticRegression):
        missing = {SimpleImputer, StandardScaler} - transformer_types
        if missing:
            raise ValueError(f"Logistic pipeline lacks in-fold steps: {sorted(missing, key=str)}")
        return
    if isinstance(estimator, LGBMClassifier):
        if SimpleImputer in transformer_types:
            raise ValueError("LightGBM pipeline must not impute: missingness is a feature")
        return
    raise ValueError(f"Unrecognised estimator in pipeline: {type(estimator).__name__}")


def _numeric_branch() -> Pipeline:
    return Pipeline(
        [
            (
                "impute",
                SimpleImputer(strategy=MEDIAN_IMPUTE, add_indicator=True),
            ),
            ("scale", StandardScaler()),
        ]
    )


def _categorical_branch() -> Pipeline:
    return Pipeline(
        [
            (
                "impute",
                SimpleImputer(strategy=CONSTANT_IMPUTE, fill_value=MISSING_CATEGORY_LABEL),
            ),
            ("encode", OneHotEncoder(handle_unknown="ignore")),
        ]
    )


def _partition_feature_columns(schema: pl.Schema) -> tuple[tuple[str, ...], tuple[str, ...]]:
    numeric: list[str] = []
    categorical: list[str] = []
    for name, dtype in schema.items():
        if name in (ID_COLUMN, LABEL_COLUMN):
            continue
        if dtype == pl.Boolean or dtype.is_numeric():
            numeric.append(name)
        elif _is_categorical_dtype(dtype):
            categorical.append(name)
        else:
            raise ValueError(f"Column {name} has unsupported dtype {dtype}")
    return tuple(numeric), tuple(categorical)


def _is_categorical_dtype(dtype: pl.DataType | type[pl.DataType]) -> bool:
    return isinstance(dtype, pl.Enum) or dtype in _CATEGORICAL_DTYPES


def _leaf_steps(component: object) -> Iterator[object]:
    if isinstance(component, Pipeline):
        for _, step in component.steps:
            yield from _leaf_steps(step)
    elif isinstance(component, ColumnTransformer):
        for _, transformer, _ in component.transformers:
            yield from _leaf_steps(transformer)
    else:
        yield component
