import { h, mount, clear } from "../utils/dom.js";
import { listWorkflowRuns } from "../api/workflows.js";
import { toast } from "../utils/toast.js";

const PER_PAGE = 10;

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
  let page = 1;
  let hasNext = false;

  const prevBtn = h(
    "button",
    { class: "btn btn--small", title: "이전 페이지" },
    "<"
  );
  const nextBtn = h(
    "button",
    { class: "btn btn--small", title: "다음 페이지" },
    ">"
  );
  const pageLabel = h(
    "span",
    { style: { fontSize: "12px", color: "var(--text-muted)", margin: "0 8px" } },
    "1"
  );
  const refreshBtn = h(
    "button",
    {
      class: "btn btn--small",
      onclick: () => { page = 1; load(); },
    },
    "↻ 새로고침"
  );

  prevBtn.addEventListener("click", () => {
    if (page <= 1) return;
    page -= 1;
    load();
  });
  nextBtn.addEventListener("click", () => {
    if (!hasNext) return;
    page += 1;
    load();
  });

  function updatePagerState(loading) {
    pageLabel.textContent = String(page);
    prevBtn.disabled = loading || page <= 1;
    nextBtn.disabled = loading || !hasNext;
  }

  async function load() {
    updatePagerState(true);
    clear(listEl);
    listEl.appendChild(
      h("li", null, h("span", { class: "spinner" }), " 로딩 중...")
    );
    try {
      // 다음 페이지 유무 확인을 위해 PER_PAGE + 1 만큼 받는다.
      // 응답 길이가 PER_PAGE 초과면 다음 페이지 있음.
      const fetched = await listWorkflowRuns(repoName, null, PER_PAGE + 1, page);
      const runs = fetched.slice(0, PER_PAGE);
      hasNext = fetched.length > PER_PAGE;

      clear(listEl);
      if (!runs.length) {
        listEl.appendChild(
          h(
            "li",
            { class: "empty" },
            page === 1 ? "실행 기록 없음" : "더 이상 표시할 항목이 없습니다."
          )
        );
        updatePagerState(false);
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
      hasNext = false;
    } finally {
      updatePagerState(false);
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
        h(
          "div",
          { style: { display: "flex", alignItems: "center", gap: "4px" } },
          prevBtn,
          pageLabel,
          nextBtn,
          h("span", { style: { width: "12px" } }),
          refreshBtn
        )
      ),
      h("p", { class: "card__desc" }, `한 페이지 ${PER_PAGE}건씩 표시합니다.`),
      listEl
    )
  );

  await load();
}
