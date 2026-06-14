# FX Barrier Option Analyzer - Roadmap

## Current State - 2026-06-14

The project has moved beyond the original AUD/USD-only MVP.

Implemented:

- Configurable FX pair input via `--pair`.
- Yahoo Finance ticker normalization, e.g. `AUD/USD -> AUDUSD=X`.
- Sparse CNH direct-history fallback using a CNY proxy path where needed.
- Historical touch baseline.
- Volatility-adjusted historical estimate.
- Price-only logistic model with walk-forward metrics.
- DXY/VIX external feature experiment.
- Driftless GBM barrier-theory estimate.
- Train-calibrated GBM/historical blend.
- Forecast-style text reports.
- PDF report generation with `--pdf`.
- GitHub Actions manual forecast workflow.
- GitHub artifact upload:
  - `forecast_report.txt`
  - `forecast_report.pdf`
  - `forecast_payload.json`
  - `agent_review.json`
- Local deterministic agent helpers:
  - natural-language request parser
  - model-result reviewer
- AI agent integration plan.

Important current limitation:

The model estimates path-touch probability, not expiry close probability and not
profit probability. For example, `P(touch +4%)` and `P(touch -4%)` can both be
high because the two events can both occur inside the same 3-month window.

## Next Version Focus

The next version should not start with UI. The highest-value improvements are:

1. Bilateral move analysis:
   - `P(touch upper)`
   - `P(touch lower)`
   - `P(touch either)`
   - `P(touch both)`
2. Forward-start forecasting:
   - today to future start-date spot distribution
   - future start-date to expiry barrier touch estimate
3. Data quality layer:
   - direct Yahoo history versus synthetic cross/proxy history
   - sample count warnings
   - sparse-history fallback visibility in reports
4. Agent upgrade:
   - optional OpenAI reviewer/parser
   - deterministic fallback remains default
5. Report quality:
   - clearer final probability naming
   - distinguish touch probability, expiry probability, and payoff probability
   - better PDF layout and optional chart/table sections

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
- `data_loader.py` using Yahoo Finance FX tickers for development
- Small in-memory fixture data for tests
- CLI or simple script entry point, optional

Core functions:

- Download and normalize FX OHLC data.
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
- Scope initially remains fixed to AUD/USD.

## Phase 2 - Feature Engine

Goal:

Start moving from historical frequency toward future touch estimation by measuring current market state.

Deliverables:

- `feature_engine.py`
- Feature snapshot for the current trade.
- Historical feature snapshots for synthetic trade dates.
- Tests proving no look-ahead leakage.
- Pair-scoped assumptions documented explicitly.

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
- Status: complete for price-derived features.

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
- `pair` is stored in all relevant tables.
- Feature datasets can be regenerated and compared.
- One analysis result can be saved and reloaded.
- Engine and model remain independent from SQLite.
- Status: complete.

## Phase 5 - Price-Only Probability Model

Goal:

Train the first probability model for `BarrierHitBeforeExpiry` using selected-pair price-derived features only.

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
- Next: use the barrier-theory baseline as the anchor for calibration and model redesign.

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
  - train-calibrated GBM/historical blend probability
  - blend Brier score and dBrier versus historical baseline

Exit criteria:

- GBM probability is deterministic and reproducible.
- Tests cover up and down barriers, near/far barriers, low/high volatility, and zero-drift behavior.
- Batch evaluation shows whether GBM improves over baseline across sample trades.
- If GBM beats or complements baseline, use it as the anchor for the next calibration model.
- If GBM fails, revisit label design and data window construction before adding more features.

Status:

- Initial implementation complete.
- `src/barrier_theory.py` implements driftless log-Brownian reflection probability.
- Single-trade and batch evaluation reports include GBM probability, blended probability, GBM dBrier, and blend dBrier.
- Tests cover GBM math, volatility sensitivity, expiry sensitivity, symmetry, fallbacks, and walk-forward evaluation.
- Initial 5y sample batch finding: GBM improves over baseline for some down-barrier scenarios, especially medium/far down barriers, but does not universally beat baseline.
- Initial blend finding: train-calibrated blend is more conservative than pure GBM; it can smooth losses, but may dilute useful GBM signal.
- UI remains deferred until probability methods are more credible.

## Phase 6 - External Market Features

Goal:

Add external features that may help estimate future FX path risk.

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
- Next: pause additional external features until GBM calibration and label design are improved.

## Phase 6.5 - Bilateral Path Probability

Goal:

Answer natural user questions such as:

```text
Will AUD/USD move up or down 4% in the next 3 months?
```

The current system can run the up and down legs separately, but it cannot yet
estimate the relationship between them.

Deliverables:

- Bilateral request type:
  - pair
  - horizon or expiry
  - upper move or upper barrier
  - lower move or lower barrier
- Path labels:
  - upper touched
  - lower touched
  - either touched
  - both touched
  - first touch side, if knowable from daily data
- Output:
  - `P(touch upper)`
  - `P(touch lower)`
  - `P(touch either)`
  - `P(touch both)`
- Text/PDF report sections explaining non-mutual exclusivity.

Exit criteria:

- Tests show that upper and lower touch events are not treated as complements.
- Historical samples can label `both` correctly using daily high/low.
- Report warns that daily OHLC cannot determine intraday sequence when both
  barriers touch on the same daily bar.

## Phase 6.6 - Forward-Start Forecasts

Goal:

Handle questions where the barrier window starts in the future:

```text
From 2026-09-30 to 2026-12-30, will AUD/USD touch 0.6935?
```

Current limitation:

The model needs a starting spot. If the start date is in the future, that spot
does not exist yet. The user should not be asked to provide it as if it were
known.

Deliverables:

- Forward-start request schema:
  - analysis date
  - forward start date
  - expiry date
  - pair
  - barrier
  - direction
- Projected forward-start spot distribution:
  - p10
  - p25
  - p50
  - p75
  - p90
- Conditional barrier touch probability per scenario.
- Integrated probability across the projected start distribution.

Exit criteria:

- Agent parser detects forward-start questions and does not invent future spot.
- Report clearly separates:
  - current spot
  - projected start-date distribution
  - conditional touch probabilities
  - integrated final estimate

## Phase 6.7 - Data Quality And Proxy Layer

Goal:

Make data-source reliability explicit, especially for non-major pairs.

Motivation:

Yahoo Finance may provide full history for `AUDCNY=X` but only one row for
`AUDCNH=X`. The analyzer can build proxy history, but the report must disclose
that choice.

Deliverables:

- Market data provenance object:
  - requested pair
  - direct ticker
  - rows returned
  - fallback method, if any
  - proxy components, if any
- Report data-quality section.
- Warnings for:
  - low direct row count
  - proxy cross-rate use
  - low historical sample count
  - missing volatility features

Exit criteria:

- AUD/CNH report states whether it used direct `AUDCNH=X` or proxy data.
- GitHub artifacts include the data-quality metadata in JSON.

## Phase 7 - Agent Integration With Optional LLM

Goal:

Upgrade the local deterministic agent layer into an optional LLM-assisted
workflow while keeping deterministic output as the source of truth.

Deliverables:

- Optional OpenAI API integration, disabled by default.
- `OPENAI_API_KEY` based configuration.
- Agent modes:
  - parse natural-language request
  - review model report
  - generate analyst memo
- Strict JSON schemas for model-facing output.
- Fallback to local deterministic parser/reviewer if the LLM is unavailable.

Rules:

- LLM must not calculate the probability.
- LLM must not hide model disagreement.
- LLM must not call touch probability profit probability.
- LLM must not invent future start-date spot.

Exit criteria:

- Unit tests cover schema validation and deterministic fallback.
- GitHub Action can optionally produce an LLM-style memo when a key is present.
- The deterministic model output remains visible in artifacts.

## Phase 8 - Minimal UI

Goal:

Make the tool usable without command-line work.

Current priority:

UI is deferred. The next priority is improving the probability engine and model evaluation layer.

Recommended UI:

Streamlit.

Deliverables:

- Automatic FX pair data refresh.
- Manual trade form.
- Analyze button.
- Result card.
- Simple FX chart with:
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

- User can refresh selected FX data and analyze one trade from the browser.
- Result matches CLI output.
- UI contains no duplicated calculation logic.

## Phase 9 - API Layer, If Needed

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

## Phase 10 - Explanation Layer

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

Build bilateral probability analysis:

```text
P(touch upper)
P(touch lower)
P(touch either)
P(touch both)
```

Then build forward-start forecasts. Do not build Streamlit or FastAPI until the
probability workflow can answer these two real user questions cleanly.
