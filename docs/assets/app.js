/* 台股估值追蹤 — 前端 */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const MARKETS = ["listed", "otc", "esb"];
  const LABEL = { listed: "上市", otc: "上櫃", esb: "興櫃" };
  const SERIES = { listed: "var(--series-1)", otc: "var(--series-2)", esb: "var(--series-3)" };
  const METRIC_LABEL = { pe: "本益比", pb: "股價淨值比", dy: "殖利率" };
  const UNIT = { pe: "倍", pb: "倍", dy: "%" };

  const state = {
    rows: [], view: [], meta: null, market: null, hist: null,
    sortKey: "cap", sortDir: -1, filterMarket: "", industry: "", q: "",
    shown: 200, metric: "pe", range: 120,
  };

  // ---------------------------------------------------------------- 工具
  const fmt = (v, d = 2) =>
    v === null || v === undefined || Number.isNaN(v) ? null : Number(v).toFixed(d);

  const human = (n) => {
    if (n === null || n === undefined) return null;
    const a = Math.abs(n);
    if (a >= 1e12) return (n / 1e12).toFixed(2) + " 兆";
    if (a >= 1e8) return (n / 1e8).toFixed(1) + " 億";
    if (a >= 1e4) return (n / 1e4).toFixed(0) + " 萬";
    return String(Math.round(n));
  };

  const cell = (v, d = 2, signed = false) => {
    const s = fmt(v, d);
    if (s === null) return '<span class="na">—</span>';
    if (!signed) return s;
    const cls = v > 0 ? "pos" : v < 0 ? "neg" : "";
    return `<span class="${cls}">${v > 0 ? "+" : ""}${s}</span>`;
  };

  async function getJSON(path, fallback) {
    try {
      const r = await fetch(path, { cache: "no-cache" });
      if (!r.ok) throw new Error(r.status);
      return await r.json();
    } catch (_) {
      return fallback;
    }
  }

  // ---------------------------------------------------------------- 主題
  const themeBtn = $("themeToggle");
  const applyTheme = (t) => {
    if (t) document.documentElement.setAttribute("data-theme", t);
    else document.documentElement.removeAttribute("data-theme");
  };
  try {
    const saved = localStorage.getItem("theme");
    if (saved) applyTheme(saved);
  } catch (_) {}
  themeBtn.addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme");
    const isDark =
      cur === "dark" ||
      (!cur && window.matchMedia("(prefers-color-scheme: dark)").matches);
    const next = isDark ? "light" : "dark";
    applyTheme(next);
    try { localStorage.setItem("theme", next); } catch (_) {}
    draw();
  });

  // ---------------------------------------------------------------- 折線圖
  /**
   * series: [{key, name, color, points: [[label, value], ...]}]
   * 單一系列不畫圖例（標題已說明是什麼）；兩個以上一律有圖例並直接標註。
   */
  function lineChart(svg, tipEl, series, opts = {}) {
    const W = 900, H = opts.height || 300;
    const M = { t: 14, r: 62, b: 26, l: 44 };
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.innerHTML = "";

    const labels = [];
    series.forEach((s) => s.points.forEach(([l]) => { if (!labels.includes(l)) labels.push(l); }));
    labels.sort();
    const vals = series.flatMap((s) => s.points.map(([, v]) => v)).filter((v) => v != null);
    if (!labels.length || !vals.length) {
      svg.innerHTML = `<text x="${W / 2}" y="${H / 2}" text-anchor="middle" class="tick">尚無資料</text>`;
      return;
    }

    let lo = Math.min(...vals), hi = Math.max(...vals);
    const pad = (hi - lo) * 0.12 || Math.abs(hi) * 0.12 || 1;
    lo = Math.max(0, lo - pad); hi = hi + pad;

    const X = (i) => M.l + (labels.length === 1 ? 0 : (i * (W - M.l - M.r)) / (labels.length - 1));
    const Y = (v) => H - M.b - ((v - lo) / (hi - lo)) * (H - M.t - M.b);
    const ns = "http://www.w3.org/2000/svg";
    const mk = (n, a) => { const e = document.createElementNS(ns, n); for (const k in a) e.setAttribute(k, a[k]); return e; };

    // 水平網格 + 刻度
    const TICKS = 5;
    for (let i = 0; i <= TICKS; i++) {
      const v = lo + ((hi - lo) * i) / TICKS, y = Y(v);
      svg.appendChild(mk("line", { class: "gridline", x1: M.l, x2: W - M.r, y1: y, y2: y }));
      const t = mk("text", { class: "tick", x: M.l - 7, y: y + 3.5, "text-anchor": "end" });
      t.textContent = v >= 100 ? v.toFixed(0) : v.toFixed(1);
      svg.appendChild(t);
    }
    svg.appendChild(mk("line", { class: "axis", x1: M.l, x2: W - M.r, y1: H - M.b, y2: H - M.b }));

    // X 軸只標年份；再要求標籤之間至少隔 46px，避免年份擠在一起
    let lastYear = "", lastX = -Infinity;
    labels.forEach((l, i) => {
      const y = String(l).slice(0, 4);
      if (y === lastYear) return;
      const x = X(i);
      if (x - lastX < 46) { lastYear = y; return; }
      lastYear = y; lastX = x;
      const t = mk("text", { class: "tick", x, y: H - M.b + 15, "text-anchor": "middle" });
      t.textContent = y;
      svg.appendChild(t);
    });

    // 線
    series.forEach((s) => {
      const pts = labels
        .map((l, i) => { const p = s.points.find((q) => q[0] === l); return p && p[1] != null ? [X(i), Y(p[1])] : null; })
        .filter(Boolean);
      if (pts.length < 2) return;
      svg.appendChild(mk("path", {
        class: "line", stroke: s.color,
        d: pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" "),
      }));
      // 直接標註在線的末端
      const last = pts[pts.length - 1];
      const t = mk("text", { class: "lbl", x: last[0] + 8, y: last[1] + 4, fill: s.color });
      t.textContent = s.name;
      svg.appendChild(t);
    });

    // 游標層
    const cross = mk("line", { class: "crosshair", y1: M.t, y2: H - M.b, x1: -99, x2: -99 });
    svg.appendChild(cross);
    const dots = mk("g", {});
    svg.appendChild(dots);

    const hit = mk("rect", { class: "hit", x: M.l, y: M.t, width: W - M.l - M.r, height: H - M.t - M.b });
    svg.appendChild(hit);

    const hide = () => { tipEl.hidden = true; cross.setAttribute("x1", -99); cross.setAttribute("x2", -99); dots.innerHTML = ""; };
    const move = (ev) => {
      const box = svg.getBoundingClientRect();
      const cx = ((ev.clientX - box.left) / box.width) * W;
      let idx = Math.round(((cx - M.l) / (W - M.l - M.r)) * (labels.length - 1));
      idx = Math.max(0, Math.min(labels.length - 1, idx));
      const x = X(idx);
      cross.setAttribute("x1", x); cross.setAttribute("x2", x);
      dots.innerHTML = "";
      const rows = [];
      series.forEach((s) => {
        const p = s.points.find((q) => q[0] === labels[idx]);
        if (!p || p[1] == null) return;
        dots.appendChild(mk("circle", { class: "pt", cx: x, cy: Y(p[1]), r: 4.5, fill: s.color }));
        rows.push(`<div class="tt-r"><span><span class="swatch" style="display:inline-block;background:${s.color}"></span> ${s.name}</span><span>${fmt(p[1])}${opts.unit || ""}</span></div>`);
      });
      if (!rows.length) return hide();
      tipEl.innerHTML = `<div class="tt-h">${labels[idx]}</div>${rows.join("")}`;
      tipEl.hidden = false;
      const wrapBox = tipEl.parentElement.getBoundingClientRect();
      let left = ev.clientX - wrapBox.left + 14;
      if (left + tipEl.offsetWidth > wrapBox.width) left = ev.clientX - wrapBox.left - tipEl.offsetWidth - 14;
      tipEl.style.left = Math.max(0, left) + "px";
      tipEl.style.top = Math.max(0, ev.clientY - wrapBox.top - 10) + "px";
    };
    hit.addEventListener("mousemove", move);
    hit.addEventListener("mouseleave", hide);
    svg.addEventListener("touchmove", (e) => { if (e.touches[0]) move(e.touches[0]); }, { passive: true });
    svg.addEventListener("touchend", hide);
  }

  // ---------------------------------------------------------------- 總覽卡
  function renderTiles() {
    const m = state.market && state.market.markets;
    const counts = (state.meta && state.meta.counts) || {};
    $("tiles").innerHTML = MARKETS.map((k) => {
      const d = (m && m[k]) || {};
      const n = counts[k] || d.count || 0;
      return `<div class="tile">
        <div class="name"><span class="swatch" style="background:${SERIES[k]}"></span>${LABEL[k]}</div>
        <div class="figs">
          <div class="fig"><div class="v">${fmt(d.pe) ?? "—"}</div><div class="k">本益比</div></div>
          <div class="fig"><div class="v">${fmt(d.ps) ?? "—"}</div><div class="k">股價營收比</div></div>
        </div>
        <div class="cnt">${n} 檔${d.cap ? "・總市值 " + human(d.cap) : ""}</div>
      </div>`;
    }).join("");
  }

  // ---------------------------------------------------------------- 歷年圖
  function renderHist() {
    const wrap = $("histChart"), tip = $("histTip");
    const monthly = (state.hist && state.hist.monthly) || {};
    const keys = Object.keys(monthly).sort().slice(-state.range);
    const series = MARKETS.map((k) => ({
      key: k, name: LABEL[k], color: SERIES[k],
      points: keys.map((ym) => [ym, ((monthly[ym].m || {})[k] || {})[state.metric] ?? null]),
    })).filter((s) => s.points.some((p) => p[1] != null));

    $("legend").innerHTML = series.length > 1
      ? series.map((s) => `<span class="item"><span class="swatch" style="background:${s.color}"></span>${s.name}</span>`).join("")
      : "";

    if (!keys.length) {
      $("histNote").textContent =
        "歷史資料尚未回補。到 GitHub 的 Actions 頁手動執行一次「歷史回補」，即可補上近十年的逐月快照。";
    }
    lineChart(wrap, tip, series, { unit: UNIT[state.metric], height: 300 });
  }

  // ---------------------------------------------------------------- 表格
  const COLS = [
    { k: "c", t: "代號", cls: "code", get: (r) => r.c },
    { k: "n", t: "名稱", get: (r) => `${r.n} <span class="mkt">${LABEL[r.m]}</span>` },
    { k: "p", t: "股價", get: (r) => cell(r.p) },
    { k: "cap", t: "市值", get: (r) => human(r.cap) ?? '<span class="na">—</span>' },
    { k: "pe", t: "本益比", get: (r) => cell(r.pe) },
    { k: "ps", t: "股價營收比", get: (r) => (r.ps == null ? '<span class="na">—</span>' : cell(r.ps) + (r.ps_basis === "估算" ? '<span class="est">估</span>' : "")) },
    { k: "pb", t: "淨值比", get: (r) => cell(r.pb) },
    { k: "dy", t: "殖利率%", get: (r) => cell(r.dy) },
    { k: "rev_yoy", t: "月營收年增%", get: (r) => cell(r.rev && r.rev.yoy, 1, true), val: (r) => r.rev && r.rev.yoy },
    { k: "rev_cum", t: "累計年增%", get: (r) => cell(r.rev && r.rev.cum_yoy, 1, true), val: (r) => r.rev && r.rev.cum_yoy },
    { k: "net_yoy", t: "淨利年增%", get: (r) => cell(r.fin && r.fin.net_yoy, 1, true), val: (r) => r.fin && r.fin.net_yoy },
    { k: "eps", t: "EPS", get: (r) => cell(r.fin && r.fin.eps), val: (r) => r.fin && r.fin.eps },
  ];

  const valueOf = (r, k) => {
    const col = COLS.find((c) => c.k === k);
    const v = col && col.val ? col.val(r) : r[k];
    return v === undefined ? null : v;
  };

  function renderHead() {
    $("thead").innerHTML = COLS.map(
      (c) => `<th data-k="${c.k}" aria-sort="${state.sortKey === c.k ? (state.sortDir > 0 ? "ascending" : "descending") : "none"}">${c.t}</th>`
    ).join("");
    $("thead").querySelectorAll("th").forEach((th) =>
      th.addEventListener("click", () => {
        const k = th.dataset.k;
        if (state.sortKey === k) state.sortDir *= -1;
        else { state.sortKey = k; state.sortDir = -1; }
        state.shown = 200;
        applyFilters();
      })
    );
  }

  function applyFilters() {
    const q = state.q.trim().toLowerCase();
    let v = state.rows.filter((r) => {
      if (state.filterMarket && r.m !== state.filterMarket) return false;
      if (state.industry && r.i !== state.industry) return false;
      if (q && !(r.c.includes(q) || (r.n || "").toLowerCase().includes(q))) return false;
      return true;
    });
    const k = state.sortKey, dir = state.sortDir;
    v.sort((a, b) => {
      const x = valueOf(a, k), y = valueOf(b, k);
      if (x == null && y == null) return 0;
      if (x == null) return 1;          // 無資料一律排最後
      if (y == null) return -1;
      if (typeof x === "string" || typeof y === "string")
        return String(x).localeCompare(String(y), "zh-Hant") * dir;
      return (x - y) * dir;
    });
    state.view = v;
    renderBody();
  }

  function renderBody() {
    const slice = state.view.slice(0, state.shown);
    $("tbody").innerHTML = slice
      .map((r) => `<tr data-c="${r.c}">${COLS.map((c) => `<td class="${c.cls || ""}">${c.get(r) ?? '<span class="na">—</span>'}</td>`).join("")}</tr>`)
      .join("");
    $("count").textContent = `${state.view.length} 檔`;
    $("more").hidden = state.view.length <= state.shown;
    $("tbody").querySelectorAll("tr").forEach((tr) =>
      tr.addEventListener("click", () => openStock(tr.dataset.c))
    );
  }

  // ---------------------------------------------------------------- 個股面板
  async function openStock(code) {
    const base = state.rows.find((r) => r.c === code);
    if (!base) return;
    const doc = await getJSON(`data/stock/${code}.json`, null);
    const d = doc || base;

    const ov = document.createElement("div");
    ov.className = "overlay";
    const rev = d.rev || {}, fin = d.fin || {};
    ov.innerHTML = `<div class="panel" role="dialog" aria-label="${base.n} 詳細">
      <div class="panel-head">
        <h3>${base.c} ${base.n}</h3>
        <span class="mkt">${LABEL[base.m]}</span>
        <span class="asof">${base.i || ""}</span>
        <button class="close" type="button">關閉</button>
      </div>
      <div class="kv">
        <div><div class="k">股價</div><div class="v">${fmt(base.p) ?? "—"}</div></div>
        <div><div class="k">本益比</div><div class="v">${fmt(base.pe) ?? "—"}</div></div>
        <div><div class="k">股價營收比</div><div class="v">${fmt(base.ps) ?? "—"}</div></div>
        <div><div class="k">淨值比</div><div class="v">${fmt(base.pb) ?? "—"}</div></div>
        <div><div class="k">市值</div><div class="v">${human(base.cap) ?? "—"}</div></div>
      </div>
      <h2>營收</h2>
      <p class="note">最新月份 ${rev.ym || "—"}</p>
      <div class="kv">
        <div><div class="k">當月營收</div><div class="v">${rev.amt != null ? human(rev.amt * 1000) : "—"}</div></div>
        <div><div class="k">年增率</div><div class="v">${cell(rev.yoy, 1, true)}</div></div>
        <div><div class="k">累計年增率</div><div class="v">${cell(rev.cum_yoy, 1, true)}</div></div>
        <div><div class="k">月增率</div><div class="v">${cell(rev.mom, 1, true)}</div></div>
      </div>
      <h2>獲利</h2>
      <p class="note">${fin.y ? `${fin.y} 年第 ${fin.q} 季累計` : "尚無財報資料"}</p>
      <div class="kv">
        <div><div class="k">EPS</div><div class="v">${fmt(fin.eps) ?? "—"}</div></div>
        <div><div class="k">毛利率%</div><div class="v">${fmt(fin.gpm, 1) ?? "—"}</div></div>
        <div><div class="k">營益率%</div><div class="v">${fmt(fin.opm, 1) ?? "—"}</div></div>
        <div><div class="k">淨利率%</div><div class="v">${fmt(fin.npm, 1) ?? "—"}</div></div>
        <div><div class="k">淨利年增%</div><div class="v">${cell(fin.net_yoy, 1, true)}</div></div>
        <div><div class="k">營益年增%</div><div class="v">${cell(fin.op_yoy, 1, true)}</div></div>
      </div>
      <h2>歷年本益比</h2>
      <div class="card"><div class="chart-wrap">
        <div class="chart-scroll"><svg class="chart" id="stockChart" role="img" aria-label="${base.n} 歷年本益比"></svg></div>
        <div class="tooltip" id="stockTip" hidden></div>
      </div></div>
    </div>`;
    document.body.appendChild(ov);

    const close = () => ov.remove();
    ov.querySelector(".close").addEventListener("click", close);
    ov.addEventListener("click", (e) => { if (e.target === ov) close(); });
    document.addEventListener("keydown", function esc(e) {
      if (e.key === "Escape") { close(); document.removeEventListener("keydown", esc); }
    });

    const hist = (d.hist || []).map(([ym, pe]) => [ym, pe]).filter((p) => p[1] != null);
    lineChart(ov.querySelector("#stockChart"), ov.querySelector("#stockTip"),
      hist.length ? [{ key: "pe", name: "本益比", color: SERIES[base.m], points: hist }] : [],
      { unit: "倍", height: 240 });
  }

  // ---------------------------------------------------------------- 事件
  /** attr = data-* 屬性名，key = state 上的欄位名 */
  function bindSeg(id, attr, key, after, cast) {
    const buttons = $(id).querySelectorAll("button");
    buttons.forEach((b) =>
      b.addEventListener("click", () => {
        buttons.forEach((x) => x.setAttribute("aria-pressed", "false"));
        b.setAttribute("aria-pressed", "true");
        const raw = b.dataset[attr];
        state[key] = cast ? cast(raw) : raw;
        after();
      })
    );
  }

  function draw() { renderTiles(); renderHist(); }

  // ---------------------------------------------------------------- 啟動
  (async function init() {
    const [meta, market, hist, rows] = await Promise.all([
      getJSON("data/meta.json", null),
      getJSON("data/market.json", null),
      getJSON("data/market_history.json", null),
      getJSON("data/latest.json", []),
    ]);
    state.meta = meta; state.market = market; state.hist = hist; state.rows = rows || [];

    $("asof").textContent = meta && meta.asOf
      ? `資料日期 ${meta.asOf}・更新於 ${(meta.updatedAt || "").replace("T", " ").slice(0, 16)}`
      : "尚無資料 — 請先在 GitHub Actions 執行一次「每日更新」";

    if (meta) {
      $("coverage").textContent =
        `共 ${meta.total} 檔：有本益比 ${meta.withPE}、有股價營收比 ${meta.withPS}、有月營收 ${meta.withRevenue}、有財報 ${meta.withFinancials}。`;
    }

    const inds = [...new Set(state.rows.map((r) => r.i).filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-Hant"));
    $("industry").innerHTML = '<option value="">所有產業</option>' + inds.map((i) => `<option>${i}</option>`).join("");

    renderHead();
    draw();
    applyFilters();

    $("q").addEventListener("input", (e) => { state.q = e.target.value; state.shown = 200; applyFilters(); });
    $("industry").addEventListener("change", (e) => { state.industry = e.target.value; state.shown = 200; applyFilters(); });
    $("more").addEventListener("click", () => { state.shown += 300; renderBody(); });
    bindSeg("marketSeg", "market", "filterMarket", () => { state.shown = 200; applyFilters(); });
    bindSeg("metricSeg", "metric", "metric", renderHist);
    bindSeg("rangeSeg", "range", "range", renderHist, Number);
  })();
})();
