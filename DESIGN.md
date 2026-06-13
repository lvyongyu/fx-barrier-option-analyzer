# FX Barrier Option Analyzer - Design Document

## 1. Product Goal

Build a lightweight analysis system for FX barrier option trades, starting with AUD/USD.

The system estimates:

```text
P(Barrier Hit Before Expiry)
```

This is not a traditional FX forecasting system. It does not predict the final AUD/USD level, the direction of AUD/USD, or a future spot price. It estimates whether a specified barrier would be touched before expiry, based on historical daily OHLC behavior.

## 2. Core Use Case

Given a trade:

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
Historically, how often did AUD/USD touch an equivalent barrier before an equivalent expiry window?
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
- Multi-currency portfolio support.
- Volatility-adjusted probability.
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

## 6. Data Requirements

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

## 7. Domain Entities

### Trade

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Internal ID |
| pair | string | MVP: AUD/USD |
| trade_date | date | Trade start date |
| spot | decimal | Spot at trade date |
| strike | decimal | Option strike |
| barrier | decimal | Barrier level |
| barrier_direction | string | `up` or `down` |
| expiry_date | date | Expiry date |
| notional | decimal | Optional in first version |
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

## 8. Suggested Architecture

Start simple.

```text
yfinance AUDUSD=X data
   |
   v
barrier_engine.py
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
  repository.py          # SQLite reads/writes
  app_streamlit.py       # UI, added after engine is tested
tests/
  test_barrier_engine.py
```

Important design rule:

The barrier calculation should be pure and testable. It should not depend on Streamlit, FastAPI, SQLite, or yfinance.

## 9. Technology Choices

### Recommended MVP Stack

- Python
- Pandas
- SQLite
- Pytest
- Streamlit, only after core logic is validated

### FastAPI

FastAPI is useful if another system needs to call this analyzer. It should not be part of the first implementation unless API access is required immediately.

Adding FastAPI too early creates two product surfaces: API and UI. That increases work before the core calculation has been validated.

## 10. Validation Rules

Reject or warn on:

- Expiry date on or before trade date.
- Spot less than or equal to zero.
- Barrier less than or equal to zero.
- Missing OHLC columns.
- Empty market data.
- Unsupported pair.
- Unsupported barrier direction.

For MVP, if historical data does not extend far enough for a complete forward window, that sample should be excluded from `sample_count`.

## 11. Expected Output

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
  "touch_probability": 45.1
}
```

## 12. Known Limitations

- Daily OHLC cannot identify intraday ordering.
- Calendar-day windows may include weekends and holidays.
- Historical probability assumes future behavior resembles historical behavior.
- No volatility regime adjustment in MVP.
- No macro, news, or implied-volatility inputs in MVP.
- No option pricing or payoff modeling in MVP.

## 13. Design Principles

- Prioritize calculation correctness over UI.
- Keep the first version auditable.
- Avoid machine learning until the historical baseline is trusted.
- Every probability should be explainable from historical samples.
- Do not mix explanatory LLM output with probability generation.
