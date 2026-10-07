/* 內部人買賣：表格欄位與個股面板圖表（非侵入式外掛） */
(() => {
  "use strict";

  const DATA_URL = "data/insider_flows.json";
  const PRICES_URL = "data/prices.json";
  const WINDOWS = [
    ["d1", "內部人1日"],
    ["d5", "內部人5天"],
    ["d10", "內部人10天"],
    ["d30", "內部人30天"],
  ];
  const BUY = "#ef4444";   // 台股習慣：紅 = 買進／向上
  const SELL = "#16a34a";  // 綠 = 賣出／向下

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>\"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[c]));

  let flowData = null;
  let priceData = null;
  let loading = null;
  let syncing = false;
  let pendingSync = false;

  function ensureStyle() {
    if ($("insider-flow-style")) return;
    const style = document.createElement("style");
    style.id = "insider-flow-style";
    style.textContent = `
      #tbl th.insider-col,#tbl td.insider-col{white-space:nowrap;text-align:right}
      #tbl th.insider-col{min-width:92px}
      .insider-chip{font-variant-numeric:tabular-nums}
      .insider-chip.pos{color:${BUY};font-weight:700}
      .insider-chip.neg{color:${SELL};font-weight:700}
      .insider-chip.zero,.insider-chip.na{color:var(--muted)}
      .insider-panel-note{margin:6px 0 10px;color:var(--muted);font-size:.9rem;line-height:1.5}
      .insider-chart-card{margin-top:12px}
      .insider-chart{display:block;width:100%;min-width:720px;height:auto}
      .insider-axis{stroke:var(--line);stroke-width:1}
      .insider-grid{stroke:var(--line);stroke-width:1;opacity:.65}
      .insider-price-line{fill:none;stroke:var(--accent);stroke-width:2.2}
      .insider-price-dot{fill:var(--accent)}
      .insider-label{fill:var(--muted);font-size:12px}
      .insider-legend{display:flex;gap:14px;align-items:center;flex-wrap:wrap;color:var(--muted);font-size:.9rem;margin-top:8px}
      .insider-legend i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:5px;vertical-align:-1px}
      .scard .insider-added .mk{color:var(--muted)}
    `;
    document.head.appendChild(style);
  }

  async function loadData() {
    if (flowData) return flowData;
    if (!loading) {
      loading = Promise.all([
        fetch(DATA_URL, { cache: "no-cache" }).then(r => r.ok ? r.json() : null).catch(() => null),
        fetch(PRICES_URL, { cache: "no-cache" }).then(r => r.ok ? r.json() : null).catch(() => null),
      ]).then(([flows, prices]) => {
        flowData = flows && flows.stocks ? flows : { stocks: {}, asOf: null, unit: "張" };
        priceData = prices || { dates: [], p: {} };
        return flowData;
      });
    }
    return loading;
  }

  function stock(code) {
    return (flowData && flowData.stocks && flowData.stocks[code]) || null;
  }

  function fmtLots(v) {
    if (v == null || Number.isNaN(Number(v))) return '<span class="insider-chip na">—</span>';
    const n = Number(v);
    if (Math.abs(n) < 0.001) return '<span class="insider-chip zero">0</span>';
    const cls = n > 0 ? "pos" : "neg";
    const abs = Math.abs(n);
    const body = abs >= 100 ? n.toFixed(0) : abs >= 10 ? n.toFixed(1) : n.toFixed(2);
    return `<span class="insider-chip ${cls}" title="單位：張">${n > 0 ? "+" : ""}${body}</span>`;
  }

  function insertAfter(ref, nodes) {
    let at = ref;
    nodes.forEach((node) => { at.after(node); at = node; });
  }

  function makeTh(key, text) {
    const th = document.createElement("th");
    th.className = "insider-col";
    th.dataset.insider = key;
    th.title = "內部人市場買進為正、賣出或持股轉讓為負；單位：張。";
    th.textContent = text;
    return th;
  }

  function makeTd(code, key) {
    const td = document.createElement("td");
    td.className = "insider-col";
    td.dataset.insider = key;
    const v = stock(code)?.summary?.[key];
    td.innerHTML = fmtLots(v);
    return td;
  }

  function augmentTable() {
    const table = $("tbl"), head = $("thead"), body = $("tbody");
    if (!table || !head || !body || !flowData) return;

    if (head.querySelectorAll("th.insider-col").length !== WINDOWS.length) {
      head.querySelectorAll("th.insider-col").forEach(n => n.remove());
      const priceHead = head.querySelector('th[data-k="priceReturn"]') || head.querySelector("th:last-child");
      if (priceHead) insertAfter(priceHead, WINDOWS.map(([k, t]) => makeTh(k, t)));
    }

    body.querySelectorAll("tr[data-c]").forEach((tr) => {
      if (tr.querySelectorAll("td.insider-col").length === WINDOWS.length) return;
      tr.querySelectorAll("td.insider-col").forEach(n => n.remove());
      const code = tr.dataset.c;
      const priceCellIndex = [...head.querySelectorAll("th")].findIndex(th => th.dataset.k === "priceReturn");
      const ref = priceCellIndex >= 0 ? tr.children[priceCellIndex] : tr.lastElementChild;
      if (!ref) return;
      insertAfter(ref, WINDOWS.map(([k]) => makeTd(code, k)));
    });
  }

  function augmentCards() {
    const cards = $("cards");
    if (!cards || !flowData) return;
    cards.querySelectorAll(".scard[data-c]").forEach((card) => {
      if (card.querySelectorAll(".insider-added").length === WINDOWS.length) return;
      card.querySelectorAll(".insider-added").forEach(n => n.remove());
      const metrics = card.querySelector(".scard-metrics");
      if (!metrics) return;
      const code = card.dataset.c;
      const data = stock(code);
      if (!data) return;
      metrics.insertAdjacentHTML("beforeend", WINDOWS.map(([k, t]) =>
        `<div class="m insider-added"><div class="mk">${t}</div><div class="mv">${fmtLots(data.summary?.[k])}</div></div>`
      ).join(""));
    });
  }

  function priceSeries(code) {
    const dates = priceData?.dates || [];
    const arr = priceData?.p?.[code] || [];
    return dates.map((d, i) => [d, arr[i]]).filter(([, v]) => v != null).slice(-180);
  }

  function drawInsiderChart(svg, code) {
    const rec = stock(code);
    const events = (rec?.series || []).map(([d, buy, sell, net, source]) => ({
      d, buy: Number(buy || 0), sell: Number(sell || 0), net: Number(net || 0), source: source || ""
    })).filter(x => x.buy || x.sell).slice(-180);
    const prices = priceSeries(code);
    const labels = [...new Set([...prices.map(p => p[0]), ...events.map(e => e.d)])].sort().slice(-180);

    const W = 900, H = 300, M = { t: 16, r: 54, b: 34, l: 52 };
    const ns = "http://www.w3.org/2000/svg";
    const mk = (name, attrs = {}) => {
      const el = document.createElementNS(ns, name);
      Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
      return el;
    };
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.innerHTML = "";
    if (!labels.length || (!events.length && !prices.length)) {
      const t = mk("text", { x: W / 2, y: H / 2, "text-anchor": "middle", class: "insider-label" });
      t.textContent = "尚無內部人買賣資料";
      svg.appendChild(t);
      return;
    }

    const X = (idx) => M.l + (labels.length <= 1 ? 0 : idx * (W - M.l - M.r) / (labels.length - 1));
    const baseline = H - M.b - 78;
    const top = M.t + 12;
    const bottom = H - M.b;
    svg.appendChild(mk("line", { x1: M.l, x2: W - M.r, y1: baseline, y2: baseline, class: "insider-axis" }));
    svg.appendChild(mk("line", { x1: M.l, x2: W - M.r, y1: bottom, y2: bottom, class: "insider-grid" }));

    const byDate = new Map(events.map(e => [e.d, e]));
    const maxLots = Math.max(1, ...events.map(e => Math.max(e.buy, e.sell)));
    const barW = Math.max(3, Math.min(14, (W - M.l - M.r) / Math.max(labels.length, 20) * 0.68));
    labels.forEach((d, idx) => {
      const e = byDate.get(d);
      if (!e) return;
      const x = X(idx) - barW / 2;
      if (e.buy > 0) {
        const h = Math.max(2, e.buy / maxLots * 70);
        const r = mk("rect", { x, y: baseline - h, width: barW, height: h, rx: 2, fill: BUY });
        r.appendChild(mk("title", {})).textContent = `${d} 買進 ${e.buy} 張`;
        svg.appendChild(r);
      }
      if (e.sell > 0) {
        const h = Math.max(2, e.sell / maxLots * 70);
        const r = mk("rect", { x, y: baseline, width: barW, height: h, rx: 2, fill: SELL });
        r.appendChild(mk("title", {})).textContent = `${d} 賣出/轉讓 ${e.sell} 張`;
        svg.appendChild(r);
      }
    });

    const priceMap = new Map(prices);
    const values = labels.map(d => priceMap.get(d)).filter(v => v != null);
    if (values.length) {
      let lo = Math.min(...values), hi = Math.max(...values);
      if (lo === hi) { lo -= 1; hi += 1; }
      const pad = (hi - lo) * 0.12 || 1;
      lo -= pad; hi += pad;
      const Yp = (v) => top + (hi - v) / (hi - lo) * (baseline - top - 20);
      let connected = false;
      const path = labels.map((d, idx) => {
        const v = priceMap.get(d);
        if (v == null) { connected = false; return ""; }
        const cmd = connected ? "L" : "M";
        connected = true;
        return `${cmd}${X(idx).toFixed(1)},${Yp(v).toFixed(1)}`;
      }).join(" ");
      svg.appendChild(mk("path", { d: path, class: "insider-price-line" }));
      const last = [...labels].reverse().find(d => priceMap.get(d) != null);
      if (last) {
        const idx = labels.indexOf(last), v = priceMap.get(last);
        svg.appendChild(mk("circle", { cx: X(idx), cy: Yp(v), r: 3.5, class: "insider-price-dot" }));
        const t = mk("text", { x: Math.min(W - M.r, X(idx) + 8), y: Yp(v) + 4, class: "insider-label" });
        t.textContent = `股價 ${Number(v).toFixed(2)}`;
        svg.appendChild(t);
      }
    }

    let lastYear = "", lastX = -999;
    labels.forEach((d, idx) => {
      const year = d.slice(0, 4), x = X(idx);
      if (year === lastYear || x - lastX < 60) return;
      lastYear = year; lastX = x;
      const t = mk("text", { x, y: H - 12, "text-anchor": "middle", class: "insider-label" });
      t.textContent = year;
      svg.appendChild(t);
    });
  }

  function panelCode(panel) {
    const h = panel.querySelector(".panel-head h3, h3");
    const m = h && h.textContent.match(/\b\d{4}\b/);
    return m ? m[0] : null;
  }

  function augmentPanel(panel) {
    if (!panel || panel.dataset.insiderDone || !flowData) return;
    const code = panelCode(panel);
    if (!code) return;
    panel.dataset.insiderDone = "1";
    const section = document.createElement("div");
    section.className = "insider-panel";
    section.innerHTML = `
      <h4>內部人買賣 vs 股價</h4>
      <p class="insider-panel-note">表格統計為最近 1／5／10／30 天買進減賣出，單位張；紅色向上為買進，綠色向下為賣出或持股轉讓。資料若尚未累積，會先顯示空白。</p>
      <div class="card insider-chart-card"><div class="chart-wrap"><div class="chart-scroll"><svg class="insider-chart" role="img" aria-label="內部人買賣與股價歷史圖"></svg></div></div>
      <div class="insider-legend"><span><i style="background:${BUY}"></i>買進</span><span><i style="background:${SELL}"></i>賣出</span><span><i style="background:var(--accent)"></i>股價</span></div></div>
    `;
    const before = [...panel.querySelectorAll("h4")].find(h => h.textContent.includes("歷年本益比"));
    if (before) before.before(section);
    else panel.appendChild(section);
    drawInsiderChart(section.querySelector("svg"), code);
  }

  function sync() {
    if (!flowData || syncing) return;
    syncing = true;
    try {
      ensureStyle();
      // 表格與手機欄位由 app.js 原生欄位系統處理；此檔只負責個股歷史圖。
      document.querySelectorAll(".overlay .panel").forEach(augmentPanel);
    } finally {
      syncing = false;
    }
  }

  function scheduleSync() {
    if (pendingSync) return;
    pendingSync = true;
    requestAnimationFrame(() => {
      pendingSync = false;
      sync();
    });
  }

  loadData().then(scheduleSync);
  new MutationObserver(() => { if (flowData) scheduleSync(); }).observe(document.body, { childList: true, subtree: true });
})();
