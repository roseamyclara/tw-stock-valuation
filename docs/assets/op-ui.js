/* 營運先行指標面板 UI 增強：移除客戶暫收款、取消存貨周轉天數、比較圖勾選、模式控制移到單項圖上方 */
(() => {
  "use strict";

  const SERIES = [
    { field: "contractObserved", key: "contract", name: "合約負債", color: "var(--accent)" },
    { field: "inventory", key: "inventory", name: "存貨", color: "var(--series-2)" },
    { field: "revenue", key: "revenue", name: "營收", color: "var(--series-3)" },
  ];
  const MOBILE = window.matchMedia("(max-width: 860px)");
  const CUSTOMER_LABEL = "客戶暫收款";
  const TURNOVER_LABEL = "存貨周轉天數";
  const HIDDEN_KEYS = new Set([
    "customer_receipts", "customer_receipts_qoq", "customer_receipts_yoy",
    "customerReceiptsTotal", "contractAndReceipts", "inventoryTurnoverDays",
  ]);

  const fmt = (v, d = 2) =>
    v === null || v === undefined || Number.isNaN(v) ? null : Number(v).toFixed(d);

  function injectStyle() {
    if (document.getElementById("op-ui-style")) return;
    const style = document.createElement("style");
    style.id = "op-ui-style";
    style.textContent = `
      .op-compare-head { align-items: flex-start; gap: 10px; }
      .op-compare-options { display: flex; flex-wrap: wrap; gap: 8px 12px; justify-content: flex-end; }
      .op-compare-options label { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; color: var(--muted); cursor: pointer; user-select: none; }
      .op-compare-options input { width: 14px; height: 14px; accent-color: var(--accent); }
      .op-mode-above-selected { margin-top: 14px; margin-bottom: 8px; }
      @media (max-width: 640px) {
        .op-compare-head { display: block; }
        .op-compare-options { justify-content: flex-start; margin-top: 8px; }
      }
    `;
    document.head.appendChild(style);
  }

  function lineChart(svg, tipEl, series, opts = {}) {
    const W = 900, H = opts.height || 250;
    const M = { t: 14, r: 62, b: 26, l: 44 };
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.innerHTML = "";

    const labels = [];
    series.forEach((s) => s.points.forEach(([label]) => {
      if (!labels.includes(label)) labels.push(label);
    }));
    labels.sort();
    const vals = series.flatMap((s) => s.points.map(([, v]) => v)).filter((v) => v != null);
    if (!series.length || !labels.length || !vals.length) {
      svg.innerHTML = `<text x="${W / 2}" y="${H / 2}" text-anchor="middle" class="tick">請勾選至少一項指標</text>`;
      return;
    }

    let lo = Math.min(...vals), hi = Math.max(...vals);
    const pad = (hi - lo) * 0.12 || Math.abs(hi) * 0.12 || 1;
    lo = Math.max(0, lo - pad);
    hi += pad;

    const X = (i) => M.l + (labels.length === 1 ? 0 : (i * (W - M.l - M.r)) / (labels.length - 1));
    const Y = (v) => H - M.b - ((v - lo) / (hi - lo)) * (H - M.t - M.b);
    const ns = "http://www.w3.org/2000/svg";
    const mk = (name, attrs) => {
      const el = document.createElementNS(ns, name);
      for (const key in attrs) el.setAttribute(key, attrs[key]);
      return el;
    };

    const TICKS = 5;
    for (let i = 0; i <= TICKS; i++) {
      const v = lo + ((hi - lo) * i) / TICKS;
      const y = Y(v);
      svg.appendChild(mk("line", { class: "gridline", x1: M.l, x2: W - M.r, y1: y, y2: y }));
      const t = mk("text", { class: "tick", x: M.l - 7, y: y + 3.5, "text-anchor": "end" });
      t.textContent = v >= 100 ? v.toFixed(0) : v.toFixed(1);
      svg.appendChild(t);
    }
    svg.appendChild(mk("line", { class: "axis", x1: M.l, x2: W - M.r, y1: H - M.b, y2: H - M.b }));

    let lastYear = "", lastX = -Infinity;
    labels.forEach((label, i) => {
      const year = String(label).slice(0, 4);
      if (year === lastYear) return;
      const x = X(i);
      if (x - lastX < 46) { lastYear = year; return; }
      lastYear = year; lastX = x;
      const t = mk("text", { class: "tick", x, y: H - M.b + 15, "text-anchor": "middle" });
      t.textContent = year;
      svg.appendChild(t);
    });

    series.forEach((s) => {
      const pts = labels.map((label, i) => {
        const point = s.points.find((p) => p[0] === label);
        return point && point[1] != null ? [X(i), Y(point[1])] : null;
      });
      let connected = false;
      const d = pts.map((point) => {
        if (!point) { connected = false; return ""; }
        const cmd = connected ? "L" : "M";
        connected = true;
        return `${cmd}${point[0].toFixed(1)},${point[1].toFixed(1)}`;
      }).join(" ");
      const valid = pts.filter(Boolean);
      if (!valid.length) return;
      svg.appendChild(mk("path", { class: "line", stroke: s.color, d }));
      valid.forEach(([cx, cy]) => svg.appendChild(mk("circle", { cx, cy, r: 3, fill: s.color })));
      const last = valid[valid.length - 1];
      const t = mk("text", { class: "lbl", x: last[0] + 8, y: last[1] + 4, fill: s.color });
      t.textContent = s.name;
      svg.appendChild(t);
    });

    const cross = mk("line", { class: "crosshair", y1: M.t, y2: H - M.b, x1: -99, x2: -99 });
    const dots = mk("g", {});
    const hit = mk("rect", { class: "hit", x: M.l, y: M.t, width: W - M.l - M.r, height: H - M.t - M.b });
    svg.appendChild(cross);
    svg.appendChild(dots);
    svg.appendChild(hit);

    const hide = () => {
      if (tipEl) tipEl.hidden = true;
      cross.setAttribute("x1", -99);
      cross.setAttribute("x2", -99);
      dots.innerHTML = "";
    };
    const move = (ev) => {
      if (!tipEl) return;
      const box = svg.getBoundingClientRect();
      const cx = ((ev.clientX - box.left) / box.width) * W;
      let idx = Math.round(((cx - M.l) / (W - M.l - M.r)) * (labels.length - 1));
      idx = Math.max(0, Math.min(labels.length - 1, idx));
      const x = X(idx);
      cross.setAttribute("x1", x);
      cross.setAttribute("x2", x);
      dots.innerHTML = "";
      const rows = [];
      series.forEach((s) => {
        const p = s.points.find((q) => q[0] === labels[idx]);
        if (!p || p[1] == null) return;
        dots.appendChild(mk("circle", { class: "pt", cx: x, cy: Y(p[1]), r: 4.5, fill: s.color }));
        rows.push(`<div class="tt-r"><span><span class="swatch" style="display:inline-block;background:${s.color}"></span> ${s.name}</span><span>${fmt(p[1])}</span></div>`);
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

  function preparePeriods(periods) {
    for (const row of Object.values(periods)) {
      row.contractObserved = row.contractTotal ?? row.contractCurrent ?? null;
      delete row.contractAndReceipts;
      delete row.inventoryTurnoverDays;
    }
  }

  function normalized(periods, labels, field) {
    const basePeriod = labels.find((period) => periods[period] && periods[period][field] != null && periods[period][field] !== 0);
    if (!basePeriod) return [];
    const baseValue = periods[basePeriod][field];
    return labels
      .filter((period) => period >= basePeriod)
      .map((period) => {
        const value = periods[period] && periods[period][field];
        return [period, value == null ? null : value / baseValue * 100];
      });
  }

  function cleanCustomerAndTurnover(panel) {
    panel.querySelectorAll("#opMetric option").forEach((option) => {
      if (HIDDEN_KEYS.has(option.value) || option.textContent.includes(CUSTOMER_LABEL) || option.textContent.includes(TURNOVER_LABEL)) option.remove();
    });
    panel.querySelectorAll(".op-summary .op-kpi, .scard-metrics .m").forEach((el) => {
      if (el.textContent.includes(CUSTOMER_LABEL) || el.textContent.includes(TURNOVER_LABEL)) el.remove();
    });
    panel.querySelectorAll("#opCombinedNote, .op-turnover-note").forEach((el) => el.remove());
  }

  async function enhanceCompareChart(panel) {
    const svg = panel.querySelector("#opCompareChart");
    const tip = panel.querySelector("#opCompareTip");
    const card = panel.querySelector(".op-normalized");
    const head = card?.querySelector(".op-chart-head");
    if (!svg || !card || !head || card.dataset.checkboxEnhanced === "1") return;
    card.dataset.checkboxEnhanced = "1";
    head.classList.add("op-compare-head");

    const titleBlock = document.createElement("div");
    titleBlock.innerHTML = `<strong>三項指標比較</strong><span>各系列首個可用期＝100</span>`;
    const options = document.createElement("div");
    options.className = "op-compare-options";
    options.setAttribute("role", "group");
    options.setAttribute("aria-label", "選擇要顯示於三項指標比較圖的系列");
    options.innerHTML = SERIES.map((s) =>
      `<label><input type="checkbox" data-op-compare-field="${s.field}" checked> ${s.name}</label>`
    ).join("");
    head.replaceChildren(titleBlock, options);

    svg.innerHTML = `<text x="450" y="125" text-anchor="middle" class="tick">載入中…</text>`;
    const code = panel.querySelector(".panel-head h3")?.textContent.trim().match(/^\d+/)?.[0];
    if (!code) return;
    const data = await fetch(`data/operating/${code}.json`, { cache: "no-cache" }).then((r) => r.ok ? r.json() : null).catch(() => null);
    const periods = data?.periods || {};
    preparePeriods(periods);
    const labels = Object.keys(periods).sort();

    const redraw = () => {
      let checked = [...options.querySelectorAll("input:checked")].map((input) => input.dataset.opCompareField);
      if (!checked.length) {
        const first = options.querySelector("input");
        if (first) first.checked = true;
        checked = first ? [first.dataset.opCompareField] : [];
      }
      const series = SERIES
        .filter((s) => checked.includes(s.field))
        .map((s) => ({ ...s, points: normalized(periods, labels, s.field) }));
      lineChart(svg, tip, series, { height: MOBILE.matches ? 220 : 250 });
    };
    options.addEventListener("change", redraw);
    MOBILE.addEventListener("change", redraw);
    redraw();
  }

  function moveModeControls(panel) {
    if (panel.dataset.modeMoved === "1") return;
    const modeControls = [...panel.querySelectorAll(".op-controls")]
      .find((el) => el.querySelector("[data-op-mode]"));
    const selectedCard = panel.querySelector("#opSelectedChart")?.closest(".card");
    if (!modeControls || !selectedCard) return;
    modeControls.classList.add("op-mode-above-selected");
    selectedCard.before(modeControls);
    panel.dataset.modeMoved = "1";
  }

  function enhance(panel) {
    if (!panel || panel.dataset.opUiEnhanced === "1") return;
    panel.dataset.opUiEnhanced = "1";
    injectStyle();
    cleanCustomerAndTurnover(panel);
    moveModeControls(panel);
    enhanceCompareChart(panel);
  }

  const observer = new MutationObserver(() => {
    document.querySelectorAll(".overlay .panel").forEach(enhance);
  });
  observer.observe(document.body, { childList: true, subtree: true });
})();
