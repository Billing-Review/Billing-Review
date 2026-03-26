# {org-repo}

> Org 전체에서 공유하는 GitHub Actions Workflow, 스크립트, 설정을 관리하는 공유 레포지토리입니다.

---

## 📁 디렉토리 구조

```
{org-repo}/
├── .github/workflows/      ← Reusable Workflows
├── scripts/                ← Workflow 실행 스크립트
├── claude-review-config/   ← Claude Code Review 설정 및 가이드
│   ├── review-prompt.md    ← Claude 역할 정의 + 출력 형식
│   ├── conventions.md      ← 공통 코딩 컨벤션
│   └── skills/             ← 기술 스택별 리뷰 가이드
```

---

## ⚡ Workflows

| Workflow | 파일 | 설명 |
|---|---|---|
| Claude Code Review | `claude-review.yml` | PR 자동 코드 리뷰 |

### 새 Workflow 추가

1. `.github/workflows/{workflow-name}.yml` 작성 (`workflow_call` 트리거)
2. 설정 파일이 필요한 경우 `{workflow-name}-config/` 디렉토리 생성
3. `{workflow-name}-config/README.md` 작성
4. 이 파일의 Workflows 테이블에 항목 추가

---

## 🖥️ Runner 등록

개발자 각자 **본인 노트북을 Runner로 등록**합니다.

`GitHub Org → Settings → Actions → Runners → New self-hosted runner`

> OS: macOS / Architecture: M시리즈 (ARM64) · Intel (x64)

필수 도구 설치는 각 Workflow config 디렉토리의 README를 참고하세요.

```bash
# 1. Runner 디렉토리 생성
mkdir -p ~/actions-runner && cd ~/actions-runner

# 2. Runner 다운로드 (Org New Runner 화면의 실제 URL 사용) — 26.03.24 기준 macOS ARM64
curl -o actions-runner-osx-arm64-2.333.0.tar.gz -L \
  https://github.com/actions/runner/releases/download/v2.333.0/actions-runner-osx-arm64-2.333.0.tar.gz

# 3. 압축 해제
tar xzf ./actions-runner-osx-arm64-2.333.0.tar.gz

# 4. Runner 설정
./config.sh \
  --url {git enterprise url}/{org-name} \
  --token {org-token} \
  --runnergroup claude-code-review \
  --name "{본인이름}-macbook" \
  --labels claude-code-review

# 5. 부팅 시 자동 실행 등록
sudo ./svc.sh install
sudo ./svc.sh start

# 6. 상태 확인
sudo ./svc.sh status
```

> Runner 이름은 본인을 식별할 수 있게 설정합니다. (예: `beomsu-macbook`)