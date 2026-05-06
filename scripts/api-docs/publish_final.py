#!/usr/bin/env python3
"""
publish_final.py

Draft 페이지를 본 위키로 publish합니다.
Draft가 없으면 오류로 종료합니다 (코드에서 직접 생성하지 않음).

환경 변수:
  DOORAY_API_KEY   Dooray API 토큰
  API_KEY          레지스트리 키 (예: GET /api/v1/todos)
  REPO_NAME        서비스 저장소 이름 (org/repo)
  DRAFT_PAGE_ID    워크플로우 내부 전달용 (사용자 입력 불필요)
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from lib.api_utils import (
    normalize_api_key, now_kst_display, now_kst_iso,
    read_registry, write_registry, set_output,
    registry_path_for, registry_rel_for,
    get_repo_page_id, set_repo_page_id,
)
from lib.dooray import (
    create_page, delete_page, get_child_pages, get_page,
    get_or_create_child_page, update_page,
)
from lib.git_utils import git_commit_and_push
from lib.config import (
    DOORAY_WIKI_ID, DOORAY_PROJECT_ID, DOORAY_DRAFT_PARENT_PAGE_ID,
    DOORAY_INTERNAL_PARENT_PAGE_ID, DOORAY_EXTERNAL_PARENT_PAGE_ID,
    DOORAY_DEFAULT_PARENT_PAGE_ID,
)

_DRAFT_META_RE = re.compile(
    r'^> \*\*\[Draft\]\*\*.*\n> 생성 시각:.*\n\n---\n\n',
    re.MULTILINE,
)


def strip_draft_meta(content: str) -> str:
    content = content.replace('\r\n', '\n')
    return _DRAFT_META_RE.sub("", content)


def get_category_parent(url_hint: str) -> str:
    if url_hint == "internal":
        parent = DOORAY_INTERNAL_PARENT_PAGE_ID
    elif url_hint == "external":
        parent = DOORAY_EXTERNAL_PARENT_PAGE_ID
    else:
        parent = DOORAY_DEFAULT_PARENT_PAGE_ID
    parent = parent or DOORAY_DEFAULT_PARENT_PAGE_ID
    if not parent:
        print("[ERROR] 본 페이지 부모 ID를 찾을 수 없습니다.", file=sys.stderr)
        sys.exit(1)
    return parent


def find_draft_in_dooray(dooray_api_key, wiki_id, draft_parent_id, base_url, api_key):
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


def main():
    dooray_api_key = os.environ.get("DOORAY_API_KEY", "")
    wiki_id = DOORAY_WIKI_ID
    project_id = DOORAY_PROJECT_ID
    draft_parent_id = DOORAY_DRAFT_PARENT_PAGE_ID
    base_url = os.environ.get("DOORAY_BASE_URL", "https://api.dooray.com")
    web_url = os.environ.get("DOORAY_WEB_URL", "https://nhnent.dooray.com")
    raw_api_key = os.environ.get("API_KEY", "")
    repo_name = os.environ.get("REPO_NAME", "")
    repo_short = repo_name.split("/")[-1] if repo_name else ""
    fallback_draft_page_id = os.environ.get("DRAFT_PAGE_ID", "")

    for var, val in {
        "DOORAY_API_KEY": dooray_api_key, "API_KEY": raw_api_key, "REPO_NAME": repo_name,
    }.items():
        if not val:
            print(f"{var} 환경 변수가 필요합니다.", file=sys.stderr)
            sys.exit(1)

    parts = raw_api_key.strip().split(" ", 1)
    api_key = normalize_api_key(parts[0], parts[1]) if len(parts) == 2 else raw_api_key
    if api_key != raw_api_key:
        print(f"[INFO] API Key 정규화: '{raw_api_key}' → '{api_key}'")

    reg_path = registry_path_for(repo_short)
    reg_rel = registry_rel_for(repo_short)
    registry = read_registry(reg_path)
    entry = registry.get(api_key, {}) if isinstance(registry.get(api_key), dict) else {}

    # draft 페이지 찾기
    draft_page_id = entry.get("draft_page_id") or fallback_draft_page_id
    if draft_page_id:
        print(f"[INFO] draft 페이지 사용: {draft_page_id}")
    else:
        draft_page_id = find_draft_in_dooray(dooray_api_key, wiki_id, draft_parent_id, base_url, api_key)

    if not draft_page_id:
        print(f"[ERROR] draft가 없습니다. 먼저 draft를 생성하세요. (api_key={api_key})", file=sys.stderr)
        sys.exit(1)

    url_hint = entry.get("url_hint", "")

    # draft 내용 가져오기 → Draft 메타 배너 제거
    draft_title, draft_content = get_page(dooray_api_key, wiki_id, draft_page_id, base_url)
    publish_title = re.sub(r"^\[API Draft\](\[수정\]|\[신규\])?\s*", "", draft_title).strip()
    clean_content = strip_draft_meta(draft_content)

    existing_page_id = entry.get("page_id")

    # 위키 페이지 생성 또는 교체
    if existing_page_id:
        update_page(dooray_api_key, wiki_id, existing_page_id, publish_title, clean_content, base_url)
        final_page_id = existing_page_id
        action = "updated"
    else:
        category_parent = get_category_parent(url_hint)
        repo_page_id = get_repo_page_id(registry, url_hint)
        if not repo_page_id:
            repo_page_id = get_or_create_child_page(
                dooray_api_key, wiki_id, category_parent, repo_short, base_url
            )
            set_repo_page_id(registry, url_hint, repo_page_id)
        final_page_id = create_page(
            dooray_api_key, wiki_id, repo_page_id, publish_title, clean_content, base_url
        )
        action = "created"

    if not final_page_id:
        print("[ERROR] 페이지 ID를 가져올 수 없습니다.", file=sys.stderr)
        sys.exit(1)

    # registry 갱신
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

    # draft 삭제
    delete_page(dooray_api_key, wiki_id, draft_page_id, base_url)

    page_url = f"{web_url}/wiki/{project_id}/{final_page_id}"
    set_output("page_id", final_page_id)
    set_output("page_url", page_url)
    print(f"[INFO] Publish 완료 ({action}): {page_url}")
