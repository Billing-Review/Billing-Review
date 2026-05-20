import { h, mount, clear } from "../utils/dom.js";
import { readRegistry, entriesOf, parseApiKey } from "../api/registry.js";
import { dispatchWorkflow } from "../api/workflows.js";
import {
  ORG,
  API_DOCS_WORKFLOW_REF,
  API_DOCS_CODE_BRANCH_DEFAULT,
} from "../config.js";
import { toast } from "../utils/toast.js";

const HTTP_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"];

export async function renderApiDocs(root, repoName) {
  // 로딩 placeholder
  mount(
    root,
    h(
      "div",
      { class: "card" },
      h("a", { class: "back-link", href: "#/matrix" }, "← 매트릭스로"),
      h("h2", { class: "card__title" }, `${repoName} — API Docs`),
      h("p", { class: "card__desc" }, h("span", { class: "spinner" }), " 데이터 로딩 중...")
    )
  );

  let registry = {};
  try {
    registry = await readRegistry(repoName);
  } catch (err) {
    toast(`로드 실패: ${err.message}`, "error", 5000);
  }

  const drafts = entriesOf(registry).filter(([, v]) => v && v.status === "draft");
  const published = entriesOf(registry).filter(([, v]) => v && v.status === "published");

  // ── Draft 목록 ──
  const draftListEl = drafts.length
    ? h(
        "ul",
        { class: "api-list" },
        ...drafts.map(([apiKey, meta]) => renderDraftRow(apiKey, meta, repoName))
      )
    : h("div", { class: "empty" }, "Draft 없음");

  // ── Published 목록 ──
  const publishedListEl = published.length
    ? h(
        "ul",
        { class: "api-list" },
        ...published.map(([apiKey, meta]) => renderPublishedRow(apiKey, meta))
      )
    : h("div", { class: "empty" }, "Published 없음");

  // ── Draft 생성 폼 ──
  const methodSel = h(
    "select",
    null,
    ...HTTP_METHODS.map((m) => h("option", { value: m }, m))
  );
  const pathInput = h("input", {
    type: "text",
    placeholder: "/api/v1/...",
  });
  const codeBranchInput = h("input", {
    type: "text",
    value: API_DOCS_CODE_BRANCH_DEFAULT,
    placeholder: API_DOCS_CODE_BRANCH_DEFAULT,
  });
  const createBtn = h(
    "button",
    {
      class: "btn",
      onclick: async () => {
        const path = pathInput.value.trim();
        if (!path) {
          toast("Path를 입력하세요", "error");
          return;
        }
        const apiKey = `${methodSel.value} ${path}`;
        const codeBranch = codeBranchInput.value.trim() || API_DOCS_CODE_BRANCH_DEFAULT;
        createBtn.disabled = true;
        createBtn.textContent = "트리거 중...";
        try {
          await dispatchWorkflow(
            repoName,
            "api-doc-create-draft.yml",
            API_DOCS_WORKFLOW_REF,           // 워크플로우 YAML 기준 (고정)
            {
              api_key: apiKey,
              branch: codeBranch,            // 코드를 읽을 브랜치
            }
          );
          toast(
            `Draft 생성 트리거됨: ${apiKey} (코드: ${codeBranch})`,
            "success"
          );
        } catch (err) {
          toast(`실패: ${err.message}`, "error", 5000);
        } finally {
          createBtn.disabled = false;
          createBtn.textContent = "Draft 생성";
        }
      },
    },
    "Draft 생성"
  );

  mount(
    root,
    h(
      "div",
      { class: "card" },
      h("a", { class: "back-link", href: "#/matrix" }, "← 매트릭스로"),
      h(
        "div",
        { style: { display: "flex", justifyContent: "space-between", alignItems: "center" } },
        h("h2", { class: "card__title", style: { margin: 0 } }, `${repoName} — API Docs`),
        h(
          "a",
          { class: "btn btn--small", href: `#/runs/${repoName}` },
          "실행 현황"
        )
      ),

      h(
        "div",
        { class: "section-title" },
        "Draft 생성",
        h(
          "span",
          {
            style: {
              marginLeft: "10px",
              fontSize: "11px",
              fontWeight: "normal",
              color: "var(--text-muted)",
              fontFamily: "monospace",
            },
          },
          `workflow: ${API_DOCS_WORKFLOW_REF} (고정)`
        )
      ),
      h(
        "div",
        { class: "form-row form-row--api-draft" },
        h("label", { class: "form-row__label" }, "Method"),
        methodSel,
        h("label", { class: "form-row__label" }, "Path"),
        pathInput,
        h("label", { class: "form-row__label" }, "코드 브랜치"),
        codeBranchInput,
        createBtn
      ),

      h(
        "div",
        { class: "section-title" },
        `Draft 목록 (${drafts.length})`
      ),
      draftListEl,

      h(
        "div",
        { class: "section-title" },
        `Published (${published.length})`
      ),
      publishedListEl
    )
  );
}

function renderDraftRow(apiKey, meta, repoName) {
  const { method, path } = parseApiKey(apiKey);
  const publishBtn = h(
    "button",
    {
      class: "btn btn--small",
      onclick: async () => {
        publishBtn.disabled = true;
        publishBtn.textContent = "트리거 중...";
        try {
          await dispatchWorkflow(repoName, "api-doc-publish.yml", API_DOCS_WORKFLOW_REF, {
            api_key: apiKey,
          });
          toast(`Publish 트리거됨: ${apiKey}`, "success");
        } catch (err) {
          toast(`실패: ${err.message}`, "error", 5000);
        } finally {
          publishBtn.disabled = false;
          publishBtn.textContent = "Publish";
        }
      },
    },
    "Publish"
  );
  return h(
    "li",
    null,
    h(
      "div",
      null,
      h("span", { class: `api-method method-${method}` }, method),
      h("span", { class: "api-path" }, path),
      meta.title ? h("span", { class: "api-title" }, `— ${meta.title}`) : null
    ),
    publishBtn
  );
}

function renderPublishedRow(apiKey, meta) {
  const { method, path } = parseApiKey(apiKey);
  return h(
    "li",
    null,
    h(
      "div",
      null,
      h("span", { class: `api-method method-${method}` }, method),
      h("span", { class: "api-path" }, path),
      meta.title ? h("span", { class: "api-title" }, `— ${meta.title}`) : null
    ),
    meta.page_id
      ? h(
          "span",
          { style: { fontSize: "11px", color: "#656d76", fontFamily: "monospace" } },
          `page: ${meta.page_id}`
        )
      : null
  );
}
