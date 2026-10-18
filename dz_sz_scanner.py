#!/usr/bin/env python3
"""
Nifty 500 Demand / Supply Zone Scanner (multi-timeframe)

Finds the most recent FRESH demand and supply zone on Daily, Weekly, Monthly,
Quarterly, Half-Yearly and Yearly candles, and reports stocks whose price is
APPROACHING or IN the zone.

Zone definition (simplified "base then explosive move"):
  Demand: small-bodied base candle, followed by a strong green candle that
          closes above the base high.  Zone = base low .. base body top.
  Supply: small-bodied base candle, followed by a strong red candle that
          closes below the base low.   Zone = base body bottom .. base high.
  Fresh : price has never CLOSED beyond the far edge of the zone since.

This is NOT GTF's proprietary logic, so results will differ from GTF Eye.
Educational use only; not investment advice.

Usage:
  python dz_sz_scanner.py                       # downloads Nifty 500 list from NSE
  python dz_sz_scanner.py --csv nifty500.csv    # use a local constituents CSV
  python dz_sz_scanner.py --timeframes Weekly Monthly --status in_zone
  python dz_sz_scanner.py --symbols MANKIND PNBHOUSING
"""
import argparse
import io
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

NIFTY500_URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"

# Bars to look back for a zone on each timeframe
TF_LOOKBACK = {
    "Daily": 120,
    "Weekly": 60,
    "Monthly": 36,
    "Quarterly": 20,
    "Half-Yearly": 12,
    "Yearly": 8,
}


# ───────────────────────── data helpers ─────────────────────────
def load_symbols(csv_path=None):
    """Return a list of NSE symbols (without the .NS suffix)."""
    if csv_path:
        df = pd.read_csv(csv_path)
    else:
        import requests

        r = requests.get(NIFTY500_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
    col = next((c for c in df.columns if c.strip().lower() == "symbol"), df.columns[0])
    return [str(s).strip() for s in df[col].dropna()]


def download_prices(symbols, start="2005-01-01", chunk=50):
    """Download daily OHLC in chunks. Returns {symbol: DataFrame}."""
    out = {}
    for i in range(0, len(symbols), chunk):
        batch = symbols[i : i + chunk]
        tickers = [s + ".NS" for s in batch]
        print(f"Downloading {i + 1}-{i + len(batch)} of {len(symbols)} ...", file=sys.stderr)
        data = yf.download(
            tickers,
            start=start,
            auto_adjust=True,
            group_by="ticker",
            progress=False,
            threads=True,
        )
        if data is None or data.empty:
            continue
        multi = isinstance(data.columns, pd.MultiIndex)
        for sym, tk in zip(batch, tickers):
            try:
                d = data[tk] if multi else data
                d = d[["Open", "High", "Low", "Close"]].dropna()
                if len(d) > 30:
                    out[sym] = d
            except KeyError:
                continue
    return out


def to_timeframe(df, tf):
    """Aggregate daily candles into the requested timeframe."""
    if tf == "Daily":
        return df
    idx = df.index
    if tf == "Weekly":
        key = idx.to_period("W-FRI")
    elif tf == "Monthly":
        key = idx.to_period("M")
    elif tf == "Quarterly":
        key = idx.to_period("Q")
    elif tf == "Half-Yearly":
        key = np.asarray(idx.year) * 2 + (np.asarray(idx.month) > 6).astype(int)
    elif tf == "Yearly":
        key = np.asarray(idx.year)
    else:
        raise ValueError(tf)
    return df.groupby(key).agg(
        Open=("Open", "first"), High=("High", "max"), Low=("Low", "min"), Close=("Close", "last")
    )


def atr_wilder(h, l, c, n=14):
    prev_c = np.concatenate(([np.nan], c[:-1]))
    tr = np.nanmax(np.vstack([h - l, np.abs(h - prev_c), np.abs(l - prev_c)]), axis=0)
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


# ───────────────────────── zone logic ─────────────────────────
def find_zones(df, lookback, body_pct, imp_mult, appr_pct):
    """Return a list of dicts for any demand/supply zone that is approaching or in zone."""
    if len(df) < 20:
        return []
    o, h, l, c = (df[k].to_numpy(dtype=float) for k in ("Open", "High", "Low", "Close"))
    n = len(c)
    last = n - 1
    a = atr_wilder(h, l, c)
    results = []
    max_i = min(lookback, n - 1)

    # ---- Demand ----
    for i in range(2, max_i + 1):
        b = last - i          # base candle
        im = b + 1            # impulse candle
        rng = h[b] - l[b]
        body = abs(c[b] - o[b])
        imp = c[im] - o[im]
        if rng > 0 and body <= body_pct / 100 * rng and c[im] > h[b] and imp >= imp_mult * a[b]:
            if (c[b + 2 :] < l[b]).any():      # not fresh
                continue
            top, bot = max(o[b], c[b]), l[b]
            in_zone = l[last] <= top and c[last] >= bot
            dist = (c[last] - top) / c[last] * 100
            approaching = (not in_zone) and c[last] > top and dist <= appr_pct
            if in_zone or approaching:
                results.append(
                    dict(
                        type="Demand",
                        status="IN ZONE" if in_zone else "Approaching",
                        zone_low=round(bot, 2),
                        zone_high=round(top, 2),
                        close=round(c[last], 2),
                        dist_pct=round(max(dist, 0), 2),
                        bars_old=i,
                    )
                )
            break  # only the most recent fresh zone

    # ---- Supply ----
    for i in range(2, max_i + 1):
        b = last - i
        im = b + 1
        rng = h[b] - l[b]
        body = abs(c[b] - o[b])
        imp = o[im] - c[im]
        if rng > 0 and body <= body_pct / 100 * rng and c[im] < l[b] and imp >= imp_mult * a[b]:
            if (c[b + 2 :] > h[b]).any():
                continue
            bot, top = min(o[b], c[b]), h[b]
            in_zone = h[last] >= bot and c[last] <= top
            dist = (bot - c[last]) / c[last] * 100
            approaching = (not in_zone) and c[last] < bot and dist <= appr_pct
            if in_zone or approaching:
                results.append(
                    dict(
                        type="Supply",
                        status="IN ZONE" if in_zone else "Approaching",
                        zone_low=round(bot, 2),
                        zone_high=round(top, 2),
                        close=round(c[last], 2),
                        dist_pct=round(max(dist, 0), 2),
                        bars_old=i,
                    )
                )
            break

    return results


# ───────────────────────── main ─────────────────────────
def main():
    p = argparse.ArgumentParser(description="Nifty 500 demand/supply zone scanner")
    p.add_argument("--csv", help="Local Nifty 500 constituents CSV (needs a 'Symbol' column)")
    p.add_argument("--symbols", nargs="+", help="Scan only these NSE symbols (e.g. MANKIND)")
    p.add_argument("--timeframes", nargs="+", default=list(TF_LOOKBACK), choices=list(TF_LOOKBACK))
    p.add_argument("--type", choices=["Demand", "Supply", "both"], default="both")
    p.add_argument("--status", choices=["in_zone", "approaching", "both"], default="both")
    p.add_argument("--body-pct", type=float, default=50, help="Max base body as %% of its range")
    p.add_argument("--impulse-atr", type=float, default=1.5, help="Min impulse body in ATRs")
    p.add_argument("--approach-pct", type=float, default=3.0, help="Approaching distance %%")
    p.add_argument("--outdir", default="results")
    args = p.parse_args()

    symbols = args.symbols or load_symbols(args.csv)
    prices = download_prices(symbols)
    print(f"Loaded price data for {len(prices)} of {len(symbols)} symbols.", file=sys.stderr)

    rows = []
    for sym, daily in prices.items():
        for tf in args.timeframes:
            try:
                tf_df = to_timeframe(daily, tf)
                for z in find_zones(tf_df, TF_LOOKBACK[tf], args.body_pct, args.impulse_atr, args.approach_pct):
                    rows.append({"symbol": sym, "timeframe": tf, **z})
            except Exception as e:  # keep scanning if one symbol fails
                print(f"{sym} {tf}: {e}", file=sys.stderr)

    res = pd.DataFrame(rows)
    if res.empty:
        print("No stocks matched.")
        return
    if args.type != "both":
        res = res[res["type"] == args.type]
    if args.status == "in_zone":
        res = res[res["status"] == "IN ZONE"]
    elif args.status == "approaching":
        res = res[res["status"] == "Approaching"]

    tf_rank = {k: i for i, k in enumerate(["Yearly", "Half-Yearly", "Quarterly", "Monthly", "Weekly", "Daily"])}
    res = res.assign(_r=res["timeframe"].map(tf_rank)).sort_values(["type", "_r", "status", "dist_pct"]).drop(columns="_r")

    outdir = Path(args.outdir)
    outdir.mkdir(exist_ok=True)
    path = outdir / f"zones_{date.today().isoformat()}.csv"
    res.to_csv(path, index=False)

    pd.set_option("display.width", 200, "display.max_rows", 500)
    for t in ("Demand", "Supply"):
        sub = res[res["type"] == t]
        if not sub.empty:
            print(f"\n=== {t.upper()} ZONES ({len(sub)}) ===")
            print(sub.drop(columns="type").to_string(index=False))
    print(f"\nSaved: {path}")


if __name__ == "__main__":
    main()
