"""Luồng chạy Smart Money (chạy trên máy, không cần server):

FMarket (danh mục quỹ) → dòng tiền theo kỳ báo cáo → kho giá cục bộ (chỉ tải ngày thiếu)
→ Simplize (cơ bản) → chấm điểm → file JSON cho dashboard + CSV.
"""

import argparse
import io
import sys

import numpy as np
import pandas as pd

from market_data import price_store

from . import config, export, flow, market, scoring, snapshots, sources

STOCK_FIELDS_ORDER = [
    "Xep_Hang", "Ma_Co_Phieu", "Ten_Cong_Ty", "San", "Nganh", "Nhom_Nganh", "Nganh_Chi_Tiet", "Nhom_Chien_Luoc",
    "Final_Score", "Data_Coverage", "Loai_Tru", "Canh_Bao_Du_Lieu",
    "Score_Value", "Score_Quality", "Score_Growth", "Score_Momentum", "Score_LowRisk", "Score_SmartMoney", "Score_Upside",
    "Gia_Hien_Tai", "Gia_Muc_Tieu", "Upside_pct", "So_Bao_Cao_MT", "Ngay_Bao_Cao_Moi",
    "PE", "PB", "ROE_pct", "ROA_pct", "Tang_Truong_LNST_pct", "Tang_Truong_DT_pct", "Co_Tuc_pct", "Von_Hoa_VND",
    "Ret_1M", "Ret_3M", "Ret_6M", "Mom_6_1", "Volatility_60D", "Max_Drawdown_6M", "Beta_120D", "ADV_20D_VND", "Ngay_Gia",
    "So_Luong_Quy", "Tong_Gia_Tri_Hien_Tai_VND", "Tong_Gia_Tri_Ky_Truoc_VND", "Ty_Le_So_Huu_Quy_pct",
    "Dong_Tien_Rong_VND", "Dong_Tien_Mua_VND", "Dong_Tien_Ban_VND", "Dong_Tien_Tren_Von_Hoa_pct", "Ty_Le_Dong_Tien",
    "So_Quy_Tang", "So_Quy_Giam", "So_Quy_Mua_Moi", "So_Quy_Thoat", "Tin_Hieu_Dong_Tien", "Co_Du_Lieu_Dong_Tien",
]


def log(msg):
    print(msg, flush=True)


def run(save=True):
    now = sources.get_server_now()
    run_date = now.strftime("%Y-%m-%d")
    warnings = []
    log(f"== SMART MONEY · {now:%Y-%m-%d %H:%M} ==")

    # 1) Danh mục quỹ hiện tại
    log("1/5 Quét danh mục quỹ FMarket...")
    current, fetch_report = sources.fetch_fmarket_holdings(run_date, run_date)
    if current.empty:
        raise RuntimeError("Không lấy được danh mục quỹ nào từ FMarket")
    history = snapshots.load_local_history(before_date=run_date)
    current, carried = snapshots.carry_forward_failed_funds(current, history, fetch_report["failed"])
    fetch_report["funds_carried"] = carried
    log(
        f"   {fetch_report['funds_live']} quỹ có cổ phiếu / {fetch_report['funds_listed']} quỹ đang hoạt động, "
        f"lỗi {fetch_report['funds_failed']}, giữ lại kỳ trước {len(carried)}"
    )
    if fetch_report["funds_failed"]:
        warnings.append(f"{fetch_report['funds_failed']} quỹ lỗi khi tải; đã dùng dữ liệu kỳ gần nhất cho {len(carried)} quỹ")
    if not history.empty:
        last_snapshot = history["Snapshot_Stamp"].max()[:10]
        gap = (pd.Timestamp(run_date) - pd.Timestamp(last_snapshot)).days
        if gap > 35:
            warnings.append(f"Lần chạy trước cách đây {gap} ngày — có thể đã bỏ lỡ một kỳ báo cáo danh mục của quỹ")
    if save:
        path = snapshots.save_snapshot(current, run_date)
        log(f"   Snapshot: {path.name}")

    # 2) Giá: cập nhật ngày thiếu trong kho cục bộ
    full_history = pd.concat([history, current], ignore_index=True) if not history.empty else current
    all_tickers = sorted(full_history["Ma_Co_Phieu"].dropna().astype(str).str.upper().unique())
    log(f"2/5 Cập nhật giá {len(all_tickers) + 1} mã (chỉ tải ngày còn thiếu)...")
    price_frames, price_stats = price_store.update_many(all_tickers + [config.BENCHMARK_SYMBOL])
    log(f"   {price_store.describe_stats(price_stats)} | nguồn: {price_store.source_report()}")
    price_map = {t: sources.to_market_frame(df) for t, df in price_frames.items()}
    benchmark = price_map.get(config.BENCHMARK_SYMBOL)
    missing_price = [t for t in all_tickers if price_map.get(t) is None]
    if benchmark is None:
        warnings.append("Không có dữ liệu VNINDEX (beta sẽ trống)")
    if price_stats.get("failed"):
        warnings.append(f"Lỗi cập nhật giá {len(price_stats['failed'])} mã (dùng dữ liệu cũ): {', '.join(price_stats['failed'][:10])}")
    # Không có giá thì mọi mã đều bị loại vì thiếu thanh khoản → dừng hẳn thay vì xuất dashboard trống
    usable_prices = sum(1 for t in all_tickers if price_map.get(t) is not None)
    if usable_prices < len(all_tickers) * 0.5:
        raise RuntimeError(
            f"Chỉ có giá của {usable_prices}/{len(all_tickers)} mã — nguồn giá không truy cập được. "
            "Kiểm tra kết nối tới SSI (máy chủ nước ngoài có thể bị chặn)."
        )

    # 3) Dòng tiền theo kỳ báo cáo
    log(f"3/5 Tính dòng tiền theo kỳ báo cáo ({history['Snapshot_Stamp'].nunique() if not history.empty else 0} snapshot trước đó)...")
    pair_flow, ticker_flow, flow_summary = flow.compute_flows(
        full_history,
        run_date,
        lambda t, d0, d1: market.price_ratio_from_history(price_map.get(t), d0, d1),
        active_funds=set(current["Ten_Quy"]),
    )
    log(
        f"   Kỳ so sánh phổ biến: {flow_summary.get('period_prev')} → {flow_summary.get('period_current')} · "
        f"{flow_summary.get('funds_with_baseline', 0)} quỹ có kỳ trước, {flow_summary.get('funds_no_baseline', 0)} quỹ chưa có"
    )

    # 4) Cơ bản + chấm điểm
    held = ticker_flow[ticker_flow["So_Luong_Quy"] > 0]["Ma_Co_Phieu"].tolist()
    log(f"4/5 Dữ liệu cơ bản Simplize ({len(held)} mã) + chấm điểm...")
    simplize = sources.SimplizeClient()
    fundamentals = sources.fetch_many(lambda t: simplize.get_fundamentals(t, now), held)
    missing_fund = [t for t, v in fundamentals.items() if v is None]
    if missing_fund:
        warnings.append(f"Simplize thiếu dữ liệu {len(missing_fund)} mã: {', '.join(missing_fund[:10])}")

    window_start = pd.Timestamp(run_date) - pd.Timedelta(days=config.PRICE_HISTORY_LOOKBACK_DAYS)
    sector_by_ticker = current.groupby("Ma_Co_Phieu")["Nganh"].first()
    flow_by_ticker = ticker_flow.set_index("Ma_Co_Phieu")
    rows = []
    for ticker in held:
        row = {"Ma_Co_Phieu": ticker, "Nganh": sector_by_ticker.get(ticker)}
        row.update(flow_by_ticker.loc[ticker].to_dict())
        row.update(fundamentals.get(ticker) or {})
        hist = price_map.get(ticker)
        if hist is not None:
            hist = hist[hist["date"] >= window_start]
        row.update(market.compute_price_metrics(hist, benchmark))
        rows.append(row)
    universe = pd.DataFrame(rows)
    for col in ["PE", "PB", "ROE_pct", "ROA_pct", "Tang_Truong_LNST_pct", "Tang_Truong_DT_pct", "Von_Hoa_VND",
                "Upside_pct", "So_Bao_Cao_MT", "Nhom_Nganh", "Loai_CK", "Co_Tuc_pct"]:
        if col not in universe:
            universe[col] = np.nan
    scored = scoring.classify_strategy_groups(scoring.score_universe(universe))
    excluded = int(scored["Loai_Tru"].notna().sum())
    log(f"   {len(scored) - excluded} mã được chấm điểm, {excluded} mã bị loại (ETF/thanh khoản)")
    scored = scored[[c for c in STOCK_FIELDS_ORDER if c in scored.columns]]

    meta = {
        "run_date": run_date,
        "generated_at": now.isoformat(),
        "model_version": "v4-multifactor",
        "factor_weights": config.FACTOR_WEIGHTS,
        "min_adv_vnd": config.MIN_ADV_VND,
        "fetch": {k: v for k, v in fetch_report.items() if k != "failed"},
        "failed_funds": fetch_report["failed"],
        "prices": {k: len(v) for k, v in price_stats.items()},
        "price_sources": price_store.source_report(),
        "flow": {k: v for k, v in flow_summary.items() if k != "funds"},
        "funds": flow_summary.get("funds", []),
        "tickers_scored": int(len(scored) - excluded),
        "tickers_excluded": excluded,
        "price_missing": missing_price,
        "warnings": warnings,
    }
    top_pairs = pair_flow[
        pair_flow["Dong_Tien_VND"].abs().fillna(0).ge(config.MIN_FLOW_ABS_VND)
        | pair_flow["Trang_Thai"].isin(["NEW_BUY", "EXIT"])
    ].sort_values("Dong_Tien_VND", key=lambda s: s.abs(), ascending=False)

    # 5) Lưu kết quả
    log("5/5 Lưu kết quả...")
    print_summary(scored, meta)
    if save:
        config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        scored.to_csv(config.OUTPUT_DIR / f"scores_{run_date}.csv", index=False, encoding="utf-8-sig")
        pair_flow.to_csv(config.OUTPUT_DIR / f"fund_flows_{run_date}.csv", index=False, encoding="utf-8-sig")
        export.write_run(
            run_date,
            meta,
            {r["Ma_Co_Phieu"]: r for r in scored.to_dict(orient="records")},
            top_pairs.to_dict(orient="records"),
        )
        dates = export.rebuild_indexes()
        log(f"   Dashboard: {len(dates)} ngày dữ liệu · CSV: {config.OUTPUT_DIR}")
    return scored, pair_flow, meta


def _fmt_bn(value):
    return "--" if value is None or not np.isfinite(value) else f"{value / 1e9:,.1f} tỷ"


def print_summary(scored, meta):
    ranked = scored[scored["Loai_Tru"].isna()]
    cols = ["Xep_Hang", "Ma_Co_Phieu", "Nhom_Chien_Luoc", "Final_Score", "Score_Value", "Score_Quality",
            "Score_Momentum", "Score_LowRisk", "Score_SmartMoney"]
    with pd.option_context("display.width", 200, "display.max_columns", 20, "display.float_format", "{:,.1f}".format):
        print("\nTOP 15 THEO ĐIỂM:")
        print(ranked[[c for c in cols if c in ranked]].head(15).to_string(index=False))
        flows = scored.dropna(subset=["Dong_Tien_Rong_VND"]).sort_values("Dong_Tien_Rong_VND")
        print(f"\nDÒNG TIỀN QUỸ ({meta['flow'].get('period_prev')} → {meta['flow'].get('period_current')}):")
        for label, frame in (("Mua ròng", flows.tail(8).iloc[::-1]), ("Bán ròng", flows.head(8))):
            items = ", ".join(f"{r.Ma_Co_Phieu} {_fmt_bn(r.Dong_Tien_Rong_VND)}" for r in frame.itertuples())
            print(f"  {label}: {items}")
    if meta["warnings"]:
        print("\nCẢNH BÁO:")
        for w in meta["warnings"]:
            print(f"  - {w}")


def ensure_utf8_stdout():
    if hasattr(sys.stdout, "buffer") and (sys.stdout.encoding or "").lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)


def main(argv=None):
    ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="Smart Money pipeline (chạy cục bộ)")
    parser.add_argument("--dry-run", action="store_true", help="Không lưu snapshot/kết quả (kiểm thử)")
    args = parser.parse_args(argv)
    run(save=not args.dry_run)


if __name__ == "__main__":
    main()
