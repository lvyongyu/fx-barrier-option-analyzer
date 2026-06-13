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
- Status: first experimental logistic regression complete; current validation may underperform baseline, so it remains a research signal.

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

## Phase 7 - Minimal UI

Goal:

Make the tool usable without command-line work.

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

Build Phase 5:

```text
improve price-only model validation
add calibration bucket report
test longer research windows such as period="10y" or period="max"
```

Do not build Streamlit or FastAPI until the forward-estimate logic is useful enough to show.
