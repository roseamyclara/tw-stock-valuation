/* 台股估值追蹤 — 前端 */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const MARKETS = ["listed", "otc", "esb"];
  const LABEL = { listed: "上市", otc: "上櫃", esb: "興櫃" };
  const SERIES = { listed: "var(--series-1)", otc: "var(--series-2)", esb: "var(--series-3)" };

  // 平板以下改用卡片列表；桌機用完整表格。斷點與 style.css 的 860px 一致。
  const MOBILE = window.matchMedia("(max-width: 860px)");

  // 公開資訊觀測站的市場代碼
  const MOPS_TYPE = { listed: "sii", otc: "otc", esb: "rotc" };

  // 官方開放資料的「產業別」→ 產業價值鏈資訊平台對應的產業鏈說明頁。
  // 只是連結，不是把對方的分類抄過來：他們的使用條款禁止重製與散布其內容。
  const CHAIN = {
    半導體業: "D000", 電腦及週邊設備業: "F000", 光電業: "G000", 通信網路業: "I000",
    電子零組件業: "J000", 資訊服務業: "R000", 其他電子業: "X000",
    生技醫療業: "C100", 農業科技: "C300",
    水泥工業: "1000", 食品工業: "M000", 塑膠工業: "N000", 化學工業: "N000",
    橡膠工業: "N000", 紡織纖維: "O000", 電機機械: "P000", 電器電纜: "P000",
    造紙工業: "2000", 鋼鐵工業: "Q000", 汽車工業: "3000",
    建材營造業: "S000", 航運業: "T000", 觀光餐旅: "B000", 觀光事業: "B000",
    金融保險業: "U000", 貿易百貨業: "V000", 油電燃氣業: "W000",
    文化創意業: "Y000", 電子商務: "R300", 數位雲端: "5400", 運動休閒: "5800",
    居家生活: "V000", 玻璃陶瓷: "X000", 綜合: "X000", 其他業: "X000", 其他: "X000",
  };

  const chainUrl = (ind) => (CHAIN[ind] ? `https://ic.tpex.org.tw/introduce.php?ic=${CHAIN[ind]}` : null);
  const mopsUrl = (r) => `https://mopsov.twse.com.tw/mops/web/t05st03?TYPEK=${MOPS_TYPE[r.m] || "sii"}&co_id=${r.c}`;

  const state = {
    rows: [], view: [], meta: null, market: null, tags: {}, movers: null, history: null,
    tdcc: { date: null, base: null, d: {} },
    // sorts: [{k, dir}]，最多 3 個，陣列順序就是優先序（索引 0 最優先）
    // 空陣列代表沒設任何條件，套用 DEFAULT_SORTS
    sorts: [], filterMarket: "", industry: "", tag: "", q: "",
    shown: 200, period: "d1", moverMarket: "listed",
  };

  const tagsOf = (code) => state.tags[code] || [];

  // 集保「400 張以上」大股東：[占集保庫存比例%, 與四週前的差(百分點)]
  const tdccOf = (code) => state.tdcc.d[code] || [null, null];

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
  try {
    const saved = localStorage.getItem("theme");
    if (saved) applyTheme(saved);
  } catch (_) {}
  paintToggle();
  themeBtn.addEventListener("click", () => {
    const next = isDarkNow() ? "light" : "dark";
    applyTheme(next);
    try { localStorage.setItem("theme", next); } catch (_) {}
    draw();
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

  // 釘住的篩選列高度會隨換行改變，量出來給表頭的 sticky top 用
  const stockBar = document.querySelector(".stock-bar");
  if (stockBar) {
    const measure = () =>
      document.documentElement.style.setProperty("--stickbar-h", stockBar.offsetHeight + "px");
    measure();
    if (window.ResizeObserver) new ResizeObserver(measure).observe(stockBar);
    else window.addEventListener("resize", measure);
  }

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

  // ---------------------------------------------------------------- 迷你走勢線
  /** 近三年的月本益比，畫成卡片下方的小走勢線。沒有歷史（興櫃）就不畫。 */
  function sparkline(marketKey) {
    const monthly = state.history && state.history.monthly;
    if (!monthly) return "";
    const keys = Object.keys(monthly).sort().slice(-36);
    const pts = keys
      .map((k) => {
        const m = monthly[k] && monthly[k].m && monthly[k].m[marketKey];
        return m && m.pe != null ? [k, m.pe] : null;
      })
      .filter(Boolean);
    if (pts.length < 6) {
      return '<div class="spark spark-empty"><div class="spark-lbl">官方未發布這個板塊的歷史本益比，無走勢可畫。</div></div>';
    }

    const W = 260, H = 40;
    const vals = pts.map((p) => p[1]);
    let lo = Math.min(...vals), hi = Math.max(...vals);
    if (hi === lo) { hi += 1; lo -= 1; }
    const pad = (hi - lo) * 0.16;
    lo -= pad; hi += pad;
    const X = (i) => (i * W) / (pts.length - 1);
    const Y = (v) => H - ((v - lo) / (hi - lo)) * H;

    const d = pts.map((p, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(p[1]).toFixed(1)}`).join(" ");
    const area = `${d} L${W},${H} L0,${H} Z`;
    const gid = `sg-${marketKey}`;
    const first = pts[0][1], last = pts[pts.length - 1][1];
    const diff = last - first;
    const since = pts[0][0];

    return `<div class="spark">
      <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="${LABEL[marketKey]}近三年本益比走勢">
        <defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="${SERIES[marketKey]}" stop-opacity="0.26"/>
          <stop offset="100%" stop-color="${SERIES[marketKey]}" stop-opacity="0"/>
        </linearGradient></defs>
        <path d="${area}" fill="url(#${gid})" stroke="none"/>
        <path d="${d}" stroke="${SERIES[marketKey]}" vector-effect="non-scaling-stroke"/>
      </svg>
      <div class="spark-lbl">本益比走勢 ${since} 起　<span class="${diff >= 0 ? "pos" : "neg"}">${diff >= 0 ? "+" : ""}${diff.toFixed(1)}</span></div>
    </div>`;
  }

  // ---------------------------------------------------------------- 總覽卡
  function renderTiles() {
    const m = state.market && state.market.markets;
    const counts = (state.meta && state.meta.counts) || {};
    $("tiles").innerHTML = MARKETS.map((k) => {
      const d = (m && m[k]) || {};
      const n = counts[k] || d.count || 0;
      const weighted = [
        d.peWeighted ? `本益比 ${fmt(d.peWeighted)}` : null,
        d.psWeighted ? `股價營收比 ${fmt(d.psWeighted)}` : null,
      ].filter(Boolean).join("、");
      const pe = fmt(d.pe), ps = fmt(d.ps);
      return `<article class="tile" style="--tile-color:${SERIES[k]}">
        <div class="name"><span class="swatch" style="background:${SERIES[k]}"></span>${LABEL[k]}</div>
        <div class="figs">
          <div class="fig"><div class="v">${pe ?? '<span class="dash">—</span>'}</div><div class="k">本益比中位數</div></div>
          <div class="fig"><div class="v">${ps ?? '<span class="dash">—</span>'}</div><div class="k">股價營收比中位數</div></div>
        </div>
        <div class="cnt">${n} 檔${d.cap ? "・總市值 " + human(d.cap) : ""}</div>
        ${weighted ? `<div class="cnt">市值加權：${weighted}</div>` : ""}
        ${sparkline(k)}
      </article>`;
    }).join("");
  }

  function renderHeroStats() {
    const meta = state.meta;
    if (!meta) return;
    const cap = state.market && state.market.markets
      ? MARKETS.reduce((s, k) => s + ((state.market.markets[k] || {}).cap || 0), 0)
      : null;
    const items = [
      ["追蹤檔數", meta.total],
      ["有本益比", meta.withPE],
      ["有月營收", meta.withRevenue],
      ["有財報", meta.withFinancials],
    ];
    if (cap) items.unshift(["三板塊總市值", human(cap)]);
    $("heroStats").innerHTML = items
      .map(([k, v]) => `<span class="pill-stat">${k} <b>${v}</b></span>`)
      .join("");
  }

  // ---------------------------------------------------------------- 表格欄位
  const COLS = [
    { k: "c", t: "代號", cls: "code", get: (r) => r.c },
    { k: "n", t: "名稱", cls: "name-cell", get: (r) => `${esc(r.n)} <span class="mkt">${LABEL[r.m]}</span>` },
    {
      k: "i", t: "業務標籤", cls: "ind",
      // 有業務標籤就顯示業務標籤；沒有的話退回官方產業別（樣式做區隔，一眼看得出來源不同）
      get: (r) => {
        const ts = tagsOf(r.c);
        if (ts.length) {
          return ts.map((t) => `<button type="button" class="tag${state.tag === t ? " is-active" : ""}" data-tag="${esc(t)}">${esc(t)}</button>`).join(" ");
        }
        return r.i ? `<button type="button" class="tag ind-tag${state.industry === r.i ? " is-active" : ""}" data-ind="${esc(r.i)}">${esc(r.i)}</button>` : '<span class="na">—</span>';
      },
    },
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
    // 籌碼面：集保股權分散表，一張 = 1,000 股，所以「400 張以上」= 400,000 股以上
    { k: "big", t: "400張以上%", get: (r) => cell(tdccOf(r.c)[0]), val: (r) => tdccOf(r.c)[0] },
    { k: "big_chg", t: "大戶月增減", get: (r) => cell(tdccOf(r.c)[1], 2, true), val: (r) => tdccOf(r.c)[1] },
  ];

  // 手機排序選單只放有意義的數值欄位
  const SORTABLE = ["cap", "p", "pe", "ps", "pb", "dy", "rev_yoy", "rev_cum", "net_yoy", "eps",
                    "big", "big_chg"];

  // ------------------------------------------------------------ 多欄排序
  const DEFAULT_SORTS = [{ k: "cap", dir: -1 }];   // 沒設條件時：市值由大到小
  const MAX_SORTS = 3;
  // 文字欄位第一次點由小到大比較直覺；數值欄位習慣先看大的
  const FIRST_DIR = { c: 1, n: 1, i: 1 };
  const firstDir = (k) => FIRST_DIR[k] || -1;
  const activeSorts = () => (state.sorts.length ? state.sorts : DEFAULT_SORTS);

  const valueOf = (r, k) => {
    const col = COLS.find((c) => c.k === k);
    const v = col && col.val ? col.val(r) : r[k];
    return v === undefined ? null : v;
  };

  const HEAD_HINT = `點一次由大到小、再點一次由小到大、第三次移除；最多同時 ${MAX_SORTS} 欄，數字越小越優先`;

  function thHtml(c) {
    const i = state.sorts.findIndex((s) => s.k === c.k);
    const s = i >= 0 ? state.sorts[i] : null;
    const aria = s ? (s.dir > 0 ? "ascending" : "descending") : "none";
    const ind = s
      ? `<span class="sort-ind" aria-hidden="true">${s.dir > 0 ? "↑" : "↓"}<b>${i + 1}</b></span>`
      : "";
    return `<th data-k="${c.k}" aria-sort="${aria}" title="${HEAD_HINT}">${c.t}${ind}</th>`;
  }

  /** 只重畫表頭（排序條件變動時呼叫），innerHTML 會換掉節點所以事件要重綁 */
  function paintHead() {
    const thead = $("thead");
    thead.innerHTML = COLS.map(thHtml).join("");
    thead.querySelectorAll("th").forEach((th) =>
      th.addEventListener("click", () => sortBy(th.dataset.k))
    );
  }

  function renderHead() {
    paintHead();

    const sel = $("sortMobile");
    sel.innerHTML = SORTABLE.map((k) => {
      const c = COLS.find((x) => x.k === k);
      return `<option value="${k}">${c.t}　由大到小</option><option value="${k}:asc">${c.t}　由小到大</option>`;
    }).join("");
    sel.value = DEFAULT_SORTS[0].k;
    // 手機的下拉選單維持單欄排序：選了就取代掉整組條件
    sel.addEventListener("change", (e) => {
      const [k, dir] = e.target.value.split(":");
      state.sorts = [{ k, dir: dir === "asc" ? 1 : -1 }];
      state.shown = 200;
      applyFilters();
      syncSortUI();
    });
  }

  /**
   * 點欄位標題：第一次加入條件、第二次反向、第三次移除。
   * 條件可以同時存在最多 MAX_SORTS 個，箭頭旁的數字就是優先序。
   */
  function sortBy(k) {
    if (!COLS.some((c) => c.k === k)) return;
    const i = state.sorts.findIndex((s) => s.k === k);
    if (i >= 0) {
      const s = state.sorts[i];
      if (s.dir === firstDir(k)) s.dir = -firstDir(k);   // 第二次：反向
      else state.sorts.splice(i, 1);                     // 第三次：移除
    } else {
      if (state.sorts.length >= MAX_SORTS) { toast(`最多同時排序 ${MAX_SORTS} 欄，請先取消一個`); return; }
      state.sorts.push({ k, dir: firstDir(k) });
    }
    state.shown = 200;
    applyFilters();
    syncSortUI();
  }

  /** 還原成預設排序（市值由大到小） */
  function resetSort() {
    if (!state.sorts.length) return;
    state.sorts = [];
    state.shown = 200;
    applyFilters();
    syncSortUI();
  }

  function syncSortUI() {
    paintHead();
    const sel = $("sortMobile");
    const primary = activeSorts()[0];
    if (SORTABLE.includes(primary.k)) {
      sel.value = primary.dir > 0 ? `${primary.k}:asc` : primary.k;
    }
  }

  let toastTimer = null;
  function toast(msg) {
    let el = document.querySelector(".toast");
    if (!el) {
      el = document.createElement("div");
      el.className = "toast";
      el.setAttribute("role", "status");
      document.body.appendChild(el);
    }
    el.textContent = msg;
    el.classList.add("is-on");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("is-on"), 2000);
  }

  // 點到頁面「真正的空白處」才還原預設排序；點表格、控制項、卡片都不算
  const KEEP_SORT = "#tbl, #sortMobile, a, button, input, select, textarea, label," +
    " [role='button'], [role='group'], dialog, .modal, .sheet, .card, .tile," +
    " .stock-cards, .rank, details, summary, .toast";
  // 用捕獲階段判斷：等到冒泡才判斷的話，表格早就重繪了，e.target 已經脫離 DOM，
  // closest() 會一律回傳 null，變成點表頭也被當成「點空白處」。
  document.addEventListener("click", (e) => {
    if (!state.sorts.length) return;
    const t = e.target;
    if (t instanceof Element && (t.closest(KEEP_SORT) || !t.isConnected)) return;
    resetSort();
  }, true);

  function applyFilters() {
    const q = state.q.trim().toLowerCase();
    let v = state.rows.filter((r) => {
      if (state.filterMarket && r.m !== state.filterMarket) return false;
      if (state.industry && r.i !== state.industry) return false;
      if (state.tag && !tagsOf(r.c).includes(state.tag)) return false;
      // 搜尋同時比對代號、名稱與業務標籤，所以打「外籍移工」找得到統振
      if (q && !(r.c.includes(q) || (r.n || "").toLowerCase().includes(q)
                 || tagsOf(r.c).some((t) => t.toLowerCase().includes(q)))) return false;
      return true;
    });
    // 依序比對每個排序條件，先分出勝負的那個決定順序
    const sorts = activeSorts();
    v.sort((a, b) => {
      for (const s of sorts) {
        const x = valueOf(a, s.k), y = valueOf(b, s.k);
        if (x == null && y == null) continue;
        if (x == null) return 1;        // 無資料一律排最後
        if (y == null) return -1;
        const d = (typeof x === "string" || typeof y === "string")
          ? String(x).localeCompare(String(y), "zh-Hant") * s.dir
          : (x - y) * s.dir;
        if (d) return d;
      }
      return 0;
    });
    state.view = v;
    renderBody();
  }

  /** 手機用：一檔一張卡，重點指標直接攤開，不必左右拖 */
  function stockCard(r) {
    const ts = tagsOf(r.c);
    const tags = ts.length
      ? ts.slice(0, 4).map((t) => `<button type="button" class="tag${state.tag === t ? " is-active" : ""}" data-tag="${esc(t)}">${esc(t)}</button>`).join("")
      : (r.i ? `<button type="button" class="tag ind-tag${state.industry === r.i ? " is-active" : ""}" data-ind="${esc(r.i)}">${esc(r.i)}</button>` : "");
    const metrics = [
      ["本益比", cell(r.pe)],
      ["股價營收比", r.ps == null ? '<span class="na">—</span>' : cell(r.ps) + (r.ps_basis === "估算" ? '<span class="est">估</span>' : "")],
      ["淨值比", cell(r.pb)],
      ["殖利率%", cell(r.dy)],
      ["月營收年增%", cell(r.rev && r.rev.yoy, 1, true)],
      ["累計年增%", cell(r.rev && r.rev.cum_yoy, 1, true)],
      ["淨利年增%", cell(r.fin && r.fin.net_yoy, 1, true)],
      ["EPS", cell(r.fin && r.fin.eps)],
      ["400張以上%", cell(tdccOf(r.c)[0])],
      ["大戶月增減", cell(tdccOf(r.c)[1], 2, true)],
    ];
    return `<div class="scard" data-c="${r.c}" role="button" tabindex="0">
      <div class="scard-top">
        <div class="scard-id">
          <div class="scard-name"><span class="nm">${esc(r.n)}</span><span class="mkt">${LABEL[r.m]}</span></div>
          <div class="scard-code">${r.c}</div>
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

    const active = state.tag || state.industry;
    $("count").innerHTML = active
      ? `<button type="button" class="clear-filter" id="clearFilter">${esc(active)} ✕</button> ${state.view.length} 檔`
      : `${state.view.length} 檔`;
    const cf = $("clearFilter");
    if (cf) cf.addEventListener("click", () => {
      state.tag = ""; state.industry = ""; $("industry").value = "";
      state.shown = 200; applyFilters();
    });

    $("more").hidden = state.view.length <= state.shown;

    // 點標籤是篩選，不是打開個股。再點一次同一個就取消。
    const onPick = (el, code) => (e) => {
      const tag = e.target.closest(".tag");
      if (tag) {
        e.stopPropagation();
        if (tag.dataset.tag !== undefined) {
          state.tag = state.tag === tag.dataset.tag ? "" : tag.dataset.tag;
          state.industry = "";
        } else {
          state.industry = state.industry === tag.dataset.ind ? "" : tag.dataset.ind;
          state.tag = "";
        }
        $("industry").value = state.industry;
        state.shown = 200;
        applyFilters();
        return;
      }
      openStock(code);
    };

    $("tbody").querySelectorAll("tr").forEach((tr) =>
      tr.addEventListener("click", onPick(tr, tr.dataset.c)));

    $("cards").querySelectorAll(".scard").forEach((el) => {
      el.addEventListener("click", onPick(el, el.dataset.c));
      el.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openStock(el.dataset.c); }
      });
    });
  }

  // ---------------------------------------------------------------- 個股面板
  const CLOSE_ICON = '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="m5.5 5.5 9 9m0-9-9 9" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>';

  async function openStock(code) {
    const base = state.rows.find((r) => r.c === code);
    if (!base) return;
    // 個股檔只存歷史；當前股價與估值直接用已載入的 latest.json
    const d = (await getJSON(`data/stock/${code}.json`, null)) || {};
    const rev = base.rev || {}, fin = base.fin || {};

    const ov = document.createElement("div");
    ov.className = "overlay";
    ov.innerHTML = `<div class="panel" role="dialog" aria-modal="true" aria-label="${esc(base.n)} 詳細">
      <div class="panel-grip" aria-hidden="true"></div>
      <div class="panel-head">
        <h3>${base.c} ${esc(base.n)}</h3>
        <span class="mkt">${LABEL[base.m]}</span>
        <span class="ind-lbl">${esc(base.i || "")}</span>
        <button class="close" type="button" aria-label="關閉">${CLOSE_ICON}</button>
      </div>
      ${tagsOf(base.c).length
        ? `<div class="panel-tags">${tagsOf(base.c).map((t) => `<span class="tag static">${esc(t)}</span>`).join("")}</div>`
        : ""}
      <div class="kv">
        <div><div class="k">股價</div><div class="v">${fmt(base.p) ?? "—"}</div></div>
        <div><div class="k">本益比</div><div class="v">${fmt(base.pe) ?? "—"}</div></div>
        <div><div class="k">股價營收比</div><div class="v">${fmt(base.ps) ?? "—"}</div></div>
        <div><div class="k">淨值比</div><div class="v">${fmt(base.pb) ?? "—"}</div></div>
        <div><div class="k">市值</div><div class="v">${human(base.cap) ?? "—"}</div></div>
      </div>
      <div class="links">
        <a href="${mopsUrl(base)}" target="_blank" rel="noopener">公開資訊觀測站</a>
        ${chainUrl(base.i) ? `<a href="${chainUrl(base.i)}" target="_blank" rel="noopener">${esc(base.i)}產業鏈說明</a>` : ""}
      </div>
      <h4>營收</h4>
      <p class="note">最新月份 ${rev.ym || "—"}${
        base.i && base.i.includes("金融") ? "。金融保險業的營收認列基礎與一般產業不同，成長率的擺盪幅度天生就大。" : ""
      }</p>
      <div class="kv">
        <div><div class="k">當月營收</div><div class="v">${rev.amt != null ? human(rev.amt * 1000) : "—"}</div></div>
        <div><div class="k">年增率</div><div class="v">${cell(rev.yoy, 1, true)}</div></div>
        <div><div class="k">累計年增率</div><div class="v">${cell(rev.cum_yoy, 1, true)}</div></div>
        <div><div class="k">月增率</div><div class="v">${cell(rev.mom, 1, true)}</div></div>
      </div>
      <h4>獲利</h4>
      <p class="note">${fin.y ? `${fin.y} 年第 ${fin.q} 季累計` : "尚無財報資料"}</p>
      <div class="kv">
        <div><div class="k">EPS</div><div class="v">${fmt(fin.eps) ?? "—"}</div></div>
        <div><div class="k">毛利率%</div><div class="v">${fmt(fin.gpm, 1) ?? "—"}</div></div>
        <div><div class="k">營益率%</div><div class="v">${fmt(fin.opm, 1) ?? "—"}</div></div>
        <div><div class="k">淨利率%</div><div class="v">${fmt(fin.npm, 1) ?? "—"}</div></div>
        <div><div class="k">淨利年增%</div><div class="v">${cell(fin.net_yoy, 1, true)}</div></div>
        <div><div class="k">營益年增%</div><div class="v">${cell(fin.op_yoy, 1, true)}</div></div>
      </div>
      <h4>歷年本益比</h4>
      <div class="card" style="margin-top:12px"><div class="chart-wrap">
        <div class="chart-scroll"><svg class="chart" id="stockChart" role="img" aria-label="${esc(base.n)} 歷年本益比"></svg></div>
        <div class="tooltip" id="stockTip" hidden></div>
      </div></div>
    </div>`;
    document.body.appendChild(ov);
    document.body.style.overflow = "hidden";

    const close = () => {
      ov.remove();
      document.body.style.overflow = "";
      document.removeEventListener("keydown", esc2);
    };
    function esc2(e) { if (e.key === "Escape") close(); }
    ov.querySelector(".close").addEventListener("click", close);
    ov.addEventListener("click", (e) => { if (e.target === ov) close(); });
    document.addEventListener("keydown", esc2);
    ov.querySelector(".close").focus();

    const hist = (d.hist || []).map(([ym, pe]) => [ym, pe]).filter((p) => p[1] != null);
    lineChart(ov.querySelector("#stockChart"), ov.querySelector("#stockTip"),
      hist.length ? [{ key: "pe", name: "本益比", color: SERIES[base.m], points: hist }] : [],
      { unit: "倍", height: MOBILE.matches ? 200 : 240 });
  }

  // ---------------------------------------------------------------- 事件
  /** attr = data-* 屬性名，key = state 上的欄位名 */
  function bindSeg(id, attr, key, after) {
    const seg = $(id);
    const buttons = [...seg.querySelectorAll("button")];
    seg.style.setProperty("--n", buttons.length);
    const paint = () => {
      const i = buttons.findIndex((b) => b.getAttribute("aria-pressed") === "true");
      seg.style.setProperty("--i", Math.max(0, i));
    };
    buttons.forEach((b) =>
      b.addEventListener("click", () => {
        buttons.forEach((x) => x.setAttribute("aria-pressed", "false"));
        b.setAttribute("aria-pressed", "true");
        paint();
        state[key] = b.dataset[attr];
        after();
      })
    );
    paint();
  }

  // ---------------------------------------------------------------- 漲幅排行
  function renderMovers() {
    const mv = state.movers;
    const note = $("moversNote");
    if (!mv || !mv.periods || !Object.keys(mv.periods).length) {
      note.textContent = "漲幅資料尚未產生 —— 到 GitHub 的 Actions 頁執行一次「每日更新」即可。";
      $("groupBars").innerHTML = "";
      $("rankList").innerHTML = "";
      return;
    }
    const keys = Object.keys(mv.periods);
    if (!mv.periods[state.period]) state.period = keys[0];
    const p = mv.periods[state.period];

    note.innerHTML = `以 <strong>${p.from}</strong> 收盤為基準，比到 <strong>${mv.asOf}</strong>，`
      + `共 ${p.days} 個交易日。`
      + (p.counts.esb ? "" : "<strong>興櫃的中長天期漲幅要等資料累積</strong>——官方沒有整批的興櫃歷史每日行情端點，只能從本站開始逐日收集。");

    // ---- 族群長條 ----
    const gs = (p.groups || []).filter((g) => g.med != null).slice(0, 12);
    const maxAbs = Math.max(...gs.map((g) => Math.abs(g.med)), 1);
    $("groupBars").innerHTML = gs.length
      ? gs.map((g) => {
          const w = (Math.abs(g.med) / maxAbs) * 100;
          const cls = g.med >= 0 ? "up" : "down";
          return `<button type="button" class="grow" data-tag="${esc(g.tag)}" data-w="${w.toFixed(1)}">
            <span class="gname">${esc(g.tag)}</span>
            <span class="gbar"><span class="gfill ${cls}"></span></span>
            <span class="gval ${g.med >= 0 ? "pos" : "neg"}">${g.med > 0 ? "+" : ""}${fmt(g.med, 1)}%</span>
            <span class="gn">${g.n} 檔</span>
          </button>`;
        }).join("")
      : '<p class="note">這個期間還沒有足夠的族群資料。</p>';

    // 下一幀才設寬度，讓長條有一次生長動畫
    requestAnimationFrame(() => {
      $("groupBars").querySelectorAll(".grow").forEach((b) => {
        b.querySelector(".gfill").style.width = b.dataset.w + "%";
      });
    });

    $("groupBars").querySelectorAll(".grow").forEach((b) =>
      b.addEventListener("click", () => {
        state.tag = b.dataset.tag; state.industry = ""; $("industry").value = "";
        state.shown = 200; applyFilters();
        document.getElementById("stocks").scrollIntoView({ behavior: "smooth", block: "start" });
      })
    );

    // ---- 個股排行 ----
    const list = (p.markets && p.markets[state.moverMarket]) || [];
    $("rankTitle").textContent = `${LABEL[state.moverMarket]}漲幅排行`;
    $("rankList").innerHTML = list.length
      ? list.slice(0, 25).map((s) => {
          const ts = (s.t && s.t.length ? s.t : (s.i ? [s.i] : []));
          return `<li data-c="${s.c}">
            <div class="rinfo">
              <div class="rhead"><span class="rc">${s.c}</span><span class="rn">${esc(s.n)}</span></div>
              ${ts.length ? `<div class="rt">${ts.map((t) => `<span class="tag static">${esc(t)}</span>`).join("")}</div>` : ""}
            </div>
            <span class="rr ${s.r >= 0 ? "pos" : "neg"}">${s.r > 0 ? "+" : ""}${fmt(s.r, 1)}%</span>
          </li>`;
        }).join("")
      : `<li class="empty">${LABEL[state.moverMarket]}在這個期間還沒有資料。</li>`;
    $("rankList").querySelectorAll("li[data-c]").forEach((li) =>
      li.addEventListener("click", () => openStock(li.dataset.c))
    );
  }

  function draw() { renderTiles(); renderMovers(); }

  // ---------------------------------------------------------------- 啟動
  (async function init() {
    const [meta, market, rows, tags, movers, history, tdcc] = await Promise.all([
      getJSON("data/meta.json", null),
      getJSON("data/market.json", null),
      getJSON("data/latest.json", []),
      getJSON("data/tags.json", {}),
      getJSON("data/movers.json", null),
      getJSON("data/market_history.json", null),
      getJSON("data/tdcc.json", null),
    ]);
    state.meta = meta; state.market = market;
    state.rows = rows || []; state.tags = tags || {}; state.movers = movers;
    state.history = history;
    if (tdcc && tdcc.d) state.tdcc = tdcc;

    // 更新時間在窄螢幕以 CSS 隱藏，只留資料日期，避免頂欄被截斷
    $("asof").innerHTML = meta && meta.asOf
      ? `${meta.asOf}<span class="asof-more">・更新於 ${esc((meta.updatedAt || "").replace("T", " ").slice(0, 16))}</span>`
      : "尚無資料 — 請先在 GitHub Actions 執行一次「每日更新」";

    if (meta) {
      $("coverage").textContent =
        `共 ${meta.total} 檔：有本益比 ${meta.withPE}、有股價營收比 ${meta.withPS}、有月營收 ${meta.withRevenue}、有財報 ${meta.withFinancials}。`;
    }

    const cov = $("tagCoverage");
    if (cov) cov.textContent = String(Object.keys(state.tags).length);

    const tn = $("tdccNote");
    if (tn) {
      tn.textContent = state.tdcc.date
        ? (state.tdcc.base
            ? `目前為 ${state.tdcc.date} 那一週，月增減是與 ${state.tdcc.base} 相比。`
            : `目前為 ${state.tdcc.date} 那一週；月增減要再累積約四週才會有數字。`)
        : "尚未抓取。";
    }

    const inds = [...new Set(state.rows.map((r) => r.i).filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-Hant"));
    $("industry").innerHTML = '<option value="">所有產業</option>' + inds.map((i) => `<option>${esc(i)}</option>`).join("");

    renderHead();
    renderHeroStats();
    draw();
    applyFilters();

    $("q").addEventListener("input", (e) => { state.q = e.target.value; state.shown = 200; applyFilters(); });
    $("industry").addEventListener("change", (e) => {
      state.industry = e.target.value; state.tag = ""; state.shown = 200; applyFilters();
    });
    $("more").addEventListener("click", () => { state.shown += 300; renderBody(); });
    bindSeg("marketSeg", "market", "filterMarket", () => { state.shown = 200; applyFilters(); });
    bindSeg("periodSeg", "period", "period", renderMovers);
    bindSeg("moverMarketSeg", "mm", "moverMarket", renderMovers);

    // 桌機／手機切換時重畫圖表尺寸
    MOBILE.addEventListener("change", () => draw());
  })();
})();
