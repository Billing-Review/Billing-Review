# 🤖 Claude Code Review

> Claude AI를 활용한 자동 PR 코드 리뷰 시스템입니다.
> PR이 열리거나 업데이트되면 Self-hosted Runner에서 자동으로 리뷰가 게시됩니다.

---

## 📌 동작 방식

```
PR 오픈 / 업데이트
        ↓
각 repo의 claude-review.yml 트리거
        ↓
Org의 Reusable Workflow 호출
        ↓
Self-hosted Runner에서 실행
  1. 대상 repo checkout
  2. {org-repo} checkout (.shared-config/)
  3. claude_review.py 실행
        ↓
Repo 설정 로드 (대상 repo의 .claude/rules/CODE_REVIEW.md)
        ↓
Skills 로드
  1순위: repo 설정의 기술 스택 선언
  2순위: diff 확장자 기반 자동 선택 (.java → java-spring)
        ↓
Claude API 호출 → 리뷰 생성
        ↓
GitHub PR에 리뷰 게시
```

---

## 📁 디렉토리 구조

```
claude-review-config/
├── review-prompt.md                ← Claude 역할 정의 + 출력 형식 (전체 리뷰)
├── review-prompt-incremental.md    ← Claude 역할 정의 + 출력 형식 (증분 리뷰)
├── conventions.md                  ← 공통 코딩 컨벤션
└── skills/                         ← 기술 스택별 리뷰 가이드
```

> Repo별 설정은 각 대상 repo의 `.claude/rules/CODE_REVIEW.md`에서 관리합니다.

---

## 🚀 설정 가이드

### 1. 사전 준비

**필수 도구 설치**

```bash
brew install python3
brew install gh
brew install node
npm install -g @anthropic-ai/claude-code

# 설치 확인
python3 --version
gh --version
claude --version
```

> 별도 로그인/인증 불필요. 인증은 Org Secret 토큰으로 자동 처리됩니다.

**Secret 등록**

`GitHub Org → Settings → Secrets and variables → Actions → New organization secret`

| Secret 이름 | 설명 |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | Claude Code OAuth 토큰 |
| `ORG_GITHUB_TOKEN` | Org repo 접근 권한이 있는 GitHub PAT |
| `CODE_REVIEW_APP_ID` | GitHub App ID (PR 리뷰 게시용) |
| `CODE_REVIEW_APP_PRIVATE_KEY` | GitHub App Private Key |

> Repository access를 **All repositories** 또는 리뷰 대상 repo로 설정합니다.

---

### 2. Repository에 Workflow 적용

리뷰를 적용할 repo에 아래 파일을 추가합니다.

**`{repo}/.github/workflows/claude-review.yml`**

```yaml
name: 🤖 Claude PR Review

on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]
  workflow_dispatch:
    inputs:
      pr_number:
        description: 'PR number to review'
        required: true
        type: string

concurrency:
  group: claude-review-${{ github.event.pull_request.number || github.event.inputs.pr_number }}
  cancel-in-progress: true

jobs:
  review:
    if: >
      github.event_name == 'workflow_dispatch' ||
      github.event.pull_request.draft == false
    permissions:
      contents: read
      pull-requests: write
    uses: {org-name}/{org-repo}/.github/workflows/claude-review.yml@main
    with:
      pr_number: ${{ github.event.pull_request.number || github.event.inputs.pr_number }}
      repo_name: ${{ github.repository }}
      manual_trigger: ${{ github.event_name == 'workflow_dispatch' && true || false }}
    secrets:
      CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      ORG_GITHUB_TOKEN: ${{ secrets.ORG_GITHUB_TOKEN }}
      CODE_REVIEW_APP_ID: ${{ secrets.CODE_REVIEW_APP_ID }}
      CODE_REVIEW_APP_PRIVATE_KEY: ${{ secrets.CODE_REVIEW_APP_PRIVATE_KEY }}
```

> 파일 내용은 수정하지 않아도 됩니다. 그대로 복사해서 사용하세요.

---

### 3. Repo별 설정 (선택)

대상 repo에 `.claude/rules/CODE_REVIEW.md` 파일을 생성합니다.

#### 파일 형식

```markdown
# {repo-name} 리뷰 규칙

## 기술 스택
- java-spring
- jpa

## 리뷰 제외
- `src/main/generated/**`
- `**/Q*.java`

## 추가 규칙
- 추가로 리뷰 시 적용할 규칙을 자유롭게 작성
```

> 설정하지 않으면 `.java` 감지 시 `java-spring` skill만 자동 로드됩니다.

**사용 가능한 skill 목록**

| skill 이름 | 적용 대상 |
|---|---|
| `java-spring` | Java, Spring Boot 전반 |
| `jpa` | JPA, Hibernate |
| `mybatis` | MyBatis XML Mapper |
| `spring-batch` | Spring Batch |
| `kafka` | Apache Kafka |
| `redis` | Redis 캐시, 분산락 |

---

## ⚙️ 환경 변수

`claude-review.yml`의 `env:` 섹션에서 재정의할 수 있습니다.

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `CLAUDE_MODEL` | `claude-opus-4-6` | 사용할 Claude 모델 |
| `CLAUDE_TIMEOUT` | `300` | Claude 응답 타임아웃 (초) |
| `MAX_DIFF_LENGTH` | `100000` | diff 최대 길이 (문자) |
| `MAX_SKILL_CHARS` | `5000` | skill 파일 1개 최대 길이 |
| `MAX_SKILLS_TOTAL` | `15000` | skill 전체 최대 길이 |

---

## 🔧 커스터마이징

### 스킬 추가

**① `scripts/claude_review.py` 수정**

```python
EXTENSION_TO_FILE_TYPE = {
    ".kt": "kotlin",
}
DEFAULT_SKILL_BY_FILE_TYPE = {
    "kotlin": "kotlin-spring",
}
```

**② `claude-review-config/skills/{skill-name}.md` 생성**

> skill 이름과 파일명이 **정확히 일치**해야 합니다.

### 공통 컨벤션 변경

`claude-review-config/conventions.md` 파일을 수정합니다.