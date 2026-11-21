"""Offline checks for hunt_stock_data.py (network calls faked).

Run: PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider ~/.gemini/config/skills/tho-san-co-phieu/scripts
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import urllib.error

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hunt_stock_data as h  # noqa: E402

MONDAY = datetime(2026, 8, 3, tzinfo=timezone.utc)


def _bar(day: datetime, high: float, low: float) -> list:
    t = int(day.timestamp() * 1000)
    return [t, "100", str(high), str(low), "100", "1000", t + 86_399_999, "100000", 10, "500", "50000", "0"]


def _daily_bars(days: int) -> list:
    """Weekdays swing 98-102 (TR 4); weekends barely move 99.5-100.5 (TR 1), like stock perps on Binance."""
    bars = []
    for i in range(days + 1):  # the extra last bar is the still-forming candle the script drops
        day = MONDAY + timedelta(days=i)
        bars.append(_bar(day, 102, 98) if day.weekday() < 5 else _bar(day, 100.5, 99.5))
    return bars


def _okx_stock(base: str) -> dict:
    """An OKX /api/v5/public/instruments SWAP row for a stock (instCategory 3); one contract is 0.1 share here."""
    return {"instType": "SWAP", "instId": f"{base}-USDT-SWAP", "instFamily": f"{base}-USDT", "uly": f"{base}-USDT",
            "settleCcy": "USDT", "ctType": "linear", "ctValCcy": base, "ctMult": "1", "state": "live",
            "instCategory": "3", "ctVal": "0.1", "lotSz": "0.01", "minSz": "0.01", "tickSz": "0.01",
            "lever": "20", "ruleType": "normal"}


def _fake_okx(monkeypatch, insts: list[dict]) -> None:
    """OKX at Binance's price with $100M a day, and a flat 100-day crowd."""
    def rows(*values: str) -> list[list[str]]:
        return [[str(1_794_672_000_000 - i * 86_400_000), *values] for i in range(100)]

    crowd = {
        "/api/v5/rubik/stat/contracts/open-interest-history": rows("10", "1", "100"),
        "/api/v5/rubik/stat/contracts/long-short-account-ratio-contract": rows("1.5"),
        "/api/v5/rubik/stat/contracts/long-short-position-ratio-contract-top-trader": rows("1.2"),
        "/api/v5/rubik/stat/taker-volume-contract": rows("100", "100"),
    }

    def get(path: str, **params):
        if path == "/api/v5/public/instruments":
            return insts
        if path == "/api/v5/public/mark-price":
            return [{"instType": "SWAP", "instId": i["instId"], "markPx": "100", "ts": "1"} for i in insts]
        if path == "/api/v5/market/tickers":
            return [{"instType": "SWAP", "instId": i["instId"], "last": "100", "volCcy24h": "1000000"} for i in insts]
        if path == "/api/v5/public/funding-rate":
            return [{"instId": params["instId"], "fundingRate": "0.0001"}]
        if path == "/api/v5/public/funding-rate-history":
            return [{"instId": params["instId"], "fundingRate": "0.0001"}] * params["limit"]
        return crowd[path]

    monkeypatch.setattr(h.okx_gate, "get", get)


def _stock(base: str) -> dict:
    return {
        "symbol": f"{base}USDT", "baseAsset": base, "quoteAsset": "USDT", "status": "TRADING",
        "contractType": "TRADIFI_PERPETUAL", "underlyingType": "EQUITY",
        "maintMarginPercent": "2.5000", "requiredMarginPercent": "5.0000",
        "filters": [
            {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
            {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
            {"filterType": "MIN_NOTIONAL", "notional": "5"},
        ],
    }


def _fake_exchange(monkeypatch, bars: list, tv_info: dict | None = None, bases: tuple[str, ...] = ("TEST",)) -> None:
    """Binance with these stock contracts on the same candles; OKX lists every one (tests call _fake_okx to change that)."""
    per_symbol = {
        "/fapi/v1/premiumIndex": lambda s: {"symbol": s, "markPrice": "100", "indexPrice": "100",
                                            "lastFundingRate": "0.0001"},
        "/fapi/v1/ticker/24hr": lambda s: {"symbol": s, "quoteVolume": "50000000", "priceChangePercent": "0.5"},
    }
    responses = {
        "/fapi/v1/exchangeInfo": {"symbols": [_stock(b) for b in bases]},
        "/fapi/v1/klines": bars,  # served for 1d and 4h alike; only the daily maths is asserted
        "/futures/data/openInterestHist": [{"sumOpenInterestValue": "1000000"}] * 30,
        "/futures/data/globalLongShortAccountRatio": [{"longShortRatio": "1.5"}] * 30,
        "/futures/data/topLongShortPositionRatio": [{"longShortRatio": "1.2"}] * 30,
        "/futures/data/takerlongshortRatio": [{"buySellRatio": "1.0"}] * 7,
        "/fapi/v1/fundingRate": [{"fundingRate": "0.0001"}] * 21,
    }
    def get_binance(path: str, **params):
        if path in per_symbol:  # one row for a symbol, every row without one
            row = per_symbol[path]
            return row(params["symbol"]) if "symbol" in params else [row(f"{b}USDT") for b in bases]
        return responses[path]

    monkeypatch.setattr(h, "get_binance", get_binance)
    monkeypatch.setattr(h, "fetch_tv_fundamentals_batch", lambda bases: {"TEST": tv_info} if tv_info else {})
    monkeypatch.setattr(h, "load_sec_tickers", lambda: {})
    _fake_okx(monkeypatch, [_okx_stock(b) for b in bases])


def _plan(monkeypatch, capsys, *argv: str, side: str = "LONG", sym: str = "TEST") -> str:
    monkeypatch.setattr(sys, "argv", ["hunt_stock_data.py", "plan", side, sym, *argv])
    h.main()
    return capsys.readouterr().out


def _check(out: str, needle: str) -> str | None:
    """PASS/FAIL of the first `plan` check line naming `needle`, None if there is no such check."""
    return next((line.split()[0] for line in out.splitlines()
                 if line.split()[:1] in (["PASS"], ["FAIL"]) and needle in line), None)


def test_plan_refuses_contract_too_new_for_atr14(monkeypatch, capsys):
    _fake_exchange(monkeypatch, _daily_bars(4))
    with pytest.raises(SystemExit, match="ATR14"):
        _plan(monkeypatch, capsys, "--stop", "96", "--target", "108")


def test_weekend_bars_do_not_shrink_the_atr_stop_floor(monkeypatch, capsys):
    # Weekday ATR is 4; counting the near-flat weekend bars drags it to ~3.3 and lets a 3.5 stop pass.
    _fake_exchange(monkeypatch, _daily_bars(68))
    out = _plan(monkeypatch, capsys, "--stop", "96.5", "--target", "108")
    assert _check(out, "stop >= 1 ATR") == "FAIL"


def test_scan_features_measure_atr_on_weekday_bars(monkeypatch):
    _fake_exchange(monkeypatch, _daily_bars(68))
    meta = h.equity_symbol_meta(h.get_binance("/fapi/v1/exchangeInfo"))["TESTUSDT"]
    ticker = {"quoteVolume": "50000000", "priceChangePercent": "0.5"}
    row = h.features("TESTUSDT", meta, ticker, h.get_binance("/fapi/v1/premiumIndex", symbol="TESTUSDT"), None, {})
    assert row["atr"] == pytest.approx(4.0)


EARNINGS_IN_5_DAYS = {"type": "stock", "days_to_earnings": 5, "next_earnings_date": "2026-10-15"}


def test_plan_fails_when_earnings_fall_inside_holding_window(monkeypatch, capsys):
    _fake_exchange(monkeypatch, _daily_bars(68), EARNINGS_IN_5_DAYS)
    out = _plan(monkeypatch, capsys, "--stop", "95", "--target", "110")
    assert _check(out, "earnings") == "FAIL"
    assert "VERDICT: FAIL" in out


def test_plan_passes_when_holding_window_ends_before_earnings(monkeypatch, capsys):
    _fake_exchange(monkeypatch, _daily_bars(68), EARNINGS_IN_5_DAYS)
    out = _plan(monkeypatch, capsys, "--stop", "95", "--target", "110", "--horizon-days", "3")
    assert _check(out, "earnings") == "PASS"
    assert "VERDICT: PASS" in out


# Weekday highs 102 and lows 98 are all swing points; _daily_bars(68) ends on Fri 9 Oct closed + Sat 10 Oct forming.
@pytest.mark.parametrize("friday_high, entry, stop, verdict", [
    (None, "102.5", "97.5", "FAIL"),  # 0.5 under the 98 swing lows: the wick that takes 98 takes it
    (None, "102.5", "96.5", "PASS"),  # 1.5 (0.37 ATR) under every low
    ("104", "109", "104.5", "FAIL"),  # 0.5 above Friday's 104 high, too recent to be a swing point
])
def test_plan_fails_a_stop_hugging_a_daily_high_or_low(monkeypatch, capsys, friday_high, entry, stop, verdict):
    bars = _daily_bars(68)
    if friday_high:
        bars[-2][2] = friday_high
    _fake_exchange(monkeypatch, bars)
    out = _plan(monkeypatch, capsys, "--entry", entry, "--stop", stop, "--target", "120")
    assert f"VERDICT: {verdict}" in out
    assert ("TG:" in out) == (verdict == "PASS")  # nothing to copy from a failed plan


def test_plan_sizes_a_market_entry_from_the_worse_of_entry_and_mark(monkeypatch, capsys):
    _fake_exchange(monkeypatch, _daily_bars(68))
    out = _plan(monkeypatch, capsys, "--entry", "99.8", "--stop", "95", "--target", "110")
    assert "entry 100  stop 95 (-5.00%" in out  # a market order fills near the 100 mark, not at 99.8


def test_plan_prints_the_lines_the_report_copies(monkeypatch, capsys):
    _fake_exchange(monkeypatch, _daily_bars(68))
    out = _plan(monkeypatch, capsys, "--stop", "95", "--target", "110")
    lines = [line for line in out.splitlines() if line.startswith("TG:")]
    assert lines[0] == "TG: 🟢 LONG TESTUSDT [US] (TEST) — Vào ngay"
    assert lines[1].startswith("TG: • Vào: 100 | Stop: 95 (-5.00%, ")
    assert lines[1].endswith(" | Chốt 1/2: 105")  # +1R, where half the position comes off
    assert lines[2].startswith("TG: • Size: ")
    assert lines[3] == "TG: • Cơ bản & KQKD: Rev YoY -, P/E - | KQKD: -"
    assert "DESK:" not in out  # stock calls are not logged on the crypto desk


def test_news_gives_a_us_ticker_direct_links_and_its_8k_filings(monkeypatch, capsys):
    today = datetime.now(timezone.utc).date()
    recent = {
        "form": ["8-K", "10-Q", "8-K"],
        "filingDate": [str(today - timedelta(days=d)) for d in (2, 5, 60)],
        "items": ["2.02,9.01", "", "5.02"],
        "accessionNumber": ["0000123-26-000001", "0000123-26-000002", "0000123-26-000003"],
        "primaryDocument": ["q3.htm", "10q.htm", "old.htm"],
    }
    yahoo = [{"published": "Fri, 30 Oct 2026 14:56:49 +0000", "source": "247wallst.com",
              "title": "Test Corp beats", "link": "https://247wallst.com/test-corp-beats/"}]
    monkeypatch.setattr(h, "load_sec_tickers", lambda: {"TEST": (123, "Test Corp")})
    monkeypatch.setattr(h, "fetch_tv_fundamentals_batch", lambda bases: {})
    monkeypatch.setattr(h, "_fetch_google_rss", lambda query, limit=8: [])
    monkeypatch.setattr(h, "_fetch_yahoo_rss", lambda ticker, limit=8: yahoo if ticker == "TEST" else [])
    monkeypatch.setattr(h, "get_sec_json", lambda url: {"filings": {"recent": recent}})
    monkeypatch.setattr(sys, "argv", ["hunt_stock_data.py", "news", "TEST"])
    h.main()
    out = capsys.readouterr().out
    assert "https://247wallst.com/test-corp-beats/" in out  # the article itself, not a news.google.com redirect
    assert "8-K ! 2.02 KQKD" in out
    assert "https://www.sec.gov/Archives/edgar/data/123/000012326000001/q3.htm" in out
    assert "10q.htm" not in out and "old.htm" not in out  # not an 8-K, and older than 30 days


def test_detail_marks_only_the_forming_4h_bar_live(monkeypatch, capsys):
    # An unmarked forming bar was read as a closed 4h rejection in the crypto hunt of 25/10 12:57.
    _fake_exchange(monkeypatch, _daily_bars(68))
    monkeypatch.setattr(sys, "argv", ["hunt_stock_data.py", "detail", "TEST"])
    h.main()
    bars = [line for line in capsys.readouterr().out.splitlines() if line.lstrip().startswith("4h ")]
    assert "LIVE" in bars[-1]
    assert not any("LIVE" in bar for bar in bars[:-1])


@pytest.mark.parametrize("base, underlying, tv_type, want", [
    ("ZHONGJI", "HK_EQUITY", "stock", "HK"),  # Hong Kong H-share, not the Shenzhen A-share
    ("GIGADEV", "HK_EQUITY", "stock", "HK"),
    ("SPCX", "EQUITY", "stock", "US"),  # SpaceX is listed on Nasdaq
    ("SKHY", "EQUITY", "dr", "ADR"),  # SK hynix ADR trades US hours
    ("UNITREE", "CN_EQUITY", None, "CN"),
    ("OPENAI", "PREMARKET", None, "PRE"),
    ("NVDA", "EQUITY", "stock", "US"),
])
def test_market_tag_follows_binance_underlying_type(base, underlying, tv_type, want):
    tv_info = {"type": tv_type} if tv_type else None
    assert h.build_fundamental_summary(base, underlying, tv_info)["market"] == want


def test_news_marks_empty_sections(monkeypatch, capsys):
    monkeypatch.setattr(h, "load_sec_tickers", lambda: {})
    monkeypatch.setattr(h, "_fetch_google_rss", lambda query, limit=8: [])
    monkeypatch.setattr(sys, "argv", ["hunt_stock_data.py", "news"])
    h.main()
    out = capsys.readouterr().out
    assert out.count("=== NEWS:") >= 1
    assert out.count("(no results)") == out.count("=== NEWS:")


# --- Grade ceiling: plan caps a setup at B on facts the report must not talk past ---

@pytest.fixture(autouse=True)
def _no_macro_events(monkeypatch):
    """Keep the real calendar and clock out of tests that set no events of their own."""
    monkeypatch.setattr(h, "load_macro_events", lambda: [], raising=False)


def _first_tg(out: str) -> str:
    return next(line for line in out.splitlines() if line.startswith("TG:"))


def _grade(out: str) -> str:
    return next(line for line in out.splitlines() if line.startswith("Hạng tối đa:"))


def test_plan_caps_at_b_a_stop_hugging_a_recent_low_that_is_no_swing_point(monkeypatch, capsys):
    # AVGO 13/11: the stop 314.5 sat 0.15 ATR over the 10/11 low 311.7, which lower lows next to it kept
    # out of the swing check, so plan passed it and the report called it clean.
    bars = _daily_bars(68)
    bars[-6][3] = "94"  # Mon 5 Oct: a swing low, 1.3 under the stop (ATR ~4.4)
    bars[-5][3] = "95"  # Tue 6 Oct: no swing point, 94 is next to it; 0.3 under the stop
    _fake_exchange(monkeypatch, bars)
    out = _plan(monkeypatch, capsys, "--stop", "95.3", "--target", "110")
    assert "VERDICT: PASS" in out  # a warning, not a veto
    assert "(near: 95)" in out
    assert _grade(out).startswith("Hạng tối đa: B")
    assert _first_tg(out).endswith("(tối đa hạng B)")


def test_plan_caps_at_b_a_pending_order_whose_24h_window_spans_a_macro_print(monkeypatch, capsys):
    # A buy limit under the market fills mostly when the print knocks the market down (AVGO 344.3 before PPI).
    _fake_exchange(monkeypatch, _daily_bars(68))
    soon = datetime.now(timezone.utc) + timedelta(hours=3)
    monkeypatch.setattr(h, "load_macro_events", lambda: [(soon, "PPI")], raising=False)
    out = _plan(monkeypatch, capsys, "--entry", "99", "--stop", "94.8", "--target", "110")
    assert "VERDICT: PASS" in out
    assert _grade(out).startswith("Hạng tối đa: B") and "PPI" in _grade(out)
    assert _first_tg(out).endswith("(tối đa hạng B)")


def test_plan_shows_but_does_not_cap_a_market_order_before_a_macro_print(monkeypatch, capsys):
    _fake_exchange(monkeypatch, _daily_bars(68))
    soon = datetime.now(timezone.utc) + timedelta(hours=3)
    monkeypatch.setattr(h, "load_macro_events", lambda: [(soon, "CPI")], raising=False)
    out = _plan(monkeypatch, capsys, "--stop", "95", "--target", "110")
    assert _grade(out) == "Hạng tối đa: A"
    assert any("CPI" in line for line in out.splitlines() if not line.startswith("TG:"))
    assert _first_tg(out) == "TG: 🟢 LONG TESTUSDT [US] (TEST) — Vào ngay"


def test_plan_caps_at_b_a_limit_more_than_1_atr_from_mark(monkeypatch, capsys):
    _fake_exchange(monkeypatch, _daily_bars(68))  # ATR 4: a 95 limit is 1.25 ATR under the 100 mark
    out = _plan(monkeypatch, capsys, "--entry", "95", "--stop", "90.5", "--target", "110")
    assert "VERDICT: PASS" in out
    assert _grade(out).startswith("Hạng tối đa: B") and "1.25 ATR" in _grade(out)


# --- stops: the entry walk agents kept rewriting in scratchpads ---

def _stops(monkeypatch, capsys, *argv: str) -> list[list[str]]:
    monkeypatch.setattr(sys, "argv", ["hunt_stock_data.py", "stops", *argv])
    h.main()
    return [line.split() for line in capsys.readouterr().out.splitlines() if line.lstrip().startswith("entry")]


def test_stops_walks_pullback_entries_to_the_tightest_passing_stop(monkeypatch, capsys):
    _fake_exchange(monkeypatch, _daily_bars(68))  # ATR 4; the 98 lows are 2 under a 1-ATR stop, clear of it
    rows = _stops(monkeypatch, capsys, "LONG", "TEST", "--span", "0.01")
    assert [(r[1], r[4]) for r in rows] == [("100", "96"), ("99.5", "95.5"), ("99", "95")]
    assert rows[0][-4:] == ["106", "|", "2R", "108"]  # 1.5R and 2R off the 4-wide risk


def test_stops_steps_a_short_stop_past_a_swing_high_band(monkeypatch, capsys):
    bars = _daily_bars(68)
    bars[-6][2] = "104.5"  # Mon 5 Oct swing high: the 1-ATR short stop (~104.1) sits 0.4 under it
    _fake_exchange(monkeypatch, bars)
    rows = _stops(monkeypatch, capsys, "SHORT", "TEST", "--span", "0")
    assert len(rows) == 1 and rows[0][1] == "100"
    assert 105.53 < float(rows[0][4]) < 105.62  # first walk step beyond 104.5 + 0.25 ATR


# --- order ledger: the 13/11 run never saw that both 12/11 limits had filled ---

T0 = datetime(2026, 11, 12, 3, 30, tzinfo=timezone.utc)
LIMIT_LONG = {"id": 1, "symbol": "AVGOUSDT", "side": "LONG", "order": "limit", "entry": 348.5, "stop": 330.3,
              "target": 380.0, "created_at": T0.isoformat(), "expires_at": (T0 + timedelta(hours=24)).isoformat()}


def _k(t: datetime, high: float, low: float) -> list:
    return [int(t.timestamp() * 1000), "0", str(high), str(low), str((high + low) / 2)]


def test_order_status_fills_a_buy_limit_then_reports_the_target():
    k5m = [_k(T0 + timedelta(minutes=5 * i), 352, 349) for i in range(18)]  # 03:30-04:55 UTC above 348.5
    k5m.append(_k(T0 + timedelta(minutes=90), 350, 348.0))  # 05:00 UTC = 12:00 ICT: filled
    k1h = [_k(T0 + timedelta(minutes=90), 352, 348), _k(T0 + timedelta(minutes=330), 381, 360)]  # 09:00 UTC: 381
    status = h.order_status(LIMIT_LONG, k5m, k1h, mark=370, now=T0 + timedelta(hours=8))
    # the 381 bar passes +1R (366.7) on its way to the target: half at +1R, half at +1.73R
    assert status == "KHỚP 12/11 12:00 ICT · chốt 1/2 ở +1R 12/11 16:00 ICT · chạm TP 12/11 16:00 ICT (+1.37R)"


@pytest.mark.parametrize("hours_later, want", [(2, "CHỜ · còn 22h"), (25, "HẾT HẠN · không khớp")])
def test_order_status_keeps_an_untouched_limit_pending_until_it_expires(hours_later, want):
    k5m = [_k(T0 + timedelta(minutes=5 * i), 360, 349) for i in range(288)]
    assert h.order_status(LIMIT_LONG, k5m, [], mark=355, now=T0 + timedelta(hours=hours_later)) == want


def test_order_status_counts_the_stop_when_one_bar_spans_stop_and_target():
    k5m = [_k(T0, 350, 348.0)]
    k1h = [_k(T0, 350, 348), _k(T0 + timedelta(hours=3), 381, 330)]
    status = h.order_status(LIMIT_LONG, k5m, k1h, mark=340, now=T0 + timedelta(hours=5))
    assert status == "KHỚP 12/11 10:30 ICT · chạm stop 12/11 13:30 ICT (-1.00R)"


def test_order_status_marks_a_filled_order_still_running_in_r():
    k5m = [_k(T0, 350, 348.0)]
    status = h.order_status(LIMIT_LONG, k5m, [_k(T0, 352, 348)], mark=366.7, now=T0 + timedelta(hours=5))
    assert status == "KHỚP 12/11 10:30 ICT · đang chạy +1.00R (mark 366.7) · chốt 1/2 ở 366.7"


# --- 30/10-20/11: 3 of 9 fills reached +1R, two of them then went back to the stop, and no target was ever hit ---

@pytest.mark.parametrize("bars, exit_at", [
    ([(1, 367, 355), (2, 360, 348)], "12/11 12:30"),  # +1R at 11:30, back to entry an hour later
    ([(1, 367, 348)], "12/11 11:30"),  # one bar spans +1R and entry: count the worse, the exit at entry
])
def test_order_status_moves_the_stop_to_entry_once_half_is_taken(bars, exit_at):
    k1h = [_k(T0, 352, 348)] + [_k(T0 + timedelta(hours=i), hi, lo) for i, hi, lo in bars]
    status = h.order_status(LIMIT_LONG, [_k(T0, 350, 348.0)], k1h, mark=350, now=T0 + timedelta(hours=5))
    assert status == f"KHỚP 12/11 10:30 ICT · chốt 1/2 ở +1R 12/11 11:30 ICT · về hòa vốn {exit_at} ICT (+0.50R)"


def test_order_status_shows_the_rest_running_with_its_stop_at_entry():
    k1h = [_k(T0, 352, 348), _k(T0 + timedelta(hours=1), 367, 355)]
    status = h.order_status(LIMIT_LONG, [_k(T0, 350, 348.0)], k1h, mark=360, now=T0 + timedelta(hours=5))
    assert status == ("KHỚP 12/11 10:30 ICT · chốt 1/2 ở +1R 12/11 11:30 ICT, stop dời về 348.5"
                      " · đang chạy +0.82R (mark 360)")


@pytest.mark.parametrize("horizon, end", [(None, "02/12 10:30"), (3, "15/11 10:30")])
def test_order_status_closes_the_order_when_its_holding_window_ends(horizon, end):
    # Bars drift 349-352 (closing 350.5) and never reach the stop, +1R or the target.
    order = LIMIT_LONG if horizon is None else {**LIMIT_LONG, "horizon_days": horizon}
    k1h = [_k(T0 + timedelta(hours=i), 352, 349) for i in range(24 * 25)]
    status = h.order_status(order, [_k(T0, 350, 348.0)], k1h, mark=360, now=T0 + timedelta(days=21))
    assert status == f"KHỚP 12/11 10:30 ICT · hết {horizon or 20} ngày {end} ICT, đóng 350.5 (+0.11R)"


def test_plan_log_saves_a_passing_order_once(monkeypatch, capsys, tmp_path):
    _fake_exchange(monkeypatch, _daily_bars(68))
    monkeypatch.setattr(h, "ORDERS", tmp_path / "orders.json", raising=False)
    first = _plan(monkeypatch, capsys, "--entry", "99", "--stop", "94.8", "--target", "110", "--log")
    again = _plan(monkeypatch, capsys, "--entry", "99", "--stop", "94.8", "--target", "110", "--log")
    failed = _plan(monkeypatch, capsys, "--entry", "102.5", "--stop", "97.5", "--target", "120", "--log")
    saved = json.loads((tmp_path / "orders.json").read_text())
    assert [(o["id"], o["entry"], o["stop"], o["order"]) for o in saved] == [(1, 99.0, 94.8, "limit")]
    assert "LOG: #1" in first and "LOG: trùng #1" in again and "LOG:" not in failed


def test_orders_cancel_refuses_an_order_that_already_filled(monkeypatch, capsys, tmp_path):
    _fake_exchange(monkeypatch, _daily_bars(68))  # every fake candle trades 98-102, so a 99 limit fills at once
    path = tmp_path / "orders.json"
    created = MONDAY.isoformat()
    path.write_text(json.dumps([{"id": 1, "symbol": "TESTUSDT", "side": "LONG", "order": "limit", "entry": 99.0,
                                 "stop": 94.8, "target": 110.0, "created_at": created,
                                 "expires_at": (MONDAY + timedelta(hours=24)).isoformat()}]))
    monkeypatch.setattr(h, "ORDERS", path, raising=False)
    monkeypatch.setattr(sys, "argv", ["hunt_stock_data.py", "orders", "--cancel", "1"])
    with pytest.raises(SystemExit, match="đã khớp"):
        h.main()
    assert "canceled_at" not in json.loads(path.read_text())[0]


# --- Universe and flags: 13/11 the top-40 cut left 29 of 40 names in tech and dropped 81 liquid others ---

def _tickers(n_liquid: int) -> tuple[dict, dict, dict]:
    meta = {f"S{i:02d}USDT": {"base_asset": f"S{i:02d}", "underlying_type": "EQUITY"} for i in range(n_liquid + 3)}
    tickers = {s: {"quoteVolume": str(90_000_000 - i * 1_000_000)} for i, s in enumerate(meta)}
    for s in list(meta)[n_liquid:n_liquid + 2]:
        tickers[s]["quoteVolume"] = "1500000"  # under the 2M liquidity floor
    etf = list(meta)[-1]
    tv = {etf.removesuffix("USDT"): {"is_etf": True}}
    return meta, tickers, tv


def test_universe_takes_every_liquid_contract_unless_capped():
    meta, tickers, tv = _tickers(45)
    every = h.select_universe(meta, tickers, tv, min_qv=2_000_000, top=0, market="ALL", include_etfs=False)
    assert len(every) == 45 and every[0] == "S00USDT"  # liquidity order, ETF and the two thin ones left out
    assert h.select_universe(meta, tickers, tv, min_qv=2_000_000, top=10, market="ALL", include_etfs=False) == every[:10]


@pytest.mark.parametrize("base", ["UVXY", "STXX"])
def test_universe_drops_non_stocks_tradingview_cannot_name(base):
    # 13/11 the wider scan let UVXY (a VIX ETP) and STXX (31.7x the stock of that ticker) in as stocks.
    meta = {f"{base}USDT": {"base_asset": base, "underlying_type": "EQUITY"}}
    tickers = {f"{base}USDT": {"quoteVolume": "90000000"}}
    assert h.select_universe(meta, tickers, {}, min_qv=1_000_000, top=0, market="ALL", include_etfs=False) == []


@pytest.mark.parametrize("atr_pct, chg24, want", [
    (4.0, 1.0, "OK"),  # x5 stop window 1-2.19 ATR
    (8.15, 1.0, "OKx4"),  # AMD 12/11: under the 8.75% x5 cap but a 0.07-ATR window; x4 gives 1.38 ATR of room
    (12.0, 1.0, "OKx3"),
    (18.0, 1.0, "OKx2"),
    (25.0, 1.0, "ATR"),  # too wide even at x2 (23.75% cap)
    (4.0, 25.0, "PUMP"),  # a 25% day still comes first
])
def test_flag_suggests_the_highest_leverage_that_leaves_room_for_a_stop(atr_pct, chg24, want):
    row = {"mmr": 0.025, "atr_pct": atr_pct, "chg24h": chg24, "fund": 0.0001, "mark_index_dev_pct": 0.01}
    assert h._tag_row(row, 5)["flag"] == want


def test_plan_tells_the_report_which_leverage_the_margin_assumes(monkeypatch, capsys):
    _fake_exchange(monkeypatch, _daily_bars(68))
    out = _plan(monkeypatch, capsys, "--stop", "95", "--target", "110", "--leverage", "3")
    size = next(line for line in out.splitlines() if line.startswith("TG: • Size:"))
    assert "Ký quỹ: " in size and "(x3)" in size


# --- 15/11 review fixes ---

def _no_wait(monkeypatch) -> None:
    monkeypatch.setattr(h, "time", SimpleNamespace(sleep=lambda seconds: None, monotonic=time.monotonic))


@pytest.mark.parametrize("first_error", [
    TimeoutError("timed out"),  # Python 3.10 urllib raises it bare when Binance takes the request and stalls
    urllib.error.HTTPError("https://fapi.binance.com/fapi/v1/time", 408, "Request Timeout", None, None),
])
def test_get_binance_retries_a_stalled_or_timed_out_request(monkeypatch, first_error):
    calls = []

    def urlopen(request, timeout):
        calls.append(request.full_url)
        if len(calls) == 1:
            raise first_error
        return io.BytesIO(b'{"serverTime": 1}')

    monkeypatch.setattr(h.urllib.request, "urlopen", urlopen)
    _no_wait(monkeypatch)
    assert h.get_binance("/fapi/v1/time") == {"serverTime": 1}
    assert len(calls) == 2


@pytest.mark.parametrize("error", [
    urllib.error.HTTPError("https://data.sec.gov/x", 403, "Forbidden", None, None),  # "Undeclared Automated Tool"
    TimeoutError("timed out"),
])
def test_sec_trouble_means_no_fundamentals_not_a_crash(monkeypatch, error):
    # Every plan reads SEC; raising there would stop every stock hunt over optional fundamentals.
    def urlopen(request, timeout):
        raise error

    monkeypatch.setattr(h.urllib.request, "urlopen", urlopen)
    _no_wait(monkeypatch)
    assert h.get_sec_json("https://data.sec.gov/submissions/CIK0000000123.json") is None


def test_order_status_catches_a_stop_in_the_hour_the_order_filled():
    # Binance starts 1h bars at the first full hour after startTime, so a market call created at 03:30 never had
    # its 03:30-04:00 stop checked; the 5m bars cover that part of the hour.
    market = {**LIMIT_LONG, "order": "market"}
    k5m = [_k(T0, 350, 349), _k(T0 + timedelta(minutes=10), 349, 330.0), _k(T0 + timedelta(minutes=15), 345, 340)]
    k1h = [_k(T0 + timedelta(minutes=30), 352, 345), _k(T0 + timedelta(minutes=90), 355, 350)]
    status = h.order_status(market, k5m, k1h, mark=352, now=T0 + timedelta(hours=3))
    assert status == "KHỚP 12/11 10:30 ICT · chạm stop 12/11 10:40 ICT (-1.00R)"


def test_levels_reach_old_swings_and_a_fresh_extreme(monkeypatch):
    # The crypto fix of 31/10 (BEAMX printed resistance []), for stocks: on 13/11 four stocks had no resistance and
    # eight no support, because a fresh 20/55-session extreme is no swing point yet and old swings were cut at 120.
    days = [MONDAY + timedelta(days=i) for i in range(368)]  # ends on a Thursday, the still-forming candle
    weekdays = [d for d in days if d.weekday() < 5]
    special = {weekdays[20]: 130.0, weekdays[-2]: 120.0}  # a swing ~240 sessions back; the last closed session
    bars = [_bar(d, special.get(d, 104.0), 96.0) if d.weekday() < 5 else _bar(d, 100.5, 99.5) for d in days]
    _fake_exchange(monkeypatch, bars)
    meta = h.equity_symbol_meta(h.get_binance("/fapi/v1/exchangeInfo"))["TESTUSDT"]
    row = h.features("TESTUSDT", meta, {"quoteVolume": "50000000", "priceChangePercent": "0.5"},
                     {"markPrice": "115", "indexPrice": "115", "lastFundingRate": "0.0001"}, None, {})
    assert row["res"] == [120.0, 130.0]


def test_plan_log_refuses_a_fourth_open_order(monkeypatch, capsys, tmp_path):
    # 14/11 the stock book held 3 pending limits plus a filled one, though the skill allows 3 trades.
    # every fake candle predates the orders, so none of them fills
    _fake_exchange(monkeypatch, _daily_bars(68), bases=("TEST", "OTHER", "THIRD", "FOURTH"))
    path = tmp_path / "orders.json"
    monkeypatch.setattr(h, "ORDERS", path, raising=False)
    for sym, side, argv in (("TEST", "LONG", LONG_99), ("OTHER", "LONG", LONG_99), ("THIRD", "SHORT", SHORT_101)):
        assert "LOG: #" in _plan(monkeypatch, capsys, *argv, "--log", side=side, sym=sym)
    with pytest.raises(SystemExit, match="3 lệnh"):
        _plan(monkeypatch, capsys, *SHORT_101, "--log", side="SHORT", sym="FOURTH")
    assert len(json.loads(path.read_text())) == 3
    monkeypatch.setattr(sys, "argv", ["hunt_stock_data.py", "orders", "--cancel", "1"])
    h.main()  # a canceled order no longer counts
    assert "LOG: #4" in _plan(monkeypatch, capsys, *SHORT_101, "--log", side="SHORT", sym="FOURTH")


# Passing levels on the 98-102 fake candles (ATR 4, mark 100): a buy limit under and a sell limit over the mark.
LONG_99 = ("--entry", "99", "--stop", "94.8", "--target", "110")
SHORT_101 = ("--entry", "101", "--stop", "105.2", "--target", "90")


def test_plan_log_refuses_a_second_open_order_on_the_same_stock_and_side(monkeypatch, capsys, tmp_path):
    # 13/11 #2 AVGO LONG 349 went in after the 12/11 AVGO LONG 348.5 had filled: one idea, two stops.
    _fake_exchange(monkeypatch, _daily_bars(68))
    path = tmp_path / "orders.json"
    monkeypatch.setattr(h, "ORDERS", path, raising=False)
    assert "LOG: #1" in _plan(monkeypatch, capsys, *LONG_99, "--log")
    with pytest.raises(SystemExit, match="#1 LONG TESTUSDT"):
        _plan(monkeypatch, capsys, "--entry", "99", "--stop", "94.7", "--target", "110", "--log")
    assert len(json.loads(path.read_text())) == 1


def test_plan_log_refuses_a_third_open_order_on_one_side(monkeypatch, capsys, tmp_path):
    # 16/11 afternoon three stock LONGs were open at once (AVGO running, XOM and UNITREE waiting); all three stopped.
    _fake_exchange(monkeypatch, _daily_bars(68), bases=("TEST", "OTHER", "THIRD"))
    monkeypatch.setattr(h, "ORDERS", tmp_path / "orders.json", raising=False)
    for sym in ("TEST", "OTHER"):
        assert "LOG: #" in _plan(monkeypatch, capsys, *LONG_99, "--log", sym=sym)
    with pytest.raises(SystemExit, match="2 lệnh LONG"):
        _plan(monkeypatch, capsys, *LONG_99, "--log", sym="THIRD")
    assert "LOG: #3" in _plan(monkeypatch, capsys, *SHORT_101, "--log", side="SHORT", sym="THIRD")


def test_plan_takes_an_earnings_date_confirmed_by_news(monkeypatch, capsys):
    # SKILL step 2 said to rerun plan with the confirmed date, but plan had no way to take one.
    _fake_exchange(monkeypatch, _daily_bars(68), EARNINGS_IN_5_DAYS)
    later = (datetime.now(timezone.utc).date() + timedelta(days=40)).isoformat()
    out = _plan(monkeypatch, capsys, "--stop", "95", "--target", "110", "--earnings-date", later)
    assert _check(out, "earnings") == "PASS"
    assert f"KQKD: {later} (còn ~40d)" in out


def test_plan_says_when_no_earnings_date_is_known(monkeypatch, capsys):
    _fake_exchange(monkeypatch, _daily_bars(68))  # no TradingView or SEC data: the earnings check passes blind
    out = _plan(monkeypatch, capsys, "--stop", "95", "--target", "110")
    assert "chưa rõ ngày KQKD" in out


@pytest.mark.parametrize("forms, items, days_ago, want", [
    (["8-K"], ["2.02,9.01"], 100, 0),  # results due 9 days ago and not filed yet: imminent, not "no earnings"
    (["6-K", "6-K"], ["", ""], 5, None),  # a foreign filer's 6-Ks (monthly sales, notices) do not date earnings
])
def test_sec_earnings_estimate(monkeypatch, tmp_path, forms, items, days_ago, want):
    today = datetime.now(timezone.utc).date()
    sub = {"sicDescription": "Semiconductors", "filings": {"recent": {
        "form": forms, "filingDate": [str(today - timedelta(days=days_ago))] * len(forms), "items": items}}}
    monkeypatch.setattr(h, "SEC_CACHE_DIR", tmp_path)
    monkeypatch.setattr(h, "get_sec_json", lambda url: sub if "submissions" in url else {})
    assert h.fetch_sec_fundamentals("TEST", {"TEST": (123, "Test Corp")})["days_to_earnings"] == want


def _news(monkeypatch, capsys, recent: dict | None) -> str:
    monkeypatch.setattr(h, "load_sec_tickers", lambda: {"TEST": (123, "Test Corp"), "OTHR": (456, "Other Corp")})
    monkeypatch.setattr(h, "fetch_tv_fundamentals_batch", lambda bases: {})
    monkeypatch.setattr(h, "_fetch_google_rss", lambda query, limit=8: [])
    monkeypatch.setattr(h, "_fetch_yahoo_rss", lambda ticker, limit=8: [])
    monkeypatch.setattr(h, "get_sec_json", lambda url: None if recent is None else {"filings": {"recent": recent}})
    monkeypatch.setattr(sys, "argv", ["hunt_stock_data.py", "news", "TEST", "OTHR"])
    h.main()
    return capsys.readouterr().out


def test_news_says_when_sec_does_not_answer(monkeypatch, capsys):
    out = _news(monkeypatch, capsys, None)  # "(no filings)" here read as "nothing happened"
    assert out.count("SEC không trả lời") == 2 and "(no filings)" not in out


def test_news_marks_6k_filings_to_open(monkeypatch, capsys):
    # A 6-K carries no item codes, so a foreign filer's results or deal news never got the "!" mark.
    filed = str(datetime.now(timezone.utc).date() - timedelta(days=1))
    out = _news(monkeypatch, capsys, {"form": ["6-K"], "filingDate": [filed], "items": [""],
                                      "accessionNumber": ["0000456-26-000001"], "primaryDocument": ["f6k.htm"]})
    assert f"[{filed}] 6-K ?" in out


# --- OKX gate: the user trades on OKX (15/11); OKX lists 186 of Binance's 227 stock perps ---

@pytest.mark.parametrize("argv", [
    ["plan", "LONG", "TEST", "--stop", "95", "--target", "110"],
    ["stops", "LONG", "TEST"],
])
def test_plan_and_stops_refuse_a_stock_okx_does_not_list(monkeypatch, capsys, argv):
    # Tencent, Meituan, BYD, BABA, ANET, UBER trade on Binance only (15/11)
    _fake_exchange(monkeypatch, _daily_bars(68))
    _fake_okx(monkeypatch, [])
    monkeypatch.setattr(sys, "argv", ["hunt_stock_data.py", *argv])
    with pytest.raises(SystemExit, match="OKX"):
        h.main()


def test_detail_prints_no_analysis_for_a_stock_okx_does_not_list(monkeypatch, capsys):
    _fake_exchange(monkeypatch, _daily_bars(68))
    _fake_okx(monkeypatch, [])
    monkeypatch.setattr(sys, "argv", ["hunt_stock_data.py", "detail", "TEST"])
    h.main()
    out = capsys.readouterr().out
    assert "OKX" in out
    assert "ATR14d" not in out


def test_plan_sizes_a_stock_order_in_okx_contracts(monkeypatch, capsys):
    # Risk 10 USDT over a 5 stop = 2 shares = 20 contracts of 0.1 share.
    _fake_exchange(monkeypatch, _daily_bars(68))
    out = _plan(monkeypatch, capsys, "--stop", "95", "--target", "110")
    size = next(line for line in out.splitlines() if line.startswith("TG: • Size:"))
    assert size.startswith("TG: • Size: 20 hợp đồng TEST-USDT-SWAP (2 TEST")


def test_detail_prints_the_okx_contract_and_crowd(monkeypatch, capsys):
    _fake_exchange(monkeypatch, _daily_bars(68))
    monkeypatch.setattr(sys, "argv", ["hunt_stock_data.py", "detail", "TEST"])
    h.main()
    out = capsys.readouterr().out
    assert "OKX TEST-USDT-SWAP" in out
    assert "OKX crowd 100d" in out


def test_scan_keeps_only_stocks_on_okx_and_still_measures_against_spy(monkeypatch, capsys, tmp_path):
    # SPY is the relative-strength yardstick, not a trade: OKX not listing it must not blank rsSPY for every row.
    _fake_exchange(monkeypatch, _daily_bars(68), bases=("TEST", "OTHER", "SPY"))
    _fake_okx(monkeypatch, [_okx_stock("TEST")])
    monkeypatch.setattr(h, "OUT_DIR", tmp_path)
    monkeypatch.setattr(h, "OUT", tmp_path / "market.json")
    monkeypatch.setattr(sys, "argv", ["hunt_stock_data.py", "scan"])
    h.main()
    rows = json.loads((tmp_path / "market.json").read_text())["rows"]
    assert [r["symbol"] for r in rows] == ["TESTUSDT"]
    assert rows[0]["rs20_vs_spy"] == 0.0  # same candles as SPY


# --- Market trend: 30/10-20/11 QQQ closed under its EMA20 every session and all 7 LONG fills hit their stop ---

FALLING = [200.0 - i for i in range(60)]
RISING = [100.0 + i for i in range(60)]


def _trend(monkeypatch, **closes: list[float]) -> None:
    """Daily closes for the index proxies (QQQUSDT=[...]); every other symbol keeps the candles already faked."""
    inner = h.get_binance

    def get_binance(path: str, **params):
        series = closes.get(params.get("symbol"))
        if path != "/fapi/v1/klines" or series is None:
            return inner(path, **params)
        days = [MONDAY + timedelta(days=i) for i in range(len(series) + 1)]  # the extra day is the forming candle
        return [[int(d.timestamp() * 1000), str(c), str(c), str(c), str(c)] for d, c in zip(days, series + series[-1:])]

    monkeypatch.setattr(h, "get_binance", get_binance)


@pytest.mark.parametrize("side, argv, qqq, want", [
    ("LONG", LONG_99, FALLING, "FAIL"),
    ("LONG", LONG_99, RISING, "PASS"),
    ("SHORT", SHORT_101, RISING, "FAIL"),
    ("SHORT", SHORT_101, FALLING, "PASS"),
])
def test_plan_only_lets_the_side_of_the_qqq_trend_through(monkeypatch, capsys, side, argv, qqq, want):
    _fake_exchange(monkeypatch, _daily_bars(68))
    _trend(monkeypatch, QQQUSDT=qqq)
    out = _plan(monkeypatch, capsys, *argv, side=side)
    assert _check(out, "market trend") == want
    assert f"VERDICT: {want}" in out


def test_plan_reads_a_korean_stock_against_ewy_not_qqq(monkeypatch, capsys):
    _fake_exchange(monkeypatch, _daily_bars(68))
    inner = h.get_binance

    def korean(path: str, **params):
        rows = inner(path, **params)
        if path == "/fapi/v1/exchangeInfo":
            rows = {"symbols": [dict(s, underlyingType="KR_EQUITY") for s in rows["symbols"]]}
        return rows

    monkeypatch.setattr(h, "get_binance", korean)
    _trend(monkeypatch, QQQUSDT=FALLING, EWYUSDT=RISING)
    out = _plan(monkeypatch, capsys, *LONG_99)
    assert _check(out, "market trend") == "PASS"
    assert "EWYUSDT" in out


def test_scan_says_which_side_each_trend_lets_through(monkeypatch, capsys, tmp_path):
    _fake_exchange(monkeypatch, _daily_bars(68))
    _trend(monkeypatch, QQQUSDT=FALLING, EWYUSDT=RISING)
    monkeypatch.setattr(h, "OUT_DIR", tmp_path)
    monkeypatch.setattr(h, "OUT", tmp_path / "market.json")
    monkeypatch.setattr(sys, "argv", ["hunt_stock_data.py", "scan"])
    h.main()
    trend = [x for x in capsys.readouterr().out.splitlines() if x.startswith("Xu hướng")]
    assert len(trend) == 1
    assert trend[0].index("QQQUSDT") < trend[0].index("chỉ SHORT") < trend[0].index("EWYUSDT") < trend[0].index("chỉ LONG")


def test_plan_log_keeps_the_holding_window_and_the_market(monkeypatch, capsys, tmp_path):
    _fake_exchange(monkeypatch, _daily_bars(68))
    monkeypatch.setattr(h, "ORDERS", tmp_path / "orders.json", raising=False)
    _plan(monkeypatch, capsys, *LONG_99, "--horizon-days", "5", "--log")
    saved = json.loads((tmp_path / "orders.json").read_text())[0]
    assert (saved["horizon_days"], saved["market"]) == (5, "US")


def test_summarize_scores_fills_and_r_by_side_grade_and_market():
    def o(side: str, grade: str = "B", market: str = "US") -> dict:
        return {"side": side, "grade": grade, "market": market, "order": "limit"}

    graded = [(o("LONG"), "closed", -1.0), (o("LONG", market="CN"), "closed", -1.0),
              (o("SHORT", grade="A"), "closed", 1.37), (o("SHORT"), "running", 0.5),
              (o("LONG"), "expired", None), (o("SHORT"), "pending", None), (o("LONG"), "canceled", None)]
    text = "\n".join(h.summarize(graded))
    assert "khớp 4/5" in text  # 4 filled of the 5 whose 24 hours ran out; pending and canceled don't count
    assert "Đã đóng 3: thắng 1, thua 2, tổng -0.63R" in text
    assert "Đang chạy 1: +0.50R" in text
    assert "LONG 2 lệnh -2.00R" in text and "SHORT 1 lệnh +1.37R" in text
    assert "A 1 lệnh +1.37R" in text and "CN 1 lệnh -1.00R" in text


def test_orders_stats_grades_the_whole_ledger(monkeypatch, capsys, tmp_path):
    # A 99 buy limit fills on the first 98-102 candle, never reaches 94.8, +1R or 110, and closes at 100 on day 20.
    _fake_exchange(monkeypatch, _daily_bars(68))
    path = tmp_path / "orders.json"
    path.write_text(json.dumps([{"id": 1, "symbol": "TESTUSDT", "side": "LONG", "order": "limit", "entry": 99.0,
                                 "stop": 94.8, "target": 110.0, "grade": "B", "market": "US",
                                 "created_at": MONDAY.isoformat(),
                                 "expires_at": (MONDAY + timedelta(hours=24)).isoformat()}]))
    monkeypatch.setattr(h, "ORDERS", path, raising=False)
    monkeypatch.setattr(sys, "argv", ["hunt_stock_data.py", "orders", "--stats"])
    h.main()
    assert "Đã đóng 1: thắng 1, thua 0, tổng +0.24R" in capsys.readouterr().out
