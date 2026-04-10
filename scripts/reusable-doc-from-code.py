#!/usr/bin/env python3
"""
reusable-doc-from-code.py

REST API URL 경로로 Controller/Handler 파일을 검색하고 Claude CLI로 API 문서를 생성합니다.

검색 방식:
  1. @*Mapping 어노테이션이 있는 Controller/Handler/Router 파일 전체 수집
  2. 각 파일에서 클래스 레벨 @RequestMapping(prefix) + 메서드 레벨 @*Mapping(path) 조합
  3. 입력 HTTP Method + URL과 정확히 일치하는 파일만 선택
  4. Controller import에서 DTO/Service/Exception 파일 추가 수집

환경 변수:
  CLAUDE_CODE_OAUTH_TOKEN   Claude CLI 인증 토큰
  REPO_NAME                 저장소 이름 (org/repo)
  BRANCH                    브랜치 이름
  HTTP_METHOD               HTTP 메서드 (GET, POST, PUT, DELETE, PATCH)
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

# 메서드 레벨 @*Mapping에서 (HTTP 메서드, 경로) 추출
# @GetMapping("/path"), @PostMapping(value="/path"), @RequestMapping(path="/path"), @GetMapping
METHOD_MAPPING_PATTERN = re.compile(
    r'@(Get|Post|Put|Delete|Patch|Request)Mapping'
    r'(?:'
    r'\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?["\']([^"\']*)["\']'  # ("path") or (value="path")
    r'|\s*\(\s*\)'                                                  # ()
    r'|\s*(?!\()'                                                   # 괄호 없음
    r')'
)

# 외부 라이브러리 import 제외 prefix
EXTERNAL_IMPORT_PREFIXES = (
    "java.", "javax.", "jakarta.",
    "org.springframework.", "org.slf4j.", "org.junit.", "org.mockito.",
    "lombok.", "com.fasterxml.", "io.swagger.", "io.micrometer.",
    "reactor.", "kotlin.", "kotlinx.",
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


def extract_method_mappings(content: str) -> list:
    """파일에서 (HTTP 메서드, 결합 경로) 목록을 반환한다."""
    class_match = CLASS_MAPPING_PATTERN.search(content)
    class_prefix = class_match.group(1).rstrip("/") if class_match else ""

    results = []
    for m in METHOD_MAPPING_PATTERN.finditer(content):
        verb = m.group(1).upper()  # Get → GET, Request → REQUEST
        path = m.group(2) or ""
        sep = "/" if path and not path.startswith("/") else ""
        combined = class_prefix + sep + path
        results.append((verb, combined))

    return results


def normalize_url(url: str) -> str:
    """path variable({id})을 * 로 치환하고 앞뒤 슬래시 정리."""
    url = re.sub(r"\{[^}]+\}", "*", url)
    return "/" + url.strip("/")


def http_method_matches(input_method: str, mapping_verb: str) -> bool:
    """입력 HTTP 메서드가 어노테이션 verb와 일치하는지 확인한다."""
    if mapping_verb == "REQUEST":
        return True  # @RequestMapping은 모든 메서드 허용
    return input_method.upper() == mapping_verb


def find_controller_files(api_urls: list, http_method: str) -> list:
    """HTTP Method + URL이 정확히 일치하는 Controller 파일을 찾는다."""

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

    # 2. HTTP Method + 정확한 경로 일치
    found = set()
    for filepath in candidate_files:
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError:
            continue

        mappings = extract_method_mappings(content)

        for input_url in api_urls:
            input_norm = normalize_url(input_url)
            for verb, combined_path in mappings:
                if not http_method_matches(http_method, verb):
                    continue
                if normalize_url(combined_path) != input_norm:
                    continue
                clean_path = filepath.lstrip("./")
                found.add(clean_path)
                print(f"  ✓ 매칭: {clean_path}")
                print(f"    └ [{verb}] {combined_path}")
                break

    return sorted(found)


def find_related_files(controller_paths: list) -> list:
    """Controller import에서 DTO/Service/Exception 파일을 탐색한다."""
    import_pattern = re.compile(r'import\s+([\w.]+);')
    related = []
    seen = set(controller_paths)

    for ctrl_path in controller_paths:
        full_path = ctrl_path if os.path.exists(ctrl_path) else f"./{ctrl_path}"
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError:
            continue

        for imp in import_pattern.findall(content):
            if any(imp.startswith(p) for p in EXTERNAL_IMPORT_PREFIXES):
                continue
            # 클래스 경로 → 파일 경로
            file_path = "src/main/java/" + imp.replace(".", "/") + ".java"
            if file_path in seen:
                continue
            if os.path.exists(file_path):
                seen.add(file_path)
                related.append(file_path)
                print(f"  + 관련 파일: {file_path}")

    return related


def read_source_files(controller_paths: list, related_paths: list) -> str:
    collected = []
    all_paths = [(p, "Controller") for p in controller_paths] + \
                [(p, "참조") for p in related_paths]

    for path, label in all_paths:
        full_path = path if os.path.exists(path) else f"./{path}"
        if os.path.exists(full_path):
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            collected.append(f"### [{label}] {path}\n```java\n{content[:MAX_FILE_CHARS]}\n```")
        else:
            print(f"::warning::파일 없음: {path}")

    if not collected:
        print("::error::읽을 수 있는 소스 파일이 없습니다.", file=sys.stderr)
        sys.exit(1)

    print(f"총 {len(collected)}개 파일 읽기 완료 (Controller {len(controller_paths)}개 + 참조 {len(related_paths)}개)")
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
            ["claude", "-p", prompt, "--model", CLAUDE_MODEL, "--output-format", "text"],
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
    http_method = os.environ.get("HTTP_METHOD", "").strip().upper()
    api_paths_str = os.environ.get("API_PATHS", "")
    url_hint_input = os.environ.get("URL_HINT_INPUT", "")

    if not http_method:
        print("HTTP_METHOD 환경 변수가 필요합니다. (GET/POST/PUT/DELETE/PATCH)", file=sys.stderr)
        sys.exit(1)
    if not api_paths_str:
        print("API_PATHS 환경 변수가 필요합니다.", file=sys.stderr)
        sys.exit(1)

    api_urls = [p.strip() for p in api_paths_str.split(",") if p.strip()]
    print(f"검색할 API: [{http_method}] {api_urls}")

    # 1. Controller 파일 검색 (HTTP Method + 정확한 경로 일치)
    controller_files = find_controller_files(api_urls, http_method)

    if not controller_files:
        print("::error::해당 API를 처리하는 Controller 파일을 찾을 수 없습니다.", file=sys.stderr)
        sys.exit(1)

    print(f"발견된 Controller 파일: {controller_files}")

    # 2. 관련 파일 탐색 (DTO, Service, Exception 등)
    print("[INFO] 관련 파일 탐색 중...")
    related_files = find_related_files(controller_files)

    # 3. 파일 내용 읽기
    code_content = read_source_files(controller_files, related_files)

    # 4. 프롬프트 파일 읽기
    with open(SYSTEM_PROMPT_FILE, "r") as f:
        system_prompt = f.read()
    with open(TEMPLATE_FILE, "r") as f:
        template = f.read()

    prompt = f"""{system_prompt}

다음은 {repo_name} 레포지토리 {branch} 브랜치에서 아래 API를 처리하는 코드입니다.

대상 API: [{http_method}] {', '.join(api_urls)}

{code_content}

아래 템플릿 형식으로 API 문서를 작성하세요.

{template}
"""

    # 5. Claude CLI로 문서 생성
    doc_content = call_claude(prompt)

    # 6. 결과 출력 — 첫 번째 URL에서 그룹명 추출 (/api/v1/orders → Orders)
    first_url = api_urls[0]
    segments = [s for s in first_url.strip("/").split("/")
                if s and not re.match(r"^(api|v\d+(\.\d+)?)$", s)]
    group_name = segments[0].capitalize() if segments else "API"
    title = f"[API Draft] {http_method} {group_name} API 명세"

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
