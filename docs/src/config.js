// =============================================================
// 환경 설정 — 배포 시 이 파일만 수정하면 됩니다.
// =============================================================

// GitHub Enterprise Server API base URL.
// 예: "https://github.example.com/api/v3"
// public github 사용 시: "https://api.github.com"
export const API_BASE_URL = "https://api.github.com";

// 관리할 조직명
export const ORG = "dev-billing";

// shared-workflows 레포 (템플릿 파일 + registry 위치)
export const SHARED_WORKFLOWS_REPO = "shared-workflows";

// =============================================================
// Feature 정의
//   - id: 내부 식별자
//   - label: 화면 표시명
//   - files: 서비스 레포에 복사할 파일 [{ source, target }]
//       source: shared-workflows 레포에서 읽을 경로
//       target: 서비스 레포에 쓸 경로
//   - manualWorkflows: 사용자가 수동으로 트리거할 수 있는 워크플로우 (서비스 레포에서)
// =============================================================
export const FEATURES = [
  {
    id: "claude-code-review",
    label: "Claude Code Review",
    files: [
      {
        source: ".github/workflows/templates/claude-pr-review.yml",
        target: ".github/workflows/claude-pr-review.yml",
      },
    ],
    manualWorkflows: [],
  },
  {
    id: "rest-api-docs",
    label: "REST API Docs",
    files: [
      {
        source: ".github/workflows/templates/api-doc-pr.yml",
        target: ".github/workflows/api-doc-pr.yml",
      },
      {
        source: ".github/workflows/templates/api-doc-publish.yml",
        target: ".github/workflows/api-doc-publish.yml",
      },
      {
        source: ".github/workflows/templates/api-doc-create-draft.yml",
        target: ".github/workflows/api-doc-create-draft.yml",
      },
    ],
    manualWorkflows: [
      { file: "api-doc-publish.yml", label: "Publish" },
      { file: "api-doc-create-draft.yml", label: "Create Draft" },
    ],
  },
];

// =============================================================
// 매트릭스에 표시할 레포 필터.
//   null  → org의 모든 레포
//   배열  → 화이트리스트
// =============================================================
export const REPO_WHITELIST = null;

// 레포 목록 정렬 기준: "updated" | "name" | "created"
export const REPO_SORT = "updated";
