/* 台股估值追蹤 — 前端 */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const MARKETS = ["listed", "otc", "esb"];
  const LABEL = { listed: "上市", otc: "上櫃", esb: "興櫃" };
  const SERIES = { listed: "var(--series-1)", otc: "var(--series-2)", esb: "var(--series-3)" };

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
    rows: [], view: [], meta: null, market: null, tags: {}, movers: null,
    sortKey: "cap", sortDir: -1, filterMarket: "", industry: "", tag: "", q: "",
    shown: 200, period: "d1", moverMarket: "listed",
  };

  const tagsOf = (code) => state.tags[code] || [];

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
      const weighted = [
        d.peWeighted ? `本益比 ${fmt(d.peWeighted)}` : null,
        d.psWeighted ? `股價營收比 ${fmt(d.psWeighted)}` : null,
      ].filter(Boolean).join("、");
      return `<div class="tile">
        <div class="name"><span class="swatch" style="background:${SERIES[k]}"></span>${LABEL[k]}</div>
        <div class="figs">
          <div class="fig"><div class="v">${fmt(d.pe) ?? "—"}</div><div class="k">本益比中位數</div></div>
          <div class="fig"><div class="v">${fmt(d.ps) ?? "—"}</div><div class="k">股價營收比中位數</div></div>
        </div>
        <div class="cnt">${n} 檔${d.cap ? "・總市值 " + human(d.cap) : ""}</div>
        ${weighted ? `<div class="cnt">市值加權：${weighted}</div>` : ""}
      </div>`;
    }).join("");
  }

  // ---------------------------------------------------------------- 表格
  const COLS = [
    { k: "c", t: "代號", cls: "code", get: (r) => r.c },
    { k: "n", t: "名稱", get: (r) => `${r.n} <span class="mkt">${LABEL[r.m]}</span>` },
    {
      k: "i", t: "業務標籤", cls: "ind",
      // 有業務標籤就顯示業務標籤；沒有的話退回官方產業別（樣式做區隔，一眼看得出來源不同）
      get: (r) => {
        const ts = tagsOf(r.c);
        if (ts.length) {
          return ts.map((t) => `<button type="button" class="tag" data-tag="${t}">${t}</button>`).join(" ");
        }
        return r.i ? `<button type="button" class="tag ind-tag" data-ind="${r.i}">${r.i}</button>` : '<span class="na">—</span>';
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
      if (state.tag && !tagsOf(r.c).includes(state.tag)) return false;
      // 搜尋同時比對代號、名稱與業務標籤，所以打「外籍移工」找得到統振
      if (q && !(r.c.includes(q) || (r.n || "").toLowerCase().includes(q)
                 || tagsOf(r.c).some((t) => t.toLowerCase().includes(q)))) return false;
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
    const active = state.tag || state.industry;
    $("count").innerHTML = active
      ? `<button type="button" class="clear-filter" id="clearFilter">${active} ✕</button> ${state.view.length} 檔`
      : `${state.view.length} 檔`;
    const cf = $("clearFilter");
    if (cf) cf.addEventListener("click", () => {
      state.tag = ""; state.industry = ""; $("industry").value = "";
      state.shown = 200; applyFilters();
    });
    $("more").hidden = state.view.length <= state.shown;
    $("tbody").querySelectorAll("tr").forEach((tr) =>
      tr.addEventListener("click", (e) => {
        // 點標籤是篩選，不是打開個股。再點一次同一個就取消。
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
        openStock(tr.dataset.c);
      })
    );
  }

  // ---------------------------------------------------------------- 個股面板
  async function openStock(code) {
    const base = state.rows.find((r) => r.c === code);
    if (!base) return;
    // 個股檔只存歷史；當前股價與估值直接用已載入的 latest.json
    const d = (await getJSON(`data/stock/${code}.json`, null)) || {};
    const rev = base.rev || {}, fin = base.fin || {};

    const ov = document.createElement("div");
    ov.className = "overlay";
    ov.innerHTML = `<div class="panel" role="dialog" aria-label="${base.n} 詳細">
      <div class="panel-head">
        <h3>${base.c} ${base.n}</h3>
        <span class="mkt">${LABEL[base.m]}</span>
        <span class="asof">${base.i || ""}</span>
        <button class="close" type="button">關閉</button>
      </div>
      ${tagsOf(base.c).length
        ? `<div class="panel-tags">${tagsOf(base.c).map((t) => `<span class="tag static">${t}</span>`).join(" ")}</div>`
        : ""}
      <div class="kv">
        <div><div class="k">股價</div><div class="v">${fmt(base.p) ?? "—"}</div></div>
        <div><div class="k">本益比</div><div class="v">${fmt(base.pe) ?? "—"}</div></div>
        <div><div class="k">股價營收比</div><div class="v">${fmt(base.ps) ?? "—"}</div></div>
        <div><div class="k">淨值比</div><div class="v">${fmt(base.pb) ?? "—"}</div></div>
        <div><div class="k">市值</div><div class="v">${human(base.cap) ?? "—"}</div></div>
      </div>
      ${chainUrl(base.i) ? `<div class="links">
        <a href="${chainUrl(base.i)}" target="_blank" rel="noopener">${base.i}產業鏈說明</a>
      </div>` : ""}
      <h2>營收</h2>
      <p class="note">最新月份 ${rev.ym || "—"}${
        base.i && base.i.includes("金融") ? "。金融保險業的營收認列基礎與一般產業不同，成長率的擺盪幅度天生就大。" : ""
      }</p>
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
          return `<button type="button" class="grow" data-tag="${g.tag}">
            <span class="gname">${g.tag}</span>
            <span class="gbar"><span class="gfill ${cls}" style="width:${w.toFixed(1)}%"></span></span>
            <span class="gval ${g.med >= 0 ? "pos" : "neg"}">${g.med > 0 ? "+" : ""}${fmt(g.med, 1)}%</span>
            <span class="gn">${g.n} 檔</span>
          </button>`;
        }).join("")
      : '<p class="note">這個期間還沒有足夠的族群資料。</p>';
    $("groupBars").querySelectorAll(".grow").forEach((b) =>
      b.addEventListener("click", () => {
        state.tag = b.dataset.tag; state.industry = ""; $("industry").value = "";
        state.shown = 200; applyFilters();
        document.getElementById("tbl").scrollIntoView({ behavior: "smooth", block: "start" });
      })
    );

    // ---- 個股排行 ----
    const list = (p.markets && p.markets[state.moverMarket]) || [];
    $("rankTitle").textContent = `${LABEL[state.moverMarket]}漲幅排行`;
    $("rankList").innerHTML = list.length
      ? list.slice(0, 25).map((s) => `<li data-c="${s.c}">
          <span class="rc">${s.c}</span>
          <span class="rn">${s.n}</span>
          <span class="rt">${(s.t && s.t.length ? s.t : (s.i ? [s.i] : [])).map((t) => `<span class="tag static">${t}</span>`).join(" ")}</span>
          <span class="rr ${s.r >= 0 ? "pos" : "neg"}">${s.r > 0 ? "+" : ""}${fmt(s.r, 1)}%</span>
        </li>`).join("")
      : `<li class="empty">${LABEL[state.moverMarket]}在這個期間還沒有資料。</li>`;
    $("rankList").querySelectorAll("li[data-c]").forEach((li) =>
      li.addEventListener("click", () => openStock(li.dataset.c))
    );
  }

  function draw() { renderTiles(); renderMovers(); }

  // ---------------------------------------------------------------- 啟動
  (async function init() {
    const [meta, market, rows, tags, movers] = await Promise.all([
      getJSON("data/meta.json", null),
      getJSON("data/market.json", null),
      getJSON("data/latest.json", []),
      getJSON("data/tags.json", {}),
      getJSON("data/movers.json", null),
    ]);
    state.meta = meta; state.market = market;
    state.rows = rows || []; state.tags = tags || {}; state.movers = movers;

    $("asof").textContent = meta && meta.asOf
      ? `資料日期 ${meta.asOf}・更新於 ${(meta.updatedAt || "").replace("T", " ").slice(0, 16)}`
      : "尚無資料 — 請先在 GitHub Actions 執行一次「每日更新」";

    if (meta) {
      $("coverage").textContent =
        `共 ${meta.total} 檔：有本益比 ${meta.withPE}、有股價營收比 ${meta.withPS}、有月營收 ${meta.withRevenue}、有財報 ${meta.withFinancials}。`;
    }

    const cov = $("tagCoverage");
    if (cov) cov.textContent = String(Object.keys(state.tags).length);

    const inds = [...new Set(state.rows.map((r) => r.i).filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-Hant"));
    $("industry").innerHTML = '<option value="">所有產業</option>' + inds.map((i) => `<option>${i}</option>`).join("");

    renderHead();
    draw();
    applyFilters();

    $("q").addEventListener("input", (e) => { state.q = e.target.value; state.shown = 200; applyFilters(); });
    $("industry").addEventListener("change", (e) => { state.industry = e.target.value; state.shown = 200; applyFilters(); });
    $("more").addEventListener("click", () => { state.shown += 300; renderBody(); });
    bindSeg("marketSeg", "market", "filterMarket", () => { state.shown = 200; applyFilters(); });
    bindSeg("periodSeg", "period", "period", renderMovers);
    bindSeg("moverMarketSeg", "mm", "moverMarket", renderMovers);
  })();
})();
