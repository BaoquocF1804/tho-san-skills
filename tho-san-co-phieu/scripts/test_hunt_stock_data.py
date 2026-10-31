"""Offline checks for hunt_stock_data.py (network calls faked).

Run: PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider ~/.gemini/config/skills/tho-san-co-phieu/scripts
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
