#!/usr/bin/env python3
"""
create_draft_from_code.py

REST API URL 경로로 Controller 파일을 검색하고 Claude로 문서를 생성한 뒤
Dooray Draft 페이지를 만들고 registry를 업데이트합니다.

환경 변수:
  CLAUDE_CODE_OAUTH_TOKEN       Claude CLI 인증 토큰
  REPO_NAME                     저장소 이름 (org/repo)
  BRANCH                        브랜치 이름
  HTTP_METHOD                   HTTP 메서드 (GET, POST, PUT, DELETE, PATCH)
  API_PATHS                     쉼표로 구분된 REST API URL 경로
  URL_HINT_INPUT                위키 경로 힌트 (internal/external, 선택)
  DOORAY_API_KEY                Dooray API 토큰
  DOORAY_WIKI_ID                Dooray 위키 ID
  DOORAY_PROJECT_ID             Dooray 프로젝트 ID
  DOORAY_DRAFT_PARENT_PAGE_ID   Draft 부모 페이지 ID
  CLAUDE_MODEL                  사용할 Claude 모델 (기본값: claude-opus-4-6)
  CLAUDE_TIMEOUT                Claude CLI 타임아웃 초 (기본값: 180)
"""

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
from lib.api_utils import (
    normalize_api_key, now_kst_display, now_kst_iso,
    read_registry, write_registry, set_output,
    registry_path_for, registry_rel_for,
)
from lib.dooray import create_page, delete_page
from lib.git_utils import git_commit_and_push

PROMPT_DIR = "shared-config/rest-api-docs"
SYSTEM_PROMPT_FILE = f"{PROMPT_DIR}/docs-writer.md"
TEMPLATE_FILE = f"{PROMPT_DIR}/api-docs-template.md"
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-6")
CLAUDE_TIMEOUT = int(os.environ.get("CLAUDE_TIMEOUT", "180"))
MAX_FILE_CHARS = 8000

CTRL_PATTERN = re.compile(r"(Controller|Handler|Router)\.(java|kt|go|py|ts|js)$")
CLASS_MAPPING_RE = re.compile(
    r'@RequestMapping\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?["\']([^"\']+)["\']'
)
METHOD_MAPPING_RE = re.compile(
    r'@(Get|Post|Put|Delete|Patch|Request)Mapping'
    r'(?:'
    r'\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?["\']([^"\']*)["\']'
    r'|\s*\(\s*\)'
    r'|\s*(?!\()'
    r')'
)
EXTERNAL_IMPORT_PREFIXES = (
    "java.", "javax.", "jakarta.",
    "org.springframework.", "org.slf4j.", "org.junit.", "org.mockito.",
    "lombok.", "com.fasterxml.", "io.swagger.", "io.micrometer.",
    "reactor.", "kotlin.", "kotlinx.",
)


def _normalize_path(url: str) -> str:
    url = re.sub(r"\{[^}]+\}", "{param}", url)
    return "/" + url.strip("/").lower()


def call_claude(prompt: str) -> str:
    env = {
        **os.environ,
        "HOME": os.path.expanduser("~"),
        "PYTHONIOENCODING": "utf-8",
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
    }
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--model", CLAUDE_MODEL, "--output-format", "text"],
            capture_output=True, check=True, timeout=CLAUDE_TIMEOUT,
            encoding="utf-8", errors="replace", env=env,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        err = (e.stdout or "") + (e.stderr or "")
        if "Not logged in" in err or "/login" in err:
            print("[ERROR] Claude 인증 실패. CLAUDE_CODE_OAUTH_TOKEN 확인 필요", file=sys.stderr)
        else:
            print(f"[ERROR] Claude CLI 실패 (exit {e.returncode}): {e.stderr[:300]}", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(f"[ERROR] Claude CLI 타임아웃 ({CLAUDE_TIMEOUT}s)", file=sys.stderr)
        sys.exit(1)


def extract_method_mappings(content: str) -> list:
    class_m = CLASS_MAPPING_RE.search(content)
    class_prefix = class_m.group(1).rstrip("/") if class_m else ""
    results = []
    for m in METHOD_MAPPING_RE.finditer(content):
        verb = m.group(1).upper()
        path = m.group(2) or ""
        sep = "/" if path and not path.startswith("/") else ""
        results.append((verb, class_prefix + sep + path))
    return results


def find_controller_files(api_urls: list, http_method: str) -> list:
    result = subprocess.run(
        ["grep", "-rl", "@.*Mapping",
         "--include=*.java", "--include=*.kt",
         "--include=*.go", "--include=*.py", "--include=*.ts", "--include=*.js", "."],
        capture_output=True, text=True,
    )
    candidates = [f for f in result.stdout.strip().splitlines() if CTRL_PATTERN.search(f)]
    if not candidates:
        print("[WARN] @*Mapping을 포함하는 Controller 파일이 없습니다.")
        return []

    found = set()
    for filepath in candidates:
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError:
            continue
        for input_url in api_urls:
            input_norm = _normalize_path(input_url)
            for verb, combined in extract_method_mappings(content):
                if verb == "REQUEST" or http_method.upper() == verb:
                    if _normalize_path(combined) == input_norm:
                        found.add(filepath.lstrip("./"))
                        print(f"  ✓ 매칭: {filepath} [{verb}] {combined}")
                        break
    return sorted(found)


def find_related_files(controller_paths: list) -> list:
    import_pattern = re.compile(r'import\s+([\w.]+);')
    related, seen = [], set(controller_paths)
    for ctrl in controller_paths:
        full = ctrl if os.path.exists(ctrl) else f"./{ctrl}"
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError:
            continue
        for imp in import_pattern.findall(content):
            if any(imp.startswith(p) for p in EXTERNAL_IMPORT_PREFIXES):
                continue
            fp = "src/main/java/" + imp.replace(".", "/") + ".java"
            if fp not in seen and os.path.exists(fp):
                seen.add(fp)
                related.append(fp)
    return related


def read_source_files(ctrl_paths: list, related_paths: list) -> str:
    parts = []
    for path, label in [(p, "Controller") for p in ctrl_paths] + [(p, "참조") for p in related_paths]:
        full = path if os.path.exists(path) else f"./{path}"
        if os.path.exists(full):
            with open(full, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            parts.append(f"### [{label}] {path}\n```java\n{content[:MAX_FILE_CHARS]}\n```")
    if not parts:
        print("::error::읽을 수 있는 소스 파일이 없습니다.", file=sys.stderr)
        sys.exit(1)
    return "\n\n".join(parts)


def main():
    repo_name = os.environ.get("REPO_NAME", "")
    branch = os.environ.get("BRANCH", "")
    http_method = os.environ.get("HTTP_METHOD", "").strip().upper()
    api_paths_str = os.environ.get("API_PATHS", "")
    url_hint = os.environ.get("URL_HINT_INPUT", "")
    dooray_api_key = os.environ.get("DOORAY_API_KEY", "")
    wiki_id = os.environ.get("DOORAY_WIKI_ID", "")
    project_id = os.environ.get("DOORAY_PROJECT_ID", "")
    draft_parent_id = os.environ.get("DOORAY_DRAFT_PARENT_PAGE_ID", "")
    base_url = os.environ.get("DOORAY_BASE_URL", "https://nhnent.dooray.com")
    repo_short = repo_name.split("/")[-1] if repo_name else ""

    for var, val in {
        "HTTP_METHOD": http_method, "API_PATHS": api_paths_str,
        "DOORAY_API_KEY": dooray_api_key, "DOORAY_WIKI_ID": wiki_id,
        "DOORAY_PROJECT_ID": project_id, "DOORAY_DRAFT_PARENT_PAGE_ID": draft_parent_id,
    }.items():
        if not val:
            print(f"{var} 환경 변수가 필요합니다.", file=sys.stderr)
            sys.exit(1)

    api_urls = [p.strip() for p in api_paths_str.split(",") if p.strip()]
    print(f"검색할 API: [{http_method}] {api_urls}")

    # 1. Controller 탐색
    ctrl_files = find_controller_files(api_urls, http_method)
    if not ctrl_files:
        print("::error::해당 API를 처리하는 Controller 파일을 찾을 수 없습니다.", file=sys.stderr)
        sys.exit(1)

    # 2. 관련 파일 탐색
    related = find_related_files(ctrl_files)
    code_content = read_source_files(ctrl_files, related)

    # 3. url_hint 자동 감지
    if not url_hint:
        combined = (code_content + " ".join(api_urls)).lower()
        if "internal" in combined:
            url_hint = "internal"
        elif "external" in combined:
            url_hint = "external"

    # 4. Claude로 문서 생성
    with open(SYSTEM_PROMPT_FILE, "r") as f:
        system_prompt = f.read()
    with open(TEMPLATE_FILE, "r") as f:
        template = f.read()

    prompt = f"""{system_prompt}

다음은 {repo_name} 레포지토리 {branch} 브랜치에서 [{http_method}] {', '.join(api_urls)} API를 처리하는 코드입니다.

{code_content}

아래 템플릿 형식으로 API 문서를 작성하세요.

{template}
"""
    print(f"[INFO] Claude 호출 중 (model={CLAUDE_MODEL})...")
    doc_content = call_claude(prompt)

    # 5. api_key 정규화
    api_key = normalize_api_key(http_method, api_urls[0])

    # 6. 기존 draft 있으면 삭제 후 새 draft 생성
    reg_path = registry_path_for(repo_short)
    reg_rel = registry_rel_for(repo_short)
    registry = read_registry(reg_path)

    existing = registry.get(api_key, {})
    if isinstance(existing, dict) and existing.get("draft_page_id"):
        delete_page(dooray_api_key, wiki_id, existing["draft_page_id"], base_url)

    title = f"[API Draft] {api_key}"

    full_content = (
        f"> **[Draft]** 자동 생성된 API 문서입니다. 검토 후 publish 하세요.\n"
        f"> 생성 시각: {now_kst_display()} | 위키 분류: {url_hint or '기본'}\n\n---\n\n"
        f"{doc_content}"
    )
    draft_page_id = create_page(dooray_api_key, wiki_id, draft_parent_id, title, full_content, base_url)
    page_url = f"{base_url}/wiki/{project_id}/{draft_page_id}"

    # 7. registry 갱신
    now = now_kst_iso()
    registry[api_key] = {
        **(existing if isinstance(existing, dict) else {}),
        "status": "draft",
        "draft_page_id": draft_page_id,
        "url_hint": url_hint,
        "created_at": existing.get("created_at", now) if isinstance(existing, dict) else now,
        "updated_at": now,
        "deprecated_at": None,
    }
    if not registry[api_key].get("page_id"):
        registry[api_key]["page_id"] = None

    write_registry(reg_path, registry)
    git_commit_and_push(
        "shared-config",
        [reg_rel],
        f"chore: create draft - {repo_short} {api_key} [skip ci]",
    )

    # 8. outputs
    set_output("api_key", api_key)
    set_output("draft_page_id", draft_page_id)
    set_output("page_url", page_url)
    set_output("title", title)

    print(f"\nDraft 생성 완료")
    print(f"  API Key : {api_key}")
    print(f"  제목    : {title}")
    print(f"  URL     : {page_url}")


if __name__ == "__main__":
    main()
