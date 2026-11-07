#!/usr/bin/env python3
"""Paper trader for the swing hunter: Connors RSI(2) + Turtle 20/10 on Binance US stock perps.

Paper only: nothing here places an order. Fills are taken afterwards from real Binance perp prices.
  python3 swing_paper.py scan [--capital 1000]   # process finished sessions, queue the next orders, report
  python3 swing_paper.py status                  # positions, queued orders, equity vs the benchmark
  python3 swing_paper.py test                    # self-check (no network)
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import statistics
import sys
import time
import urllib.request
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tho-san-co-phieu" / "scripts"))
from hunt_stock_data import KNOWN_ETFS, fetch_tv_fundamentals_batch, get_binance  # noqa: E402

HOME = Path.home() / ".local/share/tho-san-swing"   # not /tmp: WSL wipes /tmp on reboot
LEDGER = HOME / "ledger.json"
NY = ZoneInfo("America/New_York")
FEE, SLIP = 0.0005, 0.0002   # Binance taker and slippage, per side (as in the backtest)
SLOTS, WEIGHT = 10, 0.05     # per sleeve: 10 positions of 5% equity; two sleeves = the 50/50 mix
TURTLE_IN, TURTLE_OUT = 20, 10  # 11/2026 upgrade: 20/10 beat 55/20 in all four backtest periods (swing.py upgrade)
MIN_QV = 1_000_000           # median daily quote volume, USDT
NOT_STOCKS = {"UVXY"}        # ETP the TradingView lookup misses
YAHOO_TICKER = {"BRKB": "BRK-B"}
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) tho-san-swing"}


# ---------- indicators (same as the backtest) ----------

def sma(x: list, n: int) -> list:
    out, s = [None] * len(x), 0.0
    for i, v in enumerate(x):
        s += v - (x[i - n] if i >= n else 0.0)
        if i >= n - 1:
            out[i] = s / n
    return out


def rsi(c: list, n: int = 2) -> list:
    out = [None] * len(c)
    gains = [max(c[i] - c[i - 1], 0.0) for i in range(1, len(c))]
    losses = [max(c[i - 1] - c[i], 0.0) for i in range(1, len(c))]
    if len(gains) < n:
        return out
    ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n
    for i in range(n, len(c)):
        if i > n:
            ag, al = (ag * (n - 1) + gains[i - 1]) / n, (al * (n - 1) + losses[i - 1]) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def atr_wilder(h: list, l: list, c: list, n: int = 20) -> list:
    tr = [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))]
    out = [None] * len(c)
    if len(tr) < n:
        return out
    a = sum(tr[:n]) / n
    out[n - 1] = a
    for i in range(n, len(c)):
        a = (a * (n - 1) + tr[i]) / n
        out[i] = a
    return out


# ---------- the paper ledger ----------

def new_ledger(capital: float, start: date | None) -> dict:
    return dict(version=1, capital=capital, start=start.isoformat() if start else None, last_session=None, seq=0,
                positions=[], orders=[], watch={}, closed=[], history=[], bench={}, events=[])


def equity(L: dict) -> float:
    return L["history"][-1]["equity"] if L["history"] else L["capital"]


def find(L: dict, sleeve: str, sym: str) -> dict | None:
    return next((p for p in L["positions"] if p["sleeve"] == sleeve and p["sym"] == sym), None)


def open_position(L: dict, sleeve: str, sym: str, fill: float, when: date, **extra) -> dict:
    qty = WEIGHT * equity(L) / fill
    L["seq"] += 1
    p = dict(id=L["seq"], sleeve=sleeve, sym=sym, qty=qty, entry=fill, entry_date=when.isoformat(),
             fee_in=FEE * qty * fill, **extra)
    L["positions"].append(p)
    return p


def close_position(L: dict, p: dict, fill: float, when: date, reason: str, mk) -> dict:
    funding = mk.funding(p["sym"], date.fromisoformat(p["entry_date"]), when) * p["qty"] * p["entry"]
    fee_out = FEE * p["qty"] * fill
    pnl = p["qty"] * (fill - p["entry"]) - p["fee_in"] - fee_out - funding
    L["positions"].remove(p)
    c = dict(p, exit=fill, exit_date=when.isoformat(), fee_out=fee_out, funding=funding, pnl=pnl, reason=reason)
    L["closed"].append(c)
    return c


def turtle_session(L: dict, d: date, mk) -> list[str]:
    """Stop orders resting from the last close through session d's close: entries above the watch levels
    (the prior TURTLE_IN-session high), exits at each open position's stop. Earliest trigger first; SLOTS cap."""
    events, cand = [], []
    for sym, w in L["watch"].items():
        if find(L, "turtle", sym):
            continue
        hit = next(((t, max(w["level"], o)) for t, o, h, l, c in mk.bars15(sym, d) if h > w["level"]), None)
        if hit:
            cand.append((hit[0], "entry", sym, hit[1], w))
    for p in [p for p in L["positions"] if p["sleeve"] == "turtle"]:
        hit = next(((t, min(p["stop"], o)) for t, o, h, l, c in mk.bars15(p["sym"], d) if l <= p["stop"]), None)
        if hit:
            cand.append((hit[0], "exit", p["sym"], hit[1], p))
    for t, kind, sym, px, x in sorted(cand, key=lambda e: e[0]):
        if kind == "exit":
            if x in L["positions"]:
                c = close_position(L, x, px * (1 - SLIP), d, "turtle-exit", mk)
                events.append(f"BÁN {sym} (Turtle, chạm dừng/đáy {TURTLE_OUT} phiên) @ {c['exit']:.2f}: "
                              f"{c['pnl']:+.2f} USDT")
            continue
        if sum(1 for p in L["positions"] if p["sleeve"] == "turtle") >= SLOTS:
            events.append(f"Bỏ qua {sym} (Turtle phá đỉnh nhưng đã đủ {SLOTS} vị thế)")
            continue
        stop = px - 2 * x["N"]
        p = open_position(L, "turtle", sym, px * (1 + SLIP), d, N=x["N"], stop0=stop, stop=stop)
        events.append(f"MUA {sym} (Turtle, phá đỉnh {TURTLE_IN} phiên {x['level']:.2f}) @ {p['entry']:.2f}, "
                      f"dừng {stop:.2f}")
        later = next(((t2, min(stop, o)) for t2, o, h, l, c in mk.bars15(sym, d) if t2 > t and l <= stop), None)
        if later:
            c = close_position(L, p, later[1] * (1 - SLIP), d, "turtle-exit", mk)
            events.append(f"BÁN {sym} (Turtle, chạm dừng ngay trong phiên) @ {c['exit']:.2f}: {c['pnl']:+.2f} USDT")
    return events


def process_session(L: dict, d: date, mk, universe: list[str]) -> list[str]:
    """One finished session: fill the next-open orders, run the Turtle stops, then queue the orders for the
    next session from d's close and mark the book. A session already processed is skipped."""
    if L["last_session"] and d.isoformat() <= L["last_session"]:
        return []
    events = []
    for o in [o for o in L["orders"] if o["signal_date"] < d.isoformat()]:
        L["orders"].remove(o)
        px = mk.open_price(o["sym"], d)
        if px is None:
            events.append(f"Hủy lệnh {o['side']} {o['sym']}: Binance không có giá lúc mở cửa")
            continue
        if o["side"] == "buy":
            p = open_position(L, "rsi2", o["sym"], px * (1 + SLIP), d, rsi=o["rsi"])
            events.append(f"MUA {o['sym']} (RSI2 {o['rsi']:.1f}) @ {p['entry']:.2f} ≈ {p['qty'] * p['entry']:.0f} USDT")
        elif (p := find(L, "rsi2", o["sym"])) is not None:
            c = close_position(L, p, px * (1 - SLIP), d, "rsi2-exit", mk)
            events.append(f"BÁN {o['sym']} (RSI2, đóng cửa trên SMA5) @ {c['exit']:.2f}: {c['pnl']:+.2f} USDT")
    events += turtle_session(L, d, mk)
    marks, cands, watch = {}, [], {}
    for sym in sorted(set(universe) | {p["sym"] for p in L["positions"]}):
        bars = [b for b in (mk.daily(sym) or []) if b[0] <= d]
        if not bars or bars[-1][0] != d:
            continue
        h, l, c = [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars]
        marks[sym] = c[-1]
        if (p := find(L, "rsi2", sym)) and len(c) >= 5 and c[-1] > sum(c[-5:]) / 5 \
                and not any(o["sym"] == sym and o["side"] == "sell" for o in L["orders"]):
            L["orders"].append(dict(sleeve="rsi2", sym=sym, side="sell", signal_date=d.isoformat(), rsi=None))
        if (p := find(L, "turtle", sym)) and len(l) >= TURTLE_OUT:
            p["stop"] = max(p["stop0"], min(l[-TURTLE_OUT:]))
        if sym not in universe:
            continue
        if len(c) >= 201 and not find(L, "rsi2", sym) and not any(o["sym"] == sym for o in L["orders"]):
            r2 = rsi(c, 2)[-1]
            if c[-1] > sum(c[-200:]) / 200 and r2 is not None and r2 < 5:
                cands.append((r2, sym))
        if len(c) > max(TURTLE_IN, 20) and not find(L, "turtle", sym):
            N = atr_wilder(h, l, c, 20)[-1]
            if N:
                watch[sym] = dict(level=max(h[-TURTLE_IN:]), N=N)
    busy = sum(1 for p in L["positions"] if p["sleeve"] == "rsi2") + sum(1 for o in L["orders"] if o["side"] == "buy")
    for r2, sym in sorted(cands):
        if busy >= SLOTS:
            events.append(f"Bỏ qua {sym} (RSI2 {r2:.1f}: đã đủ {SLOTS} vị thế)")
            continue
        L["orders"].append(dict(sleeve="rsi2", sym=sym, side="buy", signal_date=d.isoformat(), rsi=r2))
        busy += 1
    L["watch"] = watch
    if not L["start"]:
        L["start"] = d.isoformat()
    if not L["bench"]:
        L["bench"] = {s: marks[s] for s in universe if s in marks}
    eq = L["capital"] + sum(c["pnl"] for c in L["closed"])
    eq += sum(p["qty"] * (marks.get(p["sym"], p["entry"]) - p["entry"]) - p["fee_in"] for p in L["positions"])
    bench = [marks[s] / v - 1 for s, v in L["bench"].items() if s in marks and v]
    L["history"].append(dict(date=d.isoformat(), equity=eq, bench=statistics.mean(bench) if bench else 0.0))
    L["last_session"] = d.isoformat()
    L["marks"] = marks
    return events


# ---------- live data: Yahoo daily bars for the signals, Binance perp prices for the fills ----------

def ny_ms(d: date, hh: int, mm: int) -> int:
    return int(datetime(d.year, d.month, d.day, hh, mm, tzinfo=NY).timestamp() * 1000)


def yahoo_daily(sym: str) -> list | None:
    """About 360 finished sessions of the underlying stock; cached for 3 hours."""
    f = HOME / "daily" / f"{sym}.json"
    if f.exists() and time.time() - f.stat().st_mtime < 3 * 3600:
        rows = json.loads(f.read_text())
    else:
        now = int(time.time())
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{YAHOO_TICKER.get(sym, sym)}"
               f"?period1={now - 520 * 86400}&period2={now}&interval=1d")
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60))["chart"]["result"][0]
        except Exception:
            return None
        q = r["indicators"]["quote"][0]
        rows = [[datetime.fromtimestamp(t, NY).date().isoformat(), o, h, l, c]
                for t, o, h, l, c in zip(r["timestamp"], q["open"], q["high"], q["low"], q["close"]) if None not in (o, h, l, c)]
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(rows))
        time.sleep(1.0)
    bars = [(date.fromisoformat(r[0]), r[1], r[2], r[3], r[4]) for r in rows]
    now_ny = datetime.now(NY)
    if bars and bars[-1][0] == now_ny.date() and (now_ny.hour, now_ny.minute) < (16, 30):
        bars = bars[:-1]  # today's session is still running: not a finished bar
    return bars


class LiveMarket:
    def __init__(self):
        self.days: dict = {}
        self.k15: dict = {}

    def daily(self, sym):
        if sym not in self.days:
            self.days[sym] = yahoo_daily(sym)
        return self.days[sym]

    def open_price(self, sym, d):
        k = get_binance("/fapi/v1/klines", symbol=f"{sym}USDT", interval="15m", startTime=ny_ms(d, 9, 30), limit=1)
        return float(k[0][1]) if k and k[0][0] == ny_ms(d, 9, 30) else None

    def bars15(self, sym, d):
        """Perp 15m bars from the previous session's close to d's close: stop orders rest 24/7."""
        if (sym, d) not in self.k15:
            prev = [b[0] for b in (self.daily(sym) or []) if b[0] < d]
            s, end, out = ny_ms(prev[-1] if prev else d - timedelta(days=1), 16, 0), ny_ms(d, 16, 0), []
            while s < end:
                k = get_binance("/fapi/v1/klines", symbol=f"{sym}USDT", interval="15m", startTime=s, endTime=end - 1, limit=1500)
                out += [(x[0], float(x[1]), float(x[2]), float(x[3]), float(x[4])) for x in k]
                if len(k) < 1500:
                    break
                s = k[-1][0] + 1
            self.k15[(sym, d)] = out
        return self.k15[(sym, d)]

    def funding(self, sym, start, end):
        k = get_binance("/fapi/v1/fundingRate", symbol=f"{sym}USDT", startTime=ny_ms(start, 9, 30),
                        endTime=ny_ms(end, 16, 0), limit=1000)
        return sum(float(x["fundingRate"]) for x in k)


def universe() -> list[str]:
    """US stock perps on Binance (EQUITY = US-listed incl. ADRs), no ETFs, >= 1M USDT median daily volume."""
    f = HOME / "universe.json"
    if f.exists() and time.time() - f.stat().st_mtime < 20 * 3600:
        return json.loads(f.read_text())
    info = get_binance("/fapi/v1/exchangeInfo")["symbols"]
    bases = [s["baseAsset"] for s in info if s.get("contractType") == "TRADIFI_PERPETUAL"
             and s.get("underlyingType") == "EQUITY" and s.get("quoteAsset") == "USDT" and s.get("status") == "TRADING"
             and s["baseAsset"] not in KNOWN_ETFS and s["baseAsset"] not in NOT_STOCKS]
    tv = fetch_tv_fundamentals_batch(bases)
    keep = []
    for b in bases:
        r = tv.get(b) or {}
        if r.get("is_etf") or r.get("subtype") == "preferred":
            continue
        k = get_binance("/fapi/v1/klines", symbol=f"{b}USDT", interval="1d", limit=21)[:-1]
        if len(k) >= 15 and statistics.median(float(x[7]) for x in k) >= MIN_QV:
            keep.append(b)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(sorted(keep)))
    return sorted(keep)


# ---------- commands ----------

def vn(d: str | None) -> str:
    return date.fromisoformat(d).strftime("%d/%m/%Y") if d else "?"


def report(L: dict, events: list[str], new_sessions: int | None) -> None:
    eq, h = equity(L), (L["history"][-1] if L["history"] else {})
    n = {s: sum(1 for p in L["positions"] if p["sleeve"] == s) for s in ("rsi2", "turtle")}
    marks = L.get("marks", {})
    head = (f"Vốn giấy {eq:.2f} USDT ({eq / L['capital'] - 1:+.2%} từ {vn(L['start'])}); giữ đều các mã cùng kỳ "
            f"{h.get('bench', 0.0):+.2%}. Vị thế mở: RSI2 {n['rsi2']}/{SLOTS}, Turtle {n['turtle']}/{SLOTS}.")
    orders = [f"MUA {o['sym']} (RSI2 {o['rsi']:.1f}), khoảng {WEIGHT:.0%} vốn" if o["side"] == "buy"
              else f"BÁN {o['sym']} (RSI2: đóng cửa trên SMA5)" for o in L["orders"]]
    near = sorted(((w["level"] - marks[s]) / w["N"], s, w) for s, w in L["watch"].items() if s in marks)[:5]
    lines = [f"# Thợ săn Swing (sổ lệnh giấy), phiên {vn(L['last_session'])}", "", head, ""]
    if new_sessions == 0:
        lines += ["Chưa có phiên mới đóng cửa kể từ lần quét trước; sổ giữ nguyên.", ""]
    lines += ["## Vừa xảy ra", *([f"- {e}" for e in events] or ["- Không có lệnh khớp hay thoát."]), "",
              "## Lệnh cho phiên tới (giá mở cửa 09:30 New York)", *([f"- {o}" for o in orders] or ["- Không có."]), "",
              f"## Turtle: lệnh dừng mua đặt sẵn trên {len(L['watch'])} mã (mua khi vượt đỉnh {TURTLE_IN} phiên)",
              *[f"- {s}: đỉnh {w['level']:.2f}, giá đóng cửa {marks[s]:.2f}, còn cách {dist:.1f}N" for dist, s, w in near], "",
              "## Vị thế đang mở", "", "| Mã | Nhóm | Ngày vào | Giá vào | Đóng cửa | Lãi/lỗ tạm (USDT) | Dừng |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for p in sorted(L["positions"], key=lambda p: (p["sleeve"], p["sym"])):
        m = marks.get(p["sym"], p["entry"])
        lines.append(f"| {p['sym']} | {'RSI2' if p['sleeve'] == 'rsi2' else 'Turtle'} | {vn(p['entry_date'])} | "
                     f"{p['entry']:.2f} | {m:.2f} | {p['qty'] * (m - p['entry']) - p['fee_in']:+.2f} | "
                     f"{p['stop']:.2f} |" if p["sleeve"] == "turtle" else
                     f"| {p['sym']} | RSI2 | {vn(p['entry_date'])} | {p['entry']:.2f} | {m:.2f} | "
                     f"{p['qty'] * (m - p['entry']) - p['fee_in']:+.2f} | đóng cửa > SMA5 |")
    closed = L["closed"]
    if closed:
        wins = sum(c["pnl"] > 0 for c in closed)
        lines += ["", f"Đã đóng {len(closed)} lệnh, thắng {wins} ({wins / len(closed):.0%}), tổng "
                      f"{sum(c['pnl'] for c in closed):+.2f} USDT (đã trừ phí và funding)."]
    lines += ["", "Sổ lệnh giấy: không có lệnh thật nào được đặt. Tham khảo, không phải lời khuyên đầu tư."]
    tg = [f"📒 Thợ săn Swing (giấy), phiên {vn(L['last_session'])}", head, *[f"• {e}" for e in events[:8]],
          "Phiên tới: " + ("; ".join(orders) if orders else "không có lệnh RSI2"),
          f"Turtle canh {len(L['watch'])} mã; gần nhất: " + ", ".join(f"{s} ({dist:.1f}N)" for dist, s, w in near[:3]),
          "Giấy, không phải lệnh thật."]
    text = "\n".join(tg)
    if len(text) > 1800:
        text = text[:1790] + "…"
    stamp = (L["last_session"] or "chua-quet").replace("-", "")
    (HOME / f"report-{stamp}.md").write_text("\n".join(lines) + "\n")
    (HOME / f"tg-{stamp}.md").write_text(text + "\n")
    print("\n".join(lines))
    print(f"\nTG_FILE: {HOME / f'tg-{stamp}.md'} ({len(text)} ký tự)")


def scan(capital: float) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    L = json.loads(LEDGER.read_text()) if LEDGER.exists() else new_ledger(capital, None)
    mk, uni = LiveMarket(), universe()
    sessions = [b[0] for b in (mk.daily("SPY") or [])]
    todo = [d for d in sessions if not L["last_session"] or d.isoformat() > L["last_session"]]
    if not L["last_session"]:
        todo = todo[-1:]  # first run: start from the latest finished session
    events = []
    for d in todo:
        events += [f"{d:%d/%m}: {e}" for e in process_session(L, d, mk, uni)]
    L["events"] = (L.get("events", []) + events)[-300:]
    LEDGER.write_text(json.dumps(L, indent=1))
    report(L, events, len(todo))


def status() -> None:
    if not LEDGER.exists():
        print("Chưa có sổ lệnh giấy: chạy `scan` trước.")
        return
    report(json.loads(LEDGER.read_text()), [], None)


class FakeMarket:
    """Synthetic market for the self-check: sessions are consecutive days, one 15m bar per session."""

    def __init__(self, days: dict):
        self.days = days  # sym -> list of (date, o, h, l, c)

    def daily(self, sym):
        return self.days.get(sym)

    def open_price(self, sym, d):
        return next((o for dd, o, h, l, c in self.days[sym] if dd == d), None)

    def bars15(self, sym, d):
        return [(1, o, h, l, c) for dd, o, h, l, c in self.days[sym] if dd == d]

    def funding(self, sym, start, end):
        return 0.0001  # 0.01% of notional over any holding


def selftest() -> None:
    from datetime import date, timedelta
    d0 = date(2026, 1, 1)
    up = [(d0 + timedelta(i), 100 + 0.5 * i, 100.3 + 0.5 * i, 99.7 + 0.5 * i, 100 + 0.5 * i) for i in range(260)]
    last = up[-1][4]
    dip = [(up[-1][0] + timedelta(k + 1), c + 0.1, c + 0.3, c - 0.3, c) for k, c in enumerate([last - 3, last - 6, last - 9])]
    rebound = [(dip[-1][0] + timedelta(1), last - 8.5, last + 0.5, last - 9, last), (dip[-1][0] + timedelta(2), last + 0.2, last + 1, last, last + 0.5)]
    mk = FakeMarket({"AAA": up + dip + rebound})
    L = new_ledger(1000.0, dip[-1][0])
    process_session(L, dip[-1][0], mk, ["AAA"])                     # RSI2 < 5 after 3 down days -> queue a buy
    assert [o["side"] for o in L["orders"]] == ["buy"], L["orders"]
    process_session(L, dip[-1][0], mk, ["AAA"])                     # same session again: nothing new
    assert len(L["orders"]) == 1 and L["last_session"] == dip[-1][0].isoformat(), L["orders"]
    process_session(L, rebound[0][0], mk, ["AAA"])                  # filled at that open; close > SMA5 -> queue sell
    pos = [p for p in L["positions"] if p["sleeve"] == "rsi2"]
    assert len(pos) == 1 and abs(pos[0]["entry"] - (last - 8.5) * (1 + SLIP)) < 1e-9, pos
    assert abs(pos[0]["qty"] * pos[0]["entry"] - WEIGHT * 1000) < 1e-6, pos   # 5% of equity
    assert [o["side"] for o in L["orders"]] == ["sell"], L["orders"]
    process_session(L, rebound[1][0], mk, ["AAA"])                  # sold at the next open
    closed = [c for c in L["closed"] if c["sleeve"] == "rsi2"]
    assert len(closed) == 1 and closed[0]["reason"] == "rsi2-exit", closed
    gross = closed[0]["qty"] * (closed[0]["exit"] - closed[0]["entry"])
    costs = FEE * closed[0]["qty"] * (closed[0]["entry"] + closed[0]["exit"]) + 0.0001 * closed[0]["qty"] * closed[0]["entry"]
    assert abs(closed[0]["pnl"] - (gross - costs)) < 1e-9, closed
    # Turtle: a break of the prior 20-session high fills at max(level, open); slots cap at SLOTS
    flat = [(d0 + timedelta(i), 100, 110 if i == 30 else 101, 95 if i == 45 else 99, 100) for i in range(60)]
    # the 110 high is inside 55 sessions but not 20; the 95 low is inside 20 sessions but not 10
    brk = [(d0 + timedelta(60), 100.5, 103, 100, 102)]
    drop = [(d0 + timedelta(61), 99.5, 100, 97, 98)]
    syms = [f"S{k}" for k in range(SLOTS + 2)]
    mk2 = FakeMarket({s: flat + brk + drop for s in syms})
    T = new_ledger(1000.0, d0 + timedelta(59))
    process_session(T, d0 + timedelta(59), mk2, syms)               # watch level = prior 20-session high, 101
    assert all(w["level"] == 101 for w in T["watch"].values()), T["watch"]
    process_session(T, d0 + timedelta(60), mk2, syms)               # every symbol breaks out, only SLOTS fill
    tpos = [p for p in T["positions"] if p["sleeve"] == "turtle"]
    assert len(tpos) == SLOTS and all(abs(p["entry"] - 101 * (1 + SLIP)) < 1e-9 for p in tpos), tpos
    assert all(p["stop"] == 99 for p in tpos), tpos                  # max(entry - 2N ≈ 96.6, 10-session low 99)
    process_session(T, d0 + timedelta(61), mk2, syms)               # low 97 breaks the stop at 99
    tout = [c for c in T["closed"] if c["sleeve"] == "turtle"]
    assert len(tout) == SLOTS and all(abs(c["exit"] - 99 * (1 - SLIP)) < 1e-9 for c in tout), tout
    print("swing_paper selftest ok")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["scan", "status", "test"])
    ap.add_argument("--capital", type=float, default=1000.0, help="paper capital in USDT for a new ledger")
    a = ap.parse_args()
    {"scan": lambda: scan(a.capital), "status": status, "test": selftest}[a.cmd]()
