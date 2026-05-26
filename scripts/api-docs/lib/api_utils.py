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


_SERVICE_CONFIG_PATH = os.path.join("shared-config", "rest-api-docs", "service-config.json")


def read_full_service_config() -> dict:
    """service-config.json 전체 반환 (게이트웨이 풀 + 서비스 설정 모두)."""
    if os.path.exists(_SERVICE_CONFIG_PATH):
        with open(_SERVICE_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def read_service_config(repo_short_name: str) -> dict:
    """단일 서비스의 설정만 반환 (하위호환)."""
    return read_full_service_config().get(repo_short_name, {})


def get_package(filepath: str) -> str:
    """Java 파일 상단의 'package com.x.y;' 선언에서 패키지 경로 추출."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for _ in range(30):  # 상단 30줄 안에 반드시 존재
                line = f.readline()
                if not line:
                    break
                m = re.match(r"\s*package\s+([\w.]+)\s*;", line)
                if m:
                    return m.group(1)
    except OSError:
        pass
    return ""


def find_group_for_controller(filepath: str, repo_config: dict) -> dict:
    """컨트롤러의 패키지를 보고 매칭되는 group dict 를 반환.

    - useGateway=true 인 서비스만 group 매칭 시도
    - 매칭 후보가 여럿이면 packagePrefix 가 가장 긴 것을 선택
    - 매칭 실패 시 None
    """
    if not repo_config.get("useGateway"):
        return None
    groups = repo_config.get("groups") or []
    if not groups:
        return None
    pkg = get_package(filepath)
    if not pkg:
        return None
    matches = [g for g in groups if g.get("packagePrefix") and pkg.startswith(g["packagePrefix"])]
    if not matches:
        return None
    matches.sort(key=lambda g: len(g.get("packagePrefix") or ""), reverse=True)
    return matches[0]


def apply_gateway_transform(path: str, group: dict) -> str:
    """컨트롤러 내부 path 를 게이트웨이 외부 path 로 변환.

    예시:
        path             = /external/api/todo-list/{id}
        internalUrlPrefix= /external
        externalUrlPrefix= /pay
        결과            = /pay/api/todo-list/{id}

    group 이 None 이거나 internal prefix 가 path 와 매칭 안 되면 path 그대로 반환.
    """
    if not group:
        return path
    internal = (group.get("internalUrlPrefix") or "").rstrip("/")
    external = (group.get("externalUrlPrefix") or "").rstrip("/")
    if internal and path.startswith(internal):
        remainder = path[len(internal):]
        if not remainder.startswith("/"):
            remainder = "/" + remainder
        return (external + remainder) if external else remainder
    return path


def resolve_environments(repo_config: dict, full_config: dict = None, group: dict = None) -> dict:
    """해당 컨트롤러용 환경별 Base URL dict 반환.

    useGateway 여부와 무관하게 repo_config 의 'environments' 를 그대로 사용.
    (게이트웨이 도메인도 service-config 의 해당 서비스 entry 에 직접 적는다.)
    값이 없으면 빈 dict 반환 → 호출부에서 registry fallback 등 후속 처리.

    full_config / group 인자는 향후 확장을 위해 시그니처에 유지하되 현재는 미사용.
    """
    return repo_config.get("environments") or {}


def list_services(full_config: dict) -> list:
    """서비스 키 목록만 (`_` 로 시작하는 메타 키 있을 경우 제외)."""
    return [k for k in full_config.keys() if not k.startswith("_")]


def build_env_url_section(envs: dict) -> str:
    """{환경:URL} dict 을 Claude 프롬프트용 '서버 URL' 표로 변환.

    이전 시그니처(service_config dict 통째로 받음) 와 하위호환을 위해
    'environments' 키가 있으면 안쪽 dict 을 사용한다.
    """
    if isinstance(envs, dict) and "environments" in envs and "Alpha" not in envs:
        envs = envs.get("environments") or {}
    envs = envs or {}
    if not envs:
        return ""
    rows = "\n".join(f"| {env} | {url} |" for env, url in envs.items())
    return f"## 서버 URL\n\n| 환경 | Base URL |\n|------|----------|\n{rows}\n"


def registry_path_for(repo_short_name: str) -> str:
    return os.path.join("shared-config", "rest-api-docs", repo_short_name, "api-docs-registry.json")


def registry_rel_for(repo_short_name: str) -> str:
    return os.path.join("rest-api-docs", repo_short_name, "api-docs-registry.json")


# ── Javadoc 파싱 ──────────────────────────────────────────────────────────────

_NAMED_TAGS = {
    "path": "path_params",   # @path NAME desc   → @PathVariable
    "param": "params",        # @param NAME desc  → @RequestParam (query)
    "header": "headers",      # @header NAME desc → @RequestHeader
    "body": "body_params",    # @body NAME desc   → @RequestBody/@ModelAttribute 필드
}


def _parse_javadoc(comment_text: str) -> dict:
    """/** ... */ 블록을 파싱해 구조화된 dict 반환.

    Returns:
        title       : 첫 번째 비어있지 않은 줄
        description : 태그 이전의 나머지 본문
        path_params : {'name': '설명'}  — @path (@PathVariable)
        params      : {'name': '설명'}  — @param (@RequestParam, query)
        headers     : {'name': '설명'}  — @header (@RequestHeader)
        body_params : {'name': '설명'}  — @body (@RequestBody/@ModelAttribute 필드)
        returns     : @return 설명
        doc_url     : @apiScope 값 (internal | external | private | '')
    """
    result = {
        "title": "", "description": "",
        "path_params": {}, "params": {}, "headers": {}, "body_params": {},
        "returns": "", "doc_url": "",
    }

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
        if cur_tag in _NAMED_TAGS and cur_name:
            result[_NAMED_TAGS[cur_tag]][cur_name] = text
        elif cur_tag == "return":
            result["returns"] = text

    for line in lines:
        if line.startswith("@"):
            _flush()
            cur_buf = []
            parts = line.split(None, 2)
            tag = parts[0][1:]
            if tag in _NAMED_TAGS and len(parts) >= 2:
                cur_tag, cur_name = tag, parts[1]
                cur_buf = [parts[2]] if len(parts) > 2 else []
            elif tag in ("return", "returns"):
                cur_tag, cur_name = "return", None
                # `@return rest of line` — split(None, 2) 의 잔여 토큰까지 모두 합침
                cur_buf = [line.split(None, 1)[1]] if len(parts) > 1 else []
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

    def _ann_name(text: str, annotation: str):
        """@RequestHeader("X-Caller-Id") / @RequestHeader(value="X") / @RequestHeader(name="X")
        형태에서 외부 이름 추출. 없으면 None."""
        pat = rf'@{annotation}\s*\(\s*(?:(?:value|name)\s*=\s*)?"([^"]+)"'
        m = re.search(pat, text)
        return m.group(1) if m else None

    result = {}
    for param in raw_params:
        kind, required, default_val = "other", True, None
        external_name = None

        if "@PathVariable" in param:
            kind = "path"
            external_name = _ann_name(param, "PathVariable")
        elif "@RequestParam" in param:
            kind = "query"
            external_name = _ann_name(param, "RequestParam")
            if re.search(r"required\s*=\s*false", param):
                required = False
            dv = re.search(r'defaultValue\s*=\s*"([^"]*)"', param)
            if dv:
                default_val, required = dv.group(1), False
        elif "@RequestBody" in param:
            kind = "body"
        elif "@RequestHeader" in param:
            kind = "header"
            external_name = _ann_name(param, "RequestHeader")

        # 어노테이션 제거 후 타입·이름 추출
        clean = re.sub(r"@\w+(\([^)]*\))?\s*", "", param).strip()
        clean = re.sub(r"\bfinal\b", "", clean).strip()
        parts = clean.split()
        if len(parts) >= 2:
            # 어노테이션에 명시된 외부 이름(예: 'X-Caller-Id') 이 있으면 그것을, 없으면 자바 파라미터명 사용
            key = external_name or parts[-1]
            result[key] = {
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

    # 메서드 시그니처 추출 (파라미터 어노테이션 파싱용).
    # 매핑 라인 아래의 어노테이션·빈 줄을 건너뛰어 실제 메서드 선언 라인부터 paren 균형을 추적한다.
    sig_start = mapping_idx + 1
    while sig_start < len(lines):
        s = lines[sig_start].lstrip()
        if not s or s.startswith("@") or s.startswith("//") or s.startswith("/*"):
            sig_start += 1
            continue
        break

    sig_lines, depth, found_open = [], 0, False
    for i in range(sig_start, min(sig_start + 30, len(lines))):
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


def parse_enum_constants(filepath: str) -> dict:
    """파일이 enum 이면 enum 이름과 상수 목록(+선택적 description) 을 반환.

    Returns:
        {'EnumName': {'constants': [{'name': str, 'description': str}, ...]}}
        enum 이 아니거나 파싱 실패면 {}.

    다음 두 형식을 지원한다:
        enum X { A, B, C }
        enum X { A("desc"), B("desc"), C("desc") }
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        return {}

    # public enum Foo { ... }
    enum_re = re.compile(
        r'(?:public\s+|private\s+|protected\s+)?enum\s+(\w+)\s*\{(.*?)\}',
        re.DOTALL,
    )
    result = {}
    for m in enum_re.finditer(content):
        name = m.group(1)
        body = m.group(2)
        # body 의 첫 ';' 까지가 상수 정의 영역
        constants_block = body.split(";", 1)[0]
        const_re = re.compile(r'(\w+)\s*(?:\(\s*"([^"]*)"[^)]*\))?', re.MULTILINE)
        constants = []
        # 콤마로 분리해 각 항목 파싱 (가장 단순한 형태)
        for part in constants_block.split(","):
            part = part.strip().lstrip("/").lstrip("*").strip()
            if not part:
                continue
            cm = const_re.match(part)
            if not cm:
                continue
            cname = cm.group(1)
            cdesc = (cm.group(2) or "").strip()
            if cname.isupper() or (cname and cname[0].isupper()):
                constants.append({"name": cname, "description": cdesc})
        if constants:
            result[name] = {"constants": constants}
    return result


def check_javadoc_completeness(javadoc: dict, method_params: dict) -> list:
    """Javadoc 필수 항목 누락 여부 검사. 오류 메시지 리스트 반환 (빈 리스트 = 통과).

    태그 매핑:
        @PathVariable  → @path  (구버전 @param 도 인정)
        @RequestParam  → @param
        @RequestHeader → @header (구버전 @param 도 인정)
    """
    errors = []

    if not javadoc.get("title"):
        errors.append("Javadoc 첫 줄에 API 제목이 없습니다\n  예) /**\\n   * Todo 단건 조회")

    doc_url = javadoc.get("doc_url", "")
    if doc_url not in ("internal", "external", "private"):
        errors.append(
            "@apiScope 태그가 없거나 올바르지 않습니다 (internal / external / private 중 하나여야 합니다)\n"
            "  예) @apiScope external"
        )

    path_descs = javadoc.get("path_params", {})
    query_descs = javadoc.get("params", {})
    header_descs = javadoc.get("headers", {})

    for name, info in method_params.items():
        kind = info["kind"]
        if kind == "path":
            if not (path_descs.get(name) or query_descs.get(name)):
                errors.append(
                    f"@path {name} 설명이 없습니다 (@PathVariable)\n"
                    f"  예) @path {name} 이 path variable 에 대한 설명"
                )
        elif kind == "query":
            if not query_descs.get(name):
                errors.append(
                    f"@param {name} 설명이 없습니다 (@RequestParam)\n"
                    f"  예) @param {name} 이 query parameter 에 대한 설명"
                )
        elif kind == "header":
            if not (header_descs.get(name) or query_descs.get(name)):
                errors.append(
                    f"@header {name} 설명이 없습니다 (@RequestHeader)\n"
                    f"  예) @header {name} 이 header 에 대한 설명"
                )
        elif kind == "body":
            body_descs = javadoc.get("body_params", {})
            if not (body_descs.get(name) or query_descs.get(name)):
                errors.append(
                    f"@body {name} 설명이 없습니다 (@RequestBody / @ModelAttribute)\n"
                    f"  예) @body {name} 이 인자가 받는 데이터의 역할/용도"
                )

    return errors


# ── 문서 헤더/푸터 헬퍼 ───────────────────────────────────────────────────────
SCOPE_LABEL = {
    "external": "사외",
    "internal": "사내",
    "private": "내부",
}


def build_doc_header(method: str, path: str, javadoc_title: str, scope: str) -> str:
    """문서 최상단 헤더 생성. H1 뒤 곧바로 본문(## Description)으로 이어진다.

    예시:
        # [사외] 결제 처리

    Method/URL 은 본문의 `## API Info` 표에서 다루므로 부제는 출력하지 않는다.
    scope 가 비어있거나 알 수 없는 값이면 라벨을 생략하고 제목만 사용.
    """
    label = SCOPE_LABEL.get((scope or "").lower())
    title = (javadoc_title or "").strip()
    if title and label:
        h1 = f"# [{label}] {title}"
    elif title:
        h1 = f"# {title}"
    elif label:
        h1 = f"# [{label}] {method} {path}"
    else:
        h1 = f"# [{method}] {path}"
    return f"{h1}\n\n"


def strip_pre_h2(text: str) -> str:
    """Claude 출력에서 첫 `## ` 헤딩 이전의 모든 텍스트를 제거.

    H1, 부제, 인사말("코드 분석이 완료되었습니다"), 빈 줄 등 본문 시작
    이전의 모든 사전 텍스트를 잘라낸다. 첫 H2 가 없으면 원본 그대로 반환.
    """
    if not text:
        return text
    m = re.search(r'^## ', text, re.MULTILINE)
    return text[m.start():] if m else text


import difflib

DIFF_SECTION_TITLE = "이전 버전과의 변경사항"


def _diff_signature(line: str) -> str:
    """Diff 비교 시 의미 없는 차이(공백·마크다운 포매팅)를 제거한 signature.

    - 백틱 / bold 마커 / italic 마커 모두 제거
    - 모든 공백 제거 (한글-조사 사이 공백 변화 같은 노이즈 무시)
    - 빈 줄은 빈 signature 로 통일
    """
    s = line
    s = re.sub(r"`+", "", s)
    s = re.sub(r"\*+", "", s)
    s = re.sub(r"\s+", "", s)
    return s


def _filter_noise_pairs(diff_lines: list) -> list:
    """unified_diff 출력에서 의미 변경 없는 -/+ 쌍을 context 로 변환.

    인접한 `-line` 과 `+line` 의 signature 가 동일하면 둘 다 ` line` (context) 으로
    바꿔 표시. 다수 - 와 다수 + 가 한 블록일 때는 같은 길이로 짝지어 비교.
    헤더(---, +++, @@) 는 그대로 둔다.
    """
    out = []
    i = 0
    n = len(diff_lines)
    while i < n:
        ln = diff_lines[i]
        # 헤더는 그대로
        if ln.startswith("--- ") or ln.startswith("+++ ") or ln.startswith("@@"):
            out.append(ln)
            i += 1
            continue
        # 연속 '-' 블록 → 이어지는 연속 '+' 블록 짝짓기
        if ln.startswith("-"):
            minus_block, j = [], i
            while j < n and diff_lines[j].startswith("-") and not diff_lines[j].startswith("--- "):
                minus_block.append(diff_lines[j]); j += 1
            plus_block, k = [], j
            while k < n and diff_lines[k].startswith("+") and not diff_lines[k].startswith("+++ "):
                plus_block.append(diff_lines[k]); k += 1
            # 1:1 페어링 가능 만큼 노이즈 검사
            paired = min(len(minus_block), len(plus_block))
            kept_minus, kept_plus = [], []
            for idx in range(paired):
                m_line = minus_block[idx]
                p_line = plus_block[idx]
                if _diff_signature(m_line[1:]) == _diff_signature(p_line[1:]):
                    # 의미 변경 없음 → context 로 보존 (new 쪽 텍스트로)
                    out.append(" " + p_line[1:])
                else:
                    kept_minus.append(m_line)
                    kept_plus.append(p_line)
            # 짝 못 지은 잉여
            kept_minus.extend(minus_block[paired:])
            kept_plus.extend(plus_block[paired:])
            out.extend(kept_minus)
            out.extend(kept_plus)
            i = k
            continue
        out.append(ln)
        i += 1
    return out


def _hunk_has_changes(hunk_lines: list) -> bool:
    """hunk 안에 실제 -/+ 가 남아있는지"""
    for ln in hunk_lines:
        if ln.startswith("--- ") or ln.startswith("+++ ") or ln.startswith("@@"):
            continue
        if ln.startswith("-") or ln.startswith("+"):
            return True
    return False


def _drop_empty_hunks(diff_lines: list) -> list:
    """필터링 후 변경 없는 hunk(@@) 는 제거"""
    out = []
    i = 0
    n = len(diff_lines)
    while i < n:
        ln = diff_lines[i]
        if ln.startswith("--- ") or ln.startswith("+++ "):
            out.append(ln); i += 1; continue
        if ln.startswith("@@"):
            # hunk 모으기
            hunk = [ln]; j = i + 1
            while j < n and not diff_lines[j].startswith("@@") and not diff_lines[j].startswith("--- "):
                hunk.append(diff_lines[j]); j += 1
            if _hunk_has_changes(hunk):
                out.extend(hunk)
            i = j
            continue
        out.append(ln); i += 1
    return out


def build_diff_block(prev_content: str, new_content: str,
                     max_lines: int = 200) -> str:
    """수정 Draft 용 unified diff 섹션 생성.

    의미 변경(텍스트 차이) 만 강조. 공백/백틱 같은 마크다운 포매팅 차이는 필터링.
    변경 사항이 없으면 빈 문자열 반환. 너무 길면 max_lines 까지만 노출하고
    잘렸음을 알리는 주석을 덧붙인다. publish 시 strip 으로 제거된다.
    """
    if not prev_content or not new_content:
        return ""
    prev_lines = prev_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff_lines = list(difflib.unified_diff(
        prev_lines, new_lines,
        fromfile="이전 published 버전",
        tofile="새 Draft",
        n=2,
    ))
    if not diff_lines:
        return ""

    # 노이즈 필터링 — 공백/백틱만 다른 -/+ 쌍 제거, 빈 hunk 제거
    diff_lines = _filter_noise_pairs(diff_lines)
    diff_lines = _drop_empty_hunks(diff_lines)
    # 헤더 외 실제 변경 라인이 없으면 빈 결과
    if not any(
        (ln.startswith("-") and not ln.startswith("--- "))
        or (ln.startswith("+") and not ln.startswith("+++ "))
        for ln in diff_lines
    ):
        return ""

    truncated = False
    if len(diff_lines) > max_lines:
        diff_lines = diff_lines[:max_lines]
        truncated = True
    body = "".join(diff_lines)
    body = body.replace("```", "``​`")  # 코드블록 깨짐 방지
    note = "\n\n_diff 가 너무 길어 일부만 표시되었습니다._" if truncated else ""
    return (
        f"\n\n---\n\n"
        f"### 📝 {DIFF_SECTION_TITLE}\n\n"
        f"> publish 시 자동으로 제거됩니다. 검토 후 변경 의도가 맞는지 확인해주세요.\n"
        f"> 공백·마크다운 포매팅 차이는 필터링되어, 텍스트 변경만 강조합니다.\n\n"
        f"```diff\n{body}```{note}\n"
    )


REVIEW_CHECKLIST = """

---

### 확인사항

> publish 전 아래 항목을 검토해주세요. 필요시 자유롭게 수정 후 publish 하세요.

- [ ] **API 제목** 이 사용자에게 명확한가요?
- [ ] **위키 분류** (사외/사내/내부) 가 정확한가요?
- [ ] **요청/응답 예시** 의 필드/타입/예시값이 실제 코드와 일치하나요?
- [ ] **필수/선택** 표시가 정확한가요?
- [ ] **서버 URL** 이 환경별로 모두 포함되어 있나요?
- [ ] **에러 응답** 케이스가 누락 없이 명시되어 있나요?
- [ ] **추가 설명** 이 필요한 비즈니스 규칙/제약이 있나요?
"""


def format_doc_hints(javadoc: dict, method_params: dict, field_docs: dict,
                     enums: dict = None) -> str:
    """파싱된 Javadoc 정보를 Claude 프롬프트용 구조화 텍스트로 변환.

    enums: {EnumName: {'constants': [{'name': str, 'description': str}, ...]}}
    """
    enums = enums or {}
    if not javadoc and not method_params and not field_docs and not enums:
        return ""

    parts = ["## 개발자 작성 문서 힌트 (아래 내용을 문서에 반드시 반영하세요)"]

    if javadoc.get("title"):
        parts.append(f"### 문서 제목\n{javadoc['title']}")

    if javadoc.get("description"):
        parts.append(f"### API 설명\n{javadoc['description']}")

    path_descs = javadoc.get("path_params", {})
    query_descs = javadoc.get("params", {})
    header_descs = javadoc.get("headers", {})
    body_descs = javadoc.get("body_params", {})

    path_rows, query_rows, header_rows, body_rows = [], [], [], []

    for name, info in method_params.items():
        kind = info["kind"]
        if kind == "path":
            desc = path_descs.get(name) or query_descs.get(name, "")
            path_rows.append(f"| {name} | {info['type']} | {desc} |")
        elif kind == "query":
            desc = query_descs.get(name, "")
            req = "N" if not info["required"] else "Y"
            default = info["default"] if info["default"] is not None else "-"
            query_rows.append(f"| {name} | {info['type']} | {req} | {default} | {desc} |")
        elif kind == "header":
            desc = header_descs.get(name) or query_descs.get(name, "")
            req = "N" if not info["required"] else "Y"
            header_rows.append(f"| {name} | {req} | {info['type']} | {desc} |")
        elif kind == "body":
            desc = body_descs.get(name) or query_descs.get(name, "")
            body_rows.append(f"- {name} ({info['type']}): {desc}")

    # 템플릿의 Request 섹션 이름과 일치시킨다 (Header / PathVariable / Parameters / Body)
    if header_rows:
        parts.append(
            "### Header (Request)\n"
            "| 항목명 | 필수여부 | 타입 | 의미 |\n|--------|--------|------|------|\n"
            + "\n".join(header_rows)
        )
    if path_rows:
        parts.append(
            "### PathVariable\n"
            "| 변수명 | 타입 | 설명 |\n|--------|------|------|\n"
            + "\n".join(path_rows)
        )
    if query_rows:
        parts.append(
            "### Parameters (Query)\n"
            "| 파라미터 | 타입 | 필수 | 기본값 | 설명 |\n|----------|------|------|--------|------|\n"
            + "\n".join(query_rows)
        )
    if body_rows:
        parts.append("### Body (인자 역할)\n" + "\n".join(body_rows))

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

    # ── Enum 힌트 ──
    # 어떤 DTO 필드의 @ex 값이 enum 상수 이름과 매칭되면 사용자가 이미 충분한
    # 예시를 줬다고 보고 해당 enum 의 전체 상수 dump 는 생략한다.
    # 매칭되는 @ex 가 없으면 최대 5개 상수만 노출(나머지는 +N 표시).
    if enums:
        example_tokens = set()
        for info in field_docs.values():
            ex = info.get("example", "")
            if ex:
                example_tokens.add(ex.strip().strip('"').strip("'"))

        ENUM_CAP = 5
        enum_blocks = []
        for ename, info in enums.items():
            consts = info.get("constants", [])
            if not consts:
                continue
            const_names = {c["name"] for c in consts}
            # @ex 값에 이 enum 의 상수가 들어있으면 dump 생략
            if example_tokens & const_names:
                continue
            shown = consts[:ENUM_CAP]
            rows = [
                f"- `{c['name']}`" + (f" — {c['description']}" if c.get("description") else "")
                for c in shown
            ]
            if len(consts) > ENUM_CAP:
                rows.append(f"- _… 외 {len(consts) - ENUM_CAP}개_")
            enum_blocks.append(f"**{ename}**\n" + "\n".join(rows))
        if enum_blocks:
            parts.append(
                "### 사용된 Enum (코드에서 자동 추출 — 대표값만 노출)\n"
                + "\n\n".join(enum_blocks)
            )

    return "\n\n".join(parts)
