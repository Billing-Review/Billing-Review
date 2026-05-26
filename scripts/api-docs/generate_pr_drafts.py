#!/usr/bin/env python3
"""
generate_pr_drafts.py

PR diff에서 변경된 API를 감지하고 각 API별 Dooray Draft 페이지를 생성합니다.
삭제된 API는 @Deprecated 처리합니다.
완료 후 PR comment로 draft 링크를 게시합니다.

환경 변수:
  GH_TOKEN                  GitHub 인증 토큰
  CLAUDE_CODE_OAUTH_TOKEN   Claude CLI 인증 토큰
  PR_NUMBER                 PR 번호
  REPO_NAME                 저장소 이름 (org/repo)
  DOORAY_API_KEY            Dooray API 토큰
  DOORAY_WIKI_ID            Dooray 위키 ID
  DOORAY_PROJECT_ID         Dooray 프로젝트 ID
  DOORAY_DRAFT_PARENT_PAGE_ID  Draft 부모 페이지 ID
  CLAUDE_MODEL              사용할 Claude 모델 (기본값: claude-opus-4-6)
  CLAUDE_TIMEOUT            Claude CLI 타임아웃 초 (기본값: 180)
"""

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
from lib.api_utils import (
    normalize_api_key, now_kst_display, now_kst_iso, today_kst,
    read_service_config, read_full_service_config, build_env_url_section,
    read_registry, write_registry, registry_path_for, registry_rel_for,
    extract_javadoc_and_params, parse_field_javadocs, format_doc_hints,
    check_javadoc_completeness, build_doc_header, REVIEW_CHECKLIST,
    strip_pre_h2, parse_enum_constants, build_diff_block,
    find_group_for_controller, apply_gateway_transform, resolve_environments,
)
from lib.dooray import create_page, delete_page, get_page, update_page
from lib.git_utils import git_commit_and_push
from lib.config import (
    DOORAY_WIKI_ID, DOORAY_PROJECT_ID, DOORAY_DRAFT_PARENT_PAGE_ID,
)

PROMPT_DIR = "shared-config/rest-api-docs"
SYSTEM_PROMPT_FILE = f"{PROMPT_DIR}/docs-writer.md"
TEMPLATE_FILE = f"{PROMPT_DIR}/api-docs-template.md"
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-6")
CLAUDE_TIMEOUT = int(os.environ.get("CLAUDE_TIMEOUT", "180"))
MAX_DIFF_LENGTH = 15000
MAX_FILE_CHARS = 8000

_CLASS_MAPPING_RE = re.compile(
    r'@RequestMapping\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?["\']([^"\']+)["\']'
)
# 메서드 레벨 매핑만 — @RequestMapping 은 클래스 레벨 전용으로 가정 (Spring 컨벤션)
_METHOD_MAPPING_RE = re.compile(
    r'@(Get|Post|Put|Delete|Patch)Mapping'
    r'(?:'
    r'\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?["\']([^"\']*)["\']'
    r'|\s*\(\s*\)'
    r'|\s*(?!\()'
    r')'
)
CTRL_PATTERN = re.compile(r"(Controller|Handler|Router)\.(java|kt|go|py|ts|js)$")
EXTERNAL_IMPORT_PREFIXES = (
    "java.", "javax.", "jakarta.",
    "org.springframework.", "org.slf4j.", "org.junit.", "org.mockito.",
    "lombok.", "com.fasterxml.", "io.swagger.", "io.micrometer.",
    "reactor.", "kotlin.", "kotlinx.",
)


# ── GitHub / Claude helpers ──────────────────────────────────────────────────

def get_pr_diff(pr_number: str, repo_name: str) -> str:
    result = subprocess.run(
        ["gh", "pr", "diff", pr_number, "--repo", repo_name],
        capture_output=True, text=True, env={**os.environ},
    )
    if result.returncode != 0:
        print(f"gh pr diff 실패: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout


def get_pr_metadata(pr_number: str, repo_name: str) -> tuple:
    result = subprocess.run(
        ["gh", "pr", "view", pr_number, "--repo", repo_name,
         "--json", "title,body,headRefName"],
        capture_output=True, text=True, env={**os.environ},
    )
    if result.returncode != 0:
        return "", "", ""
    data = json.loads(result.stdout)
    return data.get("title", ""), data.get("body", "") or "", data.get("headRefName", "")


def post_pr_comment(pr_number: str, repo_name: str, body: str):
    subprocess.run(
        ["gh", "pr", "comment", pr_number, "--repo", repo_name, "--body", body],
        env={**os.environ},
    )


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


# ── diff 파싱 ─────────────────────────────────────────────────────────────────

def get_class_prefix(filepath: str) -> str:
    if not os.path.exists(filepath):
        return ""
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    m = _CLASS_MAPPING_RE.search(content)
    return m.group(1).rstrip("/") if m else ""


def extract_mappings_from_text(text: str, class_prefix: str) -> list:
    results = []
    for mm in _METHOD_MAPPING_RE.finditer(text):
        verb = mm.group(1).upper()
        path = mm.group(2) or ""
        sep = "/" if path and not path.startswith("/") else ""
        full_path = class_prefix + sep + path
        if full_path:
            results.append((verb, full_path))
    return results


def get_all_apis_in_file(filepath: str) -> list:
    """Controller 파일의 모든 API 목록 반환 [(verb, full_path), ...]"""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        return []
    class_m = _CLASS_MAPPING_RE.search(content)
    class_prefix = class_m.group(1).rstrip("/") if class_m else ""
    return extract_mappings_from_text(content, class_prefix)


def get_method_line_range(filepath: str, http_method: str, target_path: str) -> tuple:
    """해당 API 메서드 블록의 라인 범위 반환 (1-indexed). 없으면 (-1, -1)"""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return -1, -1

    content = "".join(lines)
    class_m = _CLASS_MAPPING_RE.search(content)
    class_prefix = class_m.group(1).rstrip("/") if class_m else ""
    norm_target = _normalize_path(target_path)

    mapping_idx = None
    for i, line in enumerate(lines):
        for verb, full_path in extract_mappings_from_text(line.strip(), class_prefix):
            if verb.upper() == http_method.upper() and _normalize_path(full_path) == norm_target:
                mapping_idx = i
                break
        if mapping_idx is not None:
            break

    if mapping_idx is None:
        return -1, -1

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

    return start + 1, end + 1  # 1-indexed


def get_changed_line_ranges(section: str) -> list:
    """diff section의 @@ 헝크에서 변경 라인 범위 반환 (새 파일 기준, 1-indexed)"""
    ranges = []
    hunk_re = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', re.MULTILINE)
    for m in hunk_re.finditer(section):
        start = int(m.group(1))
        count = int(m.group(2)) if m.group(2) is not None else 1
        if count > 0:
            ranges.append((start, start + count - 1))
    return ranges


def parse_diff(full_diff: str) -> tuple:
    """diff → (changed: list[dict], deleted: list[dict])"""
    changed, deleted = [], []
    seen_changed, seen_deleted = set(), set()

    sections = re.split(r"(?=^diff --git )", full_diff, flags=re.MULTILINE)
    for section in sections:
        file_m = re.search(r"^diff --git a/(.+) b/", section, re.MULTILINE)
        if not file_m:
            continue
        filepath = file_m.group(1)
        if not CTRL_PATTERN.search(filepath):
            continue

        class_prefix = get_class_prefix(filepath)

        # 1) 어노테이션 변경 감지
        for line in section.splitlines():
            if not (line.startswith("+") or line.startswith("-")):
                continue
            sign, text = line[0], line[1:]
            for verb, path in extract_mappings_from_text(text, class_prefix):
                key = normalize_api_key(verb, path)
                if sign == "+" and key not in seen_changed:
                    changed.append({"method": verb, "path": path, "file": filepath})
                    seen_changed.add(key)
                elif sign == "-" and key not in seen_deleted:
                    deleted.append({"method": verb, "path": path})
                    seen_deleted.add(key)

        # 2) 메서드 바디 변경 감지 (어노테이션 변경 없는 API)
        if not os.path.exists(filepath):
            continue
        changed_ranges = get_changed_line_ranges(section)
        if not changed_ranges:
            continue
        for verb, path in get_all_apis_in_file(filepath):
            key = normalize_api_key(verb, path)
            if key in seen_changed:
                continue
            m_start, m_end = get_method_line_range(filepath, verb, path)
            if m_start == -1:
                continue
            if any(m_start <= r_end and r_start <= m_end for r_start, r_end in changed_ranges):
                changed.append({"method": verb, "path": path, "file": filepath})
                seen_changed.add(key)
                print(f"[INFO] 메서드 바디 변경 감지: {key}")

    # +와 - 모두 있으면 수정(changed)이므로 deleted에서 제거
    deleted = [d for d in deleted
               if normalize_api_key(d["method"], d["path"]) not in seen_changed]
    return changed, deleted


def filter_diff_for_file(full_diff: str, filepath: str) -> str:
    sections = re.split(r"(?=^diff --git )", full_diff, flags=re.MULTILINE)
    for section in sections:
        if f"diff --git a/{filepath}" in section or f"b/{filepath}" in section:
            return section
    return ""


# ── Controller 파일 탐색 ──────────────────────────────────────────────────────

def _normalize_path(url: str) -> str:
    url = re.sub(r"\{([^}]+)\}", lambda m: "{" + m.group(1).lower() + "}", url)
    return "/" + url.strip("/").lower()


def extract_method_for_api(filepath: str, http_method: str, target_path: str) -> str:
    """컨트롤러에서 특정 API 메서드 블록만 추출 (클래스 헤더 포함)."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        return content[:MAX_FILE_CHARS] if content else ""

    lines = content.splitlines()
    class_m = _CLASS_MAPPING_RE.search(content)
    class_prefix = class_m.group(1).rstrip("/") if class_m else ""
    norm_target = _normalize_path(target_path)

    # 대상 @*Mapping 어노테이션 라인 탐색
    mapping_idx = None
    for i, line in enumerate(lines):
        for verb, full_path in extract_mappings_from_text(line.strip(), class_prefix):
            if verb.upper() == http_method.upper() and _normalize_path(full_path) == norm_target:
                mapping_idx = i
                break
        if mapping_idx is not None:
            break

    if mapping_idx is None:
        return content[:MAX_FILE_CHARS]

    # 앞쪽 @ 어노테이션까지 포함
    start = mapping_idx
    while start > 0 and lines[start - 1].strip().startswith("@"):
        start -= 1

    # 중괄호 카운팅으로 메서드 끝 탐색
    depth, found, end = 0, False, start
    for i in range(start, len(lines)):
        depth += lines[i].count("{") - lines[i].count("}")
        if depth > 0:
            found = True
        if found and depth <= 0:
            end = i
            break

    method_block = "\n".join(lines[start:end + 1])

    # 클래스 헤더 (package + imports + 클래스 선언까지)
    header_lines = []
    for line in lines:
        header_lines.append(line)
        stripped = line.strip()
        if stripped.startswith("public class") or stripped.startswith("class "):
            header_lines.append("    // ... (other methods omitted) ...")
            break

    return "\n".join(header_lines) + "\n\n    " + method_block.replace("\n", "\n    ") + "\n}"


MAX_RELATED_FILES = 30
MAX_RELATED_DEPTH = 3


def find_related_files(controller_paths: list) -> list:
    """컨트롤러에서 시작해 import 를 따라가며 관련 .java 파일을 BFS 수집.

    DTO 안의 enum / nested DTO 까지 잡기 위해 max_depth 단계까지 추적한다.
    외부 라이브러리(spring 등) 와 self는 스킵하고, 파일 수는 cap 한다.
    """
    import_pattern = re.compile(r'import\s+([\w.]+);')
    seen = set(controller_paths)
    related = []
    queue = [(p, 0) for p in controller_paths]

    while queue and len(related) < MAX_RELATED_FILES:
        path, depth = queue.pop(0)
        full = path if os.path.exists(path) else f"./{path}"
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError:
            continue
        if depth >= MAX_RELATED_DEPTH:
            continue
        for imp in import_pattern.findall(content):
            if any(imp.startswith(p) for p in EXTERNAL_IMPORT_PREFIXES):
                continue
            file_path = "src/main/java/" + imp.replace(".", "/") + ".java"
            if file_path in seen or not os.path.exists(file_path):
                continue
            seen.add(file_path)
            related.append(file_path)
            queue.append((file_path, depth + 1))
            if len(related) >= MAX_RELATED_FILES:
                break
    return related


def read_files(paths: list, label: str = "") -> str:
    parts = []
    for path in paths:
        full = path if os.path.exists(path) else f"./{path}"
        if os.path.exists(full):
            with open(full, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            parts.append(f"### [{label or path}] {path}\n```java\n{content[:MAX_FILE_CHARS]}\n```")
    return "\n\n".join(parts)


# ── 문서 생성 ─────────────────────────────────────────────────────────────────

def infer_url_hint(path: str, code_content: str) -> str:
    combined = (path + " " + code_content).lower()
    if "internal" in combined:
        return "internal"
    if "external" in combined:
        return "external"
    return ""


def generate_doc(method: str, path: str, ctrl_file: str, full_diff: str,
                 pr_title: str, pr_body: str, existing_doc: str,
                 system_prompt: str, template: str,
                 service_config=None, prev_doc: str = "",
                 full_service_config=None, registry_entry=None) -> tuple:
    method_code = extract_method_for_api(ctrl_file, method, path)
    related = find_related_files([ctrl_file])
    code_content = f"### [Controller] {ctrl_file}\n```java\n{method_code}\n```"
    if related:
        code_content += "\n\n" + read_files(related, "참조")
    file_diff = filter_diff_for_file(full_diff, ctrl_file)

    # Javadoc 파싱
    doc_info = extract_javadoc_and_params(ctrl_file, method, path)
    javadoc = doc_info.get("javadoc", {})
    method_params = doc_info.get("method_params", {})

    # 주석 완성도 검증 — 누락 시 Actions 실패
    errors = check_javadoc_completeness(javadoc, method_params)
    if errors:
        print(f"[ERROR] [{method}] {path} — API 문서 주석이 불충분합니다:", file=sys.stderr)
        for e in errors:
            print(f"  • {e}", file=sys.stderr)
        print(f"  작성 방법: shared-workflows/rest-api-docs/javadoc-guide.md 참조", file=sys.stderr)
        sys.exit(1)

    all_field_docs = {}
    all_enums = {}
    for rp in related:
        all_field_docs.update(parse_field_javadocs(rp))
        all_enums.update(parse_enum_constants(rp))
    doc_hints = format_doc_hints(javadoc, method_params, all_field_docs, all_enums)

    javadoc_doc_url = javadoc.get("doc_url", "")
    javadoc_title = javadoc.get("title", "")

    # 게이트웨이 group 매칭 → 환경 URL / 외부 URL 계산
    repo_cfg = service_config or {}
    full_cfg = full_service_config or {}
    group = find_group_for_controller(ctrl_file, repo_cfg)
    envs = resolve_environments(repo_cfg, full_cfg, group)
    env_source = "service-config" if envs else None
    # fallback: 이전 publish 본문에서 추출된 registry.domains 사용
    if not envs and isinstance(registry_entry, dict):
        reg_domains = registry_entry.get("domains") or {}
        if reg_domains:
            envs = reg_domains
            env_source = "registry(이전 published 본문에서 자동 추출)"
    external_path = apply_gateway_transform(path, group)
    env_url_section = build_env_url_section(envs)

    env_url_hint = ""
    if env_url_section:
        env_url_hint = (
            f"\n{env_url_section}\n"
            f"위 서버 URL을 문서의 '서버 URL' / 'Domain' 섹션에 반드시 포함하세요.\n"
        )
        if env_source:
            env_url_hint += f"_({env_source} 기준)_\n"
    else:
        env_url_hint = (
            "\n**[서버 URL 미정]** service-config 와 registry 모두 도메인 정보가 없습니다.\n"
            "문서의 'Domain' 표는 URL 셀을 빈 채로 두세요. 검토자가 직접 채워 publish 하면\n"
            "다음 Draft 부터 registry 가 자동으로 기억합니다.\n"
        )
    if group and external_path != path:
        env_url_hint += (
            f"\n**[게이트웨이 경로 변환]** 이 API 는 게이트웨이를 통해 외부에 노출됩니다.\n"
            f"- 컨트롤러 내부 path : `{path}`\n"
            f"- 외부 호출 path     : `{external_path}`\n"
            f"문서의 `API Info > Path` 와 모든 예시 URL 에는 **외부 path (`{external_path}`)** 를 사용하세요.\n"
        )

    ref_section = ""
    if prev_doc:
        ref_section = f"""
## 이전 버전 문서 (URL이 변경된 API — 변경사항을 반영해 새 문서를 작성하세요)

{prev_doc[:3000]}
"""
    elif existing_doc:
        ref_section = f"""
## 기존 문서 (이미 등록된 API — 수정사항을 반영해 업데이트하세요)

{existing_doc[:3000]}
"""

    prompt = f"""{system_prompt}

**[중요] [{method}] {path} 엔드포인트 하나에 대한 API 문서만 작성하세요. 같은 컨트롤러의 다른 엔드포인트는 포함하지 마세요.**
**문서의 출력은 반드시 `## Description` 으로 시작해야 합니다.**
**H1, 인사말, "코드 분석이 완료되었습니다" 같은 사전 멘트를 어떤 경우에도 출력하지 마세요. 어떠한 설명·서론도 없이 곧바로 `## Description` 헤더부터 시작합니다.**

다음은 [{method}] {path} API에 대한 코드와 PR 변경사항입니다.

PR 제목: {pr_title}
PR 설명: {pr_body[:1000] if pr_body else "(없음)"}
{env_url_hint}
{doc_hints}

## 소스 코드
{code_content}

## PR diff (해당 파일)
```diff
{file_diff[:MAX_DIFF_LENGTH]}
```
{ref_section}
아래 템플릿 형식으로 API 문서를 작성하세요.

{template}
"""
    raw_content = call_claude(prompt)

    # 첫 H2(`## `) 이전의 모든 텍스트(서두/H1/부제/Claude 멘트 등) 제거.
    # 시스템이 헤더(H1)를 주입한다. footer 는 호출부에서 신규/수정에 따라 분기.
    body = strip_pre_h2(raw_content)
    header = build_doc_header(method, path, javadoc_title, javadoc_doc_url)
    doc_content = f"{header}{body}"

    return doc_content, javadoc_doc_url, javadoc_title


# ── Dooray draft 생성 ─────────────────────────────────────────────────────────

def create_draft(dooray_api_key: str, wiki_id: str, draft_parent_id: str,
                 base_url: str, web_url: str, project_id: str,
                 api_key: str, title: str, doc_content: str, url_hint: str,
                 registry: dict) -> str:
    # 기존 draft가 있으면 삭제
    existing = registry.get(api_key, {})
    if isinstance(existing, dict) and existing.get("draft_page_id"):
        delete_page(dooray_api_key, wiki_id, existing["draft_page_id"], base_url)

    full_content = (
        f"> **[Draft]** 자동 생성된 API 문서입니다. 검토 후 publish 하세요.\n"
        f"> 생성 시각: {now_kst_display()} | 위키 분류: {url_hint or '기본'}\n\n---\n\n"
        f"{doc_content}"
    )

    page_id = create_page(dooray_api_key, wiki_id, draft_parent_id, title, full_content, base_url)
    page_url = f"{web_url}/wiki/{project_id}/{page_id}"
    print(f"[INFO] Draft 생성: {api_key} → {page_url}")
    return page_id, page_url


# ── @Deprecated 처리 ─────────────────────────────────────────────────────────

def handle_deprecated(dooray_api_key: str, wiki_id: str, base_url: str,
                      api_key: str, registry: dict) -> tuple:
    """API를 deprecated 처리하고 (성공여부, 이전페이지내용) 반환."""
    entry = registry.get(api_key)
    if not entry:
        print(f"[INFO] registry 미등록, deprecated 스킵: {api_key}")
        return False, ""
    if isinstance(entry, dict):
        if entry.get("status") == "deprecated":
            print(f"[INFO] 이미 deprecated: {api_key}")
            return False, ""
        page_id = entry.get("page_id", "")
    else:
        page_id = str(entry)

    if not page_id:
        return False, ""

    today = today_kst()
    try:
        title, content = get_page(dooray_api_key, wiki_id, page_id, base_url)
        content = content.replace("\r\n", "\n")
        prev_content = content  # URL 변경 시 신규 draft 생성에 참조

        if "@Deprecated(" not in content:
            new_content = f"### @Deprecated({today})\n\n" + content
            update_page(dooray_api_key, wiki_id, page_id, title, new_content, base_url)

        registry[api_key] = {
            **(entry if isinstance(entry, dict) else {"page_id": page_id}),
            "status": "deprecated",
            "deprecated_at": today,
        }
        return True, prev_content
    except Exception as e:
        print(f"[WARN] deprecated 처리 실패 {api_key}: {e}")
        return False, ""


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    pr_number = os.environ.get("PR_NUMBER", "")
    repo_name = os.environ.get("REPO_NAME", "")
    # MODE: "draft"=draft생성, "deprecated"=삭제처리, "all"=draft생성+삭제처리, "delete_draft"=draft삭제
    mode = os.environ.get("GENERATE_MODE", "all").lower()
    dooray_api_key = os.environ.get("DOORAY_API_KEY", "")
    wiki_id = DOORAY_WIKI_ID
    project_id = DOORAY_PROJECT_ID
    draft_parent_id = DOORAY_DRAFT_PARENT_PAGE_ID
    base_url = os.environ.get("DOORAY_BASE_URL", "https://api.dooray.com")
    web_url = os.environ.get("DOORAY_WEB_URL", "https://nhnent.dooray.com")
    repo_short = repo_name.split("/")[-1] if repo_name else ""

    for var, val in {
        "PR_NUMBER": pr_number, "REPO_NAME": repo_name,
        "DOORAY_API_KEY": dooray_api_key,
    }.items():
        if not val:
            print(f"{var} 환경 변수가 필요합니다.", file=sys.stderr)
            sys.exit(1)

    full_diff = get_pr_diff(pr_number, repo_name)
    changed, deleted = parse_diff(full_diff)

    if not changed and not deleted:
        print("::notice::Controller 변경사항 없음 — 스킵")
        return

    # ── delete_draft 모드: PR close(미merge) 시 draft 삭제 ───────────────────
    if mode == "delete_draft":
        deleted_drafts = []
        for api in changed:
            api_key = normalize_api_key(api["method"], api["path"])
            entry = registry.get(api_key, {})
            draft_id = entry.get("draft_page_id") if isinstance(entry, dict) else None
            if draft_id:
                delete_page(dooray_api_key, wiki_id, draft_id, base_url)
                registry[api_key] = {**entry, "draft_page_id": None,
                                     "status": entry.get("status", "draft")}
                deleted_drafts.append(api_key)
                print(f"[INFO] Draft 삭제: {api_key}")
        if deleted_drafts:
            write_registry(reg_path, registry)
            git_commit_and_push(
                "shared-config", [reg_rel],
                f"chore: pr#{pr_number} draft 삭제 (PR closed) - {repo_short} [skip ci]",
            )
            post_pr_comment(pr_number, repo_name,
                "## API 문서 Draft 삭제 완료\n\n"
                "PR이 merge 없이 닫혀 아래 Draft가 삭제되었습니다.\n\n"
                + "\n".join(f"- `{k}`" for k in deleted_drafts))
        else:
            print("삭제할 draft 없음")
        return

    # mode 필터
    if mode == "draft":
        deleted = []
    elif mode == "deprecated":
        changed = []

    pr_title, pr_body, _ = get_pr_metadata(pr_number, repo_name)

    with open(SYSTEM_PROMPT_FILE, "r") as f:
        system_prompt = f.read()
    with open(TEMPLATE_FILE, "r") as f:
        template = f.read()

    reg_path = registry_path_for(repo_short)
    reg_rel = registry_rel_for(repo_short)
    registry = read_registry(reg_path)
    full_service_config = read_full_service_config()
    service_config = full_service_config.get(repo_short, {})

    draft_links = []

    # ── 삭제된 API 먼저 deprecated 처리 (이전 문서 수집 → URL 변경 감지용) ──
    deprecated_list = []
    prev_docs_by_file = {}  # {ctrl_file: prev_doc_content} — URL 변경 시 참조
    for api in deleted:
        api_key = normalize_api_key(api["method"], api["path"])
        ok, prev_content = handle_deprecated(dooray_api_key, wiki_id, base_url, api_key, registry)
        if ok:
            deprecated_list.append(api_key)
            if prev_content and api.get("file"):
                prev_docs_by_file[api["file"]] = prev_content

    # ── 변경/신규 API: draft 생성 ─────────────────────────────────────────
    for api in changed:
        method, path, ctrl_file = api["method"], api["path"], api["file"]
        api_key = normalize_api_key(method, path)

        existing_entry = registry.get(api_key, {})
        existing_doc = ""
        if isinstance(existing_entry, dict) and existing_entry.get("page_id"):
            try:
                _, existing_doc = get_page(
                    dooray_api_key, wiki_id, existing_entry["page_id"], base_url
                )
            except Exception:
                existing_doc = ""

        # URL 변경 감지: 같은 파일에서 deprecated된 API가 있으면 이전 문서를 참조
        prev_doc = prev_docs_by_file.get(ctrl_file, "")

        print(f"[INFO] 문서 생성 중: {api_key}")
        doc_content, javadoc_doc_url, javadoc_title = generate_doc(
            method, path, ctrl_file, full_diff,
            pr_title, pr_body, existing_doc,
            system_prompt, template,
            service_config=service_config,
            prev_doc=prev_doc,
            full_service_config=full_service_config,
            registry_entry=existing_entry,
        )

        # url_hint 우선순위: @docUrl > registry > 추론
        url_hint = (
            javadoc_doc_url
            or (existing_entry.get("url_hint", "") if isinstance(existing_entry, dict) else "")
            or infer_url_hint(path, ctrl_file)
        )

        # 한 번이라도 publish 됐으면 (= page_id 존재) 수정 케이스로 본다.
        # status 는 draft 사이클 사이 'draft' 로 바뀌어도 page_id 는 유지되므로 그쪽으로 판단.
        is_update = (
            isinstance(existing_entry, dict)
            and bool(existing_entry.get("page_id"))
        )
        prefix = "[API Draft][수정]" if is_update else "[API Draft][신규]"
        # draft 페이지 제목: Javadoc 제목 우선, 없으면 method + path
        draft_title = f"{prefix} {javadoc_title}" if javadoc_title else f"{prefix} {method} {path}"

        # 신규: 확인사항 / 수정: 이전 버전과의 diff (둘 중 하나만)
        if is_update and existing_doc:
            diff_block = build_diff_block(existing_doc, doc_content)
            doc_content = doc_content + (diff_block or REVIEW_CHECKLIST)
        else:
            doc_content = doc_content + REVIEW_CHECKLIST

        draft_page_id, draft_page_url = create_draft(
            dooray_api_key, wiki_id, draft_parent_id, base_url, web_url, project_id,
            api_key, draft_title, doc_content, url_hint, registry,
        )

        now = now_kst_iso()
        registry[api_key] = {
            **({} if not isinstance(existing_entry, dict) else existing_entry),
            "status": "draft",
            "draft_page_id": draft_page_id,
            "title": javadoc_title,
            "url_hint": url_hint,
            "created_at": existing_entry.get("created_at", now) if isinstance(existing_entry, dict) else now,
            "updated_at": now,
            "deprecated_at": None,
        }
        if not registry[api_key].get("page_id"):
            registry[api_key]["page_id"] = None

        draft_links.append((api_key, draft_page_url, "수정" if is_update else "신규"))

    # ── registry 커밋 ─────────────────────────────────────────────────────
    if draft_links or deprecated_list:
        write_registry(reg_path, registry)
        git_commit_and_push(
            "shared-config", [reg_rel],
            f"chore: pr#{pr_number} api docs draft - {repo_short} [skip ci]",
        )

    # ── PR comment ────────────────────────────────────────────────────────
    if draft_links or deprecated_list:
        lines = ["## API 문서 Draft 생성 완료", ""]
        if draft_links:
            lines.append("| 구분 | API | Draft 링크 |")
            lines.append("|------|-----|------------|")
            for key, url, kind in draft_links:
                lines.append(f"| {kind} | `{key}` | [Dooray Draft]({url}) |")
            lines.append("")
            lines.append("> Draft 검토 후 `API Doc Publish` 워크플로우를 실행하여 위키에 반영하세요.")
        if deprecated_list:
            lines.append("")
            lines.append("**삭제된 API (Deprecated 처리 완료)**")
            for key in deprecated_list:
                lines.append(f"- `{key}`")

        post_pr_comment(pr_number, repo_name, "\n".join(lines))
        print(f"PR #{pr_number} comment 게시 완료")

    print(f"\n완료 — draft {len(draft_links)}건, deprecated {len(deprecated_list)}건")


if __name__ == "__main__":
    main()
