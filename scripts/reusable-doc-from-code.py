#!/usr/bin/env python3
"""
reusable-doc-from-code.py

REST API URL 경로로 Controller/Handler 파일을 검색하고 Claude CLI로 API 문서를 생성합니다.

검색 방식:
  1. @*Mapping 어노테이션이 있는 Controller/Handler/Router 파일 전체 수집
  2. 각 파일에서 클래스 레벨 @RequestMapping(prefix) + 메서드 레벨 @*Mapping(path) 조합
  3. 입력 URL과 매칭되는 파일만 선택

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
import re
import subprocess
import sys

PROMPT_DIR = "shared-config/write-api-docs"
SYSTEM_PROMPT_FILE = f"{PROMPT_DIR}/docs-writer.md"
TEMPLATE_FILE = f"{PROMPT_DIR}/api-docs-template.md"
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")
CLAUDE_TIMEOUT = int(os.environ.get("CLAUDE_TIMEOUT", "120"))
MAX_FILE_CHARS = 8000
CONTROLLER_PATTERN = re.compile(r"(Controller|Handler|Router)\.(java|kt|go|py|ts|js)$")

# 클래스 레벨 @RequestMapping에서 prefix 추출
CLASS_MAPPING_PATTERN = re.compile(
    r'@RequestMapping\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?["\']([^"\']+)["\']'
)

# 메서드 레벨 @*Mapping에서 경로 추출
# @GetMapping("/path"), @PostMapping(value="/path"), @RequestMapping(path="/path"), @GetMapping (경로 없음)
METHOD_MAPPING_PATTERN = re.compile(
    r'@(?:Get|Post|Put|Delete|Patch|Request)Mapping'
    r'(?:'
    r'\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?["\']([^"\']*)["\']'  # ("path") or (value="path")
    r'|\s*\(\s*\)'                                                  # ()
    r'|\s*(?!\()'                                                   # 괄호 없음
    r')'
)


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


def extract_mapping_paths(content: str) -> tuple:
    """파일에서 클래스 레벨 prefix와 메서드 레벨 경로 목록을 추출한다."""
    # 클래스 레벨 prefix
    class_match = CLASS_MAPPING_PATTERN.search(content)
    class_prefix = class_match.group(1).rstrip("/") if class_match else ""

    # 메서드 레벨 경로들
    method_paths = []
    for m in METHOD_MAPPING_PATTERN.finditer(content):
        path = m.group(1) or ""  # 경로 없는 경우 빈 문자열
        method_paths.append(path)

    return class_prefix, method_paths


def normalize_url(url: str) -> str:
    """path variable({id}, {orderId})을 * 로 치환하고 앞뒤 슬래시 정리."""
    url = re.sub(r"\{[^}]+\}", "*", url)
    return "/" + url.strip("/")


def url_matches(input_url: str, combined_url: str) -> bool:
    """입력 URL이 Controller의 결합 URL과 매칭되는지 확인한다."""
    input_norm = normalize_url(input_url)
    combined_norm = normalize_url(combined_url)
    # 입력 URL이 combined의 prefix이거나, combined이 입력의 prefix이거나, 정확히 일치
    return (
        combined_norm == input_norm
        or combined_norm.startswith(input_norm + "/")
        or input_norm.startswith(combined_norm + "/")
        or input_norm.startswith(combined_norm.replace("*", ""))
    )


def find_controller_files(api_urls: list) -> list:
    """@*Mapping 어노테이션을 파싱하여 API URL을 처리하는 Controller 파일을 찾는다."""

    # 1. @*Mapping이 있는 Controller/Handler/Router 파일 전체 수집
    result = subprocess.run(
        ["grep", "-rl", "@.*Mapping",
         "--include=*.java", "--include=*.kt",
         "--include=*.go", "--include=*.py", "--include=*.ts", "--include=*.js", "."],
        capture_output=True, text=True,
    )
    candidate_files = [
        f for f in result.stdout.strip().splitlines()
        if CONTROLLER_PATTERN.search(f)
    ]

    if not candidate_files:
        print("[WARN] @*Mapping을 포함하는 Controller/Handler/Router 파일이 없습니다.")
        return []

    print(f"[INFO] Controller 후보 파일 {len(candidate_files)}개 발견")

    # 2. 각 파일의 Mapping 경로를 조합하여 입력 URL과 매칭
    found = set()
    for filepath in candidate_files:
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError:
            continue

        class_prefix, method_paths = extract_mapping_paths(content)

        for input_url in api_urls:
            for method_path in method_paths:
                sep = "/" if method_path and not method_path.startswith("/") else ""
                combined = class_prefix + sep + method_path

                if url_matches(input_url, combined):
                    clean_path = filepath.lstrip("./")
                    found.add(clean_path)
                    print(f"  ✓ 매칭: {clean_path}")
                    print(f"    └ {class_prefix or '(prefix 없음)'} + {method_path or '(경로 없음)'} → {combined}")
                    break

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
        if result.stderr:
            print(f"[INFO] Claude stderr: {result.stderr[:500]}")
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

    # 5. 결과 출력 — 첫 번째 URL에서 그룹명 추출 (/api/v1/orders → Orders)
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
