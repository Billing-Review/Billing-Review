#!/usr/bin/env python3
"""
Claude Code PR Review Script

Organization의 공통 설정과 리포지토리별 추가 규칙을 합쳐서
Claude에게 코드 리뷰를 요청하고 결과를 PR 코멘트로 게시한다.

디렉토리 구조 (Organization .github 리포지토리):
    review-config/
    ├── base-rules.md           ← 공통 리뷰 규칙
    ├── conventions.md          ← 공통 코딩 컨벤션
    ├── prompt-template.md      ← 시스템 프롬프트
    └── repo/
        ├── payment-service.md  ← 리포지토리별 추가 규칙
        ├── order-api.md
        └── user-service.md

사용법:
    python3 claude_review.py <pr_number> <repo_full_name>
    python3 claude_review.py 42 dev-team/payment-service
"""

import json
import os
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path


# ============================================================
# 설정
# ============================================================

SHARED_CONFIG_DIR = os.environ.get(
    "SHARED_CONFIG_DIR", ".shared-config/review-config"
)

BASE_RULES_PATH = os.path.join(SHARED_CONFIG_DIR, "base-rules.md")
CONVENTIONS_PATH = os.path.join(SHARED_CONFIG_DIR, "conventions.md")
PROMPT_TEMPLATE_PATH = os.path.join(SHARED_CONFIG_DIR, "prompt-template.md")
REPO_CONFIG_DIR = os.path.join(SHARED_CONFIG_DIR, "repo")

MAX_DIFF_LINES = int(os.environ.get("MAX_DIFF_LINES", "2000"))
CLAUDE_TIMEOUT = int(os.environ.get("CLAUDE_TIMEOUT", "300"))


# ============================================================
# GitHub CLI 래퍼
# ============================================================

def run_gh(args: list[str]) -> str:
    """gh CLI를 실행하고 stdout을 반환한다."""
    result = subprocess.run(
        ["gh"] + args,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[ERROR] gh {' '.join(args)}", file=sys.stderr)
        print(f"  stderr: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return result.stdout


def get_pr_info(pr_number: str, repo: str) -> dict:
    """PR 메타 정보를 가져온다."""
    output = run_gh([
        "pr", "view", pr_number,
        "--repo", repo,
        "--json", "title,body,author,baseRefName,headRefName,files",
    ])
    return json.loads(output)


def get_pr_diff(pr_number: str, repo: str) -> str:
    """PR diff를 가져온다."""
    return run_gh(["pr", "diff", pr_number, "--repo", repo])


def post_comment(pr_number: str, repo: str, body: str):
    """PR에 코멘트를 게시한다."""
    run_gh([
        "pr", "comment", pr_number,
        "--repo", repo,
        "--body", body,
    ])
    print(f"[INFO] Review comment posted to PR #{pr_number}")


# ============================================================
# Diff 처리
# ============================================================

# base-rules.md에서 정의한 기본 제외 패턴
DEFAULT_IGNORE_PATTERNS = [
    "*.generated.*",
    "*.min.js",
    "*.min.css",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    ".idea/*",
    ".vscode/*",
]


def parse_ignore_patterns(repo_config_content: str) -> list[str]:
    """
    리포지토리별 md에서 '리뷰 제외 대상' 섹션의 패턴을 파싱한다.
    - `src/main/generated/**` 형태의 줄을 찾는다.
    """
    patterns = []
    in_exclude_section = False

    for line in repo_config_content.split("\n"):
        stripped = line.strip()

        if "리뷰 제외" in stripped or "리뷰에서 제외" in stripped:
            in_exclude_section = True
            continue

        if in_exclude_section:
            if stripped.startswith("#"):
                in_exclude_section = False
                continue

            if stripped.startswith("- "):
                pattern = stripped[2:].strip().strip("`")
                if pattern:
                    patterns.append(pattern)

    return patterns


def filter_diff(diff: str, extra_ignore_patterns: list[str]) -> str:
    """ignore 패턴에 해당하는 파일의 diff를 제거한다."""
    all_patterns = DEFAULT_IGNORE_PATTERNS + extra_ignore_patterns

    if not all_patterns:
        return diff

    filtered_lines = []
    skip_file = False

    for line in diff.split("\n"):
        if line.startswith("diff --git"):
            # diff --git a/path/to/file b/path/to/file
            file_path = line.split(" b/")[-1] if " b/" in line else ""
            skip_file = any(fnmatch(file_path, p) for p in all_patterns)

        if not skip_file:
            filtered_lines.append(line)

    return "\n".join(filtered_lines)


def truncate_diff(diff: str, max_lines: int) -> str:
    """diff가 너무 길면 잘라낸다."""
    lines = diff.split("\n")
    if len(lines) <= max_lines:
        return diff

    truncated = "\n".join(lines[:max_lines])
    truncated += f"\n\n... (이하 {len(lines) - max_lines}줄 생략, 총 {len(lines)}줄)"
    return truncated


# ============================================================
# 프롬프트 조립
# ============================================================

def read_file_safe(path: str) -> str:
    """파일이 있으면 읽고, 없으면 빈 문자열을 반환한다."""
    p = Path(path)
    if p.exists():
        content = p.read_text().strip()
        print(f"[INFO] Loaded: {path}", file=sys.stderr)
        return content

    print(f"[WARN] Not found: {path}", file=sys.stderr)
    return ""


def find_repo_config(repo_full_name: str) -> str:
    """
    Organization의 review-config/repo/ 디렉토리에서
    PR이 올라온 리포지토리 이름과 같은 md 파일을 찾는다.

    repo_full_name: "dev-team/payment-service"
    → review-config/repo/payment-service.md 를 찾는다.
    """
    repo_name = repo_full_name.split("/")[-1]  # "payment-service"
    repo_config_path = os.path.join(REPO_CONFIG_DIR, f"{repo_name}.md")

    content = read_file_safe(repo_config_path)
    if content:
        print(f"[INFO] Repo config matched: {repo_config_path}", file=sys.stderr)
    else:
        print(f"[INFO] No repo config for '{repo_name}', using org defaults only", file=sys.stderr)

    return content


def build_prompt(pr_info: dict, diff: str, repo_full_name: str) -> str:
    """최종 프롬프트를 조립한다."""

    # 1) 시스템 프롬프트
    prompt_template = read_file_safe(PROMPT_TEMPLATE_PATH)

    # 2) 공통 규칙
    base_rules = read_file_safe(BASE_RULES_PATH)
    conventions = read_file_safe(CONVENTIONS_PATH)

    # 3) 리포지토리별 추가 규칙
    repo_config = find_repo_config(repo_full_name)

    # 4) PR 정보
    author = pr_info.get("author", {}).get("login", "unknown")
    title = pr_info.get("title", "")
    body = pr_info.get("body", "") or "설명 없음"
    head = pr_info.get("headRefName", "")
    base = pr_info.get("baseRefName", "")

    changed_files = pr_info.get("files", [])
    file_list = "\n".join(
        f"  - {f.get('path', '')} (+{f.get('additions', 0)} -{f.get('deletions', 0)})"
        for f in changed_files
    ) if changed_files else "  (파일 목록 없음)"

    # 5) 조립
    sections = []

    if prompt_template:
        sections.append(prompt_template)

    sections.append(f"""
---

## PR 정보
- **제목**: {title}
- **작성자**: {author}
- **브랜치**: `{head}` → `{base}`
- **변경 파일 수**: {len(changed_files)}개

### PR 설명
{body}

### 변경된 파일 목록
{file_list}
""")

    if base_rules:
        sections.append("---\n\n" + base_rules)

    if conventions:
        sections.append("---\n\n" + conventions)

    if repo_config:
        sections.append("---\n\n" + repo_config)

    sections.append(f"""
---

## 리뷰 대상 Diff

아래 diff를 위의 모든 규칙과 컨벤션을 기준으로 리뷰해주세요.

```diff
{diff}
```
""")

    return "\n\n".join(sections)


# ============================================================
# Claude 실행
# ============================================================

def run_claude(prompt: str) -> str:
    """Claude Code CLI를 실행하여 리뷰 결과를 받는다."""
    print(f"[INFO] Running Claude Code (timeout: {CLAUDE_TIMEOUT}s)...", file=sys.stderr)
    print(f"[INFO] Prompt length: {len(prompt)} chars", file=sys.stderr)

    try:
        result = subprocess.run(
            ["claude", "--print", "--max-turns", "1"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        print("[ERROR] Claude timed out", file=sys.stderr)
        return "⏰ Claude 리뷰가 시간 초과되었습니다. diff가 너무 크거나 네트워크 문제일 수 있습니다."

    if result.returncode != 0:
        print(f"[ERROR] Claude exited with code {result.returncode}", file=sys.stderr)
        print(f"  stderr: {result.stderr[:500]}", file=sys.stderr)
        return f"❌ Claude 실행 실패 (exit code: {result.returncode})\n```\n{result.stderr[:300]}\n```"

    output = result.stdout.strip()
    if not output:
        return "⚠️ Claude가 빈 응답을 반환했습니다."

    print(f"[INFO] Claude response: {len(output)} chars", file=sys.stderr)
    return output


# ============================================================
# 메인
# ============================================================

def main():
    if len(sys.argv) < 3:
        print("Usage: claude_review.py <pr_number> <repo_full_name>", file=sys.stderr)
        print("Example: claude_review.py 42 dev-team/payment-service", file=sys.stderr)
        sys.exit(1)

    pr_number = sys.argv[1]
    repo_full_name = sys.argv[2]

    print(f"[INFO] === Claude PR Review ===", file=sys.stderr)
    print(f"[INFO] PR: #{pr_number} in {repo_full_name}", file=sys.stderr)

    # 1) PR 정보 수집
    print(f"[INFO] Fetching PR info...", file=sys.stderr)
    pr_info = get_pr_info(pr_number, repo_full_name)

    # 2) Diff 가져오기
    print(f"[INFO] Fetching PR diff...", file=sys.stderr)
    diff = get_pr_diff(pr_number, repo_full_name)

    if not diff.strip():
        print("[WARN] Empty diff, skipping review", file=sys.stderr)
        post_comment(pr_number, repo_full_name, "## 🤖 Claude Code Review\n\n변경 사항이 없어 리뷰를 건너뜁니다.")
        return

    # 3) 리포지토리별 추가 ignore 패턴 파싱
    repo_config_content = find_repo_config(repo_full_name)
    extra_patterns = parse_ignore_patterns(repo_config_content) if repo_config_content else []
    if extra_patterns:
        print(f"[INFO] Extra ignore patterns: {extra_patterns}", file=sys.stderr)

    # 4) Diff 필터링 및 잘라내기
    diff = filter_diff(diff, extra_patterns)
    diff = truncate_diff(diff, MAX_DIFF_LINES)

    # 5) 프롬프트 조립
    print(f"[INFO] Building prompt...", file=sys.stderr)
    prompt = build_prompt(pr_info, diff, repo_full_name)

    # 6) Claude 실행
    review_result = run_claude(prompt)

    # 7) PR 코멘트 게시
    comment_body = f"## 🤖 Claude Code Review\n\n{review_result}"

    # GitHub 코멘트 최대 길이 제한 (65536자)
    if len(comment_body) > 65000:
        comment_body = comment_body[:65000] + "\n\n... (응답이 길어 일부 잘림)"

    post_comment(pr_number, repo_full_name, comment_body)

    # 8) 결과 파일 저장 (알림 스크립트용)
    result_path = os.path.join(
        os.environ.get("GITHUB_WORKSPACE", "/tmp"),
        "review-result.md",
    )
    Path(result_path).write_text(review_result)
    print(f"[INFO] Review result saved to: {result_path}", file=sys.stderr)
    print(f"[INFO] === Done ===", file=sys.stderr)


if __name__ == "__main__":
    main()