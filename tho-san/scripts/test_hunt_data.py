"""Offline checks for hunt_data.py (network calls faked).

Run: PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider ~/.gemini/config/skills/tho-san/scripts
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hunt_data as hd  # noqa: E402

START = datetime(2026, 8, 3, tzinfo=timezone.utc)


def _bars(closed: int) -> list:
    """`closed` daily candles plus the still-forming one; every third candle spikes so swing highs exist."""
    out = []
    for i in range(closed + 1):
        t = int((START + timedelta(days=i)).timestamp() * 1000)
        high = 110 if i % 3 == 1 else 104
        out.append([t, "100", str(high), "96", "100", "1000", t + 86_399_999, "100000", 10, "500", "50000", "0"])
    return out


def _symbol(name: str) -> dict:
    return {
        "symbol": name, "baseAsset": name.removesuffix("USDT"), "quoteAsset": "USDT", "status": "TRADING",
        "contractType": "PERPETUAL", "underlyingType": "COIN",
        "maintMarginPercent": "2.5000", "requiredMarginPercent": "5.0000",
        "filters": [
            {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
            {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
            {"filterType": "MIN_NOTIONAL", "notional": "5"},
        ],
    }


HISTORY = {
    "/futures/data/openInterestHist": {"sumOpenInterestValue": "1000000"},
    "/futures/data/globalLongShortAccountRatio": {"longShortRatio": "1.5"},
    "/futures/data/topLongShortPositionRatio": {"longShortRatio": "1.2"},
    "/futures/data/takerlongshortRatio": {"buySellRatio": "1.0"},
    "/fapi/v1/fundingRate": {"fundingRate": "0.0001"},
}


def _fake_exchange(monkeypatch, tmp_path, closed_by_symbol: dict[str, int]) -> None:
    """Binance as seen for these symbols; a contract with N closed candles has N days of history everywhere."""
    def get(path: str, **params):
        sym = params.get("symbol")
        if path == "/fapi/v1/exchangeInfo":
            return {"symbols": [_symbol(s) for s in closed_by_symbol]}
        if path in ("/fapi/v1/ticker/24hr", "/fapi/v1/premiumIndex"):
            rows = [{"symbol": s, "quoteVolume": "90000000", "priceChangePercent": "3",
                     "markPrice": "100", "lastFundingRate": "0.0001"} for s in closed_by_symbol]
            return rows if sym is None else next(r for r in rows if r["symbol"] == sym)
        if path == "/fapi/v1/klines":  # served for 1d and 4h alike
            return _bars(closed_by_symbol[sym])[-params["limit"]:]
        return [HISTORY[path]] * min(closed_by_symbol[sym], params["limit"])

    monkeypatch.setattr(hd, "get", get)
    monkeypatch.setattr(hd, "OUT", tmp_path / "market.json")


def _run(monkeypatch, capsys, *argv: str) -> str:
    monkeypatch.setattr(sys, "argv", ["hunt_data.py", *argv])
    hd.main()
    return capsys.readouterr().out


def test_scan_survives_a_contract_listed_today(monkeypatch, capsys, tmp_path):
    # New listings often trade huge volume on day one, so they land in the top 40 with no closed candle yet.
    _fake_exchange(monkeypatch, tmp_path, {"BTCUSDT": 60, "NEWUSDT": 0})
    out = _run(monkeypatch, capsys, "scan")
    new_row = next(line for line in out.splitlines() if line.startswith("NEWUSDT"))
    assert new_row.split()[1] == "ATR"  # no ATR14 yet, so not tradeable


def test_scan_leaves_out_tokenized_gold(monkeypatch, capsys, tmp_path):
    # PAXGUSDT ranked 29th on 31/10 and was flagged OK: gold's hours and ATR, not a crypto perp.
    _fake_exchange(monkeypatch, tmp_path, {"BTCUSDT": 60, "PAXGUSDT": 60, "XAUTUSDT": 60, "ETHUSDT": 60})
    out = _run(monkeypatch, capsys, "scan")
    assert "ETHUSDT" in out
    assert "PAXGUSDT" not in out and "XAUTUSDT" not in out


def test_levels_reach_old_swings_and_a_fresh_extreme(monkeypatch):
    # 31/10: BEAMX had cleared every 120-day swing high, so detail printed resistance [].
    highs = [104.0] * 259
    highs[20] = 130.0  # a swing high 238 days back
    highs[-1] = 120.0  # yesterday's high: no two later days yet, so not a swing point
    t0 = int(START.timestamp() * 1000)
    bars = [[t0 + i * 86_400_000, "100", str(high), "96", "100", "1000", 0, "100000", 10, "500", "50000", "0"]
            for i, high in enumerate(highs + [104.0])]  # plus the forming day

    def get(path: str, **params):
        return bars[-params["limit"]:] if path == "/fapi/v1/klines" else [HISTORY[path]] * params["limit"]

    monkeypatch.setattr(hd, "get", get)
    row = hd.features("COINUSDT", {}, {"quoteVolume": "90000000", "priceChangePercent": "3"},
                      {"markPrice": "115", "lastFundingRate": "0.0001"}, None)
    assert row["res"] == [120.0, 130.0]


def test_detail_prints_a_contract_too_new_for_atr14(monkeypatch, capsys, tmp_path):
    _fake_exchange(monkeypatch, tmp_path, {"NEWUSDT": 8})
    out = _run(monkeypatch, capsys, "detail", "NEWUSDT")
    assert "### NEWUSDT" in out
    assert "ATR14d - " in out


def test_plan_refuses_contract_too_new_for_atr14(monkeypatch, capsys, tmp_path):
    _fake_exchange(monkeypatch, tmp_path, {"NEWUSDT": 3})
    with pytest.raises(SystemExit, match="ATR14"):
        _run(monkeypatch, capsys, "plan", "LONG", "NEWUSDT", "--stop", "95", "--target", "110")


# Fixture levels: swing highs 110, swing lows 96, the last closed day and today topped at 104; ATR ~10.
# x2 so the stop cap is 23.75% and every row passes the ATR, cap, R:R and size checks on its own.
@pytest.mark.parametrize("side, stop, target, entry, verdict", [
    ("SHORT", "111", "80", None, "FAIL"),  # 1 above the 110 swing highs: the wick that takes 110 takes it
    ("SHORT", "109", "60", "95", "FAIL"),  # 1 under the 110 swing highs (XRP 1.372 under 1.3724 on 25/10)
    ("SHORT", "114", "75", None, "PASS"),  # 0.4 ATR clear of every level
    ("SHORT", "104.5", "60", "90", "FAIL"),  # 0.5 above the last day's 104 high, not a swing point yet
    ("LONG", "97", "140", "110", "FAIL"),  # 1 above the 96 swing lows
])
def test_plan_fails_a_stop_hugging_a_daily_high_or_low(monkeypatch, capsys, tmp_path,
                                                       side, stop, target, entry, verdict):
    _fake_exchange(monkeypatch, tmp_path, {"COINUSDT": 60})
    out = _run(monkeypatch, capsys, "plan", side, "COINUSDT", "--stop", stop, "--target", target,
               "--leverage", "2", *(["--entry", entry] if entry else []))
    assert f"VERDICT: {verdict}" in out
    assert ("DESK:" in out) == (verdict == "PASS")  # nothing to copy from a failed plan


@pytest.mark.parametrize("side, entry, stop, target, want", [
    ("LONG", "99.8", "85", "125", "entry 100  stop 85 (-15.00%"),  # fills near the 100 mark, not at 99.8
    ("SHORT", "100.3", "115", "75", "entry 100  stop 115 (+15.00%"),
    ("LONG", "95", "80", "125", "entry 95  stop 80 (-15.79%"),  # a limit fills at its own price
])
def test_plan_sizes_a_market_entry_from_the_worse_of_entry_and_mark(monkeypatch, capsys, tmp_path,
                                                                     side, entry, stop, target, want):
    _fake_exchange(monkeypatch, tmp_path, {"COINUSDT": 60})
    out = _run(monkeypatch, capsys, "plan", side, "COINUSDT", "--entry", entry, "--stop", stop,
               "--target", target, "--leverage", "2")
    assert want in out


def test_plan_prints_the_lines_the_report_and_desk_copy(monkeypatch, capsys, tmp_path):
    # Retyped levels drifted: the 31/10 report plan-gated an ETH stop at 2462 but logged 2455.
    _fake_exchange(monkeypatch, tmp_path, {"COINUSDT": 60})
    out = _run(monkeypatch, capsys, "plan", "SHORT", "COINUSDT", "--stop", "114", "--target", "75",
               "--leverage", "2")
    lines = [line for line in out.splitlines() if line.startswith(("TG:", "DESK:"))]
    assert lines[0] == "TG: 🔴 SHORT COINUSDT — Vào ngay"
    assert lines[1].startswith("TG: • Vào: 100 | Stop: 114 (+14.00%, ")
    assert lines[2].startswith("TG: • Size: ")
    assert lines[3] == ("DESK: ~/crypto-desk-rewrite/scripts/desk log-call SHORT COINUSDT"
                        " --entry 100 --stop 114 --target 75")


def test_plan_gives_a_breakout_stop_order_no_desk_line(monkeypatch, capsys, tmp_path):
    _fake_exchange(monkeypatch, tmp_path, {"COINUSDT": 60})  # SHORT under the mark: a stop entry
    out = _run(monkeypatch, capsys, "plan", "SHORT", "COINUSDT", "--entry", "95", "--stop", "107",
               "--target", "75", "--leverage", "2")
    assert "VERDICT: PASS" in out
    assert "TG: 🔴 SHORT COINUSDT — Stop" in out
    assert "DESK:" not in out  # the desk cannot grade stop entries yet


def test_detail_marks_only_the_forming_4h_bar_live(monkeypatch, capsys, tmp_path):
    # An unmarked forming bar was read as a closed 4h rejection in the 25/10 12:57 report.
    _fake_exchange(monkeypatch, tmp_path, {"COINUSDT": 60})
    out = _run(monkeypatch, capsys, "detail", "COINUSDT")
    bars = [line for line in out.splitlines() if line.lstrip().startswith("4h ")]
    assert len(bars) == 7
    assert "LIVE" in bars[-1]
    assert not any("LIVE" in bar for bar in bars[:-1])
