import json
import os
import re
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))


def normalize_api_key(method: str, path: str) -> str:
    """API 키 정규화: 'METHOD /normalized/path' 형식으로 통일.

    - path variable {id}, {orderId} 등 → 변수명 그대로 소문자로만 통일
    - 소문자 통일
    - trailing slash 제거
    """
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
    """registry에서 캐싱된 repo_page_id 반환."""
    meta = registry.get(_REPO_PAGE_KEY, {})
    return meta.get(url_hint or "default", "")


def set_repo_page_id(registry: dict, url_hint: str, page_id: str):
    """repo_page_id를 registry에 캐싱."""
    if _REPO_PAGE_KEY not in registry:
        registry[_REPO_PAGE_KEY] = {}
    registry[_REPO_PAGE_KEY][url_hint or "default"] = page_id


def registry_path_for(repo_short_name: str) -> str:
    """shared-config checkout 기준 registry 파일 경로 반환."""
    return os.path.join("shared-config", "rest-api-docs", repo_short_name, "api-docs-registry.json")


def registry_rel_for(repo_short_name: str) -> str:
    """git add 용 상대 경로 (shared-config 내부 기준)."""
    return os.path.join("rest-api-docs", repo_short_name, "api-docs-registry.json")
