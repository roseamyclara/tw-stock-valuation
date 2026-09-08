/* 美股估值追蹤 — 前端。版面與台股頁共用 style.css，欄位換成季度指標。 */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const MOBILE = window.matchMedia("(max-width: 860px)");
  const ACCENT = "var(--series-1)";

  const state = {
    rows: [], view: [], meta: null, market: null, tags: {},
    sortKey: "cap", sortDir: -1, tag: "", q: "", shown: 200,
  };

  const tagsOf = (code) => state.tags[code] || [];

  const fmt = (v, d = 2) =>
    v === null || v === undefined || Number.isNaN(v) ? null : Number(v).toFixed(d);

  const human = (n) => {
    if (n === null || n === undefined) return null;
    const a = Math.abs(n);
    // 台灣的位數是四位一跳（萬、億、兆），不是英文的三位一跳（thousand、
    // million、billion）。這裡的數字是美元，但單位跟著讀的人走，
    // 所以跟台股頁用同一套，不出現「十億」「百萬」這種直譯。
    if (a >= 1e12) return (n / 1e12).toFixed(2) + " 兆";
    if (a >= 1e8) return (n / 1e8).toFixed(1) + " 億";
    if (a >= 1e4) return (n / 1e4).toFixed(0) + " 萬";
    return String(Math.round(n));
  };

  const esc = (s) =>
    String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

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
  const SUN = '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><circle cx="10" cy="10" r="3.6" stroke="currentColor" stroke-width="1.7"/><path d="M10 1.6v2M10 16.4v2M18.4 10h-2M3.6 10h-2M15.9 4.1l-1.4 1.4M5.5 14.5l-1.4 1.4M15.9 15.9l-1.4-1.4M5.5 5.5 4.1 4.1" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>';
  const MOON = '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M17 12.2A7.4 7.4 0 0 1 7.8 3a7.4 7.4 0 1 0 9.2 9.2Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>';
  const themeBtn = $("themeToggle");
  const isDarkNow = () => {
    const cur = document.documentElement.getAttribute("data-theme");
    return cur === "dark" || (!cur && window.matchMedia("(prefers-color-scheme: dark)").matches);
  };
  const paintToggle = () => {
    const dark = isDarkNow();
    themeBtn.innerHTML = dark ? SUN : MOON;
    themeBtn.setAttribute("aria-label", dark ? "切換為淺色" : "切換為深色");
  };
  const applyTheme = (t) => {
    if (t) document.documentElement.setAttribute("data-theme", t);
    else document.documentElement.removeAttribute("data-theme");
    paintToggle();
  };
  try { const saved = localStorage.getItem("theme"); if (saved) applyTheme(saved); } catch (_) {}
  paintToggle();
  themeBtn.addEventListener("click", () => {
    const next = isDarkNow() ? "light" : "dark";
    applyTheme(next);
    try { localStorage.setItem("theme", next); } catch (_) {}
    renderTiles();
  });

  // ---------------------------------------------------------------- 頂欄與回頂端
  const topbar = $("topbar");
  const toTop = $("toTop");
  const onScroll = () => {
    const y = window.scrollY;
    topbar.classList.toggle("is-stuck", y > 8);
    toTop.classList.toggle("show", y > 900);
  };
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();
  toTop.addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));

  const stockBar = document.querySelector(".stock-bar");
  if (stockBar) {
    const measure = () =>
      document.documentElement.style.setProperty("--stickbar-h", stockBar.offsetHeight + "px");
    measure();
    if (window.ResizeObserver) new ResizeObserver(measure).observe(stockBar);
    else window.addEventListener("resize", measure);
  }

  // ---------------------------------------------------------------- 總覽卡
  function renderTiles() {
    const d = (state.market && state.market.markets && state.market.markets.us) || null;
    if (!d) {
      $("tiles").innerHTML =
        `<article class="tile" style="--tile-color:${ACCENT}">
           <div class="name"><span class="swatch" style="background:${ACCENT}"></span>美股</div>
           <p class="note" style="margin-top:12px">
             資料尚未產生 —— 到 GitHub 的 Actions 頁執行一次「美股每日更新」即可。
           </p>
         </article>`;
      return;
    }
    const weighted = d.peWeighted ? `本益比 ${fmt(d.peWeighted)}` : "";
    $("tiles").innerHTML = `<article class="tile" style="--tile-color:${ACCENT}">
      <div class="name"><span class="swatch" style="background:${ACCENT}"></span>美股（SEC 申報公司）</div>
      <div class="figs">
        <div class="fig"><div class="v">${fmt(d.pe) ?? '<span class="dash">—</span>'}</div><div class="k">本益比中位數</div></div>
        <div class="fig"><div class="v">${fmt(d.ps) ?? '<span class="dash">—</span>'}</div><div class="k">股價營收比中位數</div></div>
      </div>
      <div class="cnt">${d.count} 檔${d.cap ? "・總市值 " + human(d.cap) : ""}</div>
      ${weighted ? `<div class="cnt">市值加權：${weighted}</div>` : ""}
    </article>`;
  }

  function renderHeroStats() {
    const m = state.meta;
    if (!m) return;
    const items = [
      ["追蹤檔數", m.total],
      ["有本益比", m.withPE],
      ["有報價", m.withPrice],
      ["最近財報季", m.quarter],
    ].filter(([, v]) => v !== undefined && v !== null);
    $("heroStats").innerHTML = items
      .map(([k, v]) => `<span class="pill-stat">${k} <b>${v}</b></span>`).join("");
  }

  // ---------------------------------------------------------------- 表格欄位
  const COLS = [
    { k: "c", t: "代號", cls: "code", get: (r) => r.c },
    { k: "n", t: "名稱", cls: "name-cell", get: (r) => esc(r.n) },
    {
      k: "tags", t: "業務標籤", cls: "ind",
      get: (r) => {
        const ts = tagsOf(r.c);
        return ts.length
          ? ts.map((t) => `<button type="button" class="tag${state.tag === t ? " is-active" : ""}" data-tag="${esc(t)}">${esc(t)}</button>`).join(" ")
          : '<span class="na">—</span>';
      },
    },
    { k: "p", t: "股價", get: (r) => cell(r.p) },
    { k: "cap", t: "市值", get: (r) => human(r.cap) ?? '<span class="na">—</span>' },
    { k: "pe", t: "本益比", get: (r) => cell(r.pe) },
    { k: "ps", t: "股價營收比", get: (r) => cell(r.ps) },
    { k: "pb", t: "淨值比", get: (r) => cell(r.pb) },
    { k: "rev_yoy", t: "季營收年增%", get: (r) => cell(r.fin && r.fin.rev_yoy, 1, true), val: (r) => r.fin && r.fin.rev_yoy },
    { k: "net_yoy", t: "季淨利年增%", get: (r) => cell(r.fin && r.fin.net_yoy, 1, true), val: (r) => r.fin && r.fin.net_yoy },
    { k: "gpm", t: "毛利率%", get: (r) => cell(r.fin && r.fin.gpm, 1), val: (r) => r.fin && r.fin.gpm },
    { k: "npm", t: "淨利率%", get: (r) => cell(r.fin && r.fin.npm, 1), val: (r) => r.fin && r.fin.npm },
    { k: "eps", t: "EPS", get: (r) => cell(r.fin && r.fin.eps), val: (r) => r.fin && r.fin.eps },
  ];

  const SORTABLE = ["cap", "p", "pe", "ps", "pb", "rev_yoy", "net_yoy", "gpm", "npm", "eps"];

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
      th.addEventListener("click", () => sortBy(th.dataset.k)));

    const sel = $("sortMobile");
    sel.innerHTML = SORTABLE.map((k) => {
      const c = COLS.find((x) => x.k === k);
      return `<option value="${k}">${c.t}　由大到小</option><option value="${k}:asc">${c.t}　由小到大</option>`;
    }).join("");
    sel.value = state.sortKey;
    sel.addEventListener("change", (e) => {
      const [k, dir] = e.target.value.split(":");
      state.sortKey = k;
      state.sortDir = dir === "asc" ? 1 : -1;
      state.shown = 200;
      applyFilters();
      syncSortUI();
    });
  }

  function sortBy(k) {
    if (state.sortKey === k) state.sortDir *= -1;
    else { state.sortKey = k; state.sortDir = -1; }
    state.shown = 200;
    applyFilters();
    syncSortUI();
  }

  function syncSortUI() {
    $("thead").querySelectorAll("th").forEach((th) =>
      th.setAttribute("aria-sort",
        state.sortKey === th.dataset.k ? (state.sortDir > 0 ? "ascending" : "descending") : "none"));
    const sel = $("sortMobile");
    if (SORTABLE.includes(state.sortKey)) {
      sel.value = state.sortDir > 0 ? `${state.sortKey}:asc` : state.sortKey;
    }
  }

  function applyFilters() {
    const q = state.q.trim().toLowerCase();
    const v = state.rows.filter((r) => {
      if (state.tag && !tagsOf(r.c).includes(state.tag)) return false;
      if (q && !(r.c.toLowerCase().includes(q) || (r.n || "").toLowerCase().includes(q)
                 || tagsOf(r.c).some((t) => t.toLowerCase().includes(q)))) return false;
      return true;
    });
    const k = state.sortKey, dir = state.sortDir;
    v.sort((a, b) => {
      const x = valueOf(a, k), y = valueOf(b, k);
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      if (typeof x === "string" || typeof y === "string")
        return String(x).localeCompare(String(y)) * dir;
      return (x - y) * dir;
    });
    state.view = v;
    renderBody();
  }

  function stockCard(r) {
    const ts = tagsOf(r.c);
    const tags = ts.length
      ? ts.slice(0, 4).map((t) => `<button type="button" class="tag${state.tag === t ? " is-active" : ""}" data-tag="${esc(t)}">${esc(t)}</button>`).join("")
      : "";
    const metrics = [
      ["本益比", cell(r.pe)],
      ["股價營收比", cell(r.ps)],
      ["淨值比", cell(r.pb)],
      ["EPS", cell(r.fin && r.fin.eps)],
      ["季營收年增%", cell(r.fin && r.fin.rev_yoy, 1, true)],
      ["季淨利年增%", cell(r.fin && r.fin.net_yoy, 1, true)],
      ["毛利率%", cell(r.fin && r.fin.gpm, 1)],
      ["淨利率%", cell(r.fin && r.fin.npm, 1)],
    ];
    return `<div class="scard" data-c="${r.c}" role="button" tabindex="0">
      <div class="scard-top">
        <div class="scard-id">
          <div class="scard-name"><span class="nm">${r.c}</span></div>
          <div class="scard-code">${esc(r.n)}</div>
        </div>
        <div class="scard-price">
          <div class="p">${fmt(r.p) ?? "—"}</div>
          <div class="cap">市值 ${human(r.cap) ?? "—"}</div>
        </div>
      </div>
      ${tags ? `<div class="scard-tags">${tags}</div>` : ""}
      <div class="scard-metrics">
        ${metrics.map(([k, v]) => `<div class="m"><div class="mk">${k}</div><div class="mv">${v}</div></div>`).join("")}
      </div>
    </div>`;
  }

  function renderBody() {
    const slice = state.view.slice(0, state.shown);
    $("tbody").innerHTML = slice
      .map((r) => `<tr data-c="${r.c}">${COLS.map((c) => `<td class="${c.cls || ""}">${c.get(r) ?? '<span class="na">—</span>'}</td>`).join("")}</tr>`)
      .join("");
    $("cards").innerHTML = slice.map(stockCard).join("");

    $("count").innerHTML = state.tag
      ? `<button type="button" class="clear-filter" id="clearFilter">${esc(state.tag)} ✕</button> ${state.view.length} 檔`
      : `${state.view.length} 檔`;
    const cf = $("clearFilter");
    if (cf) cf.addEventListener("click", () => {
      state.tag = ""; $("tagSel").value = ""; state.shown = 200; applyFilters();
    });

    $("more").hidden = state.view.length <= state.shown;

    const onPick = (code) => (e) => {
      const tag = e.target.closest(".tag");
      if (tag) {
        e.stopPropagation();
        state.tag = state.tag === tag.dataset.tag ? "" : tag.dataset.tag;
        $("tagSel").value = state.tag;
        state.shown = 200;
        applyFilters();
        return;
      }
      openStock(code);
    };
    $("tbody").querySelectorAll("tr").forEach((tr) =>
      tr.addEventListener("click", onPick(tr.dataset.c)));
    $("cards").querySelectorAll(".scard").forEach((el) => {
      el.addEventListener("click", onPick(el.dataset.c));
      el.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openStock(el.dataset.c); }
      });
    });
  }

  // ---------------------------------------------------------------- 個股面板
  const CLOSE_ICON = '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="m5.5 5.5 9 9m0-9-9 9" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>';

  function openStock(code) {
    const r = state.rows.find((x) => x.c === code);
    if (!r) return;
    const fin = r.fin || {};
    const ov = document.createElement("div");
    ov.className = "overlay";
    ov.innerHTML = `<div class="panel" role="dialog" aria-modal="true" aria-label="${esc(r.n)} 詳細">
      <div class="panel-grip" aria-hidden="true"></div>
      <div class="panel-head">
        <h3>${r.c}</h3>
        <span class="ind-lbl">${esc(r.n)}</span>
        <button class="close" type="button" aria-label="關閉">${CLOSE_ICON}</button>
      </div>
      ${tagsOf(r.c).length
        ? `<div class="panel-tags">${tagsOf(r.c).map((t) => `<span class="tag static">${esc(t)}</span>`).join("")}</div>`
        : ""}
      <div class="kv">
        <div><div class="k">股價</div><div class="v">${fmt(r.p) ?? "—"}</div></div>
        <div><div class="k">市值</div><div class="v">${human(r.cap) ?? "—"}</div></div>
        <div><div class="k">本益比</div><div class="v">${fmt(r.pe) ?? "—"}</div></div>
        <div><div class="k">股價營收比</div><div class="v">${fmt(r.ps) ?? "—"}</div></div>
        <div><div class="k">淨值比</div><div class="v">${fmt(r.pb) ?? "—"}</div></div>
      </div>
      <h4>獲利（近四季合計）</h4>
      <p class="note">${fin.y ? `最近財報季 ${fin.y} 年第 ${fin.q} 季` : "尚無財報資料"}</p>
      <div class="kv">
        <div><div class="k">EPS</div><div class="v">${fmt(fin.eps) ?? "—"}</div></div>
        <div><div class="k">毛利率%</div><div class="v">${fmt(fin.gpm, 1) ?? "—"}</div></div>
        <div><div class="k">淨利率%</div><div class="v">${fmt(fin.npm, 1) ?? "—"}</div></div>
      </div>
      <h4>成長（最近一季 vs 去年同季）</h4>
      <div class="kv">
        <div><div class="k">季營收年增%</div><div class="v">${cell(fin.rev_yoy, 1, true)}</div></div>
        <div><div class="k">季淨利年增%</div><div class="v">${cell(fin.net_yoy, 1, true)}</div></div>
      </div>
      <div class="links">
        <a href="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=${encodeURIComponent(r.c)}&type=10-K&dateb=&owner=include&count=10" target="_blank" rel="noopener">SEC 申報文件</a>
      </div>
    </div>`;
    document.body.appendChild(ov);
    document.body.style.overflow = "hidden";

    const close = () => {
      ov.remove();
      document.body.style.overflow = "";
      document.removeEventListener("keydown", onEsc);
    };
    function onEsc(e) { if (e.key === "Escape") close(); }
    ov.querySelector(".close").addEventListener("click", close);
    ov.addEventListener("click", (e) => { if (e.target === ov) close(); });
    document.addEventListener("keydown", onEsc);
    ov.querySelector(".close").focus();
  }

  // ---------------------------------------------------------------- 啟動
  (async function init() {
    const [meta, market, rows, tags] = await Promise.all([
      getJSON("data/us/meta.json", null),
      getJSON("data/us/market.json", null),
      getJSON("data/us/latest.json", []),
      getJSON("data/us/tags.json", {}),
    ]);
    state.meta = meta; state.market = market;
    state.rows = rows || []; state.tags = tags || {};

    $("asof").innerHTML = meta && meta.asOf
      ? `${meta.asOf}<span class="asof-more">・更新於 ${esc((meta.updatedAt || "").replace("T", " ").slice(0, 16))}</span>`
      : "尚無資料 — 請先在 GitHub Actions 執行一次「美股每日更新」";

    if (meta) {
      $("coverage").textContent =
        `共 ${meta.total} 檔：有本益比 ${meta.withPE}、有股價營收比 ${meta.withPS}、有報價 ${meta.withPrice}。`
        + `　報價來源：${meta.priceSource === "none" ? "未取得（僅 SEC 官方資料）" : meta.priceSource}。`;
    }

    const allTags = [...new Set(Object.values(state.tags).flat())].sort((a, b) => a.localeCompare(b, "zh-Hant"));
    $("tagSel").innerHTML = '<option value="">所有標籤</option>'
      + allTags.map((t) => `<option>${esc(t)}</option>`).join("");

    renderHead();
    renderHeroStats();
    renderTiles();
    applyFilters();

    $("q").addEventListener("input", (e) => { state.q = e.target.value; state.shown = 200; applyFilters(); });
    $("tagSel").addEventListener("change", (e) => { state.tag = e.target.value; state.shown = 200; applyFilters(); });
    $("more").addEventListener("click", () => { state.shown += 300; renderBody(); });
    MOBILE.addEventListener("change", () => renderTiles());
  })();
})();
