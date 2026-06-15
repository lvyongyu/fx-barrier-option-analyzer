# FX Barrier Option Analyzer - Design Document

## 1. Product Goal

Build a lightweight analysis system for FX barrier option trades, starting with AUD/USD and now supporting configurable FX pairs.

The system's end goal is to estimate:

```text
P(Barrier Hit Before Expiry)
```

This is not a traditional FX point-forecasting system. It does not predict the final spot level or only the direction of the selected pair. It estimates a path-dependent event:

```text
Will the selected FX pair touch the barrier before expiry?
```

The first implementation uses historical touch frequency as a baseline prior. Later versions must improve that baseline with current volatility, market regime, and forward-looking features.

The system runs in two complementary modes:

1. **One-off analysis** - estimate `P(Barrier Hit Before Expiry)` for a single trade on demand (the original goal above).
2. **Live position monitoring** - track the user's real open trades over time and raise an SMS alert the first day a barrier is actually touched, so the user knows to act. This consumes the same barrier-hit logic but against ongoing market data rather than a backtest window.

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

The system should support Corpay-style `Ratio Convertible Forward` structures for FX pairs such as AUD/USD and AUD/CNH.

Example fields from real trade sheets:

| Product | Direction | Pair | Protected amount | Ratio amount | Strike | Barrier | Barrier period | Expiry |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Ratio Convertible Forward | Importer | AUD/USD | USD 500,000 | USD 1,000,000 | 0.6850 | 0.6935 | Continuous | 2026-12-30 |
| Ratio Convertible Forward | Importer | AUD/USD | USD 1,000,000 | USD 2,000,000 | 0.6850 | 0.6935 | Continuous | 2026-12-30 |

AUD/CNH is supported through configurable pair input. If direct Yahoo Finance CNH history is sparse, the data layer may use a documented proxy such as AUD/USD multiplied by USD/CNY history.

Options expire at 3:00 p.m. Tokyo time in these examples.

For this product, the modeling target is:

```text
Will the spot rate breach the barrier at any point during the continuous barrier period before expiry?
```

The downstream payoff scenario depends on whether the barrier breaches, but the first modeling problem remains the path event:

```text
BarrierBreachBeforeExpiry = true / false
```

### Confirmation Structure

A real Corpay confirmation can contain multiple scheduled expiries. Each expiry may contain a vanilla European leg and a barrier/knockout leg.

Example from the Uniwell confirmation:

| Expiry | European ref | Knockout ref | Strike | Barrier | Window |
| --- | --- | --- | --- | --- | --- |
| 2026-08-28 | 4096154 | 4096155 | 0.6900 | 0.7050 | 2026-04-15 to 2026-08-28 |
| 2026-09-29 | 4096156 | 4096157 | 0.6900 | 0.7050 | 2026-04-15 to 2026-09-29 |
| 2026-10-29 | 4096158 | 4096159 | 0.6900 | 0.7050 | 2026-04-15 to 2026-10-29 |

The analyzer should therefore support:

```text
Confirmation
  ScheduledExpiry[]
    OptionLeg[]
    BarrierWindow
```

The current implementation maps each knockout leg into one per-expiry `Trade` that can be analyzed independently.

### Live Position Monitoring

Beyond one-off analysis, the user maintains a register of their real open trades and wants to be alerted the moment a barrier triggers. The workflow is:

```text
1. Run a forecast for the trade (src.analyze), optionally save research data.
2. Register the real trade as a monitored position (src.monitor_cli add).
3. A scheduled job checks each active position daily against fresh market data.
4. The first day the barrier is touched, send one SMS alert and stop re-alerting.
```

Key design points:

- Monitored positions are stored in their own SQLite table (`monitored_positions`), kept separate from research/sample trades. A small dedicated DB (`data/positions.sqlite3`) is version-controlled so a scheduled GitHub Actions run can persist status back; the larger research store (`data/research.sqlite3`) stays local-only.
- The backtest hit-checker (`evaluate_actual_path`) requires the whole window to be in the past, which never holds for a live trade. Live monitoring uses a dedicated checker (`evaluate_live_path`) that scans `[trade_date, min(expiry_date, last_available_date)]`.
- A position has a lifecycle: `active -> triggered` (barrier touched) or `active -> expired` (reached expiry untouched). Alerts are de-duplicated with an `alert_sent_at` timestamp, which is set only after the SMS is actually delivered. A triggered position keeps being re-checked until that send succeeds, so a transient SMS failure is retried on the next run rather than silently lost; once delivered, the position is done and never re-alerts.
- Alert delivery goes through an isolated, pluggable notification layer (`notifications.send_alert`) that picks the first configured channel, preferring email (Gmail SMTP) with Twilio SMS as an optional fallback. Channels are configured purely through environment variables / CI secrets and support a dry-run mode. New channels (Telegram, webhook) can be added without touching the monitor logic.

## 3. MVP Scope

The MVP should stay deliberately small.

Included:

- Download selected FX daily OHLC data from Yahoo Finance.
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
- Full institutional market-data sourcing beyond Yahoo Finance.
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
Barrier-theory probability
Regime-adjusted probability
Model probability
Confidence / data-quality notes
```

The system should avoid pretending that historical frequency alone is a complete future forecast.

### Barrier-Theory Baseline

The probability stack includes a reproducible theoretical touch estimate, not only generic classifiers.

For an FX barrier event, the model should explicitly account for:

```text
spot
barrier
barrier direction
days to expiry
realized volatility
expected move to expiry
distance in volatility units
```

The first implementation uses a driftless log-Brownian reflection approximation. This gives the analyzer a transparent benchmark for path probability:

```text
P(min_path <= down_barrier before expiry)
P(max_path >= up_barrier before expiry)
```

This barrier-theory probability should be evaluated against:

- Historical baseline probability.
- Train-calibrated GBM/historical blend probability.
- Volatility-adjusted probability.
- Price-only logistic model.
- Price + external-feature model.

If the barrier-theory estimate is useful, later ML should calibrate or blend it rather than relearn barrier math from scratch. The current blend chooses the GBM weight on the training split, then evaluates on the walk-forward test split. Initial sample-trade evaluation shows GBM helps some down-barrier cases but does not universally beat the historical baseline; the blend is more conservative and can dilute useful GBM signal.

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

Market data should be downloaded automatically from Yahoo Finance. The default pair is AUD/USD:

```python
yfinance.download("AUDUSD=X", period="2y")
```

Other pairs are mapped to Yahoo-style FX tickers where available:

```text
EUR/USD -> EURUSD=X
USD/JPY -> USDJPY=X
AUD/CNH -> AUDCNH=X, with fallback/proxy handling if direct history is sparse
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
| pair | string | Example: AUD/USD, EUR/USD, AUD/CNH |
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

### MonitoredPosition

A real open trade registered for live barrier monitoring. Stored in the `monitored_positions` table, separate from research/sample trades.

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Internal ID |
| label | string | Unique human label, e.g. `audusd-06935-down-dec2026` |
| trade_id | integer | Optional link to a saved `Trade` row |
| pair / trade_date / spot / strike / barrier / expiry_date / barrier_direction | - | Trade terms (same meaning as `Trade`) |
| product_type / client_direction / note | string | Descriptive metadata |
| status | string | `active`, `triggered`, or `expired` |
| triggered_date | date | First day the barrier was touched, if any |
| triggered_price | decimal | Daily high (up) or low (down) that breached the barrier |
| alert_sent_at | datetime | When the SMS alert was sent; null until alerted (dedup guard) |
| last_checked | datetime | Timestamp of the most recent monitoring run |

### Confirmation

| Field | Type | Notes |
| --- | --- | --- |
| customer | string | Customer legal name |
| trade_date | date | Confirmation trade date |
| pair | string | Example: AUD/USD |
| base_currency | string | Example: AUD |
| quote_terms | string | Example: USD per 1 AUD |
| references | list | Confirmation reference numbers |
| expiries | list | Scheduled expiries |

### ScheduledExpiry

| Field | Type | Notes |
| --- | --- | --- |
| expiration_date | date | Option expiry date |
| settlement_date | date | Settlement date |
| legs | list | European and barrier legs |

### OptionLeg

| Field | Type | Notes |
| --- | --- | --- |
| reference | string | Corpay reference number |
| option_type | string | European or Knockout |
| option_seller | string | Seller name |
| option_buyer | string | Buyer name |
| strike | decimal | Strike rate |
| barrier | decimal | Barrier level, if applicable |
| barrier_direction | string | Required for barrier legs |
| window_start_date | date | Barrier window start |
| window_end_date | date | Barrier window end |
| call_currency | string | Call currency |
| call_amount | decimal | Call amount |
| put_currency | string | Put currency |
| put_amount | decimal | Put amount |

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
yfinance FX data
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
  price_model.py         # experimental calibrated forward touch estimate
  barrier_theory.py      # GBM barrier-touch baseline
  pdf_report.py          # PDF report rendering
  agent.py              # deterministic agent parser/reviewer
  monitor.py             # pure live-position logic (evaluate_live_path, status)
  notifications.py       # pluggable alerts: email (Gmail SMTP) + Twilio SMS, dry-run capable
  monitor_cli.py         # add/list/check real positions, sends alerts
  repository.py          # SQLite reads/writes (incl. monitored_positions)
  app_streamlit.py       # UI, added after engine is tested
tests/
  test_barrier_engine.py
```

Live monitoring reuses the pure barrier logic but adds an ongoing-data path:

```text
monitored_positions (SQLite)        scheduled GitHub Actions (daily)
        |                                      |
        v                                      v
   monitor_cli.py  --->  monitor.evaluate_live_path  --->  notifications.send_alert
        |                                                  (email / Twilio SMS)
        v
   persist status back (commit data/positions.sqlite3)
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
- Unsupported or unavailable pair data.
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
  "features": {
    "realized_vol_20d": 8.0,
    "realized_vol_60d": 9.7,
    "atr_14d": 0.78,
    "trend_20d": -1.14,
    "trend_60d": 0.58,
    "range_position_60d": -7.72,
    "recent_high_distance": 7.02,
    "recent_low_distance": -0.50
  },
  "volatility_adjustment": {
    "method": "volatility_bucket",
    "current_vol_percentile": 40.0,
    "comparable_sample_count": 63,
    "comparable_touch_count": 57,
    "volatility_adjusted_probability": 90.48,
    "used_fallback": false
  },
  "model_probability": null,
  "probability_used": 90.48,
  "method": "volatility_bucket"
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
- Compare models across generated near/medium/far up/down sample trades, not only one confirmation example.
- Treat positive `dBrier` as the first sign of model usefulness.
- Require calibration buckets to be directionally sensible before trusting a model probability.

Current findings:

- The initial logistic models generally do not beat the historical baseline across the sample-trade batch.
- DXY/VIX external features have not improved the current batch evaluation.
- An external institutional-style report produced a plausible 76% down-barrier probability for AUD/USD below 0.6908, but its simulation and calibration details are not fully auditable.

Design implication:

The next model step is calibration around the transparent GBM/barrier-theory baseline. UI, API, and additional external features should wait until this probability layer is better calibrated and evaluated.

## 14. Known Limitations

- Daily OHLC cannot identify intraday ordering.
- Calendar-day windows may include weekends and holidays.
- Historical probability assumes future behavior resembles historical behavior.
- Volatility and macro features may still fail during regime breaks.
- Daily OHLC data may miss intraday sequencing around barriers.
- The current logistic model is experimental and should not be trusted unless it beats baseline metrics.
- DXY/VIX are experimental context features, not proven predictive features.
- No macro, news, or implied-volatility inputs are trusted as core probability drivers yet.
- No option pricing or payoff modeling in MVP.
- Live monitoring uses daily OHLC, so barrier-touch alerts fire on the scheduled run after the touch closes a day, not intraday/real-time. Latency is up to ~1 day plus the cron interval.
- Monitoring depends on Yahoo Finance availability and the scheduled job running; a missed or delayed data day delays the alert.

## 15. Design Principles

- Prioritize calculation correctness over UI.
- Keep the first version auditable.
- Treat historical baseline as the benchmark, not the endpoint.
- Prefer transparent market/math baselines before complex ML.
- Move toward forward-looking probability estimation through measurable feature improvements.
- Avoid expanding ML until target-label generation, barrier-theory baseline, and calibration are trusted.
- Every probability should identify its method: baseline, volatility-adjusted, or model-based.
- Do not mix explanatory LLM output with probability generation.
