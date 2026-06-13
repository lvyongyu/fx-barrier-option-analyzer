# FX Barrier Option Analyzer - Design Document

## 1. Product Goal

Build a lightweight analysis system for FX barrier option trades, starting with AUD/USD.

The system's end goal is to estimate:

```text
P(Barrier Hit Before Expiry)
```

This is not a traditional FX point-forecasting system. It does not predict the final AUD/USD level or only the direction of AUD/USD. It estimates a path-dependent event:

```text
Will AUD/USD touch the barrier before expiry?
```

The first implementation uses historical touch frequency as a baseline prior. Later versions must improve that baseline with current volatility, market regime, and forward-looking features.

## 2. Core Use Case

Given a Corpay-style ratio convertible forward trade:

```json
{
  "pair": "AUD/USD",
  "trade_date": "2026-04-15",
  "spot": 0.6500,
  "strike": 0.6900,
  "barrier": 0.7050,
  "expiry_date": "2026-08-28",
  "barrier_direction": "up"
}
```

Answer:

```text
What is the estimated probability that AUD/USD touches this barrier before expiry?
```

The answer should eventually combine:

- Historical baseline probability.
- Current volatility regime.
- Current trend and distance-to-barrier context.
- Macro and risk-regime features.
- Model calibration and confidence.

### Real Product Examples

The system should support Corpay-style `Ratio Convertible Forward` structures for AUD/USD.

Example fields from real trade sheets:

| Product | Direction | Pair | Protected amount | Ratio amount | Strike | Barrier | Barrier period | Expiry |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Ratio Convertible Forward | Importer | AUD/USD | USD 500,000 | USD 1,000,000 | 0.6850 | 0.6935 | Continuous | 2026-12-30 |
| Ratio Convertible Forward | Importer | AUD/USD | USD 1,000,000 | USD 2,000,000 | 0.6850 | 0.6935 | Continuous | 2026-12-30 |

AUD/CNH examples are useful for understanding the broader product family, but they are out of scope for the current implementation.

Options expire at 3:00 p.m. Tokyo time in these examples.

For this product, the modeling target is:

```text
Will the spot rate breach the barrier at any point during the continuous barrier period before expiry?
```

The downstream payoff scenario depends on whether the barrier breaches, but the first modeling problem remains the path event:

```text
BarrierBreachBeforeExpiry = true / false
```

## 3. MVP Scope

The MVP should stay deliberately small.

Included:

- Download AUD/USD daily OHLC data from Yahoo Finance ticker `AUDUSD=X`.
- Enter one trade manually.
- Calculate days to expiry.
- Calculate distance to barrier.
- Calculate historical touch probability.
- Show sample count, touch count, and probability.
- Test the barrier hit logic.

Excluded from MVP:

- Machine learning.
- News analysis.
- LLM-generated probability.
- Trading execution.
- Multi-currency or non-AUD/USD support.
- Full volatility-adjusted probability.
- Full pricing model or option Greeks.

## 4. Key Definitions

### Days To Expiry

```text
days_to_expiry = expiry_date - trade_date
```

Use calendar days for the MVP. Historical windows are selected by date range, not by a fixed number of trading rows.

### Distance To Barrier

For an up barrier:

```text
distance_pct = (barrier - spot) / spot
```

Example:

```text
(0.7050 - 0.6500) / 0.6500 = 8.46%
```

For a down barrier, the same formula may be negative:

```text
distance_pct = (barrier - spot) / spot
```

Example:

```text
(0.6100 - 0.6500) / 0.6500 = -6.15%
```

### Barrier Hit

For an up barrier:

```text
barrier_hit = any daily high >= barrier before or on expiry_date
```

For a down barrier:

```text
barrier_hit = any daily low <= barrier before or on expiry_date
```

The MVP uses daily OHLC data, so it can only know whether the barrier was touched within the daily high-low range. It cannot know intraday sequence.

## 5. Historical Touch Probability Method

This method is the baseline, not the final product.

It answers:

```text
How often did similar historical setups touch the barrier?
```

It does not fully answer:

```text
Will the current trade touch the barrier?
```

To estimate the current trade's future touch probability, later versions must condition the baseline on current market state.

For a target trade:

```text
spot = current trade spot
barrier = current trade barrier
distance_pct = (barrier - spot) / spot
N = days_to_expiry
```

For every historical trading day:

1. Treat that day as a synthetic trade date.
2. Use that day's close as the synthetic spot.
3. Calculate synthetic barrier:

```text
synthetic_barrier = historical_close * (1 + distance_pct)
```

4. Look forward `N` calendar days.
5. For an up barrier, check whether any future high touches or exceeds the synthetic barrier.
6. For a down barrier, check whether any future low touches or falls below the synthetic barrier.
7. Count the sample as hit or not hit.

Final output:

```text
touch_probability = touch_count / sample_count
```

## 6. Forward Estimate Direction

The production target should become:

```text
estimated_touch_probability = f(
  historical_baseline,
  days_to_expiry,
  distance_to_barrier,
  realized_volatility,
  volatility_regime,
  trend_features,
  macro_features,
  risk_sentiment_features
)
```

The model should estimate a binary event:

```text
target = BarrierHitBeforeExpiry
```

The historical baseline remains useful because it provides a simple benchmark. Every more advanced estimate should be compared against it.

Recommended staged outputs:

```text
Historical baseline probability
Volatility-adjusted probability
Regime-adjusted probability
Model probability
Confidence / data-quality notes
```

The system should avoid pretending that historical frequency alone is a complete future forecast.

## 7. Data Requirements

### MarketPrice

Required fields:

| Field | Type | Notes |
| --- | --- | --- |
| date | date | Trading date |
| pair | string | Example: AUD/USD |
| open | decimal | Daily open |
| high | decimal | Daily high |
| low | decimal | Daily low |
| close | decimal | Daily close |

MVP data should be downloaded automatically from Yahoo Finance:

```python
yfinance.download("AUDUSD=X", period="2y")
```

Default period should be short at first:

```text
period = "2y"
```

CSV support can be added later as an import/export convenience, but it is not required for the first version.

If CSV support is added later, it should support at minimum:

```csv
date,open,high,low,close
2020-01-01,0.7000,0.7050,0.6980,0.7020
```

Column names should be treated case-insensitively.

## 8. Domain Entities

### Trade

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Internal ID |
| product_type | string | Example: Ratio Convertible Forward |
| client_direction | string | Example: Importer |
| pair | string | MVP: AUD/USD |
| trade_date | date | Trade start date |
| spot | decimal | Spot at trade date |
| strike | decimal | Option strike |
| barrier | decimal | Barrier level |
| barrier_direction | string | `up` or `down` |
| barrier_level_period | string | Example: continuous |
| expiry_date | date | Expiry date |
| expiry_time_zone | string | Example: Tokyo |
| protected_amount | decimal | Base protected notional |
| ratio_amount | decimal | Leveraged notional if applicable |
| option_type | string | Optional: call/put |

### BacktestResult

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Internal ID |
| trade_id | integer | Link to trade |
| days_to_expiry | integer | Calendar days |
| distance_pct | decimal | Barrier distance percentage |
| sample_count | integer | Historical windows tested |
| touch_count | integer | Windows where barrier was touched |
| touch_probability | decimal | `touch_count / sample_count` |
| barrier_hit | boolean | Whether actual loaded path hit the barrier, if available |
| hit_date | date | First touch date, if hit |
| max_high | decimal | Max high in trade window |
| min_low | decimal | Min low in trade window |
| days_to_hit | integer | Days from trade date to first touch |

### FeatureSnapshot

Later versions should create one feature row per synthetic historical trade date and one feature row for the current trade.

| Field | Type | Notes |
| --- | --- | --- |
| as_of_date | date | Feature calculation date |
| pair | string | Example: AUD/USD |
| days_to_expiry | integer | Calendar days |
| distance_pct | decimal | Barrier distance percentage |
| realized_vol_20d | decimal | Recent realized volatility |
| realized_vol_60d | decimal | Medium-term realized volatility |
| atr_14d | decimal | Average true range proxy |
| trend_20d | decimal | Recent return/trend |
| range_position | decimal | Spot position in recent range |
| dxy_return_20d | decimal | Optional external feature |
| vix_level | decimal | Optional external feature |
| au_us_yield_spread | decimal | Optional external feature |
| target_barrier_hit | boolean | Known only for historical rows |

## 9. Suggested Architecture

Start simple.

```text
yfinance AUDUSD=X data
   |
   v
barrier_engine.py
   |
   v
feature_engine.py
   |
   v
probability_model.py
   |
   v
CLI or Streamlit UI
   |
   v
SQLite persistence
```

Recommended module split once implementation begins:

```text
src/
  barrier_engine.py      # pure calculation logic
  data_loader.py         # yfinance download and data validation
  feature_engine.py      # volatility, trend, and regime features
  probability_model.py   # calibrated forward touch estimate
  repository.py          # SQLite reads/writes
  app_streamlit.py       # UI, added after engine is tested
tests/
  test_barrier_engine.py
```

Important design rule:

The barrier calculation should be pure and testable. It should not depend on Streamlit, FastAPI, SQLite, or yfinance.

Feature generation and probability modeling should also be testable separately from the UI.

## 10. Technology Choices

### Recommended MVP Stack

- Python
- Pandas
- Scikit-learn, once model features are introduced
- SQLite
- Pytest
- Streamlit, only after core logic is validated

### FastAPI

FastAPI is useful if another system needs to call this analyzer. It should not be part of the first implementation unless API access is required immediately.

Adding FastAPI too early creates two product surfaces: API and UI. That increases work before the core calculation has been validated.

## 11. Validation Rules

Reject or warn on:

- Expiry date on or before trade date.
- Spot less than or equal to zero.
- Barrier less than or equal to zero.
- Missing OHLC columns.
- Empty market data.
- Unsupported pair.
- Unsupported barrier direction.

For MVP, if historical data does not extend far enough for a complete forward window, that sample should be excluded from `sample_count`.

## 12. Expected Output

Example:

```json
{
  "pair": "AUD/USD",
  "spot": 0.65,
  "barrier": 0.705,
  "days_to_expiry": 135,
  "distance_pct": 8.46,
  "historical_samples": 3124,
  "touch_count": 1410,
  "historical_baseline_probability": 45.1,
  "volatility_adjusted_probability": null,
  "model_probability": null,
  "probability_used": 45.1,
  "method": "historical_baseline"
}
```

## 13. Model Evaluation

Future models should be evaluated as probability models, not only classifiers.

Required evaluation metrics:

- Out-of-sample log loss.
- Brier score.
- Calibration curve.
- Hit-rate by probability bucket.
- Comparison against historical baseline.

Validation approach:

- Use walk-forward validation.
- Avoid look-ahead leakage.
- Generate historical features using only information available as of each synthetic trade date.
- Compare every model against the baseline historical probability.

## 14. Known Limitations

- Daily OHLC cannot identify intraday ordering.
- Calendar-day windows may include weekends and holidays.
- Historical probability assumes future behavior resembles historical behavior.
- Volatility and macro features may still fail during regime breaks.
- Daily OHLC data may miss intraday sequencing around barriers.
- No volatility regime adjustment in MVP.
- No macro, news, or implied-volatility inputs in MVP.
- No option pricing or payoff modeling in MVP.

## 15. Design Principles

- Prioritize calculation correctness over UI.
- Keep the first version auditable.
- Treat historical baseline as the benchmark, not the endpoint.
- Move toward forward-looking probability estimation through measurable feature improvements.
- Avoid machine learning until the target-label generation and baseline are trusted.
- Every probability should identify its method: baseline, volatility-adjusted, or model-based.
- Do not mix explanatory LLM output with probability generation.
