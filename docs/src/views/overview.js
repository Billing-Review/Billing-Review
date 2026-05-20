import { h, mount, clear } from "../utils/dom.js";
import { loadMatrix, summarizeByFeature } from "../api/applied.js";
import { FEATURES } from "../config.js";
import { toast } from "../utils/toast.js";

export async function renderOverview(root) {
  const grid = h("div", { class: "overview-grid" });
  const refreshBtn = h(
    "button",
    {
      class: "btn btn--small",
      onclick: () => load(true),
    },
    "↻ 새로고침"
  );

  async function load(force = false) {
    clear(grid);
    grid.appendChild(
      h(
        "div",
        { class: "empty" },
        h("span", { class: "spinner" }),
        " 로딩 중..."
      )
    );
    try {
      const rows = await loadMatrix(force);
      const summary = summarizeByFeature(rows);

      clear(grid);

      // 전체 요약 카드
      grid.appendChild(renderTotalsCard(rows));

      // feature별 카드
      for (const feat of FEATURES) {
        grid.appendChild(renderFeatureCard(feat, summary[feat.id]));
      }
    } catch (err) {
      clear(grid);
      grid.appendChild(h("div", { class: "empty" }, `오류: ${err.message}`));
      toast(err.message, "error", 5000);
    }
  }

  function renderTotalsCard(rows) {
    const totalRepos = rows.filter((r) => !r.repo.archived).length;
    const fullyApplied = rows.filter(
      (r) => !r.repo.archived && FEATURES.every((f) => r.status[f.id] === "applied")
    ).length;
    const partial = rows.filter(
      (r) =>
        !r.repo.archived &&
        FEATURES.some((f) => r.status[f.id] === "applied") &&
        FEATURES.some((f) => r.status[f.id] !== "applied")
    ).length;
    const none = rows.filter(
      (r) => !r.repo.archived && FEATURES.every((f) => r.status[f.id] === "missing")
    ).length;
    return h(
      "div",
      { class: "overview-card" },
      h("h3", null, "📊 전체"),
      h(
        "div",
        { class: "stat" },
        h("span", { class: "stat-label" }, "관리 레포"),
        h("span", { class: "stat-value" }, totalRepos)
      ),
      h(
        "div",
        { class: "stat" },
        h("span", { class: "stat-label" }, "✓ 전체 적용"),
        h("span", { class: "stat-value" }, fullyApplied)
      ),
      h(
        "div",
        { class: "stat" },
        h("span", { class: "stat-label" }, "⚠ 부분 적용"),
        h("span", { class: "stat-value" }, partial)
      ),
      h(
        "div",
        { class: "stat" },
        h("span", { class: "stat-label" }, "✗ 미적용"),
        h("span", { class: "stat-value" }, none)
      )
    );
  }

  function renderFeatureCard(feat, summary) {
    const missingRepos = summary.missing.filter((r) => !r.archived);
    const partialRepos = summary.partial.filter((r) => !r.archived);
    return h(
      "div",
      { class: "overview-card" },
      h(
        "h3",
        null,
        feat.label,
        h(
          "a",
          {
            href: `#/deploy/${feat.id}`,
            class: "btn btn--small",
            style: { marginLeft: "auto" },
          },
          "배포 →"
        )
      ),
      h(
        "div",
        { class: "stat" },
        h("span", { class: "stat-label" }, "✓ 적용"),
        h("span", { class: "stat-value", style: { color: "var(--success)" } }, summary.applied.length)
      ),
      h(
        "div",
        { class: "stat" },
        h("span", { class: "stat-label" }, "⚠ 부분"),
        h("span", { class: "stat-value", style: { color: "var(--warning)" } }, summary.partial.length)
      ),
      h(
        "div",
        { class: "stat" },
        h("span", { class: "stat-label" }, "✗ 미적용"),
        h("span", { class: "stat-value", style: { color: "var(--text-muted)" } }, summary.missing.length)
      ),
      missingRepos.length || partialRepos.length
        ? h(
            "div",
            { class: "missing-list" },
            [...partialRepos, ...missingRepos].slice(0, 12).map((r) =>
              h("a", { href: `#/repos/${r.name}` }, r.name)
            ),
            [...partialRepos, ...missingRepos].length > 12
              ? h("span", null, `+${[...partialRepos, ...missingRepos].length - 12}`)
              : null
          )
        : null
    );
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
        h("h2", { class: "card__title", style: { margin: 0 } }, "적용 현황"),
        refreshBtn
      ),
      h(
        "p",
        { class: "card__desc" },
        "조직 전체의 기능 적용 통계입니다. 부분 적용 / 미적용 레포가 표시됩니다."
      ),
      grid
    )
  );

  await load();
}
