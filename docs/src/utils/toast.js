import { h } from "./dom.js";

export function toast(message, type = "info", durationMs = 3000) {
  const root = document.getElementById("toast-root");
  if (!root) return;
  const el = h("div", { class: `toast toast--${type}` }, message);
  root.appendChild(el);
  setTimeout(() => {
    el.style.opacity = "0";
    el.style.transition = "opacity 0.2s";
    setTimeout(() => el.remove(), 220);
  }, durationMs);
}
