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

import logging
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from sklearn.pipeline import Pipeline

logger = logging.getLogger(__name__)

ID_COLUMN: Final = "SK_ID_CURR"
LABEL_COLUMN: Final = "TARGET"


def numeric_columns(feature_names: tuple[str, ...]) -> tuple[str, ...]:
    """Return the numeric feature columns, excluding the id and the label.

    TODO:
        - Exclude ID_COLUMN and LABEL_COLUMN explicitly. Leaving the id in is a
          quiet disaster: SK_ID_CURR carries weak ordering structure, the model
          will use it, and the resulting AUC is unreproducible on new ids.
    """
    raise NotImplementedError


def categorical_columns(feature_names: tuple[str, ...]) -> tuple[str, ...]:
    """Return the categorical feature columns.

    TODO:
        - Identify by dtype, not by name pattern. A name-based rule misses
          ORGANIZATION_TYPE the moment a prefix changes.
    """
    raise NotImplementedError


def build_lightgbm_pipeline(
    categorical: tuple[str, ...],
    params: dict[str, object],
) -> Pipeline:
    """Build the LightGBM pipeline, which deliberately imputes nothing.

    LightGBM handles nulls natively and learns which direction the missing branch
    should take. That is the reason it is the primary model here: EXT_SOURCE_1 is
    absent for 56 percent of applicants and OWN_CAR_AGE for 66 percent, and in both
    cases the absence is informative. An imputer in front of this estimator would
    destroy exactly the signal the choice of estimator was made to capture.

    Args:
        categorical: Categorical column names, passed to the estimator directly.
        params: Hyperparameters from configs/model.yml.

    Returns:
        A Pipeline whose only data-dependent step is the estimator.

    TODO:
        - Pass categorical features to LightGBM as native categoricals rather than
          one-hot encoding them. One-hot over ORGANIZATION_TYPE at 59 levels
          fragments the splits and the tree handles the raw categories better.
        - Add no imputer and no scaler. Trees need neither, and both would leak.
        - Set scale_pos_weight from the training fold, not from the full matrix.
          Computing it over all rows is a small leak of the holdout class balance.
        - Keep the step name stable, since calibrate and explain both reach into
          the fitted pipeline by name.
    """
    raise NotImplementedError


def build_logistic_pipeline(
    numeric: tuple[str, ...],
    categorical: tuple[str, ...],
) -> Pipeline:
    """Build the logistic regression baseline pipeline, which must impute.

    Unlike the tree, logistic regression cannot consume a null, so it needs an
    imputer, and that imputer must be a Pipeline step so it fits inside the fold.
    This difference is itself the argument for the tree being the primary model: the
    baseline is forced to fill a value and lose the information that absence
    carries.

    Args:
        numeric: Numeric column names.
        categorical: Categorical column names.

    Returns:
        A ColumnTransformer-based Pipeline ending in the estimator.

    TODO:
        - Impute numeric columns with the median and add an indicator column, so at
          least the fact of absence survives imputation.
        - One-hot encode categoricals with handle_unknown set to ignore, since a
          level present only in the holdout must not raise at scoring time.
        - Scale after imputing. The scaler fits inside the fold by virtue of being
          a Pipeline step.
        - Set class_weight to balanced. Never oversample: interpolating new rows
          across many one-hot and many null columns produces invalid applicants and
          destroys the calibration this system needs.
    """
    raise NotImplementedError


def assert_no_transform_outside_pipeline(steps: tuple[str, ...]) -> None:
    """Assert the pipeline contains every data-dependent step it should.

    A guard against the habit this design exists to prevent: fitting an imputer or
    an encoder before cross-validation and passing the transformed matrix in.

    Raises:
        ValueError: If a required step is absent for the given estimator type.

    TODO:
        - For the logistic pipeline, assert an imputer and a scaler are present.
          Their absence means someone transformed the matrix upstream.
        - For the LightGBM pipeline, assert no imputer is present, which is the
          opposite failure and equally wrong.
    """
    raise NotImplementedError
