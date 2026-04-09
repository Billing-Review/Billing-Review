#!/usr/bin/env python3
"""
reusable-doc-from-diff.py

PR diff에서 API 관련 변경사항을 추출하고 Claude CLI로 문서를 생성합니다.

환경 변수:
  GH_TOKEN                  GitHub 인증 토큰
  CLAUDE_CODE_OAUTH_TOKEN   Claude CLI 인증 토큰
  PR_NUMBER                 PR 번호
  REPO_NAME                 저장소 이름 (org/repo)
  CLAUDE_MODEL              사용할 Claude 모델 (기본값: claude-sonnet-4-20250514)
  CLAUDE_TIMEOUT            Claude CLI 타임아웃 초 (기본값: 120)
  GITHUB_OUTPUT             GitHub Actions 출력 파일 경로
"""

import json
import os
import re
import subprocess
import sys

PROMPT_DIR = "shared-config/write-api-docs"
SYSTEM_PROMPT_FILE = f"{PROMPT_DIR}/docs-writer.md"
TEMPLATE_FILE = f"{PROMPT_DIR}/api-docs-template.md"
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")
CLAUDE_TIMEOUT = int(os.environ.get("CLAUDE_TIMEOUT", "120"))
MAX_DIFF_LENGTH = 15000


def set_output(name: str, value: str):
    output_file = os.environ.get("GITHUB_OUTPUT", "")
    if not output_file:
        print(f"OUTPUT {name}={value[:100]}...")
        return
    delim = "GHADELIMITER_DOC"
    with open(output_file, "a") as f:
        if "\n" in value:
            f.write(f"{name}<<{delim}\n{value}\n{delim}\n")
        else:
            f.write(f"{name}={value}\n")


def get_pr_diff(pr_number: str, repo_name: str) -> str:
    result = subprocess.run(
        ["gh", "pr", "diff", pr_number, "--repo", repo_name],
        capture_output=True,
        text=True,
        env={**os.environ},
    )
    if result.returncode != 0:
        print(f"gh pr diff 실패: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout


def get_pr_metadata(pr_number: str, repo_name: str) -> tuple:
    result = subprocess.run(
        ["gh", "pr", "view", pr_number, "--repo", repo_name, "--json", "title,body"],
        capture_output=True,
        text=True,
        env={**os.environ},
    )
    if result.returncode != 0:
        print(f"gh pr view 실패: {result.stderr}", file=sys.stderr)
        return "", ""
    data = json.loads(result.stdout)
    return data.get("title", ""), data.get("body", "") or ""


def filter_api_diff(full_diff: str) -> str:
    sections = re.split(r"(?=^diff --git )", full_diff, flags=re.MULTILINE)
    api_sections = [
        s for s in sections
        if re.search(r"(Controller|Handler|Router)\.(java|kt|go|py|ts|js)", s)
    ]
    return "\n".join(api_sections)


def call_claude(prompt: str) -> str:
    home = os.path.expanduser("~")
    print(f"[INFO] Claude 호출 (model={CLAUDE_MODEL}, timeout={CLAUDE_TIMEOUT}s)")
    print(f"[INFO] 프롬프트 길이: {len(prompt)} chars")

    env = {
        **os.environ,
        "HOME": home,
        "PYTHONIOENCODING": "utf-8",
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
    }

    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--model", CLAUDE_MODEL],
            capture_output=True,
            check=True,
            timeout=CLAUDE_TIMEOUT,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        output = result.stdout.strip()
        print(f"[INFO] Claude 응답: {len(output)} chars")
        return output
    except subprocess.CalledProcessError as e:
        err = (e.stdout or "") + (e.stderr or "")
        if "Not logged in" in err or "/login" in err:
            print("[ERROR] Claude 인증 실패. CLAUDE_CODE_OAUTH_TOKEN 확인 필요", file=sys.stderr)
        else:
            print(f"[ERROR] Claude CLI 실패 (exit {e.returncode})", file=sys.stderr)
            print(f"  stdout: {e.stdout[:500]}", file=sys.stderr)
            print(f"  stderr: {e.stderr[:500]}", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(f"[ERROR] Claude CLI 타임아웃 ({CLAUDE_TIMEOUT}s)", file=sys.stderr)
        sys.exit(1)


def main():
    pr_number = os.environ.get("PR_NUMBER", "")
    repo_name = os.environ.get("REPO_NAME", "")

    if not pr_number or not repo_name:
        print("PR_NUMBER, REPO_NAME 환경 변수가 필요합니다.", file=sys.stderr)
        sys.exit(1)

    # 1. PR diff 가져오기
    full_diff = get_pr_diff(pr_number, repo_name)

    # 2. API 관련 파일만 필터링
    api_diff = filter_api_diff(full_diff)

    if not api_diff.strip():
        print("::notice::API 관련 변경사항 없음 — 문서 생성 스킵")
        set_output("skipped", "true")
        set_output("doc_content", "")
        set_output("title", "")
        set_output("url_hint", "")
        return

    set_output("skipped", "false")
    print(f"API 변경 감지됨 ({len(api_diff)} bytes)")

    # 3. PR 메타데이터 가져오기
    pr_title, pr_body = get_pr_metadata(pr_number, repo_name)

    # 4. 프롬프트 파일 읽기
    with open(SYSTEM_PROMPT_FILE, "r") as f:
        system_prompt = f.read()
    with open(TEMPLATE_FILE, "r") as f:
        template = f.read()

    prompt = f"""{system_prompt}

다음은 GitHub PR의 API 관련 코드 변경사항(diff)입니다.

PR 제목: {pr_title}
PR 설명: {pr_body}

변경된 코드:
```diff
{api_diff[:MAX_DIFF_LENGTH]}
```

아래 템플릿 형식으로 API 문서를 작성하세요.

{template}
"""

    # 5. Claude CLI로 문서 생성
    doc_content = call_claude(prompt)

    # 6. 결과 출력
    title = f"[API Draft] {pr_title}"
    url_hint = ""
    if "internal" in api_diff.lower():
        url_hint = "internal"
    elif "external" in api_diff.lower():
        url_hint = "external"

    set_output("doc_content", doc_content)
    set_output("title", title)
    set_output("url_hint", url_hint)

    print(f"문서 생성 완료 | 제목: {title} | URL 힌트: {url_hint or '없음'}")


if __name__ == "__main__":
    main()
