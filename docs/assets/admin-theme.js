/* 後台的深淺色切換：與 app.js／screener.js 相同的 localStorage 鍵與 theme-color 色值。
 * 只處理外觀；登入、權限與資料載入都在 auth.js／admin.js，這裡不碰。 */
(function () {
  const btn = document.getElementById("themeToggle");
  if (!btn) return;
  const SUN = '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><circle cx="10" cy="10" r="3.6" stroke="currentColor" stroke-width="1.7"/><path d="M10 1.6v2M10 16.4v2M18.4 10h-2M3.6 10h-2M15.9 4.1l-1.4 1.4M5.5 14.5l-1.4 1.4M15.9 15.9l-1.4-1.4M5.5 5.5 4.1 4.1" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>';
  const MOON = '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M17 12.2A7.4 7.4 0 0 1 7.8 3a7.4 7.4 0 1 0 9.2 9.2Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>';
  const root = document.documentElement;
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  const isDark = () => { const t = root.getAttribute("data-theme"); return t === "dark" || (!t && mq.matches); };
  const paint = () => {
    const dark = isDark();
    btn.innerHTML = dark ? SUN : MOON;
    btn.setAttribute("aria-label", dark ? "切換為淺色" : "切換為深色");
  };
  const THEME_COLOR = { light: "#f6f7f9", dark: "#0c0e12" };
  const apply = (t) => {
    if (t !== "light" && t !== "dark") t = null;
    if (t) root.setAttribute("data-theme", t); else root.removeAttribute("data-theme");
    document.querySelector('meta[name="color-scheme"]')?.setAttribute("content", t || "light dark");
    document.querySelectorAll('meta[name="theme-color"]').forEach((m) => {
      const own = (m.getAttribute("media") || "").includes("dark") ? THEME_COLOR.dark : THEME_COLOR.light;
      m.setAttribute("content", t ? THEME_COLOR[t] : own);
    });
    paint();
  };
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  const withTransition = (fn) => {
    if (!document.startViewTransition || reduced.matches || document.hidden) { fn(); return; }
    document.startViewTransition(fn);
  };
  try { const saved = localStorage.getItem("theme"); if (saved) apply(saved); } catch (_) {}
  paint();
  mq.addEventListener?.("change", () => { if (!root.hasAttribute("data-theme")) paint(); });
  btn.addEventListener("click", () => {
    const next = isDark() ? "light" : "dark";
    try { localStorage.setItem("theme", next); } catch (_) {}
    withTransition(() => apply(next));
  });
})();
