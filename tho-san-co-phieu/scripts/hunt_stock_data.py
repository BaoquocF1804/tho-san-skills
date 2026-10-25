#!/usr/bin/env python3
"""Binance USDⓈ-M Global Equity Perpetuals + Global Fundamentals (TradingView + SEC EDGAR) hunter (stdlib only).

Supports all stock perpetual categories on Binance USDⓈ-M; the market tag follows Binance's underlyingType:
  - US Equities & ADRs (EQUITY: NVDA, TSLA, MU, SNDK, SPCX SpaceX, TSM, ARM, SKHY SK hynix ADR, BABA, ASML...)
  - Korean Equities (KR_EQUITY: SKHYNIX, SAMSUNG, HYUNDAI, HANMI, NAVER, LGELECTRONICS...)
  - Hong Kong Equities (HK_EQUITY: TENCENT/HK0700, HK1810 Xiaomi, BYD, MEITUAN, POPMART, ZHONGJI, GIGADEV, ZHIPU, MINIMAX...)
  - China A-shares (CN_EQUITY: UNITREE, CXMT)
  - Pre-IPO (PREMARKET: OPENAI, ANTHROPIC, MOONSHOT, OURA)
Daily and 4h indicators skip Sat/Sun candles: the perps trade 24/7 but barely move while the exchanges are shut.

Commands:
  python3 hunt_stock_data.py scan [--top 40] [--min-qv 1000000] [--market all|us|kr|hk|cn|adr|pre] [--leverage 5]
      global stock universe table (ETFs excluded by default) + /tmp/tho-san-co-phieu/market.json
  python3 hunt_stock_data.py detail SYMBOL [SYMBOL ...]
      levels in ATRs, positioning, global fundamentals (TradingView + SEC EDGAR 10-Q/10-K/20-F/6-K), earnings dates, 1d/4h bars
  python3 hunt_stock_data.py news [SYMBOL ...]
      Google News RSS for global/US/Asia macro + each stock symbol (using resolved company name) with dates
  python3 hunt_stock_data.py plan LONG|SHORT SYMBOL --stop X --target Y [--entry E] [--capital 1000] [--horizon-days 20]
      checks mark-index deviation, ATR/liquidation stop bounds, R:R, earnings inside the holding window, and sizes position

Read-only public endpoints (Binance fapi + TradingView Scanner + SEC EDGAR + Google News RSS); nothing here can trade.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import ROUND_FLOOR, Decimal
import json
import os
from pathlib import Path
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

BASE = "https://fapi.binance.com"
TV_SCAN_URL = "https://scanner.tradingview.com/global/scan"
OUT_DIR = Path("/tmp/tho-san-co-phieu")
OUT = OUT_DIR / "market.json"
SEC_CACHE_DIR = OUT_DIR / "sec-cache"

SEC_USER_AGENT = os.environ.get(
    "SEC_USER_AGENT",
    "CryptoDeskStockHunter/2.0 (baoquoc@crypto-desk.local)",
)

STOCK_UNDERLYING_TYPES = {"EQUITY", "KR_EQUITY", "HK_EQUITY", "CN_EQUITY", "PREMARKET"}

SEC_TICKER_ALIASES = {
    "BRKB": "BRK-B",
    "BRKA": "BRK-A",
    "BFB": "BF-B",
}

# Binance base asset -> TradingView ticker where the base is not the home-exchange ticker
# (US names and ADRs such as NVDA or SKHY resolve by name on NASDAQ/NYSE/AMEX)
GLOBAL_TICKER_MAP = {
    # Korea (KRX)
    "SKHYNIX": "KRX:000660",
    "SAMSUNG": "KRX:005930",
    "HYUNDAI": "KRX:005380",
    "HANMI": "KRX:042700",
    "SAMSUNGEM": "KRX:009150",
    "NAVER": "KRX:035420",
    "LGELECTRONICS": "KRX:066570",
    # Hong Kong (HKEX), incl. H-shares of mainland companies
    "TENCENT": "HKEX:700",
    "HK0700": "HKEX:700",
    "HK1810": "HKEX:1810",
    "BYD": "HKEX:1211",
    "MEITUAN": "HKEX:3690",
    "POPMART": "HKEX:9992",
    "HK0992": "HKEX:992",
    "KUAISHOU": "HKEX:1024",
    "HK0625": "HKEX:625",
    "ZHONGJI": "HKEX:3308",
    "GIGADEV": "HKEX:3986",
    "ZHIPU": "HKEX:2513",
    "MINIMAX": "HKEX:100",
    # China A-shares (SSE STAR Market)
    "UNITREE": "SSE:688836",
    "CXMT": "SSE:688825",
    # US special share classes
    "BRKB": "NYSE:BRK.B",
}

# Pre-IPO contracts (underlyingType PREMARKET): not listed anywhere, so no TradingView or SEC data
PRIVATE_COMPANIES = {
    "OPENAI": {
        "company_name": "OpenAI",
        "exchange": "PRE-IPO",
        "sector": "Artificial Intelligence",
    },
    "ANTHROPIC": {
        "company_name": "Anthropic PBC (Claude)",
        "exchange": "PRE-IPO",
        "sector": "Artificial Intelligence",
    },
    "MOONSHOT": {
        "company_name": "Moonshot AI (Kimi)",
        "exchange": "PRE-IPO",
        "sector": "Artificial Intelligence",
    },
    "OURA": {
        "company_name": "Oura Health Oy",
        "exchange": "PRE-IPO",
        "sector": "Consumer Health & Smart Rings",
    },
}

# Known ETFs & Leveraged ETPs on Binance TradFi (excluded by default unless --include-etfs)
KNOWN_ETFS = {
    "SPY", "QQQ", "TQQQ", "SQQQ", "SOXL", "SOXS", "SMH", "IWM", "DIA", "ARKK",
    "XLF", "XLE", "XLK", "XLV", "XLI", "XLP", "XLU", "XLY", "XLB", "XLRE", "XLC",
    "EWY", "EWJ", "EWZ", "EEM", "FXI", "KWEB", "ASHR", "MCHI", "INDA", "VGK", "EZU",
    "GDX", "GDXJ", "SIL", "URA", "USO", "UNG", "TLT", "HYG", "LQD", "IBIT", "ETHA",
    "KORU", "SNXX", "MUU", "MVLL", "INTW", "DRAM", "NVDL", "NVDU", "TSLL", "CONL",
    "MSTU", "MSTX", "AMDL", "AAPU", "GGLL", "METU", "MSFU", "PLTU",
    "KODEX200", "CSOPSKHYNIX2L", "CSOPSAMSUNG2L",
}

PUMP_CHANGE_24H = 20.0  # percent: single-day stock move not yet in closed-candle ATR
PUMP_FUNDING = 0.005
MAX_MARK_INDEX_DEV = 0.005  # 0.5% max deviation between markPrice and indexPrice
TAKER_FEE_ROUNDTRIP = 0.001
STOP_CLEARANCE_ATR = 0.25  # a stop nearer than this to a daily high/low goes with the wick that sweeps it

REV_TAGS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "TotalRevenuesAndOtherIncome",
    "RevenuesNetOfInterestExpense",
    "InterestAndDividendIncomeOperating",
    "Revenue",  # IFRS
]
GP_TAGS = [
    "GrossProfit",
    "OperatingIncomeLoss",
]
NI_TAGS = [
    "NetIncomeLoss",
    "ProfitLoss",
    "NetIncomeLossAvailableToCommonStockholdersBasic",
]
EPS_TAGS = [
    "EarningsPerShareDiluted",
    "EarningsPerShareBasic",
    "DilutedEarningsPerShare",  # IFRS
    "BasicEarningsPerShare",  # IFRS
]

TV_COLUMNS = [
    "name",
    "description",
    "type",
    "subtype",
    "exchange",
    "sector",
    "industry",
    "currency",
    "fundamental_currency_code",
    "market_cap_basic",
    "price_earnings_ttm",
    "price_sales_current",
    "return_on_equity_fq",
    "debt_to_equity_fq",
    "total_revenue_fq",
    "total_revenue_yoy_growth_fq",
    "total_revenue_ttm",
    "total_revenue_yoy_growth_ttm",
    "gross_margin_ttm",
    "operating_margin_ttm",
    "net_income_fq",
    "net_income_yoy_growth_fq",
    "net_margin_ttm",
    "earnings_per_share_diluted_fq",
    "earnings_per_share_diluted_yoy_growth_fq",
    "earnings_per_share_diluted_ttm",
    "earnings_release_date",
    "earnings_release_next_date",
]

_sec_lock = threading.Lock()
_sec_last_call = 0.0


def get_binance(path: str, **params):
    url = f"{BASE}{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "tho-san-co-phieu/2.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            if exc.code not in (418, 429) and exc.code < 500:
                raise
        except urllib.error.URLError:
            pass
        time.sleep(2 + 3 * attempt)
    raise RuntimeError(f"Binance unavailable after retries: {path}")


def get_sec_json(url: str):
    """Fetch JSON from SEC EDGAR respecting the <=10 req/sec rate limit and User-Agent policy."""
    global _sec_last_call
    for attempt in range(4):
        with _sec_lock:
            now = time.monotonic()
            wait = 0.12 - (now - _sec_last_call)
            if wait > 0:
                time.sleep(wait)
            _sec_last_call = time.monotonic()
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": SEC_USER_AGENT,
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            if exc.code not in (429, 500, 502, 503, 504):
                raise
        except urllib.error.URLError:
            pass
        time.sleep(1.5 * (attempt + 1))
    return None


def load_sec_tickers() -> dict[str, tuple[int, str]]:
    """Map uppercase US/ADR ticker -> (cik_int, company_title), cached for 24h."""
    SEC_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = SEC_CACHE_DIR / "company_tickers.json"
    today_tag = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    raw = None
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text())
            if cached.get("date") == today_tag and cached.get("data"):
                raw = cached["data"]
        except Exception:
            raw = None
    if raw is None:
        raw = get_sec_json("https://www.sec.gov/files/company_tickers.json") or {}
        try:
            cache_file.write_text(json.dumps({"date": today_tag, "data": raw}))
        except Exception:
            pass
    mapping: dict[str, tuple[int, str]] = {}
    for item in raw.values():
        ticker = str(item.get("ticker", "")).upper()
        if ticker:
            mapping[ticker] = (int(item["cik_str"]), str(item.get("title", "")))
    return mapping


def fetch_tv_fundamentals_batch(base_assets: list[str]) -> dict[str, dict]:
    """Batch-fetch global fundamentals from TradingView Scanner for US, KR, HK, CN, and ADR stocks."""
    candidate_tickers: list[str] = []
    for base in base_assets:
        b = base.upper()
        if b in GLOBAL_TICKER_MAP:
            candidate_tickers.append(GLOBAL_TICKER_MAP[b])
        for ex in ("NASDAQ", "NYSE", "AMEX"):
            candidate_tickers.append(f"{ex}:{b}")

    payload = json.dumps({
        "symbols": {"tickers": sorted(set(candidate_tickers)), "query": {"types": []}},
        "columns": TV_COLUMNS,
    }).encode("utf-8")

    rows = []
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                TV_SCAN_URL,
                data=payload,
                headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                rows = json.load(resp).get("data", [])
            break
        except Exception:
            time.sleep(1 + attempt)

    by_full_symbol: dict[str, dict] = {}
    by_short_name: dict[str, dict] = {}
    for item in rows:
        full_sym = item.get("s", "")
        d = item.get("d", [])
        rec = dict(zip(TV_COLUMNS, d))
        rec["tv_symbol"] = full_sym
        by_full_symbol[full_sym] = rec
        short_name = str(rec.get("name", "")).upper()
        if short_name and short_name not in by_short_name:
            by_short_name[short_name] = rec

    today_dt = datetime.now(timezone.utc).date()
    result: dict[str, dict] = {}
    for base in base_assets:
        b = base.upper()
        rec = None
        if b in GLOBAL_TICKER_MAP:
            rec = by_full_symbol.get(GLOBAL_TICKER_MAP[b])
        if rec is None:
            rec = by_short_name.get(b)
        if not rec:
            continue

        last_ts = rec.get("earnings_release_date")
        next_ts = rec.get("earnings_release_next_date")
        last_earn_str = None
        next_earn_str = None
        days_since = None
        days_to = None
        if isinstance(last_ts, (int, float)) and last_ts > 0:
            last_dt = datetime.fromtimestamp(last_ts, timezone.utc).date()
            last_earn_str = last_dt.isoformat()
            days_since = (today_dt - last_dt).days
        if isinstance(next_ts, (int, float)) and next_ts > 0:
            next_dt = datetime.fromtimestamp(next_ts, timezone.utc).date()
            next_earn_str = next_dt.isoformat()
            days_to = (next_dt - today_dt).days

        is_etf = (
            b in KNOWN_ETFS
            or rec.get("type") == "fund"
            or "etf" in str(rec.get("subtype") or "").lower()
        )
        result[b] = {
            "tv_symbol": rec.get("tv_symbol"),
            "company_name": rec.get("description") or b,
            "type": rec.get("type"),
            "subtype": rec.get("subtype"),
            "is_etf": is_etf,
            "exchange": rec.get("exchange"),
            "sector": rec.get("sector"),
            "industry": rec.get("industry"),
            "currency": rec.get("fundamental_currency_code") or rec.get("currency"),
            "market_cap_busd": round(rec["market_cap_basic"] / 1e9, 2) if rec.get("market_cap_basic") else None,
            "pe_ttm": round(rec["price_earnings_ttm"], 2) if rec.get("price_earnings_ttm") else None,
            "ps_ttm": round(rec["price_sales_current"], 2) if rec.get("price_sales_current") else None,
            "roe_fq": round(rec["return_on_equity_fq"], 1) if rec.get("return_on_equity_fq") is not None else None,
            "debt_to_equity_fq": round(rec["debt_to_equity_fq"], 2) if rec.get("debt_to_equity_fq") is not None else None,
            "rev_fq_musd": round(rec["total_revenue_fq"] / 1e6, 1) if rec.get("total_revenue_fq") else None,
            "rev_yoy_fq": round(rec["total_revenue_yoy_growth_fq"], 1) if rec.get("total_revenue_yoy_growth_fq") is not None else None,
            "rev_ttm_musd": round(rec["total_revenue_ttm"] / 1e6, 1) if rec.get("total_revenue_ttm") else None,
            "rev_yoy_ttm": round(rec["total_revenue_yoy_growth_ttm"], 1) if rec.get("total_revenue_yoy_growth_ttm") is not None else None,
            "gross_margin_ttm": round(rec["gross_margin_ttm"], 1) if rec.get("gross_margin_ttm") is not None else None,
            "operating_margin_ttm": round(rec["operating_margin_ttm"], 1) if rec.get("operating_margin_ttm") is not None else None,
            "ni_fq_musd": round(rec["net_income_fq"] / 1e6, 1) if rec.get("net_income_fq") is not None else None,
            "ni_yoy_fq": round(rec["net_income_yoy_growth_fq"], 1) if rec.get("net_income_yoy_growth_fq") is not None else None,
            "net_margin_ttm": round(rec["net_margin_ttm"], 1) if rec.get("net_margin_ttm") is not None else None,
            "eps_fq": round(rec["earnings_per_share_diluted_fq"], 2) if rec.get("earnings_per_share_diluted_fq") is not None else None,
            "eps_yoy_fq": round(rec["earnings_per_share_diluted_yoy_growth_fq"], 1) if rec.get("earnings_per_share_diluted_yoy_growth_fq") is not None else None,
            "eps_ttm": round(rec["earnings_per_share_diluted_ttm"], 2) if rec.get("earnings_per_share_diluted_ttm") is not None else None,
            "last_earnings_date": last_earn_str,
            "days_since_earnings": days_since,
            "next_earnings_date": next_earn_str,
            "days_to_earnings": days_to,
        }
    return result


def _extract_quarterly_series(tax_dict: dict, tags: list[str]) -> tuple[list[tuple[str, float]], str]:
    """Extract (~90-day) quarterly values from 10-Q/10-K/20-F/6-K across candidate tags, sorted by end date."""
    best: dict[str, float] = {}
    chosen_unit = "USD"
    for tag in reversed(tags):
        units = tax_dict.get(tag, {}).get("units", {})
        if not units:
            continue
        # Prefer USD or USD/shares, otherwise first available unit
        unit_key = next((u for u in ("USD", "USD/shares") if u in units), next(iter(units.keys()), None))
        if not unit_key:
            continue
        chosen_unit = unit_key
        for x in units.get(unit_key, []):
            if x.get("form") not in ("10-Q", "10-K", "20-F", "6-K"):
                continue
            start, end = x.get("start"), x.get("end")
            val = x.get("val")
            if not start or not end or val is None:
                continue
            try:
                d_start = datetime.strptime(start, "%Y-%m-%d")
                d_end = datetime.strptime(end, "%Y-%m-%d")
            except ValueError:
                continue
            days = (d_end - d_start).days
            if 70 <= days <= 110:
                best[end] = float(val)
    return sorted(best.items()), chosen_unit


def _yoy_growth(series: list[tuple[str, float]]) -> float | None:
    """Compute YoY % growth for the most recent quarter against a quarter ~365 days earlier."""
    if len(series) < 2:
        return None
    latest_end_str, latest_val = series[-1]
    latest_end = datetime.strptime(latest_end_str, "%Y-%m-%d")
    for prev_end_str, prev_val in reversed(series[:-1]):
        prev_end = datetime.strptime(prev_end_str, "%Y-%m-%d")
        diff_days = (latest_end - prev_end).days
        if 340 <= diff_days <= 390:
            if prev_val == 0:
                return None
            return round((latest_val - prev_val) / abs(prev_val) * 100, 1)
    return None


def fetch_sec_fundamentals(base_asset: str, sec_map: dict[str, tuple[int, str]]) -> dict | None:
    """Return SEC EDGAR filing metadata & quarterly XBRL table (us-gaap or ifrs-full) when available."""
    lookup = SEC_TICKER_ALIASES.get(base_asset.upper(), base_asset.upper())
    if lookup not in sec_map:
        return None
    cik, title = sec_map[lookup]
    SEC_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    today_tag = datetime.now(timezone.utc).strftime("%Y%m%d")
    cache_path = SEC_CACHE_DIR / f"sec2_{cik:010d}_{today_tag}.json"
    if cache_path.exists():
        try:
            data = json.loads(cache_path.read_text())
            return data if data.get("has_sec") else None
        except Exception:
            pass

    sub_resp = get_sec_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json") or {}
    if not sub_resp:
        return None
    sic_desc = sub_resp.get("sicDescription") or ""
    recent = sub_resp.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    f_dates = recent.get("filingDate", [])
    items = recent.get("items", [])

    earnings_8k_dates = [
        f_dates[i]
        for i in range(min(len(forms), len(f_dates), len(items)))
        if (forms[i] == "8-K" and "2.02" in str(items[i])) or forms[i] == "6-K"
    ]
    last_earnings_date = earnings_8k_dates[0] if earnings_8k_dates else None
    next_earnings_est = None
    days_to_earnings = None
    days_since_earnings = None
    today_dt = datetime.now(timezone.utc).date()

    if last_earnings_date:
        last_dt = datetime.strptime(last_earnings_date, "%Y-%m-%d").date()
        days_since_earnings = (today_dt - last_dt).days
        est_dt = last_dt + timedelta(days=91)
        while (est_dt - today_dt).days < -15:
            est_dt += timedelta(days=91)
        next_earnings_est = est_dt.isoformat()
        days_to_earnings = (est_dt - today_dt).days

    facts_resp = get_sec_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json")
    facts = (facts_resp or {}).get("facts", {})
    tax_dict = facts.get("us-gaap") or facts.get("ifrs-full") or {}
    rev_q, rev_unit = _extract_quarterly_series(tax_dict, REV_TAGS) if tax_dict else ([], "USD")
    gp_q, _ = _extract_quarterly_series(tax_dict, GP_TAGS) if tax_dict else ([], "USD")
    ni_q, _ = _extract_quarterly_series(tax_dict, NI_TAGS) if tax_dict else ([], "USD")
    eps_q, _ = _extract_quarterly_series(tax_dict, EPS_TAGS) if tax_dict else ([], "USD/shares")

    all_dates = sorted({d for d, _ in (rev_q[-6:] + ni_q[-6:] + eps_q[-6:])})[-6:]
    rev_dict, gp_dict, ni_dict, eps_dict = dict(rev_q), dict(gp_q), dict(ni_q), dict(eps_q)
    quarters = []
    for d in all_dates:
        r_val = rev_dict.get(d)
        g_val = gp_dict.get(d)
        n_val = ni_dict.get(d)
        e_val = eps_dict.get(d)
        margin_pct = round(g_val / r_val * 100, 1) if (r_val and g_val is not None and r_val > 0) else None
        quarters.append({
            "end": d,
            "rev_m": round(r_val / 1e6, 1) if r_val is not None else None,
            "gp_m": round(g_val / 1e6, 1) if g_val is not None else None,
            "margin_pct": margin_pct,
            "ni_m": round(n_val / 1e6, 1) if n_val is not None else None,
            "eps": round(e_val, 2) if e_val is not None else None,
        })

    result = {
        "has_sec": True,
        "cik": cik,
        "ticker": lookup,
        "company_name": title or sub_resp.get("name") or lookup,
        "sic_description": sic_desc,
        "unit": rev_unit,
        "last_earnings_date": last_earnings_date,
        "days_since_earnings": days_since_earnings,
        "next_earnings_est": next_earnings_est,
        "days_to_earnings": days_to_earnings,
        "rev_yoy_pct": _yoy_growth(rev_q),
        "ni_yoy_pct": _yoy_growth(ni_q),
        "eps_yoy_pct": _yoy_growth(eps_q),
        "latest_quarter_end": all_dates[-1] if all_dates else None,
        "quarters": quarters,
    }
    try:
        cache_path.write_text(json.dumps(result, indent=1))
    except Exception:
        pass
    return result


def resolve_market_tag(underlying_type: str, tv_info: dict | None) -> str:
    """Binance's underlyingType is authoritative; plain EQUITY splits into US-listed ADRs and US stocks."""
    tag = {"KR_EQUITY": "KR", "HK_EQUITY": "HK", "CN_EQUITY": "CN", "PREMARKET": "PRE"}.get(underlying_type)
    return tag or ("ADR" if tv_info and tv_info.get("type") == "dr" else "US")


def build_fundamental_summary(
    base_asset: str,
    underlying_type: str,
    tv_info: dict | None,
    sec_info: dict | None = None,
) -> dict:
    """Merge TradingView global fundamentals, SEC EDGAR filings, and Private/Pre-IPO metadata."""
    b = base_asset.upper()
    priv = PRIVATE_COMPANIES.get(b, {})
    mkt = resolve_market_tag(underlying_type, tv_info)
    company_name = (
        (tv_info or {}).get("company_name")
        or (sec_info or {}).get("company_name")
        or priv.get("company_name")
        or b
    )
    sector = (
        (tv_info or {}).get("sector")
        or (sec_info or {}).get("sic_description")
        or priv.get("sector")
        or "-"
    )
    exchange = (tv_info or {}).get("exchange") or priv.get("exchange") or underlying_type

    rev_yoy = (tv_info or {}).get("rev_yoy_fq")
    if rev_yoy is None and tv_info:
        rev_yoy = tv_info.get("rev_yoy_ttm")
    if rev_yoy is None and sec_info:
        rev_yoy = sec_info.get("rev_yoy_pct")

    ni_yoy = (tv_info or {}).get("ni_yoy_fq")
    if ni_yoy is None and sec_info:
        ni_yoy = sec_info.get("ni_yoy_pct")

    eps_yoy = (tv_info or {}).get("eps_yoy_fq")
    if eps_yoy is None and sec_info:
        eps_yoy = sec_info.get("eps_yoy_pct")

    last_earn = (tv_info or {}).get("last_earnings_date") or (sec_info or {}).get("last_earnings_date")
    days_since = (tv_info or {}).get("days_since_earnings")
    if days_since is None and sec_info:
        days_since = sec_info.get("days_since_earnings")

    next_earn = (tv_info or {}).get("next_earnings_date") or (sec_info or {}).get("next_earnings_est")
    days_to = (tv_info or {}).get("days_to_earnings")
    if days_to is None and sec_info:
        days_to = sec_info.get("days_to_earnings")

    return {
        "market": mkt,
        "company_name": company_name,
        "sector": sector,
        "exchange": exchange,
        "tv_symbol": (tv_info or {}).get("tv_symbol"),
        "market_cap_busd": (tv_info or {}).get("market_cap_busd"),
        "pe_ttm": (tv_info or {}).get("pe_ttm"),
        "ps_ttm": (tv_info or {}).get("ps_ttm"),
        "roe_fq": (tv_info or {}).get("roe_fq"),
        "debt_to_equity_fq": (tv_info or {}).get("debt_to_equity_fq"),
        "rev_fq_musd": (tv_info or {}).get("rev_fq_musd"),
        "rev_ttm_musd": (tv_info or {}).get("rev_ttm_musd"),
        "rev_yoy_pct": rev_yoy,
        "ni_fq_musd": (tv_info or {}).get("ni_fq_musd"),
        "ni_yoy_pct": ni_yoy,
        "eps_fq": (tv_info or {}).get("eps_fq"),
        "eps_ttm": (tv_info or {}).get("eps_ttm"),
        "eps_yoy_pct": eps_yoy,
        "gross_margin_ttm": (tv_info or {}).get("gross_margin_ttm"),
        "operating_margin_ttm": (tv_info or {}).get("operating_margin_ttm"),
        "net_margin_ttm": (tv_info or {}).get("net_margin_ttm"),
        "last_earnings_date": last_earn,
        "days_since_earnings": days_since,
        "next_earnings_date": next_earn,
        "days_to_earnings": days_to,
        "sec": sec_info,
    }


def weekday_bars(klines: list) -> list:
    """Drop Sat/Sun (UTC) candles: stock perps trade 24/7 but barely move while the exchanges are shut."""
    # ponytail: weekends only; exchange holidays still count as bars
    return [k for k in klines if datetime.fromtimestamp(k[0] / 1000, timezone.utc).weekday() < 5]


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
    out: list[float] = []
    for x in levels:
        if not out or abs(x - out[-1]) >= min_gap:
            out.append(x)
    return out


def pctile(series, value):
    return round(100 * sum(1 for v in series if v <= value) / len(series)) if series else None


def max_stop_fraction(leverage: int, mmr: float) -> float:
    return (1 / leverage - mmr) / 2


def equity_symbol_meta(info) -> dict[str, dict]:
    meta = {}
    for s in info["symbols"]:
        if (s.get("contractType") == "TRADIFI_PERPETUAL"
                and s.get("underlyingType") in STOCK_UNDERLYING_TYPES
                and s.get("quoteAsset") == "USDT"
                and s.get("status") == "TRADING"):
            f = {x["filterType"]: x for x in s["filters"]}
            meta[s["symbol"]] = {
                "base_asset": s["baseAsset"],
                "underlying_type": s["underlyingType"],
                "tick": f["PRICE_FILTER"]["tickSize"],
                "step": f["LOT_SIZE"]["stepSize"],
                "min_qty": f["LOT_SIZE"]["minQty"],
                "min_notional": f.get("MIN_NOTIONAL", {}).get("notional", "5"),
                "mmr": float(s.get("maintMarginPercent", "2.5")) / 100,
            }
    return meta


def features(sym: str, meta: dict, ticker: dict, premium: dict, spy_chg20: float | None, fund_info: dict) -> dict:
    d = weekday_bars(get_binance("/fapi/v1/klines", symbol=sym, interval="1d", limit=370)[:-1])
    h4 = weekday_bars(get_binance("/fapi/v1/klines", symbol=sym, interval="4h", limit=150)[:-1])
    h, lo, c = ([float(k[i]) for k in d] for i in (2, 3, 4))
    v = [float(k[7]) for k in d]
    c4 = [float(k[4]) for k in h4]
    mark = float(premium["markPrice"])
    index_price = float(premium.get("indexPrice") or mark)
    mark_index_dev_pct = abs(mark - index_price) / index_price * 100 if index_price else 0.0
    a = atr(h, lo, c)
    sh, sl = swings(h, lo) if len(h) >= 5 else ([], [])
    min_gap = (a or 0) * 0.25
    res_candidates = sorted(x for x in (sh + sl) if x > mark)
    sup_candidates = sorted((x for x in (sl + sh) if x < mark), reverse=True)
    oi = [float(x["sumOpenInterestValue"]) for x in get_binance(
        "/futures/data/openInterestHist", symbol=sym, period="1d", limit=30)]
    ls = [float(x["longShortRatio"]) for x in get_binance(
        "/futures/data/globalLongShortAccountRatio", symbol=sym, period="1d", limit=30)]
    top = [float(x["longShortRatio"]) for x in get_binance(
        "/futures/data/topLongShortPositionRatio", symbol=sym, period="1d", limit=30)]
    taker = [float(x["buySellRatio"]) for x in get_binance(
        "/futures/data/takerlongshortRatio", symbol=sym, period="1d", limit=7)]
    fund = [float(x["fundingRate"]) for x in get_binance("/fapi/v1/fundingRate", symbol=sym, limit=21)]
    chg20 = (c[-1] / c[-21] - 1) * 100 if len(c) > 21 else None
    return {
        "symbol": sym,
        "mark": mark,
        "index_price": index_price,
        "mark_index_dev_pct": round(mark_index_dev_pct, 3),
        "qv_musd": round(float(ticker["quoteVolume"]) / 1e6, 1),
        "chg24h": float(ticker["priceChangePercent"]),
        "chg7d": round((c[-1] / c[-8] - 1) * 100, 2) if len(c) > 8 else None,
        "chg20d": None if chg20 is None else round(chg20, 2),
        "rs20_vs_spy": None if chg20 is None or spy_chg20 is None else round(chg20 - spy_chg20, 2),
        "ema20": ema(c, 20), "ema50": ema(c, 50), "ema200": ema(c, 200),
        "ema20_4h": ema(c4, 20), "ema50_4h": ema(c4, 50),
        "rsi1d": rsi(c), "rsi4h": rsi(c4),
        "atr": a, "atr_pct": None if not a else a / mark * 100,
        "hi20": max(h[-20:]) if len(h) >= 20 else (max(h) if h else mark),
        "lo20": min(lo[-20:]) if len(lo) >= 20 else (min(lo) if lo else mark),
        "hi55": max(h[-55:]) if len(h) >= 55 else (max(h) if h else mark),
        "lo55": min(lo[-55:]) if len(lo) >= 55 else (min(lo) if lo else mark),
        "res": decluster(res_candidates, min_gap)[:3],
        "sup": decluster(sup_candidates, min_gap)[:3],
        "vol7_vs_30": round((sum(v[-7:]) / 7) / (sum(v[-30:]) / 30), 2) if len(v) >= 30 and sum(v[-30:]) > 0 else None,
        "oi_chg1d": round((oi[-1] / oi[-2] - 1) * 100, 2) if len(oi) > 1 and oi[-2] else None,
        "oi_chg7d": round((oi[-1] / oi[-8] - 1) * 100, 2) if len(oi) > 7 and oi[-8] else None,
        "ls": ls[-1] if ls else None, "ls_pct30": pctile(ls, ls[-1]) if ls else None,
        "top": top[-1] if top else None, "top_pct30": pctile(top, top[-1]) if top else None,
        "taker1d": taker[-1] if taker else None,
        "taker3d": round(sum(taker[-3:]) / len(taker[-3:]), 3) if taker else None,
        "fund": float(premium["lastFundingRate"]),
        "fund_avg": round(sum(fund) / len(fund), 6) if fund else None,
        "last5_daily": [[datetime.fromtimestamp(k[0] / 1000, timezone.utc).strftime("%m-%d"),
                         float(k[1]), float(k[2]), float(k[3]), float(k[4])] for k in d[-5:]],
        "fundamentals": fund_info,
        **meta,
    }


def fmt(x, p=2):
    return "-" if x is None else f"{x:.{p}f}"


def above(price, level):
    return "-" if level is None else ("Y" if price > level else "n")


def _tag_row(row: dict, leverage: int) -> dict:
    limit = max_stop_fraction(leverage, row["mmr"]) * 100
    pump = abs(row["chg24h"]) >= PUMP_CHANGE_24H or abs(row["fund"]) >= PUMP_FUNDING
    idx_bad = row["mark_index_dev_pct"] > MAX_MARK_INDEX_DEV * 100
    if idx_bad:
        row["flag"] = "INDEX"
    elif pump:
        row["flag"] = "PUMP"
    elif row["atr_pct"] and row["atr_pct"] <= limit:
        row["flag"] = "OK"
    else:
        row["flag"] = "ATR"
    return row


def _earn_tag(fund_info: dict | None) -> str:
    if not fund_info:
        return "-"
    d_since = fund_info.get("days_since_earnings")
    d_to = fund_info.get("days_to_earnings")
    if d_to is not None and 0 <= d_to <= 7:
        return f"{d_to}d!"
    if d_since is not None and 0 <= d_since <= 7:
        return f"-{d_since}d"
    if d_to is not None and d_to > 7:
        return f"{d_to}d"
    return "-"


def scan(args) -> None:
    meta = equity_symbol_meta(get_binance("/fapi/v1/exchangeInfo"))
    tickers = {t["symbol"]: t for t in get_binance("/fapi/v1/ticker/24hr") if t["symbol"] in meta}
    premium = {p["symbol"]: p for p in get_binance("/fapi/v1/premiumIndex") if p["symbol"] in meta}

    # Compute SPY benchmark 20d change for relative strength
    spy_chg20 = None
    if "SPYUSDT" in meta:
        spy_d = weekday_bars(get_binance("/fapi/v1/klines", symbol="SPYUSDT", interval="1d", limit=40)[:-1])
        spy_c = [float(k[4]) for k in spy_d]
        if len(spy_c) > 21:
            spy_chg20 = (spy_c[-1] / spy_c[-21] - 1) * 100

    all_bases = sorted({m["base_asset"] for m in meta.values()})
    tv_map = fetch_tv_fundamentals_batch(all_bases)
    sec_map = load_sec_tickers()
    market_filter = args.market.upper()

    # Filter candidates by quoteVolume, ETF status, and market filter
    candidates = []
    for sym, t in sorted(tickers.items(), key=lambda kv: -float(kv[1]["quoteVolume"])):
        if float(t["quoteVolume"]) < args.min_qv:
            continue
        base = meta[sym]["base_asset"].upper()
        utype = meta[sym]["underlying_type"]
        tv_info = tv_map.get(base)
        is_etf = (base in KNOWN_ETFS) or bool(tv_info and tv_info.get("is_etf"))
        if is_etf and not args.include_etfs:
            continue
        mkt = resolve_market_tag(utype, tv_info)
        if market_filter != "ALL" and mkt != market_filter:
            continue
        candidates.append(sym)
        if len(candidates) >= args.top:
            break

    def _process(sym: str) -> dict | None:
        base = meta[sym]["base_asset"].upper()
        utype = meta[sym]["underlying_type"]
        tv_info = tv_map.get(base)
        # Fetch SEC EDGAR if TradingView lacks YoY growth or earnings dates and ticker is in SEC map
        sec_info = None
        lookup = SEC_TICKER_ALIASES.get(base, base)
        if lookup in sec_map and (not tv_info or tv_info.get("rev_yoy_fq") is None or tv_info.get("next_earnings_date") is None):
            sec_info = fetch_sec_fundamentals(base, sec_map)
        fund_info = build_fundamental_summary(base, utype, tv_info, sec_info)
        row = features(sym, meta[sym], tickers[sym], premium[sym], spy_chg20, fund_info)
        return _tag_row(row, args.leverage)

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        rows = [r for r in pool.map(_process, candidates) if r is not None]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "leverage": args.leverage,
        "market_filter": market_filter,
        "spy_chg20d": round(spy_chg20, 2) if spy_chg20 is not None else None,
        "rows": rows,
    }, indent=1))

    etf_note = "ETFs included" if args.include_etfs else "ETFs excluded"
    print(f"{len(rows)} global equity perpetuals (market={market_filter}, {etf_note}), x{args.leverage}: "
          f"OK = tradeable, ATR = too volatile, PUMP = extreme move/funding, INDEX = mark/index >0.5%. Saved {OUT}")
    print(f"{'sym':<14}{'mkt':<4}{'flag':>5}{'mark':>9}{'24h':>6}{'7d':>6}{'20d':>6}{'rsSPY':>6}"
          f"{'>e20':>5}{'e20>50':>7}{'rsi1d':>6}{'rsi4h':>6}{'atr%':>5}{'resA':>5}{'supA':>5}"
          f"{'oi7d':>7}{'ls%':>4}{'top%':>5}{'fund%':>8}{'revYoY':>8}{'niYoY':>8}{'pe':>6}{'earn':>6}")
    for r in rows:
        a = r["atr"] or 0
        res = (r["res"][0] - r["mark"]) / a if r["res"] and a else None
        sup = (r["mark"] - r["sup"][0]) / a if r["sup"] and a else None
        trend = "-" if r["ema50"] is None else ("Y" if r["ema20"] > r["ema50"] else "n")
        fnd = r.get("fundamentals") or {}
        rev_str = f"{fnd['rev_yoy_pct']:.1f}%" if fnd.get("rev_yoy_pct") is not None else "-"
        ni_str = f"{fnd['ni_yoy_pct']:.1f}%" if fnd.get("ni_yoy_pct") is not None else "-"
        pe_str = f"{fnd['pe_ttm']:.1f}" if fnd.get("pe_ttm") is not None else "-"
        print(f"{r['symbol']:<14}{fnd.get('market', '-'):<4}{r['flag']:>5}{r['mark']:>9.5g}{r['chg24h']:>6.1f}"
              f"{fmt(r['chg7d'], 1):>6}{fmt(r['chg20d'], 1):>6}{fmt(r['rs20_vs_spy'], 1):>6}"
              f"{above(r['mark'], r['ema20']):>5}{trend:>7}{fmt(r['rsi1d'], 0):>6}"
              f"{fmt(r['rsi4h'], 0):>6}{fmt(r['atr_pct'], 1):>5}{fmt(res, 1):>5}{fmt(sup, 1):>5}"
              f"{fmt(r['oi_chg7d'], 1):>7}{str(r['ls_pct30']):>4}{str(r['top_pct30']):>5}"
              f" {r['fund'] * 100:>7.4f}%{rev_str:>8}{ni_str:>8}{pe_str:>6}{_earn_tag(fnd):>6}")


def detail(args) -> None:
    meta = equity_symbol_meta(get_binance("/fapi/v1/exchangeInfo"))
    sec_map = load_sec_tickers()
    req_syms = []
    for raw_sym in args.symbols:
        sym = raw_sym.upper()
        if not sym.endswith("USDT"):
            sym += "USDT"
        req_syms.append(sym)
    valid_bases = [meta[s]["base_asset"] for s in req_syms if s in meta]
    tv_map = fetch_tv_fundamentals_batch(valid_bases) if valid_bases else {}
    g = lambda x: "-" if x is None else f"{x:.6g}"  # noqa: E731

    for sym in req_syms:
        if sym not in meta:
            print(f"\n### {sym}: not a TRADING stock USDT perpetual on Binance USDⓈ-M")
            continue
        base = meta[sym]["base_asset"].upper()
        utype = meta[sym]["underlying_type"]
        tv_info = tv_map.get(base)
        sec_info = fetch_sec_fundamentals(base, sec_map)
        fnd = build_fundamental_summary(base, utype, tv_info, sec_info)
        ticker = get_binance("/fapi/v1/ticker/24hr", symbol=sym)
        r = features(sym, meta[sym], ticker, get_binance("/fapi/v1/premiumIndex", symbol=sym), None, fnd)
        a, m = r["atr"], r["mark"]
        print(f"\n### {sym} [{fnd['market']} / {fnd['exchange']}] — {fnd['company_name']} ({fnd['sector']})")
        print(f"  mark {g(m)} | index {g(r['index_price'])} (dev {r['mark_index_dev_pct']:.3f}%) "
              f"| ATR14d {g(a)} ({fmt(r['atr_pct'])}%) | qv24h ${r['qv_musd']}M")
        print(f"  1d EMA20 {g(r['ema20'])} EMA50 {g(r['ema50'])} EMA200 {g(r['ema200'])} "
              f"| 4h EMA20 {g(r['ema20_4h'])} EMA50 {g(r['ema50_4h'])}")
        print(f"  RSI1d {fmt(r['rsi1d'], 1)} RSI4h {fmt(r['rsi4h'], 1)} | 20d {g(r['hi20'])}/{g(r['lo20'])}"
              f" 55d {g(r['hi55'])}/{g(r['lo55'])} | vol7/30 {r['vol7_vs_30']}")
        if a:
            print(f"  resistance {[g(x) for x in r['res']]} = {[round((x - m) / a, 2) for x in r['res']]} ATR"
                  f" | support {[g(x) for x in r['sup']]} = {[round((m - x) / a, 2) for x in r['sup']]} ATR")
        print(f"  OI 1d {r['oi_chg1d']}% 7d {r['oi_chg7d']}% | L/S {g(r['ls'])} (pct30 {r['ls_pct30']})"
              f" | top {g(r['top'])} (pct30 {r['top_pct30']}) | taker 1d {r['taker1d']} 3d {r['taker3d']}"
              f" | funding {r['fund'] * 100:.4f}% (avg last 21 {fmt((r['fund_avg'] or 0) * 100, 4)}%)")
        print(f"  tick {r['tick']} step {r['step']} min_notional {r['min_notional']} mmr {r['mmr']:.4f}")

        # Global Fundamentals (TradingView + SEC EDGAR)
        d_to = fnd.get("days_to_earnings")
        d_since = fnd.get("days_since_earnings")
        warn = " ⚠️ SÁT NGÀY KQKD (<=7 ngày)" if (d_to is not None and 0 <= d_to <= 7) else ""
        print(f"  Earnings: Last {fnd.get('last_earnings_date') or '-'} ({d_since if d_since is not None else '-'}d ago) "
              f"| Next {fnd.get('next_earnings_date') or '-'} (in {d_to if d_to is not None else '-'}d){warn}")
        if tv_info:
            print(f"  Valuation & Ratios ({tv_info.get('tv_symbol')}, ccy {tv_info.get('currency')}): "
                  f"MktCap ${fmt(fnd.get('market_cap_busd'), 2)}B | P/E(TTM) {fmt(fnd.get('pe_ttm'), 2)} "
                  f"| P/S {fmt(fnd.get('ps_ttm'), 2)} | ROE {fmt(fnd.get('roe_fq'), 1)}% "
                  f"| D/E {fmt(fnd.get('debt_to_equity_fq'), 2)}")
            print(f"  Margins (TTM): Gross {fmt(fnd.get('gross_margin_ttm'), 1)}% "
                  f"| Operating {fmt(fnd.get('operating_margin_ttm'), 1)}% "
                  f"| Net {fmt(fnd.get('net_margin_ttm'), 1)}%")
            print(f"  Growth & Latest FQ: Rev(FQ) {fmt(fnd.get('rev_fq_musd'), 1)}M (YoY {fmt(fnd.get('rev_yoy_pct'), 1)}%) "
                  f"| NI(FQ) {fmt(fnd.get('ni_fq_musd'), 1)}M (YoY {fmt(fnd.get('ni_yoy_pct'), 1)}%) "
                  f"| EPS(FQ) {fmt(fnd.get('eps_fq'), 2)} (YoY {fmt(fnd.get('eps_yoy_pct'), 1)}%)")
        if sec_info and sec_info.get("quarters"):
            print(f"  SEC EDGAR CIK {sec_info['cik']:010d} ({sec_info['unit']}) Quarterly Filings (10-Q/10-K/20-F/6-K):")
            for q in sec_info["quarters"]:
                print(f"    {q['end']}: Rev {fmt(q['rev_m'], 1)}M | GP/Op {fmt(q['gp_m'], 1)}M "
                      f"(margin {fmt(q['margin_pct'], 1)}%) | NI {fmt(q['ni_m'], 1)}M | EPS {fmt(q['eps'], 2)}")
        elif not tv_info:
            print(f"  Fundamentals: Unlisted / Pre-IPO contract ({fnd['company_name']}) — check Google News / catalyst flow")

        print("  last closed days (date o/h/l/c):", " ".join(
            f"{k[0]} {g(k[1])}/{g(k[2])}/{g(k[3])}/{g(k[4])}" for k in r["last5_daily"]))
        today = get_binance("/fapi/v1/klines", symbol=sym, interval="1d", limit=1)[0]
        print(f"  today so far o {g(float(today[1]))} h {g(float(today[2]))} l {g(float(today[3]))}")
        bars = get_binance("/fapi/v1/klines", symbol=sym, interval="4h", limit=7)
        for k in bars:
            buy = float(k[9]) / float(k[5]) * 100 if float(k[5]) else 0
            t = datetime.fromtimestamp(k[0] / 1000, timezone.utc).strftime("%m-%d %HZ")
            print(f"   4h {t} {g(float(k[1]))}/{g(float(k[2]))}/{g(float(k[3]))}/{g(float(k[4]))}"
                  f" taker-buy {buy:.0f}%{'  LIVE, not closed' if k is bars[-1] else ''}")


def _fetch_google_rss(query: str, limit: int = 8) -> list[dict[str, str]]:
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        xml_bytes = resp.read()
    root = ET.fromstring(xml_bytes)
    items = []
    for item in root.findall("./channel/item")[:limit]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        source = (item.findtext("source") or "").strip()
        items.append({"published": pub, "source": source, "title": title, "link": link})
    return items


def news(args) -> None:
    sec_map = load_sec_tickers()
    bases = [s.upper().removesuffix("USDT") for s in args.symbols]
    tv_map = fetch_tv_fundamentals_batch(bases) if bases else {}
    queries = [
        ("WALL STREET", '("stock market" OR "Wall Street") (Nasdaq OR "S&P 500") when:2d'),
        ("ASIA", '(Kospi OR "Hang Seng" OR "Asian stocks") when:2d'),
        ("FED & YIELDS", '(Fed OR FOMC OR "Treasury yields") when:3d'),
        ("CHIPS & TARIFFS", '(semiconductor OR chip) (tariff OR "export controls") when:3d'),
    ]
    for base in bases:
        tv_info = tv_map.get(base)
        priv = PRIVATE_COMPANIES.get(base)
        lookup = SEC_TICKER_ALIASES.get(base, base)
        company_title = (
            (tv_info or {}).get("company_name")
            or (priv or {}).get("company_name")
            or (sec_map[lookup][1] if lookup in sec_map else base)
        )
        clean_title = (
            company_title.replace(" INC", "").replace(" CORP", "")
            .replace(" Co., Ltd.", "").replace(" Co., Ltd", "")
            .replace(" Corporation", "").replace(" Class B", "")
            .replace(" Class A", "").replace(" Class H", "")
            .replace(" Holdings Ltd", "").replace(" Group Limited", "")
            .replace(" Limited", "").replace(", Inc.", "").replace(" Inc.", "")
            .replace(" Corp.", "").replace(" Corp", "").strip()
        )
        queries.append((f"{base} ({company_title})", f"{clean_title} stock OR earnings OR AI when:7d"))

    for label, q in queries:
        print(f"\n=== NEWS: {label} (query: '{q}') ===")
        try:
            items = _fetch_google_rss(q, limit=args.limit)
        except Exception as exc:
            print(f"  Error fetching RSS: {exc}")
            continue
        if not items:
            print("  (no results)")
        for item in items:
            print(f"  [{item['published']}] ({item['source']}) {item['title']}")
            print(f"    {item['link']}")


def plan(args) -> None:
    sym = args.symbol.upper()
    if not sym.endswith("USDT"):
        sym += "USDT"
    side = args.side.upper()
    meta = equity_symbol_meta(get_binance("/fapi/v1/exchangeInfo")).get(sym)
    if meta is None:
        raise SystemExit(f"{sym} is not a TRADING stock USDT perpetual on Binance USDⓈ-M")
    base = meta["base_asset"].upper()
    utype = meta["underlying_type"]
    tv_info = fetch_tv_fundamentals_batch([base]).get(base)
    sec_map = load_sec_tickers()
    sec_info = fetch_sec_fundamentals(base, sec_map) if SEC_TICKER_ALIASES.get(base, base) in sec_map else None
    fnd = build_fundamental_summary(base, utype, tv_info, sec_info)
    is_etf = (base in KNOWN_ETFS) or bool(tv_info and tv_info.get("is_etf"))

    prem = get_binance("/fapi/v1/premiumIndex", symbol=sym)
    mark = float(prem["markPrice"])
    index_price = float(prem.get("indexPrice") or mark)
    mark_index_dev = abs(mark - index_price) / index_price if index_price else 0.0
    k1d = get_binance("/fapi/v1/klines", symbol=sym, interval="1d", limit=370)
    d = weekday_bars(k1d[:-1])
    h, lo, c = ([float(k[i]) for k in d] for i in (2, 3, 4))
    a = atr(h, lo, c)
    if a is None:
        raise SystemExit(f"{sym}: fewer than 15 weekday candles, so no ATR14 yet — skip this contract")
    entry = args.entry or mark
    sign = 1 if side == "LONG" else -1
    risk_unit, reward_unit = (entry - args.stop) * sign, (args.target - entry) * sign
    limit = max_stop_fraction(args.leverage, meta["mmr"])
    if risk_unit <= 0 or reward_unit <= 0:
        raise SystemExit(f"{side}: stop and target are on the wrong side of entry {entry}")
    fee_unit = entry * TAKER_FEE_ROUNDTRIP
    net_rr = (reward_unit - fee_unit) / (risk_unit + fee_unit)
    d_to = fnd.get("days_to_earnings")
    sh, sl = swings(h, lo)
    # swings() needs two later bars to confirm a point, so the last two closed weekdays and today go in as they are
    recent = d[-2:] + weekday_bars(k1d[-1:])
    near = sorted({x for x in sh + sl + [float(k[i]) for k in recent for i in (2, 3)]
                   if abs(x - args.stop) < STOP_CLEARANCE_ATR * a})
    checks = {
        f"Single-stock contract ({fnd['market']} — {fnd['company_name']}, not ETF)": not is_etf,
        f"|mark - index| / index <= {MAX_MARK_INDEX_DEV * 100:.2f}% (actual {mark_index_dev * 100:.3f}%)": (
            mark_index_dev <= MAX_MARK_INDEX_DEV
        ),
        "stop >= 1 ATR": risk_unit >= a,
        f"stop <= {limit * 100:.2f}% (x{args.leverage} liquidation buffer)": risk_unit / entry <= limit,
        f"gross R:R >= {args.min_rr}": reward_unit / risk_unit >= args.min_rr,
        f"stop >= {STOP_CLEARANCE_ATR} ATR from daily highs/lows"
        + (f" (too close: {', '.join(f'{x:.6g}' for x in near)})" if near else ""): not near,
        f"no earnings within the {args.horizon_days}-day holding window (next {fnd.get('next_earnings_date') or '-'})": (
            d_to is None or not 0 <= d_to <= args.horizon_days),
    }
    step, min_qty = Decimal(meta["step"]), Decimal(meta["min_qty"])
    raw = min(args.capital * args.risk / risk_unit, args.capital * args.margin_cap * args.leverage / entry)
    qty = (Decimal(str(raw)) / step).to_integral_value(rounding=ROUND_FLOOR) * step
    notional = float(qty) * entry
    checks[f"size >= exchange minimum (qty {meta['min_qty']}, notional {meta['min_notional']})"] = (
        qty >= min_qty and notional >= float(meta["min_notional"]))
    liq = entry * (1 - 1 / args.leverage + meta["mmr"]) if side == "LONG" else entry * (
        1 + 1 / args.leverage - meta["mmr"])
    if abs(entry / mark - 1) <= args.entry_band:
        order = "vào ngay"
    elif (side == "LONG" and entry < mark) or (side == "SHORT" and entry > mark):
        order = "lệnh chờ (limit)"
    else:
        order = "lệnh chờ (stop)"

    print(f"{side} {sym} [{fnd['market']}] ({fnd['company_name']}) x{args.leverage} | mark {mark:.6g} "
          f"| index {index_price:.6g} (dev {mark_index_dev * 100:.3f}%) | ATR14d {a:.6g} ({a / mark * 100:.2f}%) | {order}")
    print(f"entry {entry:.6g}  stop {args.stop:.6g} ({(args.stop / entry - 1) * 100:+.2f}%,"
          f" {risk_unit / a:.2f} ATR)  target {args.target:.6g} ({(args.target / entry - 1) * 100:+.2f}%)"
          f"  R:R {reward_unit / risk_unit:.2f} (net ~{net_rr:.2f})")
    print(f"size {qty.normalize()} (step {meta['step']}) notional {notional:.2f} margin "
          f"{notional / args.leverage:.2f} risk {float(qty) * risk_unit:.2f} reward "
          f"{float(qty) * reward_unit:.2f} USDT | liquidation ~{liq:.6g}")
    d_since = fnd.get("days_since_earnings")
    if d_to is not None and 0 <= d_to <= 7:
        print(f"⚠️ CẢNH BÁO KQKD: Dự kiến công bố KQKD trong {d_to} ngày ({fnd.get('next_earnings_date')})")
    elif fnd.get("last_earnings_date") or fnd.get("next_earnings_date"):
        print(f"KQKD: Gần nhất {fnd.get('last_earnings_date') or '-'} ({d_since if d_since is not None else '-'}d trước) "
              f"| Kế tiếp: {fnd.get('next_earnings_date') or '-'} (còn ~{d_to if d_to is not None else '-'}d)")
    for name, ok in checks.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print("VERDICT:", "PASS" if all(checks.values()) else "FAIL — fix the levels or drop the trade")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan")
    p.add_argument("--top", type=int, default=40)
    p.add_argument("--min-qv", type=float, default=1_000_000)
    p.add_argument("--market", choices=["all", "us", "kr", "hk", "cn", "adr", "pre"], default="all")
    p.add_argument("--include-etfs", action="store_true")
    p.add_argument("--leverage", type=int, default=5)
    p.add_argument("--workers", type=int, default=6)
    p = sub.add_parser("detail")
    p.add_argument("symbols", nargs="+")
    p = sub.add_parser("news")
    p.add_argument("symbols", nargs="*")
    p.add_argument("--limit", type=int, default=6)
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
    p.add_argument("--horizon-days", type=int, default=20)
    args = parser.parse_args()
    {"scan": scan, "detail": detail, "news": news, "plan": plan}[args.cmd](args)


if __name__ == "__main__":
    main()
