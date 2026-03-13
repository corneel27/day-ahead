"""XGBoost predictor configuration model."""

from typing import Any, Optional
from pydantic import BaseModel, Field, ConfigDict


class XGBoostConfig(BaseModel):
    """
    Configuration for the XGBoost solar-prediction model.

    ``param_grid`` and ``parameters`` are free-form dicts whose internal
    structure is dictated by XGBoost / scikit-learn, not by this project.
    They are left unvalidated so users can pass any valid XGBoost option.
    Any additional keys are also accepted via ``extra='allow'``.
    """

    tune_hyperparameters: bool = Field(
        default=False,
        description="Run GridSearchCV to find optimal hyper-parameters before training",
        json_schema_extra={
            "x-help": (
                "When enabled, the predictor performs a grid search over "
                "'param_grid' to select the best XGBoost hyper-parameters. "
                "Increases training time significantly."
            )
        },
    )
    param_grid: Optional[dict[str, Any]] = Field(
        default=None,
        description=(
            "Grid of hyper-parameters for GridSearchCV. "
            "Keys are XGBoost parameter names, values are lists of candidates."
        ),
        json_schema_extra={
            "x-help": (
                "Free-form dict passed directly to sklearn GridSearchCV. "
                "Example: {\"n_estimators\": [100, 200], \"max_depth\": [3, 6]}. "
                "Leave empty to use the built-in defaults."
            )
        },
    )
    parameters: Optional[dict[str, Any]] = Field(
        default=None,
        description=(
            "Fixed hyper-parameters used when tune_hyperparameters is false. "
            "Keys are XGBoost parameter names."
        ),
        json_schema_extra={
            "x-help": (
                "Free-form dict of XGBoost parameters used when "
                "tune_hyperparameters is disabled. "
                "Example: {\"n_estimators\": 200, \"max_depth\": 6, "
                "\"learning_rate\": 0.1}. "
                "Leave empty to use the built-in defaults."
            )
        },
    )

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
