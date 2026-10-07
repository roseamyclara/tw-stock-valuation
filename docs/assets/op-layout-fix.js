/* 營運先行指標版面修正：來源附註固定放在「指標」上方 */
(() => {
  "use strict";

  function injectStyle() {
    if (document.getElementById("op-layout-fix-style")) return;
    const style = document.createElement("style");
    style.id = "op-layout-fix-style";
    style.textContent = `
      #opSourceNote.op-source-above-metric {
        display: block;
        margin: 12px 0 8px;
      }
    `;
    document.head.appendChild(style);
  }

  function moveSourceNote(panel) {
    const sourceNote = panel.querySelector("#opSourceNote");
    const metricControls = [...panel.querySelectorAll(".op-controls")]
      .find((el) => el.querySelector("#opMetric"));
    if (!sourceNote || !metricControls) return;
    if (sourceNote.nextElementSibling === metricControls) return;
    sourceNote.classList.add("op-source-above-metric");
    metricControls.before(sourceNote);
  }

  function run() {
    injectStyle();
    document.querySelectorAll(".overlay .panel").forEach(moveSourceNote);
  }

  new MutationObserver(run).observe(document.body, { childList: true, subtree: true });
  run();
})();
