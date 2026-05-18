import json
import os
import re
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))

# ── Controller 어노테이션 파싱용 패턴 ────────────────────────────────────────
_CLASS_MAPPING_RE = re.compile(
    r'@RequestMapping\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?["\']([^"\']+)["\']'
)
_METHOD_MAPPING_RE = re.compile(
    r'@(Get|Post|Put|Delete|Patch|Request)Mapping'
    r'(?:'
    r'\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?["\']([^"\']*)["\']'
    r'|\s*\(\s*\)'
    r'|\s*(?!\()'
    r')'
)


def _normalize_path(url: str) -> str:
    url = re.sub(r"\{([^}]+)\}", lambda m: "{" + m.group(1).lower() + "}", url)
    return "/" + url.strip("/").lower()


# ── 기본 유틸 ─────────────────────────────────────────────────────────────────

def normalize_api_key(method: str, path: str) -> str:
    path = re.sub(r"\{([^}]+)\}", lambda m: "{" + m.group(1).lower() + "}", path)
    path = "/" + path.strip("/").lower()
    return f"{method.upper()} {path}"


def now_kst_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def now_kst_display() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")


def today_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def read_registry(filepath: str) -> dict:
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def write_registry(filepath: str, data: dict):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def set_output(name: str, value: str):
    output_file = os.environ.get("GITHUB_OUTPUT", "")
    if not output_file:
        print(f"OUTPUT {name}={value[:200]}")
        return
    delim = "GHADELIMITER_APIDOC"
    with open(output_file, "a") as f:
        if "\n" in value:
            f.write(f"{name}<<{delim}\n{value}\n{delim}\n")
        else:
            f.write(f"{name}={value}\n")


def write_summary(lines: list):
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY", "")
    content = "\n".join(lines) + "\n"
    if summary_file:
        with open(summary_file, "a") as f:
            f.write(content)
    else:
        print(content)


_REPO_PAGE_KEY = "__repo_page_id__"


def get_repo_page_id(registry: dict, url_hint: str) -> str:
    meta = registry.get(_REPO_PAGE_KEY, {})
    return meta.get(url_hint or "default", "")


def set_repo_page_id(registry: dict, url_hint: str, page_id: str):
    if _REPO_PAGE_KEY not in registry:
        registry[_REPO_PAGE_KEY] = {}
    registry[_REPO_PAGE_KEY][url_hint or "default"] = page_id


def read_service_config(repo_short_name: str) -> dict:
    # 통합 service-config.json 우선 사용 (rest-api-docs/service-config.json)
    consolidated = os.path.join("shared-config", "rest-api-docs", "service-config.json")
    if os.path.exists(consolidated):
        with open(consolidated, "r", encoding="utf-8") as f:
            return json.load(f).get(repo_short_name, {})
    return {}


def build_env_url_section(service_config: dict) -> str:
    envs = service_config.get("environments", {})
    if not envs:
        return ""
    rows = "\n".join(f"| {env} | {url} |" for env, url in envs.items())
    return f"## 서버 URL\n\n| 환경 | Base URL |\n|------|----------|\n{rows}\n"


def registry_path_for(repo_short_name: str) -> str:
    return os.path.join("shared-config", "rest-api-docs", repo_short_name, "api-docs-registry.json")


def registry_rel_for(repo_short_name: str) -> str:
    return os.path.join("rest-api-docs", repo_short_name, "api-docs-registry.json")


# ── Javadoc 파싱 ──────────────────────────────────────────────────────────────

def _parse_javadoc(comment_text: str) -> dict:
    """/** ... */ 블록을 파싱해 구조화된 dict 반환.

    Returns:
        title       : 첫 번째 비어있지 않은 줄
        description : 태그 이전의 나머지 본문
        params      : {'paramName': '설명'}
        returns     : @return 설명
        doc_url     : @apiScope 값 (internal | external | '')
    """
    result = {"title": "", "description": "", "params": {}, "returns": "", "doc_url": ""}

    lines = []
    for line in comment_text.splitlines():
        line = line.strip()
        line = re.sub(r"^/\*\*?", "", line)
        line = re.sub(r"\*/$", "", line)
        line = re.sub(r"^\*+\s?", "", line)
        lines.append(line.strip())

    desc_lines = []
    cur_tag = None
    cur_name = None
    cur_buf = []

    def _flush():
        text = " ".join(cur_buf).strip()
        if cur_tag == "param" and cur_name:
            result["params"][cur_name] = text
        elif cur_tag == "return":
            result["returns"] = text

    for line in lines:
        if line.startswith("@"):
            _flush()
            cur_buf = []
            parts = line.split(None, 2)
            tag = parts[0][1:]
            if tag == "param" and len(parts) >= 2:
                cur_tag, cur_name = "param", parts[1]
                cur_buf = [parts[2]] if len(parts) > 2 else []
            elif tag in ("return", "returns"):
                cur_tag, cur_name = "return", None
                cur_buf = [parts[1]] if len(parts) > 1 else []
            elif tag == "apiScope":
                result["doc_url"] = parts[1].strip() if len(parts) > 1 else ""
                cur_tag, cur_name = None, None  # 단일 값 태그 — 이후 줄은 누적하지 않음
            else:
                cur_tag, cur_name = None, None
        elif cur_tag is not None:
            if line:
                cur_buf.append(line)
        else:
            desc_lines.append(line)

    _flush()

    non_empty = [l for l in desc_lines if l]
    if non_empty:
        result["title"] = non_empty[0]
        result["description"] = "\n".join(non_empty[1:]).strip()

    return result


def _parse_method_params(sig_text: str) -> dict:
    """메서드 시그니처에서 파라미터별 어노테이션 정보 추출.

    Returns:
        {'paramName': {'kind': 'path'|'query'|'body'|'header'|'other',
                       'type': str, 'required': bool, 'default': str|None}}
    """
    paren_start = sig_text.find("(")
    if paren_start == -1:
        return {}

    depth, paren_end = 0, -1
    for i in range(paren_start, len(sig_text)):
        if sig_text[i] == "(":
            depth += 1
        elif sig_text[i] == ")":
            depth -= 1
            if depth == 0:
                paren_end = i
                break
    if paren_end == -1:
        return {}

    params_text = sig_text[paren_start + 1:paren_end]

    # 콤마로 분리 (< > 내부 제외)
    raw_params, depth, cur = [], 0, ""
    for ch in params_text:
        if ch in "<(":
            depth += 1
        elif ch in ">)":
            depth -= 1
        if ch == "," and depth == 0:
            if cur.strip():
                raw_params.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        raw_params.append(cur.strip())

    result = {}
    for param in raw_params:
        kind, required, default_val = "other", True, None

        if "@PathVariable" in param:
            kind = "path"
        elif "@RequestParam" in param:
            kind = "query"
            if re.search(r"required\s*=\s*false", param):
                required = False
            dv = re.search(r'defaultValue\s*=\s*"([^"]*)"', param)
            if dv:
                default_val, required = dv.group(1), False
        elif "@RequestBody" in param:
            kind = "body"
        elif "@RequestHeader" in param:
            kind = "header"

        # 어노테이션 제거 후 타입·이름 추출
        clean = re.sub(r"@\w+(\([^)]*\))?\s*", "", param).strip()
        clean = re.sub(r"\bfinal\b", "", clean).strip()
        parts = clean.split()
        if len(parts) >= 2:
            result[parts[-1]] = {
                "kind": kind,
                "type": parts[-2],
                "required": required,
                "default": default_val,
            }

    return result


def extract_javadoc_and_params(filepath: str, http_method: str, path: str) -> dict:
    """Controller 파일에서 특정 API 메서드의 Javadoc + 파라미터 정보 추출.

    Returns:
        {'javadoc': dict, 'method_params': dict, 'found': bool}
    """
    result = {"javadoc": {}, "method_params": {}, "found": False}

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return result

    content = "".join(lines)
    cm = _CLASS_MAPPING_RE.search(content)
    class_prefix = cm.group(1).rstrip("/") if cm else ""
    norm_target = _normalize_path(path)

    # 매핑 어노테이션 라인 탐색
    mapping_idx = None
    for i, line in enumerate(lines):
        for m in _METHOD_MAPPING_RE.finditer(line.strip()):
            verb = m.group(1).upper()
            if verb == "REQUEST":
                verb = "GET"
            mp = m.group(2) or ""
            sep = "/" if mp and not mp.startswith("/") else ""
            full = class_prefix + sep + mp
            if verb == http_method.upper() and _normalize_path(full) == norm_target:
                mapping_idx = i
                break
        if mapping_idx is not None:
            break

    if mapping_idx is None:
        return result
    result["found"] = True

    # 매핑 라인 위로 올라가며 Javadoc 블록 탐색 (어노테이션 라인 건너뜀)
    idx = mapping_idx - 1
    while idx >= 0 and lines[idx].strip().startswith("@"):
        idx -= 1
    while idx >= 0 and not lines[idx].strip():
        idx -= 1

    if idx >= 0 and lines[idx].strip() == "*/":
        end_idx = idx
        start_idx = idx
        while start_idx >= 0 and "/**" not in lines[start_idx]:
            start_idx -= 1
        if start_idx >= 0:
            comment = "".join(lines[start_idx:end_idx + 1])
            result["javadoc"] = _parse_javadoc(comment)

    # 메서드 시그니처 추출 (파라미터 어노테이션 파싱용)
    sig_lines, depth, found_open = [], 0, False
    for i in range(mapping_idx, min(mapping_idx + 30, len(lines))):
        sig_lines.append(lines[i])
        for ch in lines[i]:
            if ch == "(":
                depth += 1
                found_open = True
            elif ch == ")":
                depth -= 1
        if found_open and depth <= 0:
            break
    result["method_params"] = _parse_method_params("".join(sig_lines))

    return result


def parse_field_javadocs(filepath: str) -> dict:
    """DTO 파일에서 필드별 /** */ 주석 파싱.

    Returns:
        {'fieldName': {'description': str, 'example': str}}
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        return {}

    pattern = re.compile(
        r'/\*\*(.*?)\*/\s*'
        r'(?:@\w+(?:\([^)]*\))?\s*)*'
        r'(?:private|protected|public)\s+'
        r'(?:final\s+)?'
        r'[\w<>\[\],\s]+?\s+'
        r'(\w+)\s*;',
        re.DOTALL,
    )

    result = {}
    for m in pattern.finditer(content):
        comment_raw, field_name = m.group(1), m.group(2)
        desc_parts, example = [], ""
        for line in comment_raw.splitlines():
            line = re.sub(r"^\s*\*\s?", "", line).strip()
            if not line:
                continue
            if "@ex" in line:
                example = line.split("@ex", 1)[1].strip()
            elif not line.startswith("@"):
                desc_parts.append(line)
        description = " ".join(desc_parts).strip()
        if description or example:
            result[field_name] = {"description": description, "example": example}

    return result


def check_javadoc_completeness(javadoc: dict, method_params: dict) -> list:
    """Javadoc 필수 항목 누락 여부 검사. 오류 메시지 리스트 반환 (빈 리스트 = 통과)."""
    errors = []

    if not javadoc.get("title"):
        errors.append("Javadoc 첫 줄에 API 제목이 없습니다\n  예) /**\\n   * Todo 단건 조회")

    doc_url = javadoc.get("doc_url", "")
    if doc_url not in ("internal", "external"):
        errors.append(
            "@apiScope 태그가 없거나 올바르지 않습니다 (internal 또는 external 중 하나여야 합니다)\n"
            "  예) @apiScope external"
        )

    param_descs = javadoc.get("params", {})
    for name, info in method_params.items():
        if info["kind"] in ("path", "query") and not param_descs.get(name):
            errors.append(
                f"@param {name} 설명이 없습니다\n"
                f"  예) @param {name} 이 파라미터에 대한 설명"
            )

    return errors


def format_doc_hints(javadoc: dict, method_params: dict, field_docs: dict) -> str:
    """파싱된 Javadoc 정보를 Claude 프롬프트용 구조화 텍스트로 변환."""
    if not javadoc and not method_params and not field_docs:
        return ""

    parts = ["## 개발자 작성 문서 힌트 (아래 내용을 문서에 반드시 반영하세요)"]

    if javadoc.get("title"):
        parts.append(f"### 문서 제목\n{javadoc['title']}")

    if javadoc.get("description"):
        parts.append(f"### API 설명\n{javadoc['description']}")

    param_descs = javadoc.get("params", {})
    path_rows, query_rows, body_rows = [], [], []

    for name, info in method_params.items():
        desc = param_descs.get(name, "")
        if info["kind"] == "path":
            path_rows.append(f"| {name} | {info['type']} | {desc} |")
        elif info["kind"] == "query":
            req = "N" if not info["required"] else "Y"
            default = info["default"] if info["default"] is not None else "-"
            query_rows.append(f"| {name} | {info['type']} | {req} | {default} | {desc} |")
        elif info["kind"] == "body":
            body_rows.append(f"- {name} ({info['type']}): {desc}")

    if path_rows:
        parts.append(
            "### Path Variables\n"
            "| 변수명 | 타입 | 설명 |\n|--------|------|------|\n"
            + "\n".join(path_rows)
        )
    if query_rows:
        parts.append(
            "### Query Parameters\n"
            "| 파라미터 | 타입 | 필수 | 기본값 | 설명 |\n|----------|------|------|--------|------|\n"
            + "\n".join(query_rows)
        )
    if body_rows:
        parts.append("### Request Body\n" + "\n".join(body_rows))

    if javadoc.get("returns"):
        parts.append(f"### 응답 설명\n{javadoc['returns']}")

    if field_docs:
        field_lines = []
        for fname, info in field_docs.items():
            line = f"- **{fname}**: {info.get('description', '')}"
            if info.get("example"):
                line += f" (예시: `{info['example']}`)"
            field_lines.append(line)
        parts.append("### DTO 필드 설명\n" + "\n".join(field_lines))

    return "\n\n".join(parts)
