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

- The historical touch probability method is accepted.
- MVP scope is agreed.
- Non-MVP features are explicitly deferred.

## Phase 1 - Calculation Engine Only

Goal:

Build the smallest reliable core engine.

Deliverables:

- `barrier_engine.py`
- `test_barrier_engine.py`
- `data_loader.py` using `yfinance.download("AUDUSD=X", period="2y")`
- Small in-memory fixture data for tests
- CLI or simple script entry point, optional

Core functions:

- Download and normalize AUD/USD OHLC data.
- Calculate `days_to_expiry`.
- Calculate `distance_pct`.
- Check actual barrier hit within a trade window.
- Calculate historical touch probability with rolling windows.

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

## Phase 2 - Data Layer

Goal:

Persist market prices, trades, and backtest results.

Deliverables:

- SQLite schema.
- Market data save/load functions.
- Repository functions for:
  - inserting market prices
  - loading market prices
  - saving trades
  - saving backtest results

Tables:

- `trades`
- `market_prices`
- `backtest_results`

Exit criteria:

- Market price storage is idempotent by `date + pair`.
- One trade can be saved.
- One analysis result can be saved and reloaded.
- Engine still remains independent from SQLite.

## Phase 3 - Minimal UI

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

Displayed metrics:

- Current spot.
- Barrier.
- Barrier distance percentage.
- Days to expiry.
- Historical samples.
- Touch count.
- Historical touch probability.

Exit criteria:

- User can refresh AUD/USD data and analyze one trade from the browser.
- Result matches the engine output.
- UI contains no duplicated calculation logic.

## Phase 4 - CSV Import, Optional

Goal:

Add manual data import only if needed.

Deliverables:

- CSV import function.
- CSV validation.
- Data quality checks.

Validation:

- Confirm columns are present.
- Confirm date range.
- Detect duplicate dates.
- Detect missing or zero prices.

Exit criteria:

- CSV can be imported when Yahoo Finance is unavailable or custom data is needed.
- Imported data remains compatible with existing engine tests.

## Phase 5 - API Layer, If Needed

Goal:

Expose the analyzer to other systems.

Recommended stack:

- FastAPI

Possible endpoints:

- `GET /health`
- `POST /market-prices/upload`
- `POST /market-prices/refresh`
- `POST /analyze`
- `GET /trades/{trade_id}`
- `GET /results/{result_id}`

Exit criteria:

- API output matches engine output.
- API has request validation.
- API is documented with OpenAPI.

Decision gate:

Only build this phase if there is a real integration need. If Streamlit is enough, skip this phase.

## Phase 6 - Volatility Adjustment

Goal:

Compare raw historical probability with volatility-aware probability.

Potential metrics:

- Realized volatility.
- ATR.
- Rolling high-low range.
- Volatility percentile.

Possible outputs:

- Historical probability.
- Current volatility regime.
- Volatility-adjusted probability.

Exit criteria:

- Raw probability remains visible.
- Volatility adjustment is separately labeled.
- Adjustment method is documented and testable.

## Phase 7 - Multi-Factor Model

Goal:

Experiment with predictive features after the historical baseline is trusted.

Possible features:

- DXY.
- AUD-US yield spread.
- Iron ore.
- VIX.
- China PMI.
- Realized volatility.
- Trend and range features.

Possible model:

- XGBoost or logistic regression.

Target:

```text
BarrierHit
```

Exit criteria:

- Baseline historical probability remains the benchmark.
- Model is evaluated out of sample.
- Feature leakage is explicitly checked.

## Phase 8 - Explanation Layer

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

Do Phase 1 only:

```text
barrier_engine.py
test_barrier_engine.py
sample_audusd.csv
```

Do not build Streamlit, FastAPI, or SQLite until the core calculation is accepted.
