# GitHub Actions 관리 페이지

`shared-workflows` org 도구를 관리하는 정적 웹 페이지입니다. 서버 없이 GitHub Pages로 호스팅합니다.

## 기능

1. **적용 현황 매트릭스** — 조직 내 모든 레포에 어떤 기능이 적용되었는지 확인
2. **기능 적용** — `claude-code-review`, `rest-api-docs` 워크플로우 파일을 대상 레포의 default branch에 자동 커밋
3. **REST API Docs 관리** — Draft 목록 조회, Publish 수동 트리거, Draft 생성 폼
4. **워크플로우 실행 현황** — 최근 실행 결과 확인

## 인증

- 진입 시 GitHub Personal Access Token 입력 필요
- 필요 권한: `repo`, `workflow`
- `sessionStorage`에 저장 (탭 닫으면 자동 삭제)

## 배포 — GitHub Pages

1. 레포 `Settings → Pages → Source`: `Deploy from a branch`
2. Branch: `main` (또는 main 계열) / `docs` 폴더 선택
3. 가능하다면 `Visibility: Private` 으로 설정 (Enterprise)

## 설정 변경

`docs/src/config.js` 에서 아래 값을 변경:

```js
export const API_BASE_URL = "https://github.example.com/api/v3"; // GHES host
export const ORG = "dev-billing";
export const SHARED_WORKFLOWS_REPO = "shared-workflows";
```

## 파일 구조

```
docs/
├── index.html           진입점
├── assets/style.css     스타일
└── src/
    ├── app.js           라우터
    ├── config.js        환경 설정
    ├── state.js         글로벌 상태 + sessionStorage
    ├── api/
    │   ├── github.js    fetch 래퍼 (인증, rate limit)
    │   ├── repos.js     레포 / 파일 CRUD
    │   ├── registry.js  api-docs-registry.json 로딩
    │   └── workflows.js workflow_dispatch / runs
    ├── views/
    │   ├── login.js     PAT 입력
    │   ├── matrix.js    적용 현황 매트릭스
    │   ├── apply-modal.js 기능 적용 모달
    │   ├── api-docs.js  REST API Docs 관리
    │   └── runs.js      실행 현황
    └── utils/           dom, toast, b64
```

## 워크플로우 템플릿

[적용] 클릭 시 복사되는 템플릿은 `shared-workflows/.github/workflows/templates/` 에 위치:

- `claude-pr-review.yml`
- `api-doc-pr.yml`
- `api-doc-publish.yml`
- `api-doc-create-draft.yml`

이 템플릿들을 수정하면 이후 [적용] 시 새 내용이 반영됩니다.

## 로컬 실행

```bash
cd docs
python3 -m http.server 8765
# http://localhost:8765 접속
```
