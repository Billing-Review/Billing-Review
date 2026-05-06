#!/usr/bin/env python3
"""
create_draft_from_code.py

이미 merge된 코드에서 문서화되지 않은 API의 Draft를 생성합니다.
PR 없이 코드를 직접 조회해 Claude로 문서를 생성합니다.

환경 변수:
  API_KEY                  레지스트리 키 (예: GET /api/v1/todos)
  REPO_NAME                서비스 저장소 이름 (org/repo)
  DOORAY_API_KEY           Dooray API 토큰
  CLAUDE_CODE_OAUTH_TOKEN  Claude CLI 인증
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
    read_service_config, build_env_url_section,
    extract_javadoc_and_params, parse_field_javadocs, format_doc_hints,
    check_javadoc_completeness,
)
from lib.dooray import create_page, delete_page
from lib.git_utils import git_commit_and_push
from lib.config import DOORAY_WIKI_ID, DOORAY_PROJECT_ID, DOORAY_DRAFT_PARENT_PAGE_ID

PROMPT_DIR = "shared-config/rest-api-docs"
SYSTEM_PROMPT_FILE = f"{PROMPT_DIR}/docs-writer.md"
TEMPLATE_FILE = f"{PROMPT_DIR}/api-docs-template.md"
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-6")
CLAUDE_TIMEOUT = int(os.environ.get("CLAUDE_TIMEOUT", "300"))
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
    url = re.sub(r"\{([^}]+)\}", lambda m: "{" + m.group(1).lower() + "}", url)
    return "/" + url.strip("/").lower()


def find_controller_file(http_method: str, path: str) -> str:
    result = subprocess.run(
        ["grep", "-rl", "@.*Mapping",
         "--include=*.java", "--include=*.kt",
         "--include=*.go", "--include=*.py", "--include=*.ts", "--include=*.js", "."],
        capture_output=True, text=True,
    )
    candidates = [f for f in result.stdout.strip().splitlines() if CTRL_PATTERN.search(f)]
    norm = _normalize_path(path)

    for filepath in candidates:
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError:
            continue
        cm = CLASS_MAPPING_RE.search(content)
        class_prefix = cm.group(1).rstrip("/") if cm else ""
        for m in METHOD_MAPPING_RE.finditer(content):
            verb = m.group(1).upper()
            if verb == "REQUEST":
                verb = "GET"
            if http_method.upper() != verb:
                continue
            mp = m.group(2) or ""
            sep = "/" if mp and not mp.startswith("/") else ""
            if _normalize_path(class_prefix + sep + mp) == norm:
                return filepath.lstrip("./")
    return ""


def extract_method_block(filepath: str, http_method: str, path: str) -> str:
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return ""

    content = "".join(lines)
    cm = CLASS_MAPPING_RE.search(content)
    class_prefix = cm.group(1).rstrip("/") if cm else ""
    norm = _normalize_path(path)

    mapping_idx = None
    for i, line in enumerate(lines):
        for m in METHOD_MAPPING_RE.finditer(line.strip()):
            verb = m.group(1).upper()
            if verb == "REQUEST":
                verb = "GET"
            mp = m.group(2) or ""
            sep = "/" if mp and not mp.startswith("/") else ""
            if verb == http_method.upper() and _normalize_path(class_prefix + sep + mp) == norm:
                mapping_idx = i
                break
        if mapping_idx is not None:
            break

    if mapping_idx is None:
        return content[:MAX_FILE_CHARS]

    start = mapping_idx
    while start > 0 and lines[start - 1].strip().startswith("@"):
        start -= 1

    depth, found, end = 0, False, start
    for i in range(start, len(lines)):
        depth += lines[i].count("{") - lines[i].count("}")
        if depth > 0:
            found = True
        if found and depth <= 0:
            end = i
            break

    header_lines = []
    for line in lines:
        header_lines.append(line)
        stripped = line.strip()
        if stripped.startswith("public class") or stripped.startswith("class "):
            header_lines.append("    // ... (other methods omitted) ...\n")
            break

    method_block = "".join(lines[start:end + 1])
    return "".join(header_lines) + "\n    " + method_block.replace("\n", "\n    ") + "\n}"


def find_related_files(ctrl_path: str) -> list:
    import_pattern = re.compile(r'import\s+([\w.]+);')
    related, seen = [], {ctrl_path}
    try:
        with open(ctrl_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        return []
    for imp in import_pattern.findall(content):
        if any(imp.startswith(p) for p in EXTERNAL_IMPORT_PREFIXES):
            continue
        fp = "src/main/java/" + imp.replace(".", "/") + ".java"
        if fp not in seen and os.path.exists(fp):
            seen.add(fp)
            related.append(fp)
    return related


def read_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()[:MAX_FILE_CHARS]
    except OSError:
        return ""


def infer_url_hint(path: str, ctrl_path: str) -> str:
    combined = (path + " " + ctrl_path).lower()
    if "internal" in combined:
        return "internal"
    if "external" in combined:
        return "external"
    return ""


def call_claude(prompt: str) -> str:
    env = {**os.environ, "HOME": os.path.expanduser("~"),
           "PYTHONIOENCODING": "utf-8", "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8"}
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
            print(f"[ERROR] Claude CLI 실패: {e.stderr[:300]}", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(f"[ERROR] Claude CLI 타임아웃 ({CLAUDE_TIMEOUT}s)", file=sys.stderr)
        sys.exit(1)


def main():
    dooray_api_key = os.environ.get("DOORAY_API_KEY", "")
    raw_api_key = os.environ.get("API_KEY", "")
    repo_name = os.environ.get("REPO_NAME", "")
    base_url = os.environ.get("DOORAY_BASE_URL", "https://api.dooray.com")
    web_url = os.environ.get("DOORAY_WEB_URL", "https://nhnent.dooray.com")

    for var, val in {
        "DOORAY_API_KEY": dooray_api_key, "API_KEY": raw_api_key, "REPO_NAME": repo_name,
    }.items():
        if not val:
            print(f"{var} 환경 변수가 필요합니다.", file=sys.stderr)
            sys.exit(1)

    parts = raw_api_key.strip().split(" ", 1)
    if len(parts) != 2:
        print(f"[ERROR] API_KEY 형식이 올바르지 않습니다. (예: GET /api/v1/todos)", file=sys.stderr)
        sys.exit(1)

    http_method, path = parts
    api_key = normalize_api_key(http_method, path)
    repo_short = repo_name.split("/")[-1]

    reg_path = registry_path_for(repo_short)
    reg_rel = registry_rel_for(repo_short)
    registry = read_registry(reg_path)
    existing = registry.get(api_key, {})

    # 기존 draft가 있으면 삭제 후 재생성
    if isinstance(existing, dict) and existing.get("draft_page_id"):
        print(f"[INFO] 기존 draft 삭제 후 재생성: {api_key}")
        delete_page(dooray_api_key, DOORAY_WIKI_ID, existing["draft_page_id"], base_url)

    # Controller 탐색
    ctrl_file = find_controller_file(http_method, path)
    if not ctrl_file:
        print(f"[ERROR] [{http_method}] {path} 를 처리하는 Controller를 찾을 수 없습니다.", file=sys.stderr)
        sys.exit(1)
    print(f"[INFO] Controller 발견: {ctrl_file}")

    # 메서드 블록 + 관련 파일 추출
    method_code = extract_method_block(ctrl_file, http_method, path)
    related = find_related_files(ctrl_file)
    code_content = f"### [Controller] {ctrl_file}\n```java\n{method_code}\n```"
    if related:
        for rp in related:
            code_content += f"\n\n### [참조] {rp}\n```java\n{read_file(rp)}\n```"

    # Javadoc 파싱
    doc_info = extract_javadoc_and_params(ctrl_file, http_method, path)
    javadoc = doc_info.get("javadoc", {})
    method_params = doc_info.get("method_params", {})

    # 주석 완성도 검증
    errors = check_javadoc_completeness(javadoc, method_params)
    if errors:
        print(f"[ERROR] [{http_method}] {path} — API 문서 주석이 불충분합니다:", file=sys.stderr)
        for e in errors:
            print(f"  • {e}", file=sys.stderr)
        print(f"\n  작성 방법: shared-workflows/rest-api-docs/javadoc-guide.md 참조", file=sys.stderr)
        sys.exit(1)

    all_field_docs = {}
    for rp in related:
        all_field_docs.update(parse_field_javadocs(rp))
    doc_hints = format_doc_hints(javadoc, method_params, all_field_docs)

    javadoc_title = javadoc.get("title", "")
    javadoc_doc_url = javadoc.get("doc_url", "")

    # url_hint 우선순위: @docUrl > registry > 추론
    url_hint = (
        javadoc_doc_url
        or (existing.get("url_hint", "") if isinstance(existing, dict) else "")
        or infer_url_hint(path, ctrl_file)
    )

    # Claude로 문서 생성
    with open(SYSTEM_PROMPT_FILE, "r") as f:
        system_prompt = f.read()
    with open(TEMPLATE_FILE, "r") as f:
        template = f.read()

    service_config = read_service_config(repo_short)
    env_url_section = build_env_url_section(service_config)
    env_url_hint = ""
    if env_url_section:
        env_url_hint = f"\n{env_url_section}\n위 서버 URL을 문서의 '서버 URL' 섹션에 반드시 포함하세요.\n"

    prompt = f"""{system_prompt}

**[중요] [{http_method}] {path} 엔드포인트 하나에 대한 API 문서만 작성하세요.**
**문서의 첫 줄(H1)은 작성하지 마세요. 개요부터 시작하세요.**

다음은 {repo_name} 레포지토리에서 [{http_method}] {path} API를 처리하는 코드입니다.
{env_url_hint}
{doc_hints}

## 소스 코드
{code_content}

아래 템플릿 형식으로 API 문서를 작성하세요.

{template}
"""
    print(f"[INFO] 문서 생성 중 (model={CLAUDE_MODEL})...")
    raw_content = call_claude(prompt)

    # H1은 프로그래밍적으로 주입 ([METHOD] /path 형식)
    body = re.sub(r'^\s*#(?!#)[^\n]+\n+', '', raw_content)
    doc_content = f"# [{http_method}] {path}\n\n{body}"

    # Draft 생성
    is_update = isinstance(existing, dict) and existing.get("status") in ("published", "deprecated")
    prefix = "[API Draft][수정]" if is_update else "[API Draft][신규]"
    draft_title = f"{prefix} {javadoc_title}" if javadoc_title else f"{prefix} {http_method} {path}"
    full_content = (
        f"> **[Draft]** 자동 생성된 API 문서입니다. 검토 후 publish 하세요.\n"
        f"> 생성 시각: {now_kst_display()} | 위키 분류: {url_hint or '기본'}\n\n---\n\n"
        f"{doc_content}"
    )

    draft_page_id = create_page(
        dooray_api_key, DOORAY_WIKI_ID, DOORAY_DRAFT_PARENT_PAGE_ID,
        draft_title, full_content, base_url,
    )
    page_url = f"{web_url}/wiki/{DOORAY_PROJECT_ID}/{draft_page_id}"
    print(f"[INFO] Draft 생성 완료: {page_url}")

    # Registry 갱신
    now = now_kst_iso()
    registry[api_key] = {
        **({} if not isinstance(existing, dict) else existing),
        "status": "draft",
        "draft_page_id": draft_page_id,
        "title": javadoc_title,
        "url_hint": url_hint,
        "created_at": existing.get("created_at", now) if isinstance(existing, dict) else now,
        "updated_at": now,
        "deprecated_at": None,
    }
    if not registry[api_key].get("page_id"):
        registry[api_key]["page_id"] = None

    write_registry(reg_path, registry)
    git_commit_and_push(
        "shared-config", [reg_rel],
        f"chore: create draft from code - {repo_short} {api_key} [skip ci]",
    )

    set_output("draft_page_id", draft_page_id)
    set_output("page_url", page_url)
    print(f"\nDraft 생성 완료")
    print(f"  API Key : {api_key}")
    print(f"  URL     : {page_url}")


if __name__ == "__main__":
    main()
