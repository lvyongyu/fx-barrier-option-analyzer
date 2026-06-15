# FX Barrier Option Analyzer

The project estimates whether an FX pair will touch a barrier before expiry. It defaults to AUD/USD but can run other Yahoo Finance FX pairs such as EUR/USD, GBP/USD, USD/JPY, and AUD/CNH.

Current focus: improve the probability engine and model evaluation. UI and API work are intentionally deferred.

AI agent integration is planned as an interpretation and workflow layer, not as
a replacement for the probability engine. See [AI Agent Plan](docs/AI_AGENT_PLAN.md).

## Requirements

- Python 3.12+
- Internet access for `yfinance`

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

If your machine does not expose `python3.12`, use any Python 3.12+ interpreter path.

## Run Tests

```bash
pytest
```

## Local Agent Helpers

The first agent layer is local and deterministic. It does not call an LLM yet.

Parse a natural-language forecast request:

```bash
python -m src.agent_cli parse-request "想预测一下未来3个月audusd是否跌1.5%"
```

Review a machine-readable model payload:

```bash
python -m src.analyze \
  --pair AUD/USD \
  --expiry-date 2026-09-13 \
  --strike 0.704871 \
  --barrier 0.694298 \
  --barrier-direction down \
  --json > forecast_payload.json

python -m src.agent_cli review-json forecast_payload.json
```

## Analyze A Trade

```bash
python -m src.analyze \
  --pair AUD/USD \
  --trade-date 2026-04-15 \
  --expiry-date 2026-08-28 \
  --spot 0.6500 \
  --strike 0.6900 \
  --barrier 0.7050 \
  --barrier-direction up \
  --period 2y
```

## Bilateral Move Analysis

Use bilateral analysis for questions like:

```text
未来3个月 AUD/CNH 是否涨跌 3%？
```

Example:

```bash
python -m src.bilateral_cli \
  --pair AUD/CNH \
  --period 5y \
  --move-pct 3 \
  --horizon-days 92 \
  --pdf reports/audcnh_3m_bilateral_3pct_forecast.pdf
```

This reports:

- `P(touch upper)`
- `P(touch lower)`
- `P(touch either)`
- `P(touch both)`

Upper and lower touch events are not complements. A pair can touch both barriers
inside the same forecast window.

Corpay-style Ratio Convertible Forward example:

The screenshot-style Corpay input maps to:

```text
Product: Ratio Convertible Forward
Client direction: Importer
Protected amount: USD 500,000
Ratio amount: USD 1,000,000
Strike rate: 0.6850
Barrier level: 0.6935
Barrier level period: continuous
Expiry date: 2026-12-30
Expiry time: 3:00 p.m. Tokyo time
```

The current analyzer still requires manual `trade_date` and `spot`, because the screenshot does not show those fields.

```bash
python -m src.analyze \
  --product-type "Ratio Convertible Forward" \
  --pair AUD/USD \
  --client-direction Importer \
  --protected-amount 500000 \
  --ratio-amount 1000000 \
  --amount-currency USD \
  --trade-date 2026-04-15 \
  --expiry-date 2026-12-30 \
  --spot 0.6800 \
  --strike 0.6850 \
  --barrier 0.6935 \
  --barrier-direction up \
  --barrier-level-period continuous \
  --expiry-time-zone Tokyo \
  --period 2y
```

FX market data is downloaded from Yahoo Finance. Pair labels are converted automatically:

```text
AUD/USD -> AUDUSD=X
EUR/USD -> EURUSD=X
USD/JPY -> USDJPY=X
```

The default pair is `AUD/USD`.

For CNH pairs, Yahoo Finance direct history can be sparse. The current data
loader may fall back to a CNY proxy path, for example deriving AUD/CNH from
AUD/USD and USD/CNY history. Treat those results as proxy-based until a better
institutional data source is added.

## Track Real Positions & Alert

Monitor your *real* trades and get an SMS the moment a barrier is first touched.
Live positions are stored in the `monitored_positions` table of a dedicated
SQLite DB (`data/positions.sqlite3`), separate from the research store. That DB is
small and **tracked in git** so a scheduled job can persist status back; the
research store (`data/research.sqlite3`) stays local-only and is gitignored.

```bash
# 1. (optional) run a forecast and save research data
python -m src.analyze --pair AUD/USD --expiry-date 2026-12-30 \
  --strike 0.7050 --barrier 0.6935 --barrier-direction down \
  --save-db data/research.sqlite3

# 2. register the real trade for monitoring (writes to data/positions.sqlite3)
python -m src.monitor_cli add \
  --id audusd-06935-down-dec2026 --pair AUD/USD \
  --trade-date 2026-06-01 --spot 0.7050 --strike 0.7050 \
  --barrier 0.6935 --barrier-direction down --expiry-date 2026-12-30 \
  --client-direction Exporter

# 3. list tracked positions and their status
python -m src.monitor_cli list

# 4. check for fresh barrier touches (sends SMS on a new trigger)
python -m src.monitor_cli check --notify        # add --dry-run to only print
```

A position moves `active -> triggered` (barrier touched) or `active -> expired`
(passed expiry untouched). The first time a position triggers, one SMS is sent and
`alert_sent_at` is recorded so it never re-alerts. Use `--db` to point at a
different SQLite file. Real Corpay confirmations are down-and-out, so use
`--barrier-direction down` with a barrier below spot.

### SMS configuration (Twilio)

SMS uses Twilio's REST API via the standard library (no extra dependency). Set:

| Env var | Meaning |
| --- | --- |
| `TWILIO_ACCOUNT_SID` | Twilio account SID (`AC...`) |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `TWILIO_FROM_NUMBER` | sender number, E.164 (e.g. `+15555550123`) |
| `ALERT_TO_NUMBER` | your phone, E.164 (e.g. `+8613800138000`) |

### Daily check via GitHub Actions

`.github/workflows/monitor-positions.yml` runs `check --notify` daily (21:10 UTC)
and commits status changes back to `data/positions.sqlite3`. Add the four variables
above as repository **secrets** (Settings → Secrets and variables → Actions). Use
the workflow's manual `dry_run` input to test without sending SMS. Commit your
populated `data/positions.sqlite3` so the cloud run can see your positions.

## Confirmation Structure

Real Corpay confirmations may contain multiple scheduled expiries. The Uniwell confirmation maps to:

```text
Confirmation
  2026-08-28
    4096154 European
    4096155 Knockout
  2026-09-29
    4096156 European
    4096157 Knockout
  2026-10-29
    4096158 European
    4096159 Knockout
```

The code currently supports manual confirmation mapping with:

```python
from src.confirmation import build_uniwell_confirmation_example, barrier_legs_to_trades
```

It does not yet automatically parse PDFs. Each knockout leg is converted into a per-expiry `Trade` for analysis.

The CLI also prints a current price-derived feature snapshot:

```text
Current feature snapshot:
As of: 2026-06-13
Realized vol 20d: 8.00%
Realized vol 60d: 9.70%
ATR 14d: 0.78%
Trend 20d: -1.14%
Trend 60d: 0.58%
Range position 60d: -7.72%
Recent high distance: 7.02%
Recent low distance: -0.50%
```

These features are not yet a model. They are the inputs needed for the next volatility/regime-adjusted estimate.

The CLI now also prints a first volatility-adjusted estimate:

```text
Volatility-adjusted estimate:
Method: volatility_bucket
Current 20d vol percentile: 40.00%
Comparable samples: 63
Comparable touch count: 57
Volatility-adjusted probability: 90.48%
```

This compares the current trade against historical samples whose 20-day realized volatility percentile is near the current volatility percentile. If there are too few comparable samples, the tool falls back to the historical baseline and explains why.

By default, the CLI prints a readable summary. Add `--json` if you want the raw structured result:

```bash
python -m src.analyze \
  --trade-date 2026-04-15 \
  --expiry-date 2026-08-28 \
  --spot 0.6500 \
  --strike 0.6900 \
  --barrier 0.7050 \
  --barrier-direction up \
  --period 2y \
  --json
```

Use `--report-style forecast` for an institutional-style probability report:

```bash
python -m src.analyze \
  --product-type "Ratio Convertible Forward" \
  --client-direction Importer \
  --protected-amount 500000 \
  --ratio-amount 1000000 \
  --amount-currency USD \
  --trade-date 2026-04-15 \
  --expiry-date 2026-12-30 \
  --spot 0.6800 \
  --strike 0.6850 \
  --barrier 0.6935 \
  --barrier-direction up \
  --period 2y \
  --report-style forecast
```

The forecast-style report includes:

- question and forecast date
- probability distribution
- most likely outcome
- trade snapshot
- reference estimates
- barrier-theory details
- touch-supporting and touch-opposing factors
- model risk notes

## Run From GitHub Actions

The repository includes a manual workflow:

```text
Actions -> Manual FX Barrier Forecast -> Run workflow
```

Required inputs:

- `pair`
- `expiry_date`
- `strike`
- `barrier`
- `barrier_direction`: price direction being tested. Use `up` for daily high >= barrier, and `down` for daily low <= barrier.

Optional inputs:

- `trade_date`: analysis date, YYYY-MM-DD. If blank, use the latest market date for the selected pair
- `spot`: spot on the analysis date. If blank, use the selected pair's close for `trade_date`
- `period`: Yahoo Finance history window, default `5y`

`protected_amount` and `ratio_amount` are intentionally not required because they affect payoff exposure, not barrier-touch probability.

If `trade_date` and `spot` are left blank, the report is a current-market risk check. If the latest spot is already beyond the barrier in the selected barrier direction, the touch probability can be 100%. To reproduce the original trade-date view, enter the original `trade_date` and `spot`.

The workflow prints the forecast report in the run log and uploads these artifacts:

- `forecast_report.txt`
- `forecast_report.pdf`
- `forecast_payload.json`
- `agent_review.json`

Add `--save-db` to persist research data into SQLite:

```bash
python -m src.analyze \
  --product-type "Ratio Convertible Forward" \
  --client-direction Importer \
  --protected-amount 500000 \
  --ratio-amount 1000000 \
  --amount-currency USD \
  --trade-date 2026-04-15 \
  --expiry-date 2026-12-30 \
  --spot 0.6800 \
  --strike 0.6850 \
  --barrier 0.6935 \
  --barrier-direction up \
  --period 2y \
  --save-db data/research.sqlite3
```

The research database stores:

- `market_prices`
- `trades`
- `feature_snapshots`
- `analysis_results`
- `volatility_adjustments`

Export a price-only training dataset for the future model:

```bash
python -m src.analyze \
  --product-type "Ratio Convertible Forward" \
  --client-direction Importer \
  --protected-amount 500000 \
  --ratio-amount 1000000 \
  --amount-currency USD \
  --trade-date 2026-04-15 \
  --expiry-date 2026-12-30 \
  --spot 0.6800 \
  --strike 0.6850 \
  --barrier 0.6935 \
  --barrier-direction up \
  --period 2y \
  --export-training-dataset data/training_price_only.csv
```

The training dataset contains one row per synthetic historical trade date:

```text
price-derived features as of that date
target_barrier_hit over the forward expiry window
```

Features are calculated using only data available on or before each synthetic trade date.

The CLI also trains an experimental price-only logistic regression model and compares it against a baseline probability on a walk-forward split:

```text
Price-only model estimate:
Model probability: 41.04%
Train rows: 192
Test rows: 83
Train hit rate: 78.65%
Test hit rate: 100.00%
Baseline probability: 78.65%
Model Brier score: 0.3597
Baseline Brier score: 0.0456
Model comparison: model underperformed baseline on Brier score
```

The model probability should not be trusted unless its validation metrics beat or usefully complement the baseline.

Add `--include-external-features` to download DXY and VIX, print external market context,
and train a second experimental model that uses both price features and external features:

```bash
python -m src.analyze \
  --trade-date 2026-04-15 \
  --expiry-date 2026-12-30 \
  --spot 0.6800 \
  --strike 0.6850 \
  --barrier 0.6935 \
  --barrier-direction up \
  --period 2y \
  --include-external-features
```

Example external features:

```text
External market features:
As of: 2026-06-12
DXY return 20d: 0.88%
DXY trend 60d: -0.34%
VIX level: 17.6800
VIX change 20d: -0.7500
```

Example external model output:

```text
Price + external model estimate:
Model probability: 48.12%
Train rows: 174
Test rows: 75
Model comparison: model beat baseline on Brier score
```

The external model is still experimental. Treat it as useful only when its walk-forward
metrics improve on the baseline or explain a clear difference from the price-only model.

## Model Evaluation Report

Use the evaluation report to compare historical window lengths before trusting any model output:

```bash
python -m src.evaluation_report \
  --trade-date 2026-04-15 \
  --expiry-date 2026-12-30 \
  --spot 0.6800 \
  --strike 0.6850 \
  --barrier 0.6935 \
  --barrier-direction up \
  --periods 2y 5y 10y
```

The report compares:

- historical baseline probability
- volatility-adjusted probability
- GBM barrier-theory probability and Brier score
- train-calibrated GBM/historical blend probability and Brier score
- price-only model probability and Brier score
- price + external model probability and Brier score
- calibration buckets showing predicted probability versus actual hit rate

Calibration buckets answer the practical question: when the model predicts a 40-60%
touch probability, did similar historical samples actually hit about 40-60% of the time?

## Sample Trade Suite

Generate several AUD/USD trade examples from the latest historical close:

```bash
python -m src.sample_trades --period 5y
```

The suite creates near/medium/far up-barrier and down-barrier examples using recent
AUD/USD ATR to set barrier distances. This gives the model evaluation layer a broader
set of scenarios than one long-tenor, near-barrier confirmation example.

Evaluate the full sample suite:

```bash
python -m src.evaluation_report --sample-trades --periods 5y
```

The batch report shows which trade types, if any, have positive model `dBrier`.
Positive `dBrier` means the model beat the historical baseline on walk-forward Brier score.

Example 5y batch finding after adding the GBM barrier-theory baseline:

```text
medium_down_90d  GBM dBrier  0.0662   Blend dBrier  0.0275   Price dBrier -0.1982
far_down_180d    GBM dBrier  0.0171   Blend dBrier  0.0121   Price dBrier -0.1227
```

This means the transparent GBM estimate is already more useful than the generic logistic model in some down-barrier scenarios. The blend is more conservative than pure GBM: it can smooth losses, but it can also dilute useful GBM signal.

## External Forecast Comparison

An external institutional-style forecast for June 11, 2026 to September 11, 2026 estimated:

```text
Daily lowest AUD/USD < 0.6908: 76%
Daily lowest AUD/USD 0.6908 to 0.696: 12%
Daily lowest AUD/USD >= 0.696: 12%
```

This is equivalent to a down-barrier touch probability question. A quick local comparison showed:

```text
Using spot 0.7049 and barrier 0.6908:
5y historical touch probability ~= 76.44%

Using spot 0.7007 and barrier 0.6908:
5y historical touch probability ~= 84.45%
```

Simple driftless GBM estimates were lower, roughly 57-73% depending on spot and realized volatility.

Conclusion: the external forecast is directionally reasonable, but the report is not fully auditable because it does not disclose enough simulation and calibration detail. The project now includes a reproducible barrier-theory baseline:

```text
GBM touch probability
train-calibrated GBM/historical blend
distance in volatility units
expected move to expiry
barrier z-score
GBM and blend dBrier in batch evaluation
```

The goal is not to copy the external forecast. The goal is to build a transparent version that can be tested against historical outcomes.

## Calculation Summary

For the target trade:

```text
days_to_expiry = expiry_date - trade_date
distance_pct = (barrier - spot) / spot
```

For every historical trading day for the selected pair:

1. Use that day's close as synthetic spot.
2. Apply the target trade's `distance_pct`.
3. Look forward the same number of calendar days as the target trade.
4. For an up barrier, count a hit if any future daily high touches the synthetic barrier.
5. For a down barrier, count a hit if any future daily low touches the synthetic barrier.

```text
touch_probability = touch_count / sample_count
```

Feature snapshots use only market data available on or before the snapshot date. Tests cover this no-look-ahead boundary.
