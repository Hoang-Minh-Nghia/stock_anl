import {
  FACTORS, FLOW_STATUS, PALETTE, applyChartDefaults, createTable, esc, fmt, fmtPct, fmtVnd, groupTag, GROUPS,
  heatCell, loadData, loadHistory, modelLabel, num, renderStatus, scoreCell, signClass,
} from "./common.js?v=5.1.0";

const $ = (id) => document.getElementById(id);
const state = { data: null, rows: [] };
let trendChart = null;

const columns = [
  { key: "Xep_Hang", header: "#", align: "num", render: (r) => (r.Xep_Hang ? esc(r.Xep_Hang) : `<span class="muted">–</span>`) },
  {
    key: "Ma_Co_Phieu",
    header: "Mã",
    render: (r) => `<span class="ticker">${esc(r.Ma_Co_Phieu)}</span>${r.Loai_Tru ? `<div class="muted" style="font-size:11px">${esc(r.Loai_Tru)}</div>` : ""}`,
  },
  { key: "Nhom_Nganh", header: "Ngành", render: (r) => `<span class="nowrap">${esc(r.Nhom_Nganh || r.Nganh || "--")}</span>` },
  { key: "Nhom_Chien_Luoc", header: "Nhóm", render: (r) => (r.Nhom_Chien_Luoc ? groupTag(r.Nhom_Chien_Luoc) : "--") },
  { key: "Final_Score", header: "Điểm", render: (r) => scoreCell(r.Final_Score) },
  ...FACTORS.map((f) => ({ key: f.key, header: f.label, align: "num", render: (r) => heatCell(r[f.key]) })),
  { key: "Gia_Hien_Tai", header: "Giá", align: "num", render: (r) => fmt(r.Gia_Hien_Tai, 0) },
  { key: "Upside_pct", header: "Upside", align: "num", title: "Theo trung vị giá mục tiêu ≤180 ngày", render: (r) => `<span class="${signClass(r.Upside_pct)}">${fmtPct(r.Upside_pct, 0, { signed: true })}</span>` },
  { key: "PE", header: "P/E", align: "num", render: (r) => fmt(r.PE, 1) },
  { key: "PB", header: "P/B", align: "num", render: (r) => fmt(r.PB, 2) },
  { key: "ROE_pct", header: "ROE", align: "num", render: (r) => fmtPct(r.ROE_pct, 1) },
  { key: "Dong_Tien_Rong_VND", header: "Dòng tiền quỹ", align: "num", render: (r) => `<span class="${signClass(r.Dong_Tien_Rong_VND)}">${fmtVnd(r.Dong_Tien_Rong_VND, { signed: true })}</span>` },
  { key: "Data_Coverage", header: "Độ phủ", align: "num", title: "Tỷ lệ dữ liệu nhân tố có sẵn", render: (r) => fmtPct(r.Data_Coverage, 0, { ratio: true }) },
];

const table = createTable($("ranking-table"), {
  columns,
  defaultSort: { key: "Final_Score", dir: "desc" },
  emptyText: "Không có mã phù hợp bộ lọc",
  rowClass: (r) => (r.Loai_Tru ? "excluded" : ""),
  onRowClick: openDrawer,
});

function applyFilters() {
  const q = $("search").value.trim().toLowerCase();
  const sector = $("filter-sector").value;
  const group = $("filter-group").value;
  const showExcluded = $("show-excluded").checked;
  const rows = state.rows.filter((r) => {
    if (!showExcluded && r.Loai_Tru) return false;
    if (sector && (r.Nhom_Nganh || r.Nganh) !== sector) return false;
    if (group && r.Nhom_Chien_Luoc !== group) return false;
    if (q && !`${r.Ma_Co_Phieu} ${r.Ten_Cong_Ty || ""}`.toLowerCase().includes(q)) return false;
    return true;
  });
  $("row-count").textContent = `${rows.length} mã`;
  table.update(rows);
}

function fillSelect(select, values) {
  const current = select.value;
  const first = select.options[0].outerHTML;
  select.innerHTML = first + values.map((v) => `<option value="${esc(v)}">${esc(v)}</option>`).join("");
  select.value = values.includes(current) ? current : "";
}

function renderKpis(data) {
  const ranked = state.rows.filter((r) => !r.Loai_Tru && Number.isFinite(num(r.Final_Score)));
  const excluded = state.rows.length - ranked.length;
  $("kpi-count").textContent = fmt(ranked.length, 0);
  $("kpi-count-sub").textContent = excluded ? `${excluded} mã bị loại (ETF / thanh khoản)` : "Không có mã bị loại";

  const top = [...ranked].sort((a, b) => num(b.Final_Score) - num(a.Final_Score))[0];
  $("kpi-top").textContent = top ? top.Ma_Co_Phieu : "--";
  $("kpi-top-sub").textContent = top ? `${fmt(top.Final_Score, 1)} điểm · ${top.Nhom_Nganh || top.Nganh || ""}` : "--";

  const flow = data.meta?.flow || {};
  $("kpi-period").textContent = flow.period_current ? `${flow.period_prev} → ${flow.period_current}` : "--";
  $("kpi-period").style.fontSize = "17px";
  $("kpi-period-sub").textContent = flow.funds_total ? `${flow.funds_with_baseline}/${flow.funds_total} quỹ có kỳ so sánh` : "--";

  const net = state.rows.reduce((s, r) => s + (Number.isFinite(num(r.Dong_Tien_Rong_VND)) ? num(r.Dong_Tien_Rong_VND) : 0), 0);
  $("kpi-flow").textContent = fmtVnd(net, { signed: true });
  $("kpi-flow").className = `value ${signClass(net)}`;
  const buyers = state.rows.filter((r) => r.Tin_Hieu_Dong_Tien === "MUA").length;
  const sellers = state.rows.filter((r) => r.Tin_Hieu_Dong_Tien === "BAN").length;
  $("kpi-flow-sub").textContent = `${buyers} mã mua ròng · ${sellers} mã bán ròng`;

  const weights = data.meta?.factor_weights;
  if (weights) {
    $("weights").textContent = FACTORS.map((f) => `${f.label} ${Math.round((weights[f.key] || 0) * 100)}%`).join(" · ");
  }
}

const TREND_DAYS = 60;

function renderTrend(history, data) {
  // Chỉ vẽ các ngày cùng phiên bản mô hình với ngày đang xem (thang điểm khác nhau giữa các mô hình)
  const model = data.runs[data.date]?.model_version;
  const usable = Object.keys(history || {})
    .filter((d) => d <= data.date && data.runs[d]?.model_version === model)
    .sort()
    .slice(-TREND_DAYS);
  const top = [...state.rows]
    .filter((r) => !r.Loai_Tru && Number.isFinite(num(r.Final_Score)))
    .sort((a, b) => num(b.Final_Score) - num(a.Final_Score))
    .slice(0, 10)
    .map((r) => r.Ma_Co_Phieu);

  if (usable.length < 2) {
    $("trend-hint").textContent = "Chưa đủ lịch sử cho mô hình hiện tại — mỗi lần chạy sẽ thêm 1 ngày";
  } else {
    $("trend-hint").textContent = `${usable.length} ngày (mô hình ${modelLabel(model)}) · top 10 của ngày đang xem`;
  }
  if (!window.Chart) return;
  applyChartDefaults();
  if (trendChart) trendChart.destroy();
  trendChart = new window.Chart($("trend-chart"), {
    type: "line",
    data: {
      labels: usable,
      datasets: top.map((ticker, i) => ({
        label: ticker,
        data: usable.map((d) => {
          const v = num(history[d]?.[ticker]?.Final_Score);
          return Number.isFinite(v) ? Number(v.toFixed(1)) : null;
        }),
        borderColor: PALETTE[i % PALETTE.length],
        backgroundColor: PALETTE[i % PALETTE.length],
        spanGaps: true,
        borderWidth: 2,
        pointRadius: usable.length < 8 ? 3 : 0,
        tension: 0.25,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "nearest", intersect: false },
      plugins: { legend: { position: "bottom", labels: { boxWidth: 10 } } },
      scales: { x: { grid: { display: false } }, y: { title: { display: true, text: "Điểm" } } },
    },
  });
}

// ---------------------------------------------------------------- drawer
function closeDrawer() {
  $("drawer-root").innerHTML = "";
  document.removeEventListener("keydown", onEsc);
}
function onEsc(e) {
  if (e.key === "Escape") closeDrawer();
}

function metric(label, value) {
  return `<div><span class="muted">${esc(label)}</span><span>${value}</span></div>`;
}

function openDrawer(r) {
  const flows = (state.data.flows || [])
    .filter((f) => f.Ma_Co_Phieu === r.Ma_Co_Phieu)
    .sort((a, b) => Math.abs(num(b.Dong_Tien_VND)) - Math.abs(num(a.Dong_Tien_VND)));

  const factorRows = FACTORS.map((f) => {
    const v = num(r[f.key]);
    const width = Number.isFinite(v) ? v : 0;
    return `<div class="factor"><span>${esc(f.label)}</span><span class="score" style="min-width:0"><span class="bar"><i style="width:${width.toFixed(1)}%"></i></span></span><b class="num">${Number.isFinite(v) ? Math.round(v) : "--"}</b></div>`;
  }).join("");

  const flowRows = flows.length
    ? `<div class="table-wrap short"><table><thead><tr><th>Quỹ</th><th>Hành động</th><th class="num">Tỷ trọng</th><th class="num">Dòng tiền</th></tr></thead><tbody>${flows
        .map((f) => {
          const st = FLOW_STATUS[f.Trang_Thai] || { label: f.Trang_Thai, css: "" };
          return `<tr><td>${esc(f.Ten_Quy)}</td><td><span class="tag ${st.css}">${esc(st.label)}</span></td><td class="num">${fmt(f.Ty_Le_Truoc_pct, 2)}% → ${fmt(f.Ty_Le_Hien_Tai_pct, 2)}%</td><td class="num ${signClass(f.Dong_Tien_VND)}">${fmtVnd(f.Dong_Tien_VND, { signed: true })}</td></tr>`;
        })
        .join("")}</tbody></table></div>
      <div class="muted" style="font-size:12px;margin-top:6px">Dòng tiền đã loại trừ biến động giá. Tỷ trọng có thể giảm dù quỹ mua thêm khi tổng tài sản quỹ tăng (nhà đầu tư nộp tiền).</div>`
    : `<div class="muted">Không có giao dịch quỹ đáng kể trong kỳ gần nhất (≥ 1 tỷ).</div>`;

  $("drawer-root").innerHTML = `
    <div class="drawer-backdrop" data-close></div>
    <aside class="drawer" role="dialog" aria-label="Chi tiết ${esc(r.Ma_Co_Phieu)}">
      <button class="btn close" data-close aria-label="Đóng">✕</button>
      <h3>${esc(r.Ma_Co_Phieu)} ${r.Xep_Hang ? `<span class="muted" style="font-size:15px">#${esc(r.Xep_Hang)}</span>` : ""}</h3>
      <div class="muted">${esc(r.Ten_Cong_Ty || "")}${r.San ? ` · ${esc(r.San)}` : ""}</div>
      <div class="status-row">${r.Nhom_Chien_Luoc ? groupTag(r.Nhom_Chien_Luoc) : ""}<span class="pill">${esc(r.Nhom_Nganh || r.Nganh || "--")}</span>${r.Nganh_Chi_Tiet ? `<span class="pill">${esc(r.Nganh_Chi_Tiet)}</span>` : ""}</div>
      ${r.Loai_Tru ? `<div class="alert" style="margin-top:12px">Không xếp hạng: ${esc(r.Loai_Tru)}</div>` : ""}
      <section>
        <h4>Điểm tổng hợp: ${fmt(r.Final_Score, 1)} · độ phủ dữ liệu ${fmtPct(r.Data_Coverage, 0, { ratio: true })}</h4>
        ${factorRows}
      </section>
      <section>
        <h4>Chỉ số</h4>
        <div class="metrics">
          ${metric("Giá hiện tại", fmt(r.Gia_Hien_Tai, 0))}
          ${metric("Giá mục tiêu (trung vị)", `${fmt(r.Gia_Muc_Tieu, 0)} <span class="muted">(${esc(r.So_Bao_Cao_MT ?? 0)} BC)</span>`)}
          ${metric("Upside", `<span class="${signClass(r.Upside_pct)}">${fmtPct(r.Upside_pct, 1, { signed: true })}</span>`)}
          ${metric("P/E · P/B", `${fmt(r.PE, 1)} · ${fmt(r.PB, 2)}`)}
          ${metric("ROE · ROA", `${fmtPct(r.ROE_pct, 1)} · ${fmtPct(r.ROA_pct, 1)}`)}
          ${metric("Tăng trưởng LNST / DT", `${fmtPct(r.Tang_Truong_LNST_pct, 0)} / ${fmtPct(r.Tang_Truong_DT_pct, 0)}`)}
          ${metric("Cổ tức", fmtPct(r.Co_Tuc_pct, 1))}
          ${metric("Vốn hoá", fmtVnd(r.Von_Hoa_VND))}
          ${metric("Lợi nhuận 1T / 3T / 6T", `${fmtPct(r.Ret_1M, 1, { ratio: true, signed: true })} / ${fmtPct(r.Ret_3M, 1, { ratio: true, signed: true })} / ${fmtPct(r.Ret_6M, 1, { ratio: true, signed: true })}`)}
          ${metric("Biến động 60 phiên", fmtPct(r.Volatility_60D, 1, { ratio: true }))}
          ${metric("Sụt giảm tối đa 6T", fmtPct(r.Max_Drawdown_6M, 1, { ratio: true }))}
          ${metric("Beta 120 phiên", fmt(r.Beta_120D, 2))}
          ${metric("GTGD TB 20 phiên", fmtVnd(r.ADV_20D_VND))}
          ${metric("Quỹ nắm giữ", `${fmt(r.So_Luong_Quy, 0)} quỹ · ${fmtVnd(r.Tong_Gia_Tri_Hien_Tai_VND)}`)}
          ${metric("Quỹ sở hữu / vốn hoá", fmtPct(r.Ty_Le_So_Huu_Quy_pct, 2))}
        </div>
      </section>
      <section>
        <h4>Quỹ giao dịch trong kỳ · ròng <span class="${signClass(r.Dong_Tien_Rong_VND)}">${fmtVnd(r.Dong_Tien_Rong_VND, { signed: true })}</span></h4>
        ${flowRows}
      </section>
    </aside>`;
  $("drawer-root").querySelectorAll("[data-close]").forEach((el) => el.addEventListener("click", closeDrawer));
  document.addEventListener("keydown", onEsc);
}

// ---------------------------------------------------------------- boot
async function boot() {
  const data = await loadData();
  state.data = data;
  state.rows = data.stocks;
  renderStatus($("status"), $("alert"), data);
  if (!data.meta) {
    table.update([]);
    return;
  }

  fillSelect($("filter-sector"), [...new Set(state.rows.map((r) => r.Nhom_Nganh || r.Nganh).filter(Boolean))].sort((a, b) => a.localeCompare(b, "vi")));
  fillSelect($("filter-group"), GROUPS.map((g) => g.key).filter((k) => state.rows.some((r) => r.Nhom_Chien_Luoc === k)));
  renderKpis(data);
  applyFilters();
  ["search", "filter-sector", "filter-group", "show-excluded"].forEach((id) => $(id).addEventListener("input", applyFilters));

  $("trend-hint").textContent = "Đang tải lịch sử điểm...";
  renderTrend(await loadHistory(), data);
}

boot().catch((err) => {
  console.error(err);
  $("status").innerHTML = `<span class="pill bad">Lỗi khởi tạo giao diện</span>`;
});
