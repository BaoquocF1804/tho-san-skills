"""OKX public data for the hunters (stdlib only, no API keys): the user places orders on OKX.

Binance stays the analysis source (the thickest market); this module decides which Binance contracts can be traded
on OKX, sizes them in OKX contracts, and reads OKX's own crowd. Shared by tho-san and tho-san-co-phieu.
"""

from __future__ import annotations

import http.client
import json
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://www.okx.com"


def get(path: str, **params) -> list:
    """The `data` list of an OKX v5 public GET; OKX reports errors with HTTP 200 and a nonzero `code`."""
    url = f"{BASE}{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "tho-san/1.1"})
            with urllib.request.urlopen(request, timeout=20) as response:
                body = json.load(response)
            if body.get("code") != "0":
                raise RuntimeError(f"OKX {path}: code {body.get('code')} {body.get('msg')}")
            return body["data"]
        except urllib.error.HTTPError as exc:
            if exc.code not in (408, 418, 429) and exc.code < 500:
                raise
        except (OSError, http.client.HTTPException, ValueError):
            pass  # URLError, a stalled read (TimeoutError), a dropped or cut body
        time.sleep(2 + 3 * attempt)
    raise RuntimeError(f"OKX unavailable after retries: {path}")


CRYPTO, STOCK = "1", "3"  # OKX instCategory (4 = commodities)
MAX_GAP = 0.01  # OKX vs Binance mark: wider means another contract under the same name (INIT 2.9%, pre-IPO ~90%)


def swaps(category: str) -> dict[str, dict]:
    """Live OKX USDT swaps of one category by base name: contract size, max leverage, mark, 24h USDT volume."""
    marks = {x["instId"]: float(x["markPx"] or 0) for x in get("/api/v5/public/mark-price", instType="SWAP")}
    usdt_24h = {x["instId"]: float(x["volCcy24h"] or 0) * float(x["last"] or 0)
                for x in get("/api/v5/market/tickers", instType="SWAP")}
    return {i["instFamily"].removesuffix("-USDT"): {
        "okx": i["instId"], "ct_val": i["ctVal"], "lot_sz": i["lotSz"], "min_sz": i["minSz"], "tick_sz": i["tickSz"],
        "okx_max_lev": int(i["lever"] or 0), "okx_mark": marks[i["instId"]], "okx_qv": usdt_24h.get(i["instId"], 0.0),
    } for i in get("/api/v5/public/instruments", instType="SWAP")
        if i["settleCcy"] == "USDT" and i["state"] == "live" and i.get("instCategory") == category
        and i["instId"] in marks}


def on_okx(meta: dict[str, dict], marks: dict[str, float], okx: dict[str, dict],
           min_qv: float = 0.0) -> dict[str, dict]:
    """Binance contracts OKX lists under the same base name and category at a mark within MAX_GAP, OKX data merged.

    ponytail: Binance's 1000-prefixed contracts (1000PEPE, 1000SHIB, 1000BONK, 1000FLOKI, 1000SATS) quote 1000
    coins, so their names miss OKX's and they drop out; map the prefix and rescale every printed price to keep them.
    """
    out = {}
    for sym, m in meta.items():
        o, mark = okx.get(m["base_asset"]), marks.get(sym)
        if o and mark and abs(o["okx_mark"] / mark - 1) <= MAX_GAP and o["okx_qv"] >= min_qv:
            out[sym] = {**m, **o, "okx_gap_pct": (o["okx_mark"] / mark - 1) * 100}
    return out


def missing(sym: str) -> str:
    return (f"{sym}: không đặt được trên OKX (OKX không có hợp đồng cùng tên và cùng loại, hoặc giá lệch Binance"
            f" quá {MAX_GAP:.0%}) — bỏ mã này")


def venue(m: dict) -> str:
    """What the order on OKX needs: the contract, its price beside Binance's, liquidity, size unit and leverage cap."""
    return (f"OKX {m['okx']} | mark {m['okx_mark']:.6g} ({m['okx_gap_pct']:+.2f}% vs Binance)"
            f" | 24h ${m['okx_qv'] / 1e6:.1f}M | 1 hợp đồng = {m['ct_val']} {m['base_asset']}"
            f" | max x{m['okx_max_lev']}")


def crowd(m: dict) -> str:
    """OKX's own positioning for the contract: 100 daily rows (an OKX day starts 16:00 UTC), plus OKX funding."""
    def rows(path: str) -> list[list[float]]:  # OKX sends newest first
        return [[float(x) for x in r[1:]] for r in reversed(get(path, instId=m["okx"], period="1D", limit=100))]

    oi = [r[2] for r in rows("/api/v5/rubik/stat/contracts/open-interest-history")]  # [contracts, coins, USD]
    ls = [r[0] for r in rows("/api/v5/rubik/stat/contracts/long-short-account-ratio-contract")]
    top = [r[0] for r in rows("/api/v5/rubik/stat/contracts/long-short-position-ratio-contract-top-trader")]
    taker = [buy / sell for sell, buy in rows("/api/v5/rubik/stat/taker-volume-contract") if sell]
    fund = [float(x["fundingRate"]) for x in get("/api/v5/public/funding-rate-history", instId=m["okx"], limit=21)]
    now = float(get("/api/v5/public/funding-rate", instId=m["okx"])[0]["fundingRate"])

    def chg(days: int) -> str:
        return f"{(oi[-1] / oi[-1 - days] - 1) * 100:+.1f}" if len(oi) > days and oi[-1 - days] else "-"

    def last(s: list[float]) -> str:
        return f"{s[-1]:.4g}" if s else "-"

    def pct(s: list[float]) -> str:
        return str(round(100 * sum(v <= s[-1] for v in s) / len(s))) if s else "-"

    taker3d = f"{sum(taker[-3:]) / len(taker[-3:]):.4g}" if taker else "-"
    fund_avg = sum(fund) / len(fund) if fund else 0.0
    return (f"  OKX crowd 100d: OI 1d {chg(1)}% 7d {chg(7)}% | L/S {last(ls)} (pct100 {pct(ls)})"
            f" | top {last(top)} (pct100 {pct(top)}) | taker 1d {last(taker)} 3d {taker3d}"
            f" | funding {now * 100:.4f}% (avg last 21 {fund_avg * 100:.4f}%)")
