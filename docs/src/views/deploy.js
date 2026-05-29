import { h, mount, clear } from "../utils/dom.js";
import { loadMatrix } from "../api/applied.js";
import { FEATURES } from "../config.js";
import { toast } from "../utils/toast.js";
import { applyFeatureToRepo } from "./apply-modal.js";

export async function renderDeploy(root, featureId /* optional */) {
  // featureId 미지정이면 첫 번째 feature로 폴백
  const feature = FEATURES.find((f) => f.id === featureId) || FEATURES[0];

  const featurePicker = h(
    "div",
    { class: "feature-picker" },
    h("span", { class: "feature-picker__label" }, "기능"),
    h(
      "select",
      {
        class: "feature-picker__select",
        onchange: (e) => {
          location.hash = `#/deploy/${e.target.value}`;
        },
      },
      ...FEATURES.map((f) =>
        h(
          "option",
          { value: f.id, selected: f.id === feature.id ? true : null },
          f.label
        )
      )
    )
  );

  const listEl = h("div", { class: "deploy-list" });
  const searchInput = h("input", {
    type: "search",
    placeholder: "레포 검색...",
    style: { width: "260px" },
  });
  const selectAllCheck = h("input", { type: "checkbox" });
  const selectedCountEl = h("span", { style: { color: "var(--text-muted)" } });
  const applyBtn = h("button", { class: "btn", disabled: true }, "선택 항목 일괄 적용 (0)");
  const refreshBtn = h(
    "button",
    { class: "btn btn--small", onclick: () => load(true) },
    "↻"
  );

  let allRows = [];
  let selectedRepos = new Set();
  let running = false;

  function statusFor(row) {
    return row.status[feature.id];
  }

  function filteredRows() {
    const q = searchInput.value.trim().toLowerCase();
    return allRows.filter((row) => {
      if (row.repo.archived) return false;
      if (q && !row.repo.name.toLowerCase().includes(q)) return false;
      return true;
    });
  }

  function updateApplyBtn() {
    const n = selectedRepos.size;
    applyBtn.textContent = `선택 항목 일괄 적용 (${n})`;
    applyBtn.disabled = n === 0 || running;
    selectedCountEl.textContent = n > 0 ? `${n}개 선택됨` : "";
  }

  function renderList() {
    clear(listEl);
    const rows = filteredRows();
    if (!rows.length) {
      listEl.appendChild(h("div", { class: "empty" }, "결과 없음"));
      return;
    }
    // toolbar
    listEl.appendChild(
      h(
        "div",
        { class: "deploy-toolbar" },
        h(
          "label",
          { style: { display: "flex", alignItems: "center", gap: "6px" } },
          selectAllCheck,
          " 미적용 전체 선택"
        ),
        selectedCountEl
      )
    );

    for (const row of rows) {
      const st = statusFor(row);
      const isApplied = st === "applied";
      const cb = h("input", {
        type: "checkbox",
        disabled: isApplied,
        checked: selectedRepos.has(row.repo.name),
      });
      cb.addEventListener("change", () => {
        if (cb.checked) selectedRepos.add(row.repo.name);
        else selectedRepos.delete(row.repo.name);
        updateApplyBtn();
      });
      listEl.appendChild(
        h(
          "div",
          { class: "deploy-row" + (isApplied ? " is-applied" : "") },
          cb,
          h(
            "div",
            null,
            h(
              "a",
              { href: `#/repos/${row.repo.name}`, class: "repo-link" },
              row.repo.name
            )
          ),
          h(
            "div",
            null,
            isApplied
              ? h("span", { class: "status-applied" }, "✓ 적용됨")
              : st === "partial"
              ? h("span", { class: "status-partial" }, "⚠ 부분")
              : h("span", { class: "status-missing" }, "✗ 미적용")
          ),
          h(
            "div",
            null,
            h(
              "a",
              {
                class: "btn btn--small",
                href: row.repo.html_url,
                target: "_blank",
                rel: "noopener",
              },
              "GitHub"
            )
          )
        )
      );
    }
    updateApplyBtn();
  }

  selectAllCheck.addEventListener("change", () => {
    selectedRepos.clear();
    if (selectAllCheck.checked) {
      for (const row of filteredRows()) {
        if (statusFor(row) !== "applied") selectedRepos.add(row.repo.name);
      }
    }
    renderList();
  });

  searchInput.addEventListener("input", renderList);

  applyBtn.addEventListener("click", async () => {
    if (selectedRepos.size === 0 || running) return;
    if (feature.extraSetup) {
      alert(
        `"${feature.label}" 은(는) 추가 설정(도메인 등)이 필요해 일괄 적용으로 처리할 수 없습니다.\n\n` +
        `[레포 관리] 에서 각 레포의 [적용] 또는 [재적용] 버튼을 사용하세요.`
      );
      return;
    }
    if (
      !confirm(
        `${selectedRepos.size}개 레포에 "${feature.label}"을(를) 적용합니다.\n\n계속하시겠습니까?`
      )
    )
      return;
    running = true;
    updateApplyBtn();
    const targets = allRows.filter((r) => selectedRepos.has(r.repo.name));
    let ok = 0,
      fail = 0;
    for (const row of targets) {
      try {
        await applyFeatureToRepo(feature, row.repo);
        ok++;
        toast(`✓ ${row.repo.name}`, "success", 1500);
      } catch (err) {
        fail++;
        toast(`✗ ${row.repo.name}: ${err.message}`, "error", 4000);
      }
    }
    running = false;
    selectedRepos.clear();
    selectAllCheck.checked = false;
    toast(`완료: ${ok} 성공 / ${fail} 실패`, fail ? "error" : "success", 5000);
    await load(true);
  });

  async function load(force = false) {
    clear(listEl);
    listEl.appendChild(
      h(
        "div",
        { class: "empty" },
        h("span", { class: "spinner" }),
        " 로딩 중..."
      )
    );
    try {
      allRows = await loadMatrix(force);
      renderList();
    } catch (err) {
      clear(listEl);
      listEl.appendChild(h("div", { class: "empty" }, `오류: ${err.message}`));
    }
  }

  mount(
    root,
    h(
      "div",
      { class: "card" },
      h(
        "div",
        {
          style: {
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          },
        },
        h("h2", { class: "card__title", style: { margin: 0 } }, "기능 배포"),
        refreshBtn
      ),
      featurePicker,
      h(
        "p",
        { class: "card__desc" },
        h("strong", null, feature.label),
        " 을(를) 여러 레포에 한 번에 적용합니다. 이미 적용된 레포는 비활성화됩니다."
      ),
      feature.extraSetup
        ? h(
            "div",
            { class: "callout callout--warning" },
            "⚠ 이 기능은 추가 설정(도메인 등)이 필요해 ",
            h("strong", null, "일괄 적용 불가"),
            "합니다. ",
            h("a", { href: "#/repos" }, "[레포 관리]"),
            " 에서 각 레포에 개별 적용하세요."
          )
        : null,
      h(
        "div",
        { style: { display: "flex", gap: "8px", marginBottom: "12px" } },
        searchInput,
        h("div", { style: { flex: 1 } }),
        applyBtn
      ),
      listEl
    )
  );

  await load();
}
