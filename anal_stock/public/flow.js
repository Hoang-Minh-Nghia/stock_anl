import {
  FLOW_STATUS, applyChartDefaults, createTable, esc, fmt, fmtPct, fmtVnd, loadData, num, renderStatus, signClass,
} from "./common.js?v=5.0.1";

const $ = (id) => document.getElementById(id);
let chart = null;
let pairs = [];

const tickerCell = (r) => `<span class="ticker">${esc(r.Ma_Co_Phieu)}</span>`;
const flowCell = (key) => (r) => `<span class="${signClass(r[key])}">${fmtVnd(r[key], { signed: true })}</span>`;

const tickerColumns = [
  { key: "Ma_Co_Phieu", header: "Mã", render: tickerCell },
  { key: "Dong_Tien_Rong_VND", header: "Ròng", align: "num", render: flowCell("Dong_Tien_Rong_VND") },
  { key: "Dong_Tien_Tren_Von_Hoa_pct", header: "% vốn hoá", align: "num", render: (r) => fmtPct(r.Dong_Tien_Tren_Von_Hoa_pct, 2, { signed: true }) },
  { key: "So_Quy_Tang", header: "Quỹ mua", align: "num", render: (r) => fmt(r.So_Quy_Tang, 0) },
  { key: "So_Quy_Giam", header: "Quỹ bán", align: "num", render: (r) => fmt(r.So_Quy_Giam, 0) },
  { key: "So_Quy_Mua_Moi", header: "Mới", align: "num", title: "Mua mới hoặc vào top 10", render: (r) => fmt(r.So_Quy_Mua_Moi, 0) },
  { key: "So_Quy_Thoat", header: "Thoát", align: "num", title: "Bán hết hoặc rời top 10", render: (r) => fmt(r.So_Quy_Thoat, 0) },
  { key: "Final_Score", header: "Điểm", align: "num", render: (r) => fmt(r.Final_Score, 1) },
];

const buyTable = createTable($("buy-table"), { columns: tickerColumns, defaultSort: { key: "Dong_Tien_Rong_VND", dir: "desc" }, emptyText: "Chưa có mã mua ròng" });
const sellTable = createTable($("sell-table"), { columns: tickerColumns, defaultSort: { key: "Dong_Tien_Rong_VND", dir: "asc" }, emptyText: "Chưa có mã bán ròng" });

const pairTable = createTable($("pair-table"), {
  columns: [
    { key: "Ten_Quy", header: "Quỹ", render: (r) => `<b>${esc(r.Ten_Quy)}</b>` },
    { key: "Ma_Co_Phieu", header: "Mã", render: tickerCell },
    {
      key: "Trang_Thai",
      header: "Hành động",
      render: (r) => {
        const st = FLOW_STATUS[r.Trang_Thai] || { label: r.Trang_Thai, css: "" };
        return `<span class="tag ${st.css}">${esc(st.label)}</span>${r.Dieu_Chinh_Chia_Tach ? ` <span class="muted" title="Đã điều chỉnh chia tách / thưởng cổ phiếu">⚙</span>` : ""}`;
      },
    },
    { key: "Ty_Le_Truoc_pct", header: "Tỷ trọng trước", align: "num", render: (r) => fmtPct(r.Ty_Le_Truoc_pct, 2) },
    { key: "Ty_Le_Hien_Tai_pct", header: "Tỷ trọng nay", align: "num", render: (r) => fmtPct(r.Ty_Le_Hien_Tai_pct, 2) },
    { key: "CP_Hien_Tai", header: "Số CP nay", align: "num", render: (r) => fmt(r.CP_Hien_Tai, 0) },
    { key: "Dong_Tien_VND", header: "Dòng tiền", align: "num", render: flowCell("Dong_Tien_VND") },
    { key: "Ky_Hien_Tai", header: "Kỳ", render: (r) => `<span class="nowrap muted">${esc(r.Ky_Truoc || "")} → ${esc(r.Ky_Hien_Tai || "")}</span>` },
  ],
  defaultSort: { key: "Dong_Tien_VND", dir: "desc" },
  emptyText: "Không có giao dịch phù hợp",
});

const fundTable = createTable($("fund-table"), {
  columns: [
    { key: "Ten_Quy", header: "Quỹ", render: (r) => `<b>${esc(r.Ten_Quy)}</b>` },
    {
      key: "Trang_Thai",
      header: "Trạng thái",
      render: (r) => {
        const map = {
          OK: ["Có kỳ so sánh", "buy"],
          NO_BASELINE: ["Chưa có kỳ trước", ""],
          STALE: ["Lâu chưa cập nhật", "sell"],
          INACTIVE: ["Không còn công bố", "sell"],
        };
        const [label, css] = map[r.Trang_Thai] || [r.Trang_Thai, ""];
        return `<span class="tag ${css}">${esc(label)}</span>`;
      },
    },
    { key: "Ky_Truoc", header: "Kỳ trước", render: (r) => `${esc(r.Ky_Truoc || "--")}${r.Ky_Truoc_Uoc_Luong ? ` <span class="muted" title="Ngày báo cáo ước lượng từ ngày xuất hiện">~</span>` : ""}` },
    { key: "Ky_Hien_Tai", header: "Kỳ hiện tại", render: (r) => esc(r.Ky_Hien_Tai || "--") },
    { key: "Ngay_Cap_Nhat", header: "Thấy lần đầu", render: (r) => esc(r.Ngay_Cap_Nhat || "--") },
  ],
  defaultSort: { key: "Ten_Quy", dir: "asc" },
  emptyText: "Chưa có thông tin quỹ (cần chạy pipeline mới)",
});

function renderChart(rows) {
  if (!window.Chart) return;
  applyChartDefaults();
  const valid = rows.filter((r) => Number.isFinite(num(r.Dong_Tien_Rong_VND)));
  const buys = valid.filter((r) => num(r.Dong_Tien_Rong_VND) > 0).sort((a, b) => num(b.Dong_Tien_Rong_VND) - num(a.Dong_Tien_Rong_VND)).slice(0, 10);
  const sells = valid.filter((r) => num(r.Dong_Tien_Rong_VND) < 0).sort((a, b) => num(a.Dong_Tien_Rong_VND) - num(b.Dong_Tien_Rong_VND)).slice(0, 10);
  const combined = [...buys, ...sells.reverse()];
  const values = combined.map((r) => num(r.Dong_Tien_Rong_VND) / 1e9);
  if (chart) chart.destroy();
  chart = new window.Chart($("flow-chart"), {
    type: "bar",
    data: {
      labels: combined.map((r) => r.Ma_Co_Phieu),
      datasets: [{
        label: "Dòng tiền ròng (tỷ VND)",
        data: values,
        backgroundColor: values.map((v) => (v >= 0 ? "rgba(57,217,138,0.8)" : "rgba(255,107,107,0.8)")),
        borderRadius: 6,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (ctx) => `Ròng: ${fmt(ctx.raw, 1)} tỷ VND` } },
      },
      scales: { x: { grid: { display: false } }, y: { title: { display: true, text: "Tỷ VND" } } },
    },
  });
}

function applyPairFilters() {
  const q = $("pair-search").value.trim().toUpperCase();
  const fund = $("pair-fund").value;
  const status = $("pair-status").value;
  const rows = pairs.filter((p) => (!q || p.Ma_Co_Phieu.includes(q)) && (!fund || p.Ten_Quy === fund) && (!status || p.Trang_Thai === status));
  $("pair-count").textContent = `${rows.length} giao dịch`;
  pairTable.update(rows);
}

function fillSelect(select, entries) {
  select.innerHTML = select.options[0].outerHTML + entries.map(([v, label]) => `<option value="${esc(v)}">${esc(label)}</option>`).join("");
}

async function boot() {
  const data = await loadData();
  renderStatus($("status"), $("alert"), data);
  if (!data.meta) return;

  const rows = data.stocks.filter((r) => Number.isFinite(num(r.Dong_Tien_Rong_VND)));
  const flow = data.meta?.flow || {};
  $("kpi-period").textContent = flow.period_current ? `${flow.period_prev} → ${flow.period_current}` : "--";
  $("kpi-period-sub").textContent = flow.funds_total
    ? `${flow.funds_with_baseline} quỹ so sánh · ${flow.funds_no_baseline} quỹ chưa có kỳ trước`
    : "Dữ liệu mô hình cũ: so sánh ngày liền kề";

  const buy = rows.reduce((s, r) => s + Math.max(0, num(r.Dong_Tien_Rong_VND)), 0);
  const sell = rows.reduce((s, r) => s + Math.min(0, num(r.Dong_Tien_Rong_VND)), 0);
  const net = buy + sell;
  const buyers = rows.filter((r) => num(r.Dong_Tien_Rong_VND) > 0);
  const sellers = rows.filter((r) => num(r.Dong_Tien_Rong_VND) < 0);
  $("kpi-net").textContent = fmtVnd(net, { signed: true });
  $("kpi-net").className = `value ${signClass(net)}`;
  $("kpi-net-sub").textContent = buy + Math.abs(sell) > 0 ? `Tỷ lệ mua ${fmtPct((buy / (buy - sell)) * 100, 0)} tổng giao dịch` : "--";
  $("kpi-buy").textContent = fmtVnd(buy);
  $("kpi-buy-sub").textContent = `${buyers.length} mã`;
  $("kpi-sell").textContent = fmtVnd(sell);
  $("kpi-sell-sub").textContent = `${sellers.length} mã`;

  renderChart(rows);
  buyTable.update(buyers);
  sellTable.update(sellers);

  pairs = (data.flows || []).filter((p) => p && p.Ma_Co_Phieu);
  fillSelect($("pair-fund"), [...new Set(pairs.map((p) => p.Ten_Quy))].sort().map((f) => [f, f]));
  fillSelect($("pair-status"), Object.entries(FLOW_STATUS).filter(([k]) => pairs.some((p) => p.Trang_Thai === k)).map(([k, v]) => [k, v.label]));
  applyPairFilters();
  ["pair-search", "pair-fund", "pair-status"].forEach((id) => $(id).addEventListener("input", applyPairFilters));

  fundTable.update(data.meta?.funds || []);
}

boot().catch((err) => {
  console.error(err);
  $("status").innerHTML = `<span class="pill bad">Lỗi khởi tạo giao diện</span>`;
});
