"""Offline checks for hunt_stock_data.py (network calls faked).

Run: PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider ~/.gemini/config/skills/tho-san-co-phieu/scripts
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

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


def _fake_exchange(monkeypatch, bars: list, tv_info: dict | None = None) -> None:
    symbol = {
        "symbol": "TESTUSDT", "baseAsset": "TEST", "quoteAsset": "USDT", "status": "TRADING",
        "contractType": "TRADIFI_PERPETUAL", "underlyingType": "EQUITY",
        "maintMarginPercent": "2.5000", "requiredMarginPercent": "5.0000",
        "filters": [
            {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
            {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
            {"filterType": "MIN_NOTIONAL", "notional": "5"},
        ],
    }
    responses = {
        "/fapi/v1/exchangeInfo": {"symbols": [symbol]},
        "/fapi/v1/premiumIndex": {"symbol": "TESTUSDT", "markPrice": "100", "indexPrice": "100",
                                  "lastFundingRate": "0.0001"},
        "/fapi/v1/ticker/24hr": {"symbol": "TESTUSDT", "quoteVolume": "50000000", "priceChangePercent": "0.5"},
        "/fapi/v1/klines": bars,  # served for 1d and 4h alike; only the daily maths is asserted
        "/futures/data/openInterestHist": [{"sumOpenInterestValue": "1000000"}] * 30,
        "/futures/data/globalLongShortAccountRatio": [{"longShortRatio": "1.5"}] * 30,
        "/futures/data/topLongShortPositionRatio": [{"longShortRatio": "1.2"}] * 30,
        "/futures/data/takerlongshortRatio": [{"buySellRatio": "1.0"}] * 7,
        "/fapi/v1/fundingRate": [{"fundingRate": "0.0001"}] * 21,
    }
    monkeypatch.setattr(h, "get_binance", lambda path, **params: responses[path])
    monkeypatch.setattr(h, "fetch_tv_fundamentals_batch", lambda bases: {"TEST": tv_info} if tv_info else {})
    monkeypatch.setattr(h, "load_sec_tickers", lambda: {})


def _plan(monkeypatch, capsys, *argv: str) -> str:
    monkeypatch.setattr(sys, "argv", ["hunt_stock_data.py", "plan", "LONG", "TEST", *argv])
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
    row = h.features("TESTUSDT", meta, ticker, h.get_binance("/fapi/v1/premiumIndex"), None, {})
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
    assert status == "KHỚP 12/11 12:00 ICT · chạm TP 12/11 16:00 ICT (+1.73R)"


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
    assert status == "KHỚP 12/11 10:30 ICT · đang chạy +1.00R (mark 366.7)"


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


@pytest.fixture(autouse=True)
def _no_kronos(monkeypatch):
    """Offline checks never load the Kronos model: plan/detail fall back to their no-MC path."""
    monkeypatch.setitem(sys.modules, "kronos", None)


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


def test_kronos_stays_out_of_plan_and_detail_unless_asked(monkeypatch, capsys):
    # 13/11 walk-forward check: Kronos-small daily forecasts were biased and worse than a coin flip, so its lines
    # must not reach a report by default. The kronos import is blocked here, so asking for it prints its error.
    _fake_exchange(monkeypatch, _daily_bars(68))
    assert "Kronos" not in _plan(monkeypatch, capsys, "--stop", "95", "--target", "110")
    assert "Kronos" in _plan(monkeypatch, capsys, "--stop", "95", "--target", "110", "--kronos")
    monkeypatch.setattr(sys, "argv", ["hunt_stock_data.py", "detail", "TEST"])
    h.main()
    assert "Kronos" not in capsys.readouterr().out
