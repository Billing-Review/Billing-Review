#!/usr/bin/env python3
"""
publish_final.py

API 문서를 위키에 반영합니다.

동작 순서:
  1. registry에 api_key 있으면 → draft 내용 fetch → 위키 publish
  2. registry에 없고 Dooray draft 폴더에 있으면 → draft 내용 fetch → 위키 publish
  3. 둘 다 없으면 → 코드에서 직접 생성 → 위키 바로 publish

환경 변수:
  DOORAY_API_KEY                  Dooray API 토큰
  DOORAY_WIKI_ID                  Dooray 위키 ID
  DOORAY_PROJECT_ID               Dooray 프로젝트 ID
  DOORAY_DRAFT_PARENT_PAGE_ID     Draft 부모 페이지 ID
  DOORAY_INTERNAL_PARENT_PAGE_ID  사내 API 위키 부모 페이지 ID
  DOORAY_EXTERNAL_PARENT_PAGE_ID  사외 API 위키 부모 페이지 ID
  DOORAY_DEFAULT_PARENT_PAGE_ID   기본 위키 부모 페이지 ID
  API_KEY                         레지스트리 키 (예: GET /api/v1/todos)
  REPO_NAME                       서비스 저장소 이름 (org/repo)
  BRANCH                          코드를 읽을 브랜치 (기본값: master)
  DRAFT_PAGE_ID                   워크플로우 내부 전달용 (사용자 입력 불필요)
  CLAUDE_CODE_OAUTH_TOKEN         Claude CLI 인증 토큰
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
from lib.dooray import (
    create_page, delete_page, get_child_pages, get_page,
    get_or_create_child_page, update_page,
)
from lib.git_utils import git_commit_and_push

PROMPT_DIR = "shared-config/rest-api-docs"
SYSTEM_PROMPT_FILE = f"{PROMPT_DIR}/docs-writer.md"
TEMPLATE_FILE = f"{PROMPT_DIR}/api-docs-template.md"
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
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
_DRAFT_META_RE = re.compile(
    r'^> \*\*\[Draft\]\*\*.*\n> 생성 시각:.*\n\n---\n\n',
    re.MULTILINE,
)


# ── 코드 기반 문서 생성 ───────────────────────────────────────────────────────

def _normalize_path(url: str) -> str:
    url = re.sub(r"\{([^}]+)\}", lambda m: "{" + m.group(1).lower() + "}", url)
    return "/" + url.strip("/").lower()


def find_controller_files(http_method: str, path: str) -> list:
    result = subprocess.run(
        ["grep", "-rl", "@.*Mapping",
         "--include=*.java", "--include=*.kt",
         "--include=*.go", "--include=*.py", "--include=*.ts", "--include=*.js", "."],
        capture_output=True, text=True,
    )
    candidates = [f for f in result.stdout.strip().splitlines() if CTRL_PATTERN.search(f)]
    norm = _normalize_path(path)
    found = set()
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
            if verb != "REQUEST" and http_method.upper() != verb:
                continue
            mp = m.group(2) or ""
            sep = "/" if mp and not mp.startswith("/") else ""
            if _normalize_path(class_prefix + sep + mp) == norm:
                found.add(filepath.lstrip("./"))
    return sorted(found)


def find_related_files(ctrl_paths: list) -> list:
    import_pattern = re.compile(r'import\s+([\w.]+);')
    related, seen = [], set(ctrl_paths)
    for ctrl in ctrl_paths:
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
    return "\n\n".join(parts)


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
        print(f"[ERROR] Claude CLI 실패: {e.stderr[:300]}", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(f"[ERROR] Claude CLI 타임아웃 ({CLAUDE_TIMEOUT}s)", file=sys.stderr)
        sys.exit(1)


def generate_from_code(http_method: str, path: str, repo_name: str, branch: str) -> tuple:
    """코드에서 문서 생성 → (content, url_hint) 반환."""
    ctrl_files = find_controller_files(http_method, path)
    if not ctrl_files:
        print(f"[ERROR] [{http_method}] {path} 를 처리하는 Controller를 찾을 수 없습니다.", file=sys.stderr)
        sys.exit(1)

    related = find_related_files(ctrl_files)
    code_content = read_source_files(ctrl_files, related)

    url_hint = ""
    combined = (code_content + path).lower()
    if "internal" in combined:
        url_hint = "internal"
    elif "external" in combined:
        url_hint = "external"

    with open(SYSTEM_PROMPT_FILE, "r") as f:
        system_prompt = f.read()
    with open(TEMPLATE_FILE, "r") as f:
        template = f.read()

    prompt = f"""{system_prompt}

다음은 {repo_name} 레포지토리 {branch} 브랜치에서 [{http_method}] {path} API를 처리하는 코드입니다.

{code_content}

아래 템플릿 형식으로 API 문서를 작성하세요.

{template}
"""
    print(f"[INFO] 코드에서 문서 생성 중 (model={CLAUDE_MODEL})...")
    doc = call_claude(prompt)
    return doc, url_hint


# ── Dooray / 위키 헬퍼 ────────────────────────────────────────────────────────

def strip_draft_meta(content: str) -> str:
    return _DRAFT_META_RE.sub("", content)


def get_category_parent(url_hint: str) -> str:
    if url_hint == "internal":
        parent = os.environ.get("DOORAY_INTERNAL_PARENT_PAGE_ID", "")
    elif url_hint == "external":
        parent = os.environ.get("DOORAY_EXTERNAL_PARENT_PAGE_ID", "")
    else:
        parent = os.environ.get("DOORAY_DEFAULT_PARENT_PAGE_ID", "")
    parent = parent or os.environ.get("DOORAY_DEFAULT_PARENT_PAGE_ID", "")
    if not parent:
        print("[ERROR] 본 페이지 부모 ID를 찾을 수 없습니다.", file=sys.stderr)
        sys.exit(1)
    return parent


def find_draft_in_dooray(dooray_api_key: str, wiki_id: str,
                          draft_parent_id: str, base_url: str, api_key: str) -> str:
    if not draft_parent_id:
        return ""
    children = get_child_pages(dooray_api_key, wiki_id, draft_parent_id, base_url)
    norm_path = api_key.split(" ", 1)[-1].lower()
    for child in children:
        if norm_path in child.get("subject", "").lower():
            page_id = child.get("id", "")
            print(f"[INFO] Dooray draft 발견: {child.get('subject')} (id={page_id})")
            return page_id
    return ""


def prepend_history(existing_content: str, api_key: str) -> str:
    history_line = f"> 수정: `{api_key}` ({now_kst_display()})\n"
    if existing_content.startswith("> 수정:"):
        return history_line + existing_content
    return history_line + "\n" + existing_content


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    dooray_api_key = os.environ.get("DOORAY_API_KEY", "")
    wiki_id = os.environ.get("DOORAY_WIKI_ID", "")
    project_id = os.environ.get("DOORAY_PROJECT_ID", "")
    draft_parent_id = os.environ.get("DOORAY_DRAFT_PARENT_PAGE_ID", "")
    base_url = os.environ.get("DOORAY_BASE_URL", "https://api.dooray.com")
    web_url = os.environ.get("DOORAY_WEB_URL", "https://nhnent.dooray.com")
    raw_api_key = os.environ.get("API_KEY", "")
    repo_name = os.environ.get("REPO_NAME", "")
    branch = os.environ.get("BRANCH", "master")
    repo_short = repo_name.split("/")[-1] if repo_name else ""
    fallback_draft_page_id = os.environ.get("DRAFT_PAGE_ID", "")

    for var, val in {
        "DOORAY_API_KEY": dooray_api_key, "DOORAY_WIKI_ID": wiki_id,
        "DOORAY_PROJECT_ID": project_id, "API_KEY": raw_api_key, "REPO_NAME": repo_name,
    }.items():
        if not val:
            print(f"{var} 환경 변수가 필요합니다.", file=sys.stderr)
            sys.exit(1)

    # api_key 정규화
    parts = raw_api_key.strip().split(" ", 1)
    api_key = normalize_api_key(parts[0], parts[1]) if len(parts) == 2 else raw_api_key
    if api_key != raw_api_key:
        print(f"[INFO] API Key 정규화: '{raw_api_key}' → '{api_key}'")

    reg_path = registry_path_for(repo_short)
    reg_rel = registry_rel_for(repo_short)
    registry = read_registry(reg_path)
    entry = registry.get(api_key, {}) if isinstance(registry.get(api_key), dict) else {}

    # ── 콘텐츠 소스 결정 ─────────────────────────────────────────────────────
    draft_page_id = entry.get("draft_page_id") or fallback_draft_page_id
    generated_content = None  # None이면 draft에서 fetch, str이면 직접 사용

    if draft_page_id:
        print(f"[INFO] draft 페이지 사용: {draft_page_id}")
    else:
        # Dooray draft 폴더에서 탐색
        draft_page_id = find_draft_in_dooray(dooray_api_key, wiki_id, draft_parent_id, base_url, api_key)

    if not draft_page_id:
        # 코드에서 직접 생성
        print(f"[INFO] draft 없음 — 코드에서 직접 생성합니다.")
        method, path = (parts[0], parts[1]) if len(parts) == 2 else ("GET", api_key)
        generated_content, url_hint = generate_from_code(method, path, repo_name, branch)
    else:
        url_hint = entry.get("url_hint", "")

    # ── 콘텐츠 준비 ──────────────────────────────────────────────────────────
    if generated_content is not None:
        clean_content = generated_content
        publish_title = api_key
    else:
        draft_title, draft_content = get_page(dooray_api_key, wiki_id, draft_page_id, base_url)
        publish_title = re.sub(r"^\[API Draft\](\[수정\]|\[신규\])?\s*", "", draft_title).strip()
        clean_content = strip_draft_meta(draft_content)

    existing_page_id = entry.get("page_id")

    # ── 위키 페이지 생성/업데이트 ─────────────────────────────────────────────
    if existing_page_id:
        _, existing_content = get_page(dooray_api_key, wiki_id, existing_page_id, base_url)
        new_content = prepend_history(existing_content, api_key) + "\n\n---\n\n" + clean_content
        update_page(dooray_api_key, wiki_id, existing_page_id, publish_title, new_content, base_url)
        final_page_id = existing_page_id
        action = "updated"
    else:
        category_parent = get_category_parent(url_hint)
        repo_page_id = get_or_create_child_page(
            dooray_api_key, wiki_id, category_parent, repo_short, base_url
        )
        final_page_id = create_page(
            dooray_api_key, wiki_id, repo_page_id, publish_title, clean_content, base_url
        )
        action = "created"

    if not final_page_id:
        print("[ERROR] 페이지 ID를 가져올 수 없습니다.", file=sys.stderr)
        sys.exit(1)

    # ── registry 갱신 ─────────────────────────────────────────────────────────
    now = now_kst_iso()
    registry[api_key] = {
        **entry,
        "status": "published",
        "page_id": final_page_id,
        "draft_page_id": None,
        "url_hint": url_hint,
        "created_at": entry.get("created_at", now) or now,
        "updated_at": now,
        "deprecated_at": entry.get("deprecated_at"),
    }
    write_registry(reg_path, registry)
    git_commit_and_push(
        "shared-config", [reg_rel],
        f"chore: publish api doc - {repo_short} {api_key} [skip ci]",
    )

    # draft 페이지 삭제 (코드 직접 생성인 경우 draft 없으므로 스킵)
    if draft_page_id and generated_content is None:
        delete_page(dooray_api_key, wiki_id, draft_page_id, base_url)

    page_url = f"{web_url}/wiki/{project_id}/{final_page_id}"
    set_output("page_id", final_page_id)
    set_output("page_url", page_url)

    print(f"\n위키 반영 완료 ({action})")
    print(f"  repo    : {repo_name}")
    print(f"  API Key : {api_key}")
    print(f"  제목    : {publish_title}")
    print(f"  URL     : {page_url}")


if __name__ == "__main__":
    main()
