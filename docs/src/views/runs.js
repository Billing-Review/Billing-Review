import { h, mount, clear } from "../utils/dom.js";
import { listWorkflowRuns } from "../api/workflows.js";
import { toast } from "../utils/toast.js";

const STATUS_ICON = {
  completed: { success: "✓", failure: "✗", cancelled: "⊘", skipped: "↪" },
  in_progress: "●",
  queued: "○",
  waiting: "⋯",
};

function iconFor(run) {
  if (run.status === "completed") {
    const ic = STATUS_ICON.completed[run.conclusion] || "?";
    return ic;
  }
  return STATUS_ICON[run.status] || "?";
}

function colorFor(run) {
  if (run.status === "completed") {
    if (run.conclusion === "success") return "var(--success)";
    if (run.conclusion === "failure") return "var(--danger)";
    if (run.conclusion === "cancelled") return "var(--text-muted)";
  }
  if (run.status === "in_progress") return "var(--warning)";
  return "var(--text-muted)";
}

function relativeTime(iso) {
  const diff = Date.now() - new Date(iso).getTime();
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return `${sec}초 전`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}분 전`;
  const hour = Math.floor(min / 60);
  if (hour < 24) return `${hour}시간 전`;
  const day = Math.floor(hour / 24);
  return `${day}일 전`;
}

export async function renderRuns(root, repoName) {
  const listEl = h("ul", { class: "api-list" });
  const refreshBtn = h(
    "button",
    { class: "btn btn--small", onclick: () => load() },
    "↻ 새로고침"
  );

  async function load() {
    clear(listEl);
    listEl.appendChild(
      h("li", null, h("span", { class: "spinner" }), " 로딩 중...")
    );
    try {
      const runs = await listWorkflowRuns(repoName, null, 20);
      clear(listEl);
      if (!runs.length) {
        listEl.appendChild(h("li", { class: "empty" }, "실행 기록 없음"));
        return;
      }
      for (const run of runs) {
        listEl.appendChild(
          h(
            "li",
            null,
            h(
              "div",
              null,
              h(
                "span",
                { style: { color: colorFor(run), fontWeight: "600", marginRight: "8px" } },
                iconFor(run)
              ),
              h("span", { style: { fontWeight: 500 } }, run.name || run.display_title || "(no name)"),
              h(
                "span",
                { class: "api-title" },
                ` · ${run.event} · ${relativeTime(run.created_at)}`
              )
            ),
            h(
              "a",
              {
                href: run.html_url,
                target: "_blank",
                rel: "noopener",
                class: "btn btn--small",
              },
              "보기"
            )
          )
        );
      }
    } catch (err) {
      clear(listEl);
      listEl.appendChild(h("li", { class: "empty" }, `오류: ${err.message}`));
      toast(`실행 목록 조회 실패: ${err.message}`, "error", 5000);
    }
  }

  mount(
    root,
    h(
      "div",
      { class: "card" },
      h("a", { class: "back-link", href: `#/api-docs/${repoName}` }, "← API Docs로"),
      h(
        "div",
        { style: { display: "flex", justifyContent: "space-between", alignItems: "center" } },
        h("h2", { class: "card__title", style: { margin: 0 } }, `${repoName} — 워크플로우 실행 현황`),
        refreshBtn
      ),
      h("p", { class: "card__desc" }, "최근 20건의 워크플로우 실행 결과입니다."),
      listEl
    )
  );

  await load();
}
