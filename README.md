# FX Barrier Option Analyzer

Phase 1 is intentionally small: download AUD/USD daily OHLC data from Yahoo Finance and calculate historical barrier-touch probability.

No UI, database, or API yet.

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

## Analyze A Trade

```bash
python -m src.analyze \
  --trade-date 2026-04-15 \
  --expiry-date 2026-08-28 \
  --spot 0.6500 \
  --strike 0.6900 \
  --barrier 0.7050 \
  --barrier-direction up \
  --period 2y
```

Corpay-style Ratio Convertible Forward example:

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
  --barrier-level-period continuous \
  --expiry-time-zone Tokyo \
  --period 2y
```

The default market data source is:

```python
yfinance.download("AUDUSD=X", period="2y")
```

Automatic download and analysis are currently scoped to `AUD/USD` only.

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

## Calculation Summary

For the target trade:

```text
days_to_expiry = expiry_date - trade_date
distance_pct = (barrier - spot) / spot
```

For every historical AUD/USD trading day:

1. Use that day's close as synthetic spot.
2. Apply the target trade's `distance_pct`.
3. Look forward the same number of calendar days as the target trade.
4. For an up barrier, count a hit if any future daily high touches the synthetic barrier.
5. For a down barrier, count a hit if any future daily low touches the synthetic barrier.

```text
touch_probability = touch_count / sample_count
```

Feature snapshots use only market data available on or before the snapshot date. Tests cover this no-look-ahead boundary.
