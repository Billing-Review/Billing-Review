#!/usr/bin/env python3
"""
reusable-doc-from-code.py

소스 코드 파일을 읽어 Claude CLI로 API 문서를 생성합니다.

환경 변수:
  CLAUDE_CODE_OAUTH_TOKEN   Claude CLI 인증 토큰
  REPO_NAME                 저장소 이름 (org/repo)
  BRANCH                    브랜치 이름
  API_PATHS                 쉼표로 구분된 API 파일 경로
  URL_HINT_INPUT            위키 경로 힌트 (internal/external, 선택)
  CLAUDE_MODEL              사용할 Claude 모델 (기본값: claude-sonnet-4-20250514)
  CLAUDE_TIMEOUT            Claude CLI 타임아웃 초 (기본값: 120)
  GITHUB_OUTPUT             GitHub Actions 출력 파일 경로
"""

import os
import subprocess
import sys

PROMPT_DIR = "shared-config/write-api-docs"
SYSTEM_PROMPT_FILE = f"{PROMPT_DIR}/docs-writer.md"
TEMPLATE_FILE = f"{PROMPT_DIR}/api-docs-template.md"
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")
CLAUDE_TIMEOUT = int(os.environ.get("CLAUDE_TIMEOUT", "120"))
MAX_FILE_CHARS = 8000


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


def read_api_files(api_paths: list) -> str:
    collected = []
    missing = []
    for path in api_paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            collected.append(f"### {path}\n```\n{content[:MAX_FILE_CHARS]}\n```")
        else:
            missing.append(path)

    if missing:
        print(f"::warning::파일 없음: {', '.join(missing)}")

    if not collected:
        print("::error::읽을 수 있는 API 파일이 없습니다.", file=sys.stderr)
        sys.exit(1)

    print(f"{len(collected)}개 파일 읽기 완료")
    return "\n\n".join(collected)


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
    repo_name = os.environ.get("REPO_NAME", "")
    branch = os.environ.get("BRANCH", "")
    api_paths_str = os.environ.get("API_PATHS", "")
    url_hint_input = os.environ.get("URL_HINT_INPUT", "")

    if not api_paths_str:
        print("API_PATHS 환경 변수가 필요합니다.", file=sys.stderr)
        sys.exit(1)

    api_paths = [p.strip() for p in api_paths_str.split(",") if p.strip()]

    # 1. 코드 파일 읽기
    code_content = read_api_files(api_paths)

    # 2. 프롬프트 파일 읽기
    with open(SYSTEM_PROMPT_FILE, "r") as f:
        system_prompt = f.read()
    with open(TEMPLATE_FILE, "r") as f:
        template = f.read()

    prompt = f"""{system_prompt}

다음은 {repo_name} 레포지토리 {branch} 브랜치의 API 코드입니다.

{code_content}

아래 템플릿 형식으로 API 문서를 작성하세요.

{template}
"""

    # 3. Claude CLI로 문서 생성
    doc_content = call_claude(prompt)

    # 4. 결과 출력
    first_file = os.path.basename(api_paths[0]) if api_paths else "API"
    group_name = (
        first_file
        .replace("Controller.java", "")
        .replace("Handler.java", "")
        .replace("Router.java", "")
    )
    title = f"[API Draft] {group_name} API 명세"

    url_hint = url_hint_input
    if not url_hint:
        combined = code_content.lower()
        if "internal" in combined:
            url_hint = "internal"
        elif "external" in combined:
            url_hint = "external"

    set_output("doc_content", doc_content)
    set_output("title", title)
    set_output("url_hint", url_hint)

    print(f"문서 생성 완료 | 제목: {title} | URL 힌트: {url_hint or '없음'}")


if __name__ == "__main__":
    main()
