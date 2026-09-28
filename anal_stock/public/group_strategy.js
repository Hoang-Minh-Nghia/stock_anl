import { GROUPS, createTable, esc, fmt, fmtPct, fmtVnd, heatCell, loadData, num, renderStatus, scoreCell, signClass } from "./common.js?v=5.1.0";

const $ = (id) => document.getElementById(id);
const TOP_N = 15;

function groupColumns() {
  return [
    { key: "Xep_Hang", header: "#", align: "num", render: (r) => esc(r.Xep_Hang ?? "–") },
    { key: "Ma_Co_Phieu", header: "Mã", render: (r) => `<span class="ticker">${esc(r.Ma_Co_Phieu)}</span>` },
    { key: "Nhom_Nganh", header: "Ngành", render: (r) => `<span class="nowrap">${esc(r.Nhom_Nganh || r.Nganh || "--")}</span>` },
    { key: "Final_Score", header: "Điểm", render: (r) => scoreCell(r.Final_Score) },
    { key: "Score_Quality", header: "Chất lượng", align: "num", render: (r) => heatCell(r.Score_Quality) },
    { key: "Score_Value", header: "Định giá", align: "num", render: (r) => heatCell(r.Score_Value) },
    { key: "ROE_pct", header: "ROE", align: "num", render: (r) => fmtPct(r.ROE_pct, 1) },
    { key: "PE", header: "P/E", align: "num", render: (r) => fmt(r.PE, 1) },
    { key: "Co_Tuc_pct", header: "Cổ tức", align: "num", render: (r) => fmtPct(r.Co_Tuc_pct, 1) },
    { key: "Dong_Tien_Rong_VND", header: "Dòng tiền quỹ", align: "num", render: (r) => `<span class="${signClass(r.Dong_Tien_Rong_VND)}">${fmtVnd(r.Dong_Tien_Rong_VND, { signed: true })}</span>` },
  ];
}

function average(rows, key) {
  const vals = rows.map((r) => num(r[key])).filter(Number.isFinite);
  return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : NaN;
}

async function boot() {
  const data = await loadData();
  renderStatus($("status"), $("alert"), data);
  if (!data.meta) return;

  const ranked = data.stocks.filter((r) => !r.Loai_Tru && Number.isFinite(num(r.Final_Score)));
  const grouped = Object.fromEntries(GROUPS.map((g) => [g.key, []]));
  ranked.forEach((r) => (grouped[r.Nhom_Chien_Luoc] || grouped[GROUPS[3].key]).push(r));
  const total = ranked.length;

  $("bars").innerHTML = GROUPS.map((g) => {
    const count = grouped[g.key].length;
    const pct = total ? (count / total) * 100 : 0;
    return `<div class="bar-row"><span>${esc(g.short)} <span class="muted">(${count})</span></span><div class="bar-track"><div class="bar-fill fill-${g.css}" style="width:${pct.toFixed(1)}%"></div></div><span class="num">${fmt(pct, 1)}%</span></div>`;
  }).join("");

  $("kpis").innerHTML = GROUPS.map((g) => {
    const rows = grouped[g.key];
    const holding = rows.reduce((s, r) => s + (Number.isFinite(num(r.Tong_Gia_Tri_Hien_Tai_VND)) ? num(r.Tong_Gia_Tri_Hien_Tai_VND) : 0), 0);
    const flow = rows.reduce((s, r) => s + (Number.isFinite(num(r.Dong_Tien_Rong_VND)) ? num(r.Dong_Tien_Rong_VND) : 0), 0);
    return `<div class="kpi"><div class="label"><span class="tag ${g.css}">${esc(g.short)}</span></div>
      <div class="value">${rows.length} mã</div>
      <div class="sub">Điểm TB ${fmt(average(rows, "Final_Score"), 1)} · quỹ nắm ${fmtVnd(holding)}</div>
      <div class="sub">Dòng tiền kỳ: <span class="${signClass(flow)}">${fmtVnd(flow, { signed: true })}</span></div></div>`;
  }).join("");

  $("groups").innerHTML = GROUPS.map(
    (g) => `<article class="panel"><div class="panel-head"><h2><span class="tag ${g.css}" style="font-size:14px">${esc(g.short)}</span></h2><span class="hint">Top ${TOP_N} theo điểm</span></div><div class="table-wrap short" id="group-${g.css}"></div></article>`
  ).join("");

  GROUPS.forEach((g) => {
    const rows = [...grouped[g.key]].sort((a, b) => num(b.Final_Score) - num(a.Final_Score)).slice(0, TOP_N);
    createTable($(`group-${g.css}`), { columns: groupColumns(), defaultSort: { key: "Final_Score", dir: "desc" }, emptyText: "Không có mã trong nhóm" }).update(rows);
  });
}

boot().catch((err) => {
  console.error(err);
  $("status").innerHTML = `<span class="pill bad">Lỗi khởi tạo giao diện</span>`;
});
