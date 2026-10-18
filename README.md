# DZ-AND-SZ: Nifty 500 Demand & Supply Zone Scanner

Scans Nifty 500 stocks for fresh **demand** and **supply** zones on Daily, Weekly,
Monthly, Quarterly, Half-Yearly and Yearly timeframes, and lists stocks whose price is
**approaching** or **inside** a zone.

> Simplified base-then-explosive-move logic. It is **not** GTF's proprietary method, so results
> will differ from GTF Eye. For education only, not investment advice.

## Setup

```bash
pip install -r requirements.txt
```

## Run

```bash
python dz_sz_scanner.py                                  # all timeframes, Nifty 500
python dz_sz_scanner.py --timeframes Weekly Monthly      # only some timeframes
python dz_sz_scanner.py --type Demand --status in_zone   # only demand zones, price inside
python dz_sz_scanner.py --symbols MANKIND PNBHOUSING     # test on specific stocks
python dz_sz_scanner.py --csv nifty500.csv               # use a local constituents CSV
```

Results print to the terminal and are saved to `results/zones_<date>.csv`.

If the automatic Nifty 500 download fails (NSE sometimes blocks scripts), download the
constituents CSV from niftyindices.com and pass it with `--csv`.

## Tunable settings

| Flag | Default | Meaning |
|---|---|---|
| `--body-pct` | 50 | Max base candle body as % of its range |
| `--impulse-atr` | 1.5 | Min size of the explosive candle, in ATRs |
| `--approach-pct` | 3.0 | How close (%) price must be to count as "approaching" |

Prices come from Yahoo Finance via `yfinance` (can be delayed or occasionally missing).
The latest higher-timeframe candle is still forming, so signals can change before it closes.
