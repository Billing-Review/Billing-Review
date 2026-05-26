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

// 관리 페이지에서 표시할 레포 목록 파일 (shared-workflows 레포 내 경로)
export const REPO_LIST_PATH = "docs/repo-list.json";

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
    // 적용 시 추가로 입력받을 정보. 'service-config' 타입은 shared-workflows 의
    // rest-api-docs/service-config.json 에 환경별 URL 을 등록한다.
    extraSetup: "service-config",
  },
];

// 레포 목록 정렬 기준: "updated" | "name" | "created"
export const REPO_SORT = "updated";

// =============================================================
// REST API Docs 워크플로우 dispatch 기본값
// =============================================================
// 워크플로우 YAML 을 읽고 실행할 브랜치 (워크플로우 파일이 항상 존재해야 함)
export const API_DOCS_WORKFLOW_REF = "main";

// Draft 생성 시 컨트롤러 "소스 코드"를 읽을 기본 브랜치
export const API_DOCS_CODE_BRANCH_DEFAULT = "main";
