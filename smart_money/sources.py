"""Thu thập dữ liệu từ FMarket (danh mục quỹ), Simplize (cơ bản) và SSI (giá)."""

import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from . import config
from .http import make_session

_session = make_session()
_lock = threading.Lock()


def _ms_to_date(ms):
    if not ms or not isinstance(ms, (int, float)) or ms <= 0:
        return None
    return pd.Timestamp(int(ms), unit="ms", tz="UTC").tz_convert(config.VN_TZ).strftime("%Y-%m-%d")


# ----------------------------------------------------------------- SSI time
def get_server_now():
    """Thời gian hiện tại (giờ VN) theo máy chủ SSI; lỗi thì dùng giờ máy."""
    try:
        resp = _session.get(config.SSI_TIME_URL, timeout=5)
        if resp.status_code == 200:
            ms = resp.json().get("data")
            if isinstance(ms, (int, float)) and ms > 0:
                return pd.Timestamp(int(ms), unit="ms", tz="UTC").tz_convert(config.VN_TZ)
    except Exception:
        pass
    return pd.Timestamp.now(tz=config.VN_TZ)


# ----------------------------------------------------------------- FMarket
def list_fmarket_funds():
    """Danh sách quỹ đang hoạt động có thể nắm cổ phiếu (STOCK, BALANCED)."""
    body = {
        "types": config.FMARKET_PRODUCT_TYPES,
        "issuerIds": [],
        "sortOrder": "DESC",
        "sortField": "navTo6Months",
        "page": 1,
        "pageSize": 200,
        "isIpo": False,
        "fundAssetTypes": [],
        "bondRemainPeriods": [],
        "searchField": "",
        "isBuyByReward": False,
        "thirdAppIds": [],
    }
    resp = _session.post(
        config.FMARKET_FILTER_URL,
        data=json.dumps(body),
        headers={"Content-Type": "application/json"},
        timeout=20,
    )
    resp.raise_for_status()
    rows = (resp.json().get("data") or {}).get("rows") or []
    funds = []
    for row in rows:
        asset_type = row.get("dataFundAssetType")
        asset_code = asset_type.get("code") if isinstance(asset_type, dict) else asset_type
        if row.get("status") != "PRODUCT_ACTIVE" or asset_code not in config.FMARKET_FUND_ASSET_TYPES:
            continue
        funds.append({"id": row["id"], "shortName": row.get("shortName"), "assetType": asset_code})
    return funds


def _fetch_fund_detail(fund):
    try:
        resp = _session.get(config.FMARKET_PRODUCT_URL.format(fund_id=fund["id"]), timeout=15)
        if resp.status_code != 200:
            return fund, None, f"HTTP {resp.status_code}"
        return fund, resp.json().get("data") or {}, None
    except Exception as exc:  # lỗi mạng sau khi đã retry
        return fund, None, str(exc)[:120]


def fetch_fmarket_holdings(run_stamp, run_date):
    """Quét danh mục top holdings của các quỹ.

    Trả về (DataFrame holdings, fetch_report dict).
    Quỹ lỗi mạng được liệt kê trong fetch_report["failed"] để pipeline giữ lại dữ liệu kỳ trước.
    """
    funds = list_fmarket_funds()
    rows, failed, no_stock = [], [], []

    with ThreadPoolExecutor(max_workers=config.HTTP_WORKERS) as pool:
        for fund, data, error in pool.map(_fetch_fund_detail, funds):
            if error is not None:
                failed.append({"id": fund["id"], "name": fund["shortName"], "error": error})
                continue
            report = data.get("fundReport") or {}
            aum = report.get("totalAssetValue") or 0
            report_date = _ms_to_date(report.get("reportTime"))
            stocks = [h for h in (data.get("productTopHoldingList") or []) if h.get("type") == "STOCK"]
            if not stocks:
                no_stock.append(fund["shortName"])
                continue
            for h in stocks:
                pct = float(h.get("netAssetPercent") or 0)
                volume = h.get("volume")
                asset_value = h.get("assetValue")
                rows.append(
                    {
                        "Snapshot_Stamp": run_stamp,
                        "Snapshot_Date": run_date,
                        "Fund_Id": fund["id"],
                        "Ten_Quy": data.get("shortName") or fund["shortName"],
                        "Loai_Quy": fund["assetType"],
                        "Ma_Co_Phieu": str(h.get("stockCode") or "").strip().upper(),
                        "Nganh": h.get("industry") or "Khác",
                        "AUM_VND": float(aum),
                        "Ty_Le_Trong_Quy": pct,
                        "Gia_Tri_VND": float(aum) * pct / 100.0,
                        "So_Co_Phieu": float(volume) if volume else np.nan,
                        "Gia_Tri_Tai_San_VND": float(asset_value) if asset_value else np.nan,
                        "Report_Date": report_date,
                        "Fetch_Status": "LIVE",
                    }
                )

    report = {
        "funds_listed": len(funds),
        "funds_live": len({r["Ten_Quy"] for r in rows}),
        "funds_failed": len(failed),
        "failed": failed,
        "funds_without_stock": no_stock,
    }
    return pd.DataFrame(rows), report


# ----------------------------------------------------------------- Simplize
class SimplizeClient:
    def __init__(self):
        self._build_id = None

    def _refresh_build_id(self):
        resp = _session.get(config.SIMPLIZE_HOME_URL, timeout=15)
        match = re.search(r'"buildId":"(.*?)"', resp.text)
        if not match:
            raise RuntimeError("Không lấy được buildId của Simplize")
        with _lock:
            self._build_id = match.group(1)

    def _get_page_props(self, ticker):
        if self._build_id is None:
            self._refresh_build_id()
        for attempt in range(2):
            url = config.SIMPLIZE_REPORT_URL.format(build_id=self._build_id, ticker=ticker)
            resp = _session.get(url, timeout=15)
            if resp.status_code == 200:
                return resp.json().get("pageProps") or {}
            if resp.status_code == 404 and attempt == 0:
                # buildId đổi sau mỗi lần Simplize deploy
                self._refresh_build_id()
                continue
            return None
        return None

    def get_fundamentals(self, ticker, as_of):
        try:
            props = self._get_page_props(ticker)
        except Exception:
            return None
        if not props or not props.get("summary"):
            return None
        s = props["summary"]

        targets, latest_report = [], None
        cutoff = as_of - pd.Timedelta(days=config.ANALYST_TARGET_MAX_AGE_DAYS)
        for rep in props.get("analysisReports") or []:
            target = rep.get("targetPrice")
            issue = pd.to_datetime(rep.get("issueDate"), format="%d/%m/%Y", errors="coerce")
            if not target or target <= 0 or pd.isna(issue):
                continue
            issue = issue.tz_localize(config.VN_TZ)
            if issue < cutoff:
                continue
            targets.append(float(target))
            latest_report = max(latest_report, issue) if latest_report is not None else issue

        price = s.get("priceClose")
        target_median = float(np.median(targets)) if targets else np.nan
        upside = (target_median / price - 1) * 100 if targets and price else np.nan

        return {
            "Ten_Cong_Ty": s.get("nameVi") or s.get("name"),
            "San": s.get("stockExchange"),
            "Loai_CK": s.get("type"),
            "Nhom_Nganh": s.get("bcEconomicSectorName"),
            "Nganh_Chi_Tiet": (s.get("industryActivity") or "").strip() or None,
            "Gia_Hien_Tai": price,
            "PE": s.get("peRatio"),
            "PB": s.get("pbRatio"),
            "ROE_pct": s.get("roe"),
            "ROA_pct": s.get("roa"),
            "EPS": s.get("epsRatio"),
            "Von_Hoa_VND": s.get("marketCap"),
            "Tang_Truong_LNST_pct": s.get("netIncomeLtmGrowth"),
            "Tang_Truong_DT_pct": s.get("revenueLtmGrowth"),
            "Co_Tuc_pct": s.get("dividendYieldCurrent"),
            "Beta_5Y": s.get("beta5y"),
            "Gia_Muc_Tieu": target_median,
            "So_Bao_Cao_MT": len(targets),
            "Ngay_Bao_Cao_Moi": latest_report.strftime("%Y-%m-%d") if latest_report is not None else None,
            "Upside_pct": upside,
        }


# ----------------------------------------------------------------- giá (kho cục bộ)
def to_market_frame(prices):
    """Chuyển dữ liệu kho giá sang dạng dùng cho chỉ số rủi ro: date, close, volume, ret_1d."""
    if prices is None or prices.empty:
        return None
    frame = prices.rename(columns={"time": "date"})[["date", "close", "volume"]].copy()
    frame = frame.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
    frame["ret_1d"] = frame["close"].pct_change()
    return frame


def fetch_many(func, items, workers=config.HTTP_WORKERS):
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return dict(zip(items, pool.map(func, items)))
