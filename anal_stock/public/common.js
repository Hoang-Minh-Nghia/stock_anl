// Tiện ích dùng chung cho các trang dashboard (chạy cục bộ).
// Dữ liệu do `python run.py` sinh ra trong ./data/: index.json, runs/{ngày}.json, score_history.json.

const DATA_DIR = "./data";
const TIMEOUT_MS = 15000;

export const GROUPS = [
  { key: "Tăng trưởng (Phi chu kỳ)", short: "Tăng trưởng", css: "g" },
  { key: "Tấn công (Chu kỳ)", short: "Tấn công (chu kỳ)", css: "a" },
  { key: "Phòng thủ (Cổ tức)", short: "Phòng thủ", css: "d" },
  { key: "Theo dõi thêm / Trung lập", short: "Trung lập", css: "n" },
];

export const FACTORS = [
  { key: "Score_Value", label: "Định giá" },
  { key: "Score_Quality", label: "Chất lượng" },
  { key: "Score_Growth", label: "Tăng trưởng" },
  { key: "Score_Momentum", label: "Xu hướng giá" },
  { key: "Score_LowRisk", label: "Rủi ro thấp" },
  { key: "Score_SmartMoney", label: "Dòng tiền quỹ" },
  { key: "Score_Upside", label: "Giá mục tiêu" },
];

export const FLOW_STATUS = {
  INCREASE: { label: "Mua thêm", css: "buy" },
  NEW_BUY: { label: "Mua mới", css: "buy" },
  ENTER_TOP10: { label: "Vào top 10", css: "buy" },
  DECREASE: { label: "Bán bớt", css: "sell" },
  EXIT: { label: "Bán hết", css: "sell" },
  LEFT_TOP10: { label: "Rời top 10", css: "sell" },
  UNCHANGED: { label: "Không đổi", css: "" },
  NO_BASELINE: { label: "Chưa có kỳ trước", css: "" },
  STALE: { label: "Dữ liệu cũ", css: "" },
};

// ---------------------------------------------------------------- escape & format
const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ESC[c]);
}

export function num(value) {
  if (value === null || value === undefined || value === "") return NaN;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : NaN;
}

export function fmt(value, digits = 1) {
  const n = num(value);
  return Number.isFinite(n) ? n.toLocaleString("vi-VN", { minimumFractionDigits: digits, maximumFractionDigits: digits }) : "--";
}

export function fmtPct(value, digits = 1, { ratio = false, signed = false } = {}) {
  let n = num(value);
  if (!Number.isFinite(n)) return "--";
  if (ratio) n *= 100;
  const sign = signed && n > 0 ? "+" : "";
  return `${sign}${n.toLocaleString("vi-VN", { minimumFractionDigits: digits, maximumFractionDigits: digits })}%`;
}

export function fmtVnd(value, { signed = false } = {}) {
  const n = num(value);
  if (!Number.isFinite(n)) return "--";
  const abs = Math.abs(n);
  const sign = n < 0 ? "-" : signed && n > 0 ? "+" : "";
  if (abs >= 1e12) return `${sign}${(abs / 1e12).toLocaleString("vi-VN", { maximumFractionDigits: 2 })} nghìn tỷ`;
  if (abs >= 1e9) return `${sign}${(abs / 1e9).toLocaleString("vi-VN", { maximumFractionDigits: 1 })} tỷ`;
  if (abs >= 1e6) return `${sign}${(abs / 1e6).toLocaleString("vi-VN", { maximumFractionDigits: 0 })} triệu`;
  return `${sign}${abs.toLocaleString("vi-VN", { maximumFractionDigits: 0 })}`;
}

export function signClass(value) {
  const n = num(value);
  return !Number.isFinite(n) || n === 0 ? "" : n > 0 ? "pos" : "neg";
}

export function groupMeta(name) {
  return GROUPS.find((g) => g.key === name) || GROUPS[3];
}

export function groupTag(name) {
  const g = groupMeta(name);
  return `<span class="tag ${g.css}">${esc(g.short)}</span>`;
}

export function scoreCell(value) {
  const n = num(value);
  if (!Number.isFinite(n)) return `<span class="muted">--</span>`;
  const w = Math.max(0, Math.min(100, n));
  return `<span class="score"><b>${fmt(n, 1)}</b><span class="bar"><i style="width:${w.toFixed(1)}%"></i></span></span>`;
}

export function heatCell(value) {
  const n = num(value);
  if (!Number.isFinite(n)) return `<span class="heat muted">--</span>`;
  const t = Math.max(0, Math.min(100, n)) / 100;
  const hue = Math.round(t * 130); // đỏ → xanh
  return `<span class="heat" style="background:hsla(${hue},70%,45%,0.22);color:hsl(${hue},80%,72%)">${Math.round(n)}</span>`;
}

// ---------------------------------------------------------------- data loading
async function fetchJson(url, timeoutMs = TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const resp = await fetch(url, { cache: "no-store", signal: controller.signal });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return await resp.json();
  } finally {
    clearTimeout(timer);
  }
}

/** Chuẩn hoá bản ghi (hỗ trợ dữ liệu mô hình cũ v3 trước khi có v4). */
export function normalizeRecord(row, ticker) {
  const r = { ...(row || {}) };
  r.Ma_Co_Phieu = r.Ma_Co_Phieu || ticker;
  r.PE ??= r["P/E"];
  r.ROE_pct ??= r["ROE_%"];
  r.Upside_pct ??= r["Upside_%"];
  r.Tong_Gia_Tri_Hien_Tai_VND ??= r.Tong_Gia_Tri_VND;
  r.Dong_Tien_Rong_VND ??= r.Delta_Gia_Tri_VND;
  r.So_Quy_Tang ??= r.So_Quy_Mua_Rong;
  r.So_Quy_Giam ??= r.So_Quy_Ban_Rong;
  r.So_Quy_Thoat ??= r.So_Quy_Rut;
  r.Nhom_Nganh ??= r.Nganh_Gop;
  r.isLegacy = !("Score_Value" in r);
  return r;
}

function recordsToList(records) {
  return Object.entries(records || {}).map(([ticker, row]) => normalizeRecord(row, ticker));
}

/** Lịch sử điểm theo ngày: {ngày: {mã: {Final_Score, Xep_Hang, Nhom_Chien_Luoc}}}. */
export async function loadHistory() {
  try {
    const compact = await fetchJson(`${DATA_DIR}/score_history.json`, 30000);
    return Object.fromEntries(
      Object.entries(compact || {}).map(([date, rows]) => [
        date,
        Object.fromEntries(Object.entries(rows).map(([t, v]) => [t, { Final_Score: v[0], Xep_Hang: v[1], Nhom_Chien_Luoc: v[2] }])),
      ])
    );
  } catch {
    return {};
  }
}

/**
 * Tải dữ liệu của ngày đang chọn (?date=YYYY-MM-DD, mặc định ngày mới nhất).
 * Trả {date, latestDate, dates, runs, meta, stocks, flows, errors}.
 */
export async function loadData() {
  const result = { date: null, latestDate: null, dates: [], runs: {}, meta: null, stocks: [], flows: [], errors: [] };
  let index;
  try {
    index = await fetchJson(`${DATA_DIR}/index.json`);
  } catch (err) {
    result.errors.push(
      location.protocol === "file:"
        ? "Trình duyệt chặn đọc file khi mở trực tiếp. Hãy mở bằng lệnh: python run.py --serve"
        : "Chưa có dữ liệu. Hãy chạy: python run.py"
    );
    return result;
  }
  result.dates = index.dates || [];
  result.runs = index.runs || {};
  result.latestDate = index.latest;
  const wanted = new URLSearchParams(location.search).get("date");
  result.date = result.dates.includes(wanted) ? wanted : index.latest;
  if (!result.date) return result;

  try {
    const run = await fetchJson(`${DATA_DIR}/runs/${result.date}.json`);
    result.meta = run.meta || {};
    result.stocks = recordsToList(run.stocks);
    result.flows = (run.flows || []).filter(Boolean);
  } catch (err) {
    result.errors.push(`Không đọc được dữ liệu ngày ${result.date}: ${err.message}`);
  }
  return result;
}

// ---------------------------------------------------------------- status UI
function todayVN() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Ho_Chi_Minh" }).format(new Date());
}

/** Ô chọn ngày: đổi ngày → tải lại trang với ?date=. */
export function renderDatePicker(container, data) {
  if (!container || !data.dates.length) return;
  // Giữ ngày đang xem khi chuyển trang
  if (data.date && data.date !== data.latestDate) {
    document.querySelectorAll(".nav a").forEach((a) => {
      a.href = `${a.getAttribute("href").split("?")[0]}?date=${encodeURIComponent(data.date)}`;
    });
  }
  const options = [...data.dates]
    .reverse()
    .map((d) => {
      const legacy = data.runs[d]?.legacy ? " (mô hình cũ)" : "";
      return `<option value="${esc(d)}"${d === data.date ? " selected" : ""}>${esc(d)}${d === data.latestDate ? " · mới nhất" : legacy}</option>`;
    })
    .join("");
  container.innerHTML = `<label class="date-picker">Ngày <select aria-label="Chọn ngày dữ liệu">${options}</select></label>`;
  container.querySelector("select").addEventListener("change", (e) => {
    const params = new URLSearchParams(location.search);
    if (e.target.value === data.latestDate) params.delete("date");
    else params.set("date", e.target.value);
    const qs = params.toString();
    location.href = location.pathname + (qs ? `?${qs}` : "");
  });
}

export function renderStatus(container, alertBox, data) {
  if (!container) return;
  renderDatePicker(document.getElementById("date-picker"), data);
  const pills = [];
  const warnings = [...(data.meta?.warnings || [])];

  if (!data.date || !data.meta) {
    container.innerHTML = `<span class="pill bad">Không có dữ liệu</span>`;
    if (alertBox) {
      alertBox.hidden = false;
      alertBox.innerHTML = esc(data.errors.join(" · ") || "Chưa có dữ liệu. Hãy chạy: python run.py");
    }
    return;
  }

  const isLatest = data.date === data.latestDate;
  const ageDays = Math.round((new Date(todayVN()) - new Date(data.latestDate)) / 86400000);
  if (isLatest) {
    const freshCss = ageDays <= 1 ? "ok" : ageDays <= 7 ? "warn" : "bad";
    pills.push(`<span class="pill ${freshCss}">Cập nhật ${esc(data.date)}${ageDays > 1 ? ` · ${ageDays} ngày trước` : ""}</span>`);
  } else {
    pills.push(`<span class="pill warn">Đang xem ngày cũ ${esc(data.date)}</span>`);
  }
  if (data.meta.fetch) {
    const f = data.meta.fetch;
    const css = f.funds_failed ? "warn" : "ok";
    pills.push(`<span class="pill ${css}" title="Số quỹ có nắm cổ phiếu trên FMarket">Quỹ nắm cổ phiếu: ${esc(f.funds_live)}${f.funds_failed ? ` · lỗi ${esc(f.funds_failed)}` : ""}</span>`);
  }
  if (data.meta.model_version) pills.push(`<span class="pill">Mô hình ${esc(data.meta.model_version)}</span>`);
  if (data.meta.legacy || data.stocks.some((s) => s.isLegacy)) {
    warnings.push("Ngày này dùng mô hình cũ (v3, chuyển về từ Firebase) — nhiều cột nhân tố và dòng tiền theo kỳ sẽ trống.");
  }
  if (isLatest && ageDays > 7) warnings.push(`Dữ liệu đã cũ ${ageDays} ngày — chạy "python run.py" để cập nhật.`);

  container.innerHTML = pills.join("");
  if (alertBox) {
    alertBox.hidden = warnings.length === 0;
    alertBox.innerHTML = warnings.length ? `<strong>Lưu ý dữ liệu</strong><ul>${warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>` : "";
  }
}

// ---------------------------------------------------------------- sortable table
/**
 * columns: [{key, header, align: "num"|undefined, render(row) -> html, sortValue(row)}]
 * Mỗi bảng có trạng thái sort riêng.
 */
export function createTable(container, { columns, defaultSort, emptyText = "Không có dữ liệu", rowClass, onRowClick }) {
  const state = { key: defaultSort?.key ?? columns[0].key, dir: defaultSort?.dir ?? "desc", rows: [] };

  function sortValue(col, row) {
    const v = col.sortValue ? col.sortValue(row) : row[col.key];
    const n = num(v);
    return Number.isFinite(n) ? n : v ?? null;
  }

  function render() {
    const col = columns.find((c) => c.key === state.key) || columns[0];
    const factor = state.dir === "asc" ? 1 : -1;
    const sorted = [...state.rows].sort((a, b) => {
      const av = sortValue(col, a);
      const bv = sortValue(col, b);
      if (av === null && bv === null) return 0;
      if (av === null) return 1; // giá trị trống luôn ở cuối
      if (bv === null) return -1;
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * factor;
      return String(av).localeCompare(String(bv), "vi", { numeric: true }) * factor;
    });

    const head = columns
      .map((c) => {
        const arrow = c.key === state.key ? `<span class="arrow">${state.dir === "asc" ? "▲" : "▼"}</span>` : "";
        return `<th data-key="${esc(c.key)}" class="${c.align || ""}" title="${esc(c.title || "")}">${esc(c.header)}${arrow}</th>`;
      })
      .join("");

    const body = sorted.length
      ? sorted
          .map((row, i) => {
            const cls = [onRowClick ? "clickable" : "", rowClass ? rowClass(row) : ""].join(" ").trim();
            const cells = columns
              .map((c) => `<td class="${c.align || ""}">${c.render ? c.render(row, i) : esc(row[c.key] ?? "--")}</td>`)
              .join("");
            return `<tr class="${cls}" data-idx="${state.rows.indexOf(row)}">${cells}</tr>`;
          })
          .join("")
      : `<tr><td class="empty" colspan="${columns.length}">${esc(emptyText)}</td></tr>`;

    container.innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  }

  container.addEventListener("click", (event) => {
    const th = event.target.closest("th[data-key]");
    if (th) {
      const key = th.dataset.key;
      state.dir = state.key === key && state.dir === "desc" ? "asc" : "desc";
      state.key = key;
      render();
      return;
    }
    const tr = event.target.closest("tr[data-idx]");
    if (tr && onRowClick) onRowClick(state.rows[Number(tr.dataset.idx)]);
  });

  return {
    update(rows) {
      state.rows = rows || [];
      render();
    },
  };
}

// ---------------------------------------------------------------- chart defaults
export function applyChartDefaults() {
  if (!window.Chart) return;
  window.Chart.defaults.color = "#93a4be";
  window.Chart.defaults.borderColor = "rgba(138,158,188,0.15)";
  window.Chart.defaults.font.family = "Inter, system-ui, sans-serif";
}

export const PALETTE = ["#46c2ff", "#39d98a", "#fbbf24", "#ff9f43", "#a78bfa", "#f472b6", "#2dd4bf", "#f87171", "#60a5fa", "#c084fc"];
