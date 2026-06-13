from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.training_dataset import TARGET_COLUMN, price_only_feature_columns, price_plus_external_feature_columns


@dataclass(frozen=True)
class PriceModelEvaluation:
    model_probability: float | None
    train_rows: int
    test_rows: int
    positive_rate_train: float | None
    positive_rate_test: float | None
    baseline_probability: float | None
    model_brier_score: float | None
    baseline_brier_score: float | None
    model_log_loss: float | None
    baseline_log_loss: float | None
    used_fallback: bool
    fallback_reason: str | None


def evaluate_price_only_model(
    dataset: pd.DataFrame,
    current_features: dict[str, float | int | None],
    train_fraction: float = 0.7,
) -> PriceModelEvaluation:
    return evaluate_probability_model(
        dataset,
        current_features,
        feature_columns=price_only_feature_columns(),
        train_fraction=train_fraction,
    )


def evaluate_price_plus_external_model(
    dataset: pd.DataFrame,
    current_features: dict[str, float | int | None],
    train_fraction: float = 0.7,
) -> PriceModelEvaluation:
    return evaluate_probability_model(
        dataset,
        current_features,
        feature_columns=price_plus_external_feature_columns(),
        train_fraction=train_fraction,
    )


def evaluate_probability_model(
    dataset: pd.DataFrame,
    current_features: dict[str, float | int | None],
    feature_columns: list[str],
    train_fraction: float = 0.7,
) -> PriceModelEvaluation:
    prepared = prepare_model_dataset(dataset, feature_columns=feature_columns)
    if prepared.empty:
        return _fallback("training dataset has no usable rows")

    if prepared[TARGET_COLUMN].nunique() < 2:
        return _fallback("training dataset target has only one class")

    split_index = int(len(prepared) * train_fraction)
    if split_index <= 0 or split_index >= len(prepared):
        return _fallback("training dataset is too small for walk-forward split")

    train = prepared.iloc[:split_index]
    test = prepared.iloc[split_index:]
    if train[TARGET_COLUMN].nunique() < 2:
        return _fallback("training split target has only one class")

    model = build_price_only_model()
    model.fit(train[feature_columns], train[TARGET_COLUMN].astype(int))

    test_probabilities = model.predict_proba(test[feature_columns])[:, 1]
    y_test = test[TARGET_COLUMN].astype(int)
    baseline_probability = float(train[TARGET_COLUMN].mean())
    baseline_probabilities = [baseline_probability] * len(test)
    current_frame = pd.DataFrame([{column: current_features.get(column) for column in feature_columns}])
    if current_frame.isna().any(axis=None):
        model_probability = None
        used_fallback = True
        fallback_reason = "current feature snapshot has missing model features"
    else:
        model_probability = float(model.predict_proba(current_frame[feature_columns])[:, 1][0] * 100)
        used_fallback = False
        fallback_reason = None

    return PriceModelEvaluation(
        model_probability=model_probability,
        train_rows=int(len(train)),
        test_rows=int(len(test)),
        positive_rate_train=float(train[TARGET_COLUMN].mean() * 100),
        positive_rate_test=float(test[TARGET_COLUMN].mean() * 100),
        baseline_probability=baseline_probability * 100,
        model_brier_score=float(brier_score_loss(y_test, test_probabilities)),
        baseline_brier_score=float(brier_score_loss(y_test, baseline_probabilities)),
        model_log_loss=float(log_loss(y_test, test_probabilities, labels=[0, 1])),
        baseline_log_loss=float(log_loss(y_test, baseline_probabilities, labels=[0, 1])),
        used_fallback=used_fallback,
        fallback_reason=fallback_reason,
    )


def build_price_only_model() -> Pipeline:
    return Pipeline(
        [
            ("scaler", StandardScaler()),
            ("logistic", LogisticRegression(max_iter=1_000, class_weight="balanced")),
        ]
    )


def prepare_model_dataset(dataset: pd.DataFrame, feature_columns: list[str] | None = None) -> pd.DataFrame:
    if feature_columns is None:
        feature_columns = price_only_feature_columns()
    required = ["as_of_date", TARGET_COLUMN, *feature_columns]
    missing = [column for column in required if column not in dataset.columns]
    if missing:
        raise ValueError(f"training dataset missing columns: {', '.join(missing)}")

    prepared = dataset.copy()
    prepared["as_of_date"] = pd.to_datetime(prepared["as_of_date"])
    prepared = prepared.sort_values("as_of_date").reset_index(drop=True)
    prepared = prepared.dropna(subset=feature_columns + [TARGET_COLUMN])
    return prepared


def _fallback(reason: str) -> PriceModelEvaluation:
    return PriceModelEvaluation(
        model_probability=None,
        train_rows=0,
        test_rows=0,
        positive_rate_train=None,
        positive_rate_test=None,
        baseline_probability=None,
        model_brier_score=None,
        baseline_brier_score=None,
        model_log_loss=None,
        baseline_log_loss=None,
        used_fallback=True,
        fallback_reason=reason,
    )
