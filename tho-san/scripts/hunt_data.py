#!/usr/bin/env python3
"""Binance USDⓈ-M public market data for a manual futures hunt (stdlib only, no API keys).

  python3 hunt_data.py scan [--top 40] [--leverage 5] [--workers 6]
      universe table (top perpetuals by volume) + /tmp/tho-san/market.json
  python3 hunt_data.py detail SYMBOL [SYMBOL ...]
      levels in ATRs, positioning, last daily candles, today's candle, recent 4h bars
  python3 hunt_data.py plan LONG|SHORT SYMBOL --stop X --target Y [--entry E] [--capital 1000]
      checks the risk rules against a fresh mark and ATR, then sizes the position; on PASS prints the TG: lines
      the report pastes and the DESK: log-call line, so no level is retyped

Indicators are textbook: EMA seeded with an SMA, Wilder RSI/ATR on closed candles, swing
points with two bars on each side over all 259 closed days plus the fresh 20/55-day extremes
(de-clustered by 0.25 ATR, including S/R flip levels).
Read-only public endpoints; nothing here can trade.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path

BASE = "https://fapi.binance.com"
OUT = Path("/tmp/tho-san/market.json")
# USD stablecoins, plus tokenized gold (gold's hours and ATR). Binance tags gold RWA like the real
# tokens MANTRA and CFG, so it is excluded by name.
EXCLUDED_BASES = {"USDC", "FDUSD", "TUSD", "USDP", "DAI", "BUSD", "USDE", "RLUSD", "USD1", "PAXG", "XAUT"}
PUMP_CHANGE_24H = 25.0  # percent: today's move is not in the closed-candle ATR yet
PUMP_FUNDING = 0.005  # per interval, near the exchange cap: one side is paying to stay in
TAKER_FEE_ROUNDTRIP = 0.001  # 0.05% entry + 0.05% exit on Binance USDⓈ-M
STOP_CLEARANCE_ATR = 0.25  # a stop nearer than this to a daily high/low goes with the wick that sweeps it


def get(path: str, **params):
    url = f"{BASE}{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "tho-san/1.1"})
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code not in (408, 418, 429) and exc.code < 500:
                raise
        except urllib.error.URLError:
            pass
        time.sleep(2 + 3 * attempt)
    raise RuntimeError(f"Binance unavailable after retries: {path}")


def ema(values, n):
    if len(values) < n:
        return None
    k, e = 2 / (n + 1), sum(values[:n]) / n
    for v in values[n:]:
        e = v * k + e * (1 - k)
    return e


def rsi(values, n=14):
    if len(values) <= n:
        return None
    diffs = [values[i] - values[i - 1] for i in range(1, len(values))]
    gain = sum(max(d, 0) for d in diffs[:n]) / n
    loss = sum(max(-d, 0) for d in diffs[:n]) / n
    for d in diffs[n:]:
        gain, loss = (gain * (n - 1) + max(d, 0)) / n, (loss * (n - 1) + max(-d, 0)) / n
    return 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)


def atr(highs, lows, closes, n=14):
    if len(closes) <= n:
        return None
    trs = [max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
           for i in range(1, len(closes))]
    a = sum(trs[:n]) / n
    for t in trs[n:]:
        a = (a * (n - 1) + t) / n
    return a


def swings(highs, lows, lookback=120):
    start = max(2, len(highs) - lookback)
    sh = [highs[i] for i in range(start, len(highs) - 2) if highs[i] == max(highs[i - 2:i + 3])]
    sl = [lows[i] for i in range(start, len(lows) - 2) if lows[i] == min(lows[i - 2:i + 3])]
    return sh, sl


def decluster(levels: list[float], min_gap: float) -> list[float]:
    """Keep distinct structural levels separated by at least min_gap."""
    out: list[float] = []
    for x in levels:
        if not out or abs(x - out[-1]) >= min_gap:
            out.append(x)
    return out


def pctile(series, value):
    return round(100 * sum(1 for v in series if v <= value) / len(series)) if series else None


def max_stop_fraction(leverage: int, mmr: float) -> float:
    """Half the distance to an isolated-margin liquidation, so a stop always fires first."""
    return (1 / leverage - mmr) / 2


def symbol_meta(info) -> dict[str, dict]:
    meta = {}
    for s in info["symbols"]:
        if (s.get("contractType") == "PERPETUAL" and s.get("quoteAsset") == "USDT"
                and s.get("status") == "TRADING" and s.get("underlyingType") == "COIN"
                and s.get("baseAsset") not in EXCLUDED_BASES):
            f = {x["filterType"]: x for x in s["filters"]}
            meta[s["symbol"]] = {
                "tick": f["PRICE_FILTER"]["tickSize"],
                "step": f["LOT_SIZE"]["stepSize"],
                "min_qty": f["LOT_SIZE"]["minQty"],
                "min_notional": f.get("MIN_NOTIONAL", {}).get("notional", "0"),
                "mmr": float(s.get("maintMarginPercent", "2.5")) / 100,
            }
    return meta


def features(sym: str, meta: dict, ticker: dict, premium: dict, btc_chg20: float | None) -> dict:
    d = get("/fapi/v1/klines", symbol=sym, interval="1d", limit=260)[:-1]  # closed days only
    h4 = get("/fapi/v1/klines", symbol=sym, interval="4h", limit=150)[:-1]
    h, lo, c = ([float(k[i]) for k in d] for i in (2, 3, 4))
    v = [float(k[7]) for k in d]
    c4 = [float(k[4]) for k in h4]
    mark = float(premium["markPrice"])
    a = atr(h, lo, c)
    sh, sl = swings(h, lo, lookback=len(h))  # every loaded day; plan's stop check stays at 120
    hi20, lo20 = max(h[-20:], default=None), min(lo[-20:], default=None)  # listing day has no closed candle
    hi55, lo55 = max(h[-55:], default=None), min(lo[-55:], default=None)
    # A swing needs two later days, so a fresh 20/55-day extreme is not one yet; without it a
    # breakout past every swing leaves that side empty.
    levels = sh + sl + [x for x in (hi20, lo20, hi55, lo55) if x is not None]
    min_gap = (a or 0) * 0.25
    # Include both swing highs and broken swing lows (S/R flip) sorted from mark outward
    res_candidates = sorted(x for x in levels if x > mark)
    sup_candidates = sorted((x for x in levels if x < mark), reverse=True)
    oi = [float(x["sumOpenInterestValue"]) for x in get(
        "/futures/data/openInterestHist", symbol=sym, period="1d", limit=30)]
    ls = [float(x["longShortRatio"]) for x in get(
        "/futures/data/globalLongShortAccountRatio", symbol=sym, period="1d", limit=30)]
    top = [float(x["longShortRatio"]) for x in get(
        "/futures/data/topLongShortPositionRatio", symbol=sym, period="1d", limit=30)]
    taker = [float(x["buySellRatio"]) for x in get(
        "/futures/data/takerlongshortRatio", symbol=sym, period="1d", limit=7)]
    fund = [float(x["fundingRate"]) for x in get("/fapi/v1/fundingRate", symbol=sym, limit=21)]
    chg20 = (c[-1] / c[-21] - 1) * 100 if len(c) > 21 else None
    return {
        "symbol": sym, "mark": mark,
        "qv_musd": round(float(ticker["quoteVolume"]) / 1e6),
        "chg24h": float(ticker["priceChangePercent"]),
        "chg7d": round((c[-1] / c[-8] - 1) * 100, 2) if len(c) > 8 else None,
        "chg20d": None if chg20 is None else round(chg20, 2),
        "rs20_vs_btc": None if chg20 is None or btc_chg20 is None else round(chg20 - btc_chg20, 2),
        "ema20": ema(c, 20), "ema50": ema(c, 50), "ema200": ema(c, 200),
        "ema20_4h": ema(c4, 20), "ema50_4h": ema(c4, 50),
        "rsi1d": rsi(c), "rsi4h": rsi(c4),
        "atr": a, "atr_pct": None if not a else a / mark * 100,
        "hi20": hi20, "lo20": lo20, "hi55": hi55, "lo55": lo55,
        "res": decluster(res_candidates, min_gap)[:3],
        "sup": decluster(sup_candidates, min_gap)[:3],
        "vol7_vs_30": round((sum(v[-7:]) / 7) / (sum(v[-30:]) / 30), 2) if len(v) >= 30 else None,
        "oi_chg1d": round((oi[-1] / oi[-2] - 1) * 100, 2) if len(oi) > 1 else None,
        "oi_chg7d": round((oi[-1] / oi[-8] - 1) * 100, 2) if len(oi) > 7 else None,
        "ls": ls[-1] if ls else None, "ls_pct30": pctile(ls, ls[-1]) if ls else None,
        "top": top[-1] if top else None, "top_pct30": pctile(top, top[-1]) if top else None,
        "taker1d": taker[-1] if taker else None,
        "taker3d": round(sum(taker[-3:]) / len(taker[-3:]), 3) if taker else None,
        "fund": float(premium["lastFundingRate"]),
        "fund_avg": round(sum(fund) / len(fund), 6) if fund else None,
        "last5_daily": [[datetime.fromtimestamp(k[0] / 1000, timezone.utc).strftime("%m-%d"),
                         float(k[1]), float(k[2]), float(k[3]), float(k[4])] for k in d[-5:]],
        **meta,
    }


def fmt(x, p=2):
    return "-" if x is None else f"{x:.{p}f}"


def above(price, level):
    return "-" if level is None else ("Y" if price > level else "n")


def _tag_row(row: dict, leverage: int) -> dict:
    limit = max_stop_fraction(leverage, row["mmr"]) * 100
    pump = abs(row["chg24h"]) >= PUMP_CHANGE_24H or abs(row["fund"]) >= PUMP_FUNDING
    row["flag"] = "PUMP" if pump else ("OK" if row["atr_pct"] and row["atr_pct"] <= limit else "ATR")
    return row


def scan(args) -> None:
    meta = symbol_meta(get("/fapi/v1/exchangeInfo"))
    tickers = {t["symbol"]: t for t in get("/fapi/v1/ticker/24hr") if t["symbol"] in meta}
    premium = {p["symbol"]: p for p in get("/fapi/v1/premiumIndex") if p["symbol"] in meta}
    universe = sorted((s for s, t in tickers.items() if float(t["quoteVolume"]) >= args.min_qv),
                      key=lambda s: -float(tickers[s]["quoteVolume"]))[:args.top]
    btc_row = _tag_row(features("BTCUSDT", meta["BTCUSDT"], tickers["BTCUSDT"], premium["BTCUSDT"], None),
                       args.leverage)
    btc_chg20 = btc_row["chg20d"]
    btc_row["rs20_vs_btc"] = None if btc_chg20 is None else 0.0  # BTC against itself

    others = [s for s in universe if s != "BTCUSDT"]

    def _fetch_one(sym: str) -> dict:
        row = features(sym, meta[sym], tickers[sym], premium[sym], btc_chg20)
        return _tag_row(row, args.leverage)

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        other_rows = list(pool.map(_fetch_one, others))

    rows = [btc_row] + other_rows
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(),
                               "leverage": args.leverage, "rows": rows}, indent=1))
    print(f"{len(rows)} contracts, x{args.leverage}: OK = ATR within the max stop, "
          f"ATR = too volatile, PUMP = today's move/funding not in the ATR. Saved {OUT}")
    print(f"{'sym':<14}{'flag':>5}{'mark':>11}{'24h':>6}{'7d':>7}{'20d':>7}{'rsBTC':>7}{'>e20':>5}"
          f"{'e20>50':>7}{'>e200':>6}{'rsi1d':>6}{'rsi4h':>6}{'atr%':>6}{'resATR':>7}{'supATR':>7}"
          f"{'oi7d':>7}{'ls%':>5}{'top%':>5}{'tkr3d':>6}{'fund%':>9}")
    for r in rows:
        a = r["atr"] or 0
        res = (r["res"][0] - r["mark"]) / a if r["res"] and a else None
        sup = (r["mark"] - r["sup"][0]) / a if r["sup"] and a else None
        trend = "-" if r["ema50"] is None else ("Y" if r["ema20"] > r["ema50"] else "n")
        print(f"{r['symbol']:<14}{r['flag']:>5}{r['mark']:>11.5g}{r['chg24h']:>6.1f}"
              f"{fmt(r['chg7d'], 1):>7}{fmt(r['chg20d'], 1):>7}{fmt(r['rs20_vs_btc'], 1):>7}"
              f"{above(r['mark'], r['ema20']):>5}{trend:>7}{above(r['mark'], r['ema200']):>6}"
              f"{fmt(r['rsi1d'], 0):>6}"
              f"{fmt(r['rsi4h'], 0):>6}{fmt(r['atr_pct'], 1):>6}{fmt(res, 1):>7}{fmt(sup, 1):>7}"
              f"{fmt(r['oi_chg7d'], 1):>7}{str(r['ls_pct30']):>5}{str(r['top_pct30']):>5}"
              f"{fmt(r['taker3d']):>6}{r['fund'] * 100:>8.4f}%")


def detail(args) -> None:
    meta = symbol_meta(get("/fapi/v1/exchangeInfo"))
    g = lambda x: "-" if x is None else f"{x:.6g}"  # noqa: E731
    for sym in (s.upper() for s in args.symbols):
        if sym not in meta:
            print(f"\n### {sym}: not a TRADING crypto USDT perpetual on Binance USDⓈ-M"
                  " (stablecoins and gold are left out)")
            continue
        ticker = get("/fapi/v1/ticker/24hr", symbol=sym)
        r = features(sym, meta[sym], ticker, get("/fapi/v1/premiumIndex", symbol=sym), None)
        a, m = r["atr"], r["mark"]
        print(f"\n### {sym} mark {g(m)} | ATR14d {g(a)} ({fmt(r['atr_pct'])}%) | EMA20 {g(r['ema20'])} "
              f"EMA50 {g(r['ema50'])} EMA200 {g(r['ema200'])} | 4h EMA20 {g(r['ema20_4h'])} "
              f"EMA50 {g(r['ema50_4h'])}")
        print(f"  RSI1d {fmt(r['rsi1d'], 1)} RSI4h {fmt(r['rsi4h'], 1)} | 20d {g(r['hi20'])}/{g(r['lo20'])}"
              f" 55d {g(r['hi55'])}/{g(r['lo55'])} | vol7/30 {r['vol7_vs_30']}")
        if a:
            print(f"  resistance {[g(x) for x in r['res']]} = {[round((x - m) / a, 2) for x in r['res']]} ATR"
                  f" | support {[g(x) for x in r['sup']]} = {[round((m - x) / a, 2) for x in r['sup']]} ATR")
        print(f"  OI 1d {r['oi_chg1d']}% 7d {r['oi_chg7d']}% | L/S {g(r['ls'])} (pct30 {r['ls_pct30']})"
              f" | top {g(r['top'])} (pct30 {r['top_pct30']}) | taker 1d {r['taker1d']} 3d {r['taker3d']}"
              f" | funding {r['fund'] * 100:.4f}% (avg last 21 {fmt((r['fund_avg'] or 0) * 100, 4)}%)")
        print(f"  tick {r['tick']} step {r['step']} min_notional {r['min_notional']} mmr {r['mmr']:.4f}")
        print("  last closed days (date o/h/l/c):", " ".join(
            f"{k[0]} {g(k[1])}/{g(k[2])}/{g(k[3])}/{g(k[4])}" for k in r["last5_daily"]))
        today = get("/fapi/v1/klines", symbol=sym, interval="1d", limit=1)[0]
        print(f"  today so far o {g(float(today[1]))} h {g(float(today[2]))} l {g(float(today[3]))}")
        bars = get("/fapi/v1/klines", symbol=sym, interval="4h", limit=7)
        for k in bars:
            buy = float(k[9]) / float(k[5]) * 100 if float(k[5]) else 0
            t = datetime.fromtimestamp(k[0] / 1000, timezone.utc).strftime("%m-%d %HZ")
            print(f"   4h {t} {g(float(k[1]))}/{g(float(k[2]))}/{g(float(k[3]))}/{g(float(k[4]))}"
                  f" taker-buy {buy:.0f}%{'  LIVE, not closed' if k is bars[-1] else ''}")


def plan(args) -> None:
    sym, side = args.symbol.upper(), args.side.upper()
    meta = symbol_meta(get("/fapi/v1/exchangeInfo")).get(sym)
    if meta is None:
        raise SystemExit(f"{sym} is not a TRADING crypto USDT perpetual on Binance USDⓈ-M"
                         " (stablecoins and gold are left out)")
    mark = float(get("/fapi/v1/premiumIndex", symbol=sym)["markPrice"])
    k1d = get("/fapi/v1/klines", symbol=sym, interval="1d", limit=260)
    h, lo, c = ([float(k[i]) for k in k1d[:-1]] for i in (2, 3, 4))  # closed days: same ATR as scan/detail
    a = atr(h, lo, c)
    if a is None:
        raise SystemExit(f"{sym}: fewer than 15 closed daily candles, so no ATR14 yet — skip this contract")
    entry, note = args.entry or mark, ""
    sign = 1 if side == "LONG" else -1
    if abs(entry / mark - 1) <= args.entry_band:
        order = "vào ngay"
        # A market order fills around the mark: size it from whichever of the two is worse.
        worse = max(entry, mark) if side == "LONG" else min(entry, mark)
        if worse != entry:
            note = f"vào ngay khớp quanh mark: tính từ {worse:.10g} thay vì entry {entry:.10g}"
            entry = worse
    elif (side == "LONG" and entry < mark) or (side == "SHORT" and entry > mark):
        order = "lệnh chờ (limit)"
    else:
        order = "lệnh chờ (stop)"
    risk_unit, reward_unit = (entry - args.stop) * sign, (args.target - entry) * sign
    limit = max_stop_fraction(args.leverage, meta["mmr"])
    if risk_unit <= 0 or reward_unit <= 0:
        raise SystemExit(f"{side}: stop and target are on the wrong side of entry {entry}")
    fee_unit = entry * TAKER_FEE_ROUNDTRIP
    net_rr = (reward_unit - fee_unit) / (risk_unit + fee_unit)
    sh, sl = swings(h, lo)
    # swings() needs two later bars to confirm a point, so the last two closed days and today go in as they are
    near = sorted({x for x in sh + sl + [float(k[i]) for k in k1d[-3:] for i in (2, 3)]
                   if abs(x - args.stop) < STOP_CLEARANCE_ATR * a})
    checks = {
        "stop >= 1 ATR": risk_unit >= a,
        f"stop <= {limit * 100:.2f}% (x{args.leverage} liquidation buffer)": risk_unit / entry <= limit,
        f"gross R:R >= {args.min_rr}": reward_unit / risk_unit >= args.min_rr,
        f"stop >= {STOP_CLEARANCE_ATR} ATR from daily highs/lows"
        + (f" (too close: {', '.join(f'{x:.6g}' for x in near)})" if near else ""): not near,
    }
    step, min_qty = Decimal(meta["step"]), Decimal(meta["min_qty"])
    raw = min(args.capital * args.risk / risk_unit, args.capital * args.margin_cap * args.leverage / entry)
    qty = (Decimal(str(raw)) / step).to_integral_value(rounding=ROUND_FLOOR) * step
    notional = float(qty) * entry
    checks[f"size >= exchange minimum (qty {meta['min_qty']}, notional {meta['min_notional']})"] = (
        qty >= min_qty and notional >= float(meta["min_notional"]))
    liq = entry * (1 - 1 / args.leverage + meta["mmr"]) if side == "LONG" else entry * (
        1 + 1 / args.leverage - meta["mmr"])
    print(f"{side} {sym} x{args.leverage} | mark {mark:.6g} | ATR14d {a:.6g} ({a / mark * 100:.2f}%)"
          f" | {order}")
    if note:
        print(note)
    print(f"entry {entry:.6g}  stop {args.stop:.6g} ({(args.stop / entry - 1) * 100:+.2f}%,"
          f" {risk_unit / a:.2f} ATR)  target {args.target:.6g} ({(args.target / entry - 1) * 100:+.2f}%)"
          f"  R:R {reward_unit / risk_unit:.2f} (net ~{net_rr:.2f})")
    print(f"size {qty.normalize():f} (step {meta['step']}) notional {notional:.2f} margin "
          f"{notional / args.leverage:.2f} risk {float(qty) * risk_unit:.2f} reward "
          f"{float(qty) * reward_unit:.2f} USDT | liquidation ~{liq:.6g}")
    for name, ok in checks.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    passed = all(checks.values())
    print("VERDICT:", "PASS" if passed else "FAIL — fix the levels or drop the trade")
    if passed:
        # Report-ready lines: the report pastes TG:, the desk runs DESK:, so no level gets retyped.
        kind = {"vào ngay": "Vào ngay", "lệnh chờ (limit)": "Limit", "lệnh chờ (stop)": "Stop"}[order]
        print(f"TG: {'🟢 LONG' if side == 'LONG' else '🔴 SHORT'} {sym} — {kind}")
        print(f"TG: • Vào: {entry:.10g} | Stop: {args.stop:.10g} ({(args.stop / entry - 1) * 100:+.2f}%,"
              f" {risk_unit / a:.2f} ATR) | TP: {args.target:.10g} ({(args.target / entry - 1) * 100:+.2f}%)"
              f" | R:R: {reward_unit / risk_unit:.2f}")
        print(f"TG: • Size: {qty.normalize():f} ({notional:.2f} USDT) | Ký quỹ: {notional / args.leverage:.2f}"
              f" | Rủi ro: {float(qty) * risk_unit:.2f} | Thanh lý: ~{liq:.6g}")
        if order != "lệnh chờ (stop)":  # the desk cannot grade stop entries yet
            print(f"DESK: ~/crypto-desk-rewrite/scripts/desk log-call {side} {sym}"
                  f" --entry {entry:.10g} --stop {args.stop:.10g} --target {args.target:.10g}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan")
    p.add_argument("--top", type=int, default=40)
    p.add_argument("--min-qv", type=float, default=20_000_000)
    p.add_argument("--leverage", type=int, default=5)
    p.add_argument("--workers", type=int, default=6)
    p = sub.add_parser("detail")
    p.add_argument("symbols", nargs="+")
    p = sub.add_parser("plan")
    p.add_argument("side", choices=["LONG", "SHORT", "long", "short"])
    p.add_argument("symbol")
    p.add_argument("--stop", type=float, required=True)
    p.add_argument("--target", type=float, required=True)
    p.add_argument("--entry", type=float)
    p.add_argument("--capital", type=float, default=1000)
    p.add_argument("--risk", type=float, default=0.01)
    p.add_argument("--leverage", type=int, default=5)
    p.add_argument("--margin-cap", type=float, default=0.20)
    p.add_argument("--min-rr", type=float, default=1.5)
    p.add_argument("--entry-band", type=float, default=0.005)
    args = parser.parse_args()
    {"scan": scan, "detail": detail, "plan": plan}[args.cmd](args)


if __name__ == "__main__":
    main()

