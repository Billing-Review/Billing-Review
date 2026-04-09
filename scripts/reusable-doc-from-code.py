#!/usr/bin/env python3
"""
reusable-doc-from-code.py

REST API URL 경로로 Controller/Handler 파일을 검색하고 Claude CLI로 API 문서를 생성합니다.

환경 변수:
  CLAUDE_CODE_OAUTH_TOKEN   Claude CLI 인증 토큰
  REPO_NAME                 저장소 이름 (org/repo)
  BRANCH                    브랜치 이름
  API_PATHS                 쉼표로 구분된 REST API URL 경로 (예: /api/v1/orders,/api/v1/payments)
  URL_HINT_INPUT            위키 경로 힌트 (internal/external, 선택)
  CLAUDE_MODEL              사용할 Claude 모델 (기본값: claude-sonnet-4-20250514)
  CLAUDE_TIMEOUT            Claude CLI 타임아웃 초 (기본값: 120)
  GITHUB_OUTPUT             GitHub Actions 출력 파일 경로
"""

import os
import subprocess
import sys
from pathlib import Path

PROMPT_DIR = "shared-config/write-api-docs"
SYSTEM_PROMPT_FILE = f"{PROMPT_DIR}/docs-writer.md"
TEMPLATE_FILE = f"{PROMPT_DIR}/api-docs-template.md"
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")
CLAUDE_TIMEOUT = int(os.environ.get("CLAUDE_TIMEOUT", "120"))
MAX_FILE_CHARS = 8000
CONTROLLER_PATTERN = re.compile(r"(Controller|Handler|Router)\.(java|kt|go|py|ts|js)$")

import re


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


def find_controller_files(api_urls: list) -> list:
    """API URL 경로를 포함하는 Controller/Handler/Router 파일을 검색한다."""
    found = set()

    for url in api_urls:
        # URL에서 검색 키워드 추출: /api/v1/orders → orders, order 등
        # 경로 세그먼트 중 버전(v1, v2...)과 공통 prefix(api) 제외
        segments = [
            s for s in url.strip("/").split("/")
            if s and not re.match(r"^(api|v\d+(\.\d+)?)$", s)
        ]

        # 1차: 파일 내에서 URL 문자열 직접 검색
        result = subprocess.run(
            ["grep", "-rl", url, "--include=*.java", "--include=*.kt",
             "--include=*.go", "--include=*.py", "--include=*.ts", "--include=*.js", "."],
            capture_output=True, text=True,
        )
        for f in result.stdout.strip().splitlines():
            if CONTROLLER_PATTERN.search(f):
                found.add(f.lstrip("./"))

        # 2차: URL 직접 검색 결과 없으면 세그먼트 키워드로 Controller 파일명 검색
        if not any(url in open(f).read() for f in [f"./{p}" for p in found] if os.path.exists(f"./{p}")):
            for segment in segments:
                result = subprocess.run(
                    ["find", ".", "-type", "f",
                     "-iname", f"*{segment}*",
                     "-name", "*Controller*", "-o",
                     "-type", "f", "-iname", f"*{segment}*", "-name", "*Handler*", "-o",
                     "-type", "f", "-iname", f"*{segment}*", "-name", "*Router*"],
                    capture_output=True, text=True,
                )
                for f in result.stdout.strip().splitlines():
                    if CONTROLLER_PATTERN.search(f):
                        found.add(f.lstrip("./"))

    return sorted(found)


def read_controller_files(file_paths: list) -> str:
    collected = []
    for path in file_paths:
        full_path = path if os.path.exists(path) else f"./{path}"
        if os.path.exists(full_path):
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            collected.append(f"### {path}\n```\n{content[:MAX_FILE_CHARS]}\n```")
        else:
            print(f"::warning::파일 없음: {path}")

    if not collected:
        print("::error::읽을 수 있는 Controller 파일이 없습니다.", file=sys.stderr)
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

    api_urls = [p.strip() for p in api_paths_str.split(",") if p.strip()]
    print(f"검색할 API URL: {api_urls}")

    # 1. URL로 Controller 파일 검색
    controller_files = find_controller_files(api_urls)

    if not controller_files:
        print("::error::해당 API URL을 처리하는 Controller 파일을 찾을 수 없습니다.", file=sys.stderr)
        sys.exit(1)

    print(f"발견된 Controller 파일: {controller_files}")

    # 2. 파일 내용 읽기
    code_content = read_controller_files(controller_files)

    # 3. 프롬프트 파일 읽기
    with open(SYSTEM_PROMPT_FILE, "r") as f:
        system_prompt = f.read()
    with open(TEMPLATE_FILE, "r") as f:
        template = f.read()

    prompt = f"""{system_prompt}

다음은 {repo_name} 레포지토리 {branch} 브랜치에서 아래 API URL을 처리하는 코드입니다.

대상 API URL: {', '.join(api_urls)}

{code_content}

아래 템플릿 형식으로 API 문서를 작성하세요.

{template}
"""

    # 4. Claude CLI로 문서 생성
    doc_content = call_claude(prompt)

    # 5. 결과 출력
    # 첫 번째 URL 세그먼트에서 그룹명 추출 (예: /api/v1/orders → orders)
    first_url = api_urls[0]
    segments = [s for s in first_url.strip("/").split("/")
                if s and not re.match(r"^(api|v\d+(\.\d+)?)$", s)]
    group_name = segments[0].capitalize() if segments else "API"
    title = f"[API Draft] {group_name} API 명세"

    url_hint = url_hint_input
    if not url_hint:
        combined = (code_content + " ".join(api_urls)).lower()
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
