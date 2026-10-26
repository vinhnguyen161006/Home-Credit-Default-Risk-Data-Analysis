"""Pipeline construction and the guard against transforms outside the fold.

The frames here carry nulls in both numeric and text columns, because those are the
inputs the imputers must survive. A pipeline that only fits clean data would pass while
proving nothing about the fold.
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from lightgbm import LGBMClassifier
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from hcr.modeling.pipeline import (
    ESTIMATOR_STEP,
    PREPROCESS_STEP,
    assert_no_transform_outside_pipeline,
    build_lightgbm_pipeline,
    build_logistic_pipeline,
    categorical_columns,
    numeric_columns,
    scale_pos_weight_from_labels,
)

LIGHTGBM_PARAMS: dict[str, object] = {"n_estimators": 5, "verbosity": -1}
ROW_COUNT = 40


@pytest.fixture
def mixed_frame() -> pl.DataFrame:
    rng = np.random.default_rng(7)
    return pl.DataFrame(
        {
            "SK_ID_CURR": list(range(ROW_COUNT)),
            "TARGET": [int(index % 4 == 0) for index in range(ROW_COUNT)],
            "EXT_SOURCE_1": [
                None if index % 3 == 0 else float(value)
                for index, value in enumerate(rng.uniform(size=ROW_COUNT))
            ],
            "AMT_CREDIT": rng.uniform(1e5, 1e6, ROW_COUNT),
            "FLAG_OWN_CAR": [index % 2 == 0 for index in range(ROW_COUNT)],
            "ORGANIZATION_TYPE": [
                None if index % 5 == 0 else "School" for index in range(ROW_COUNT)
            ],
        }
    )


def test_numeric_columns_exclude_identifier_and_label(mixed_frame: pl.DataFrame) -> None:
    numeric = numeric_columns(mixed_frame.schema)

    assert "SK_ID_CURR" not in numeric
    assert "TARGET" not in numeric
    assert {"EXT_SOURCE_1", "AMT_CREDIT", "FLAG_OWN_CAR"} <= set(numeric)


def test_categorical_columns_are_identified_by_dtype(mixed_frame: pl.DataFrame) -> None:
    assert categorical_columns(mixed_frame.schema) == ("ORGANIZATION_TYPE",)


def test_unsupported_dtype_stops_column_classification() -> None:
    schema = pl.Schema({"SK_ID_CURR": pl.Int64, "TARGET": pl.Int64, "WHEN": pl.Date})

    with pytest.raises(ValueError, match="unsupported dtype"):
        numeric_columns(schema)


def test_logistic_pipeline_fits_frame_with_nulls(mixed_frame: pl.DataFrame) -> None:
    features = mixed_frame.drop("SK_ID_CURR", "TARGET")
    pipeline = build_logistic_pipeline(
        numeric=numeric_columns(features.schema),
        categorical=categorical_columns(features.schema),
    )

    pipeline.fit(features.to_pandas(), mixed_frame["TARGET"].to_numpy())
    probabilities = pipeline.predict_proba(features.to_pandas())[:, 1]

    assert np.all((probabilities >= 0.0) & (probabilities <= 1.0))


def test_logistic_pipeline_passes_the_in_fold_guard() -> None:
    pipeline = build_logistic_pipeline(numeric=("EXT_SOURCE_1",), categorical=())

    assert_no_transform_outside_pipeline(pipeline)


def test_logistic_guard_rejects_pipeline_without_scaler() -> None:
    preprocess = ColumnTransformer(
        [("numeric", SimpleImputer(strategy="median"), ["EXT_SOURCE_1"])]
    )
    pipeline = Pipeline([(PREPROCESS_STEP, preprocess), (ESTIMATOR_STEP, LogisticRegression())])

    with pytest.raises(ValueError, match="in-fold steps"):
        assert_no_transform_outside_pipeline(pipeline)


def test_lightgbm_pipeline_passes_the_guard_without_imputer() -> None:
    pipeline = build_lightgbm_pipeline(LIGHTGBM_PARAMS)

    assert_no_transform_outside_pipeline(pipeline)


def test_lightgbm_guard_rejects_an_imputer_in_front_of_the_tree() -> None:
    pipeline = Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            (ESTIMATOR_STEP, LGBMClassifier(**LIGHTGBM_PARAMS)),
        ]
    )

    with pytest.raises(ValueError, match="must not impute"):
        assert_no_transform_outside_pipeline(pipeline)


def test_guard_rejects_an_estimator_the_project_does_not_train() -> None:
    pipeline = Pipeline([("scale", StandardScaler()), (ESTIMATOR_STEP, StandardScaler())])

    with pytest.raises(ValueError, match="Unrecognised estimator"):
        assert_no_transform_outside_pipeline(pipeline)


def test_scale_pos_weight_is_negatives_over_positives() -> None:
    labels = pl.Series([1, 0, 0, 0])

    assert scale_pos_weight_from_labels(labels) == pytest.approx(3.0)


def test_scale_pos_weight_rejects_labels_without_positives() -> None:
    with pytest.raises(ValueError, match="no positive case"):
        scale_pos_weight_from_labels(pl.Series([0, 0, 0]))
