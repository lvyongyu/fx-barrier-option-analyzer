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
