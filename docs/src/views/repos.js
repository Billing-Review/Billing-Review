import { h, mount, clear } from "../utils/dom.js";
import { loadMatrix, appliedCount } from "../api/applied.js";
import { FEATURES } from "../config.js";
import { toast } from "../utils/toast.js";
import { openApplyModal } from "./apply-modal.js";

const STORAGE_KEY_FILTER = "ui.repos.filter";

export async function renderRepos(root, repoName /* optional */) {
  const sidebarList = h("div", { class: "sidebar__list" });
  const searchInput = h("input", {
    type: "search",
    placeholder: "레포 검색...",
  });
  const showOnlyMissing = h("input", { type: "checkbox" });
  const showArchived = h("input", { type: "checkbox" });
  const refreshBtn = h(
    "button",
    {
      class: "btn btn--small",
      onclick: () => loadAll(true),
    },
    "↻"
  );

  // 필터 복원
  try {
    const saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY_FILTER) || "{}");
    if (saved.onlyMissing) showOnlyMissing.checked = true;
    if (saved.archived) showArchived.checked = true;
    if (saved.q) searchInput.value = saved.q;
  } catch {}

  const detailEl = h("div", { class: "detail" });

  let allRows = [];
  let selectedRepoName = repoName || null;

  function saveFilters() {
    sessionStorage.setItem(
      STORAGE_KEY_FILTER,
      JSON.stringify({
        q: searchInput.value,
        onlyMissing: showOnlyMissing.checked,
        archived: showArchived.checked,
      })
    );
  }

  function filteredRows() {
    const q = searchInput.value.trim().toLowerCase();
    return allRows.filter((row) => {
      if (!showArchived.checked && row.repo.archived) return false;
      if (q && !row.repo.name.toLowerCase().includes(q)) return false;
      if (showOnlyMissing.checked) {
        const hasMissing = FEATURES.some(
          (f) => row.status[f.id] !== "applied"
        );
        if (!hasMissing) return false;
      }
      return true;
    });
  }

  function renderSidebar() {
    saveFilters();
    clear(sidebarList);
    const rows = filteredRows();
    if (!rows.length) {
      sidebarList.appendChild(h("div", { class: "empty" }, "결과 없음"));
      return;
    }
    for (const row of rows) {
      const { applied, total } = appliedCount(row);
      const cls =
        applied === total ? "full" : applied === 0 ? "empty" : "partial";
      const item = h(
        "a",
        {
          class:
            "sidebar__item" +
            (row.repo.name === selectedRepoName ? " is-active" : ""),
          href: `#/repos/${row.repo.name}`,
        },
        h("span", { class: "name" }, row.repo.name),
        h("span", { class: `badge ${cls}` }, `${applied}/${total}`)
      );
      sidebarList.appendChild(item);
    }
  }

  function renderDetail() {
    clear(detailEl);
    if (!selectedRepoName) {
      detailEl.appendChild(
        h(
          "div",
          { class: "card empty" },
          "← 왼쪽에서 레포를 선택하세요"
        )
      );
      return;
    }
    const row = allRows.find((r) => r.repo.name === selectedRepoName);
    if (!row) {
      detailEl.appendChild(
        h(
          "div",
          { class: "card empty" },
          `'${selectedRepoName}' 을 찾을 수 없습니다`
        )
      );
      return;
    }
    const { repo, status } = row;
    detailEl.appendChild(
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
          h("h2", { class: "card__title", style: { margin: 0 } }, repo.name),
          h(
            "a",
            {
              class: "btn btn--small",
              href: repo.html_url,
              target: "_blank",
              rel: "noopener",
            },
            "GitHub →"
          )
        ),
        h(
          "div",
          { class: "meta" },
          h("span", null, "default: ", h("code", null, repo.default_branch || "-")),
          repo.archived
            ? h("span", { style: { color: "var(--warning)" } }, "[archived]")
            : null,
          repo.fork ? h("span", null, "[fork]") : null,
          h(
            "span",
            null,
            "최근 push: ",
            repo.pushed_at ? new Date(repo.pushed_at).toLocaleDateString("ko-KR") : "-"
          )
        ),
        h("div", { class: "section-title" }, "Features"),
        ...FEATURES.map((feat) => renderFeatureCard(feat, repo, status[feat.id])),
        h(
          "div",
          {
            class: "section-title",
            style: { marginTop: "20px" },
          },
          "바로가기"
        ),
        h(
          "div",
          { style: { display: "flex", gap: "8px" } },
          status["rest-api-docs"] === "applied"
            ? h(
                "a",
                { class: "btn btn--small", href: `#/api-docs/${repo.name}` },
                "API Docs 관리"
              )
            : null,
          h(
            "a",
            { class: "btn btn--small", href: `#/runs/${repo.name}` },
            "실행 현황"
          )
        )
      )
    );
  }

  function renderFeatureCard(feat, repo, st) {
    const stLabel =
      st === "applied"
        ? h("span", { class: "status-applied" }, "✓ 적용됨")
        : st === "partial"
        ? h("span", { class: "status-partial" }, "⚠ 부분 적용")
        : h("span", { class: "status-missing" }, "✗ 미적용");

    const actions = [];
    if (st !== "applied") {
      actions.push(
        h(
          "button",
          {
            class: "btn btn--small",
            onclick: () => openApplyModal(feat, repo, () => loadAll(true)),
          },
          st === "partial" ? "재적용" : "적용"
        )
      );
    } else {
      actions.push(
        h(
          "button",
          {
            class: "btn btn--small btn--ghost",
            style: { color: "var(--text)", border: "1px solid var(--border)" },
            onclick: () => openApplyModal(feat, repo, () => loadAll(true)),
          },
          "재적용"
        )
      );
      if (feat.id === "rest-api-docs") {
        actions.push(
          h(
            "a",
            { class: "btn btn--small", href: `#/api-docs/${repo.name}` },
            "관리"
          )
        );
      }
    }

    return h(
      "div",
      { class: "feature-card" },
      h(
        "div",
        { class: "feature-card__main" },
        h("span", { class: "feature-card__name" }, feat.label),
        h("span", { class: "feature-card__desc" }, stLabel)
      ),
      h("div", { class: "feature-card__actions" }, ...actions)
    );
  }

  async function loadAll(force = false) {
    sidebarList.innerHTML = "";
    sidebarList.appendChild(
      h(
        "div",
        { class: "empty", style: { padding: "16px" } },
        h("span", { class: "spinner" }),
        " 로딩 중..."
      )
    );
    try {
      allRows = await loadMatrix(force);
      renderSidebar();
      renderDetail();
    } catch (err) {
      clear(sidebarList);
      sidebarList.appendChild(
        h("div", { class: "empty" }, `오류: ${err.message}`)
      );
      toast(`레포 목록 조회 실패: ${err.message}`, "error", 5000);
    }
  }

  searchInput.addEventListener("input", renderSidebar);
  showOnlyMissing.addEventListener("change", renderSidebar);
  showArchived.addEventListener("change", renderSidebar);

  mount(
    root,
    h(
      "div",
      { class: "split" },
      h(
        "aside",
        { class: "sidebar" },
        h(
          "div",
          { class: "sidebar__head" },
          h(
            "div",
            { style: { display: "flex", gap: "6px" } },
            searchInput,
            refreshBtn
          )
        ),
        h(
          "div",
          { class: "sidebar__filters" },
          h("label", null, showOnlyMissing, " 미적용만"),
          h("label", null, showArchived, " archived")
        ),
        sidebarList
      ),
      detailEl
    )
  );

  await loadAll();
}
