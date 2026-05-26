import { h } from "./dom.js";

// 동적 환경별 URL 입력 폼.
//   initialEnvs : { Alpha: "https://...", Real: "..." }
//   options.defaults : 초기값 없을 때 노출할 기본 키 (기본 ["Alpha","Real"])
//   options.serviceName : URL placeholder 치환용 ("{service}")
//
// 반환: { container, addBtn, getValues(), reset(envs) }
export function buildEnvForm(initialEnvs, options = {}) {
  const defaults = options.defaults || ["Alpha", "Real"];
  const serviceName = options.serviceName || "service";

  const container = h("div", { class: "env-form__rows" });
  const rows = [];

  function buildPlaceholder(key) {
    const k = (key || "env").toLowerCase();
    return `https://${k === "real" ? "" : k + "-"}${serviceName}.example.com`;
  }

  function addRow(key = "", url = "") {
    const keyIn = h("input", {
      type: "text",
      placeholder: "환경명 (예: Alpha)",
      value: key,
      class: "env-row__key",
    });
    const urlIn = h("input", {
      type: "text",
      placeholder: buildPlaceholder(key),
      value: url,
      class: "env-row__url",
    });
    keyIn.addEventListener("input", () => {
      urlIn.placeholder = buildPlaceholder(keyIn.value);
    });
    const removeBtn = h(
      "button",
      {
        type: "button",
        class: "btn--remove",
        title: "삭제",
      },
      "×"
    );
    const row = h("div", { class: "env-row env-row--editable" }, keyIn, urlIn, removeBtn);
    const entry = { keyIn, urlIn, row };
    removeBtn.addEventListener("click", () => {
      row.remove();
      const i = rows.indexOf(entry);
      if (i >= 0) rows.splice(i, 1);
    });
    rows.push(entry);
    container.appendChild(row);
  }

  function getValues() {
    const out = {};
    for (const { keyIn, urlIn } of rows) {
      const k = keyIn.value.trim();
      const v = urlIn.value.trim();
      if (k && v) out[k] = v;
    }
    return out;
  }

  function reset(envs) {
    while (container.firstChild) container.removeChild(container.firstChild);
    rows.length = 0;
    const entries = Object.entries(envs || {});
    if (entries.length) {
      for (const [k, v] of entries) addRow(k, v);
    } else {
      for (const k of defaults) addRow(k, "");
    }
  }

  const addBtn = h(
    "button",
    { type: "button", class: "btn btn--small", onclick: () => addRow() },
    "+ 환경 추가"
  );

  reset(initialEnvs);

  return { container, addBtn, getValues, reset };
}
