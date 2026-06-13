# FX Barrier Option Analyzer - Roadmap

## Phase 0 - Design Lock

Goal:

Agree on the calculation method before writing application code.

Deliverables:

- Design document.
- Roadmap.
- Yahoo Finance data source definition.
- Accepted definitions for:
  - days to expiry
  - distance to barrier
  - up barrier hit
  - down barrier hit
  - historical sample count

Exit criteria:

- The target is accepted: estimate `P(Barrier Hit Before Expiry)`.
- Historical touch probability is accepted as the first baseline, not the final forecasting method.
- MVP scope is agreed.
- Non-MVP features are explicitly deferred.

## Phase 1 - Calculation Engine Only

Goal:

Build the smallest reliable baseline engine.

Deliverables:

- `barrier_engine.py`
- `test_barrier_engine.py`
- `data_loader.py` using `yfinance.download("AUDUSD=X", period="2y")` for development
- Small in-memory fixture data for tests
- CLI or simple script entry point, optional

Core functions:

- Download and normalize AUD/USD OHLC data.
- Support longer research windows such as `period="10y"` or `period="max"` for backtesting and training.
- Calculate `days_to_expiry`.
- Calculate `distance_pct`.
- Check actual barrier hit within a trade window.
- Calculate historical touch probability with rolling windows.
- Represent Corpay-style Ratio Convertible Forward trade fields.

Tests:

- Up barrier hit uses daily high.
- Down barrier hit uses daily low.
- Touch after expiry does not count.
- Missing forward history is excluded from sample count.
- Distance percentage is calculated correctly.
- Probability equals `touch_count / sample_count`.

Exit criteria:

- Tests pass locally.
- Output can reproduce a known hand-worked example.
- No UI, API, or database logic is mixed into the engine.
- Scope remains fixed to AUD/USD.

## Phase 2 - Feature Engine

Goal:

Start moving from historical frequency toward future touch estimation by measuring current market state.

Deliverables:

- `feature_engine.py`
- Feature snapshot for the current trade.
- Historical feature snapshots for synthetic trade dates.
- Tests proving no look-ahead leakage.
- AUD/USD-only assumptions documented explicitly.

Trade metadata:

- `product_type`
- `client_direction`
- `protected_amount`
- `ratio_amount`
- `barrier_level_period`

These fields describe the trade and report, but they should not automatically become predictive model features.

Core predictive features:

- `distance_pct`
- `days_to_expiry`
- `realized_vol_20d`
- `realized_vol_60d`
- `atr_14d`
- `trend_20d`
- `trend_60d`
- `range_position_60d`
- `recent_high_distance`
- `recent_low_distance`

Exit criteria:

- Features for a historical synthetic trade date use only data available on or before that date.
- Current trade feature snapshot is printed alongside the historical baseline.
- Tests cover volatility, trend, and leakage boundaries.

## Phase 3 - Volatility-Adjusted Estimate

Goal:

Create the first forward-looking adjustment above the historical baseline.

Deliverables:

- Volatility regime classification.
- Baseline probability by comparable volatility buckets.
- Volatility-adjusted probability.
- CLI output showing both baseline and adjusted probability.

Possible method:

- Calculate current realized volatility.
- Rank it against historical realized volatility distribution.
- Compare current trade only with historical windows in similar volatility buckets.
- Fall back to full historical baseline if sample count is too low.

Exit criteria:

- Output includes:
  - historical baseline probability
  - current volatility percentile
  - volatility-adjusted probability
  - comparable sample count
- Tests prove bucket filtering and fallback behavior.
- Status: complete.

## Phase 4 - Data Layer For Research

Goal:

Persist market prices, trades, generated labels, feature datasets, and evaluation outputs.

Deliverables:

- SQLite schema.
- Market data save/load functions.
- Trade persistence.
- Label persistence.
- Feature dataset export.
- Evaluation result persistence.

Tables:

- `trades`
- `market_prices`
- `feature_snapshots`
- `barrier_labels`
- `analysis_results`
- `model_evaluations`

Exit criteria:

- Market price storage is idempotent by `date + pair`.
- `pair` is fixed to AUD/USD in this phase.
- Feature datasets can be regenerated and compared.
- One analysis result can be saved and reloaded.
- Engine and model remain independent from SQLite.
- Status: complete.

## Phase 5 - Price-Only Probability Model

Goal:

Train the first probability model for `BarrierHitBeforeExpiry` using AUD/USD price-derived features only.

Deliverables:

- Historical training dataset.
- Price-only training dataset export.
- Walk-forward validation.
- Calibrated model probability.
- Model evaluation report.

Candidate models:

- Logistic regression as first model.
- Gradient boosting only after baseline and leakage tests are solid.

Required metrics:

- Brier score.
- Log loss.
- Calibration curve.
- Probability bucket hit rates.
- Comparison against historical baseline.

Exit criteria:

- Training dataset contains features and `target_barrier_hit` labels without look-ahead leakage.
- Model beats or usefully complements baseline out of sample.
- Feature leakage checks pass.
- CLI output clearly labels model probability versus baseline probability.
- Status: experimental logistic regression complete with walk-forward Brier/log-loss and calibration buckets.
- Status: model evaluation report can compare 2y/5y/10y windows before trusting model output.
- Status: batch evaluation can compare generated near/medium/far up/down sample trades.
- Finding: current logistic models generally do not beat the historical baseline across sample trades.
- Next: redesign the model around a barrier-theory baseline before adding UI.

## Phase 5.5 - Barrier-Theory Baseline

Goal:

Add a reproducible theoretical barrier-touch probability that is closer to the structure of the problem than a generic classifier.

Motivation:

An external institutional-style forecast for the June 11, 2026 to September 11, 2026 AUD/USD downside bucket estimated a 76% probability that the daily low would fall below 0.6908. Reproducing the same style of question locally showed:

- 5y historical touch probability near 76% when using the latest yfinance spot around 0.7049.
- 5y historical touch probability near 84% when using the report's lower starting spot around 0.7007.
- Simple driftless GBM touch estimates in the 57-73% range depending on spot and volatility.

This suggests the next model layer should be an auditable barrier-theory estimate, not another generic ML feature set.

Deliverables:

- Closed-form or simulation-based GBM barrier-touch probability.
- Inputs:
  - spot
  - barrier
  - barrier direction
  - days to expiry
  - realized volatility, initially 20d and 60d
  - optional drift, defaulting to zero
- Derived features:
  - expected move to expiry
  - distance in volatility units
  - barrier z-score
- Batch report columns:
  - GBM probability
  - GBM Brier score
  - GBM dBrier versus historical baseline
  - calibrated blend probability, if useful

Exit criteria:

- GBM probability is deterministic and reproducible.
- Tests cover up and down barriers, near/far barriers, low/high volatility, and zero-drift behavior.
- Batch evaluation shows whether GBM improves over baseline across sample trades.
- If GBM beats or complements baseline, use it as the anchor for the next calibration model.
- If GBM fails, revisit label design and data window construction before adding more features.

Status:

- Planned next.
- UI remains deferred until probability methods are more credible.

## Phase 6 - External Market Features

Goal:

Add external features that may help estimate future AUD/USD path risk.

Candidate data:

- DXY.
- VIX.
- AU-US yield spread.
- Iron ore proxy.
- AUD/USD implied volatility, if available.
- RBA/Fed rate expectations, if available.

Exit criteria:

- Each feature has a documented source.
- Each feature is lagged correctly to avoid look-ahead leakage.
- Model evaluation shows whether the feature improves calibration.
- Status: DXY/VIX snapshots are available and can be included in a price + external model comparison.
- Status: evaluation report compares price-only versus price + external models across multiple historical windows.
- Status: batch evaluation compares price-only versus price + external models across generated sample trades.
- Finding: DXY/VIX did not improve the current sample-trade batch evaluation.
- Next: pause additional external features until the GBM/barrier-theory baseline is implemented.

## Phase 7 - Minimal UI

Goal:

Make the tool usable without command-line work.

Current priority:

UI is deferred. The next priority is improving the probability engine and model evaluation layer.

Recommended UI:

Streamlit.

Deliverables:

- Automatic AUD/USD data refresh.
- Manual trade form.
- Analyze button.
- Result card.
- Simple AUD/USD chart with:
  - close price
  - strike line
  - barrier line
- Feature and probability breakdown.

Displayed metrics:

- Current spot.
- Barrier.
- Barrier distance percentage.
- Days to expiry.
- Historical baseline probability.
- Volatility-adjusted probability.
- Model probability, once available.
- Confidence and data-quality notes.

Exit criteria:

- User can refresh AUD/USD data and analyze one trade from the browser.
- Result matches CLI output.
- UI contains no duplicated calculation logic.

## Phase 8 - API Layer, If Needed

Goal:

Expose the analyzer to other systems.

Recommended stack:

- FastAPI

Possible endpoints:

- `GET /health`
- `POST /market-prices/refresh`
- `POST /analyze`
- `GET /trades/{trade_id}`
- `GET /results/{result_id}`

Exit criteria:

- API output matches CLI output.
- API has request validation.
- API is documented with OpenAPI.

Decision gate:

Only build this phase if there is a real integration need. If Streamlit is enough, skip this phase.

## Phase 9 - Explanation Layer

Goal:

Use LLMs to explain results, not generate probabilities.

Possible agents:

- Macro agent.
- News agent.
- Contrarian agent.
- Judge agent.

Rules:

- LLMs must not invent probability.
- LLMs may summarize why the probability may be higher or lower.
- Quantitative probability must come from the engine or validated model.

Exit criteria:

- Explanation is clearly separated from calculation.
- Output includes source and confidence notes.

## Recommended Immediate Next Step

Build confirmation-level analysis:

```text
analyze all knockout legs in one confirmation
print one probability row per scheduled expiry
keep PDF parsing manual for now
```

Do not build Streamlit or FastAPI until the forward-estimate logic is useful enough to show.
