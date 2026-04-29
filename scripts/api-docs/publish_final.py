#!/usr/bin/env python3
"""
publish_final.py

Draft 페이지를 검토 후 본 API 문서 위키에 반영합니다.

동작:
  1. registry에서 api_key → draft_page_id, url_hint 조회
  2. Dooray에서 draft 페이지 내용 fetch
  3. Draft 메타 배너 제거
  4. 기존 page_id가 있으면 수정 이력 라인 상단 추가 후 update
     없으면 카테고리 → 레포 하위에 신규 create
  5. registry 갱신 (status=published, page_id, draft_page_id=null)
  6. Draft 페이지 삭제

환경 변수:
  DOORAY_API_KEY                  Dooray API 토큰
  DOORAY_WIKI_ID                  Dooray 위키 ID
  DOORAY_PROJECT_ID               Dooray 프로젝트 ID
  DOORAY_INTERNAL_PARENT_PAGE_ID  사내 API 위키 부모 페이지 ID
  DOORAY_EXTERNAL_PARENT_PAGE_ID  사외 API 위키 부모 페이지 ID
  DOORAY_DEFAULT_PARENT_PAGE_ID   기본 위키 부모 페이지 ID
  API_KEY                         레지스트리 키 (예: GET /api/v1/todos)
  REPO_NAME                       서비스 저장소 이름 (org/repo)
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from lib.api_utils import (
    now_kst_display, now_kst_iso,
    read_registry, write_registry, set_output,
    registry_path_for, registry_rel_for,
)
from lib.dooray import (
    create_page, delete_page, get_page, get_or_create_child_page, update_page,
)
from lib.git_utils import git_commit_and_push

_DRAFT_META_RE = re.compile(
    r'^> \*\*\[Draft\]\*\*.*\n> 생성 시각:.*\n\n---\n\n',
    re.MULTILINE,
)


def strip_draft_meta(content: str) -> str:
    return _DRAFT_META_RE.sub("", content)


def get_category_parent(url_hint: str) -> str:
    if url_hint == "internal":
        parent = os.environ.get("DOORAY_INTERNAL_PARENT_PAGE_ID", "")
    elif url_hint == "external":
        parent = os.environ.get("DOORAY_EXTERNAL_PARENT_PAGE_ID", "")
    else:
        parent = os.environ.get("DOORAY_DEFAULT_PARENT_PAGE_ID", "")
    if not parent:
        parent = os.environ.get("DOORAY_DEFAULT_PARENT_PAGE_ID", "")
    if not parent:
        print("[ERROR] 본 페이지 부모 ID를 찾을 수 없습니다.", file=sys.stderr)
        sys.exit(1)
    return parent


def prepend_history(existing_content: str, api_key: str) -> str:
    """수정 시 상단에 이력 라인 추가."""
    history_line = f"> 수정: `{api_key}` ({now_kst_display()})\n"
    # 이미 이력 섹션이 있으면 첫 번째 이력 라인 위에 삽입, 없으면 맨 앞에 추가
    if existing_content.startswith("> 수정:"):
        return history_line + existing_content
    return history_line + "\n" + existing_content


def main():
    dooray_api_key = os.environ.get("DOORAY_API_KEY", "")
    wiki_id = os.environ.get("DOORAY_WIKI_ID", "")
    project_id = os.environ.get("DOORAY_PROJECT_ID", "")
    base_url = os.environ.get("DOORAY_BASE_URL", "https://api.dooray.com")
    raw_api_key = os.environ.get("API_KEY", "")
    repo_name = os.environ.get("REPO_NAME", "")
    repo_short = repo_name.split("/")[-1] if repo_name else ""
    fallback_draft_page_id = os.environ.get("DRAFT_PAGE_ID", "")

    for var, val in {
        "DOORAY_API_KEY": dooray_api_key, "DOORAY_WIKI_ID": wiki_id,
        "DOORAY_PROJECT_ID": project_id, "API_KEY": raw_api_key, "REPO_NAME": repo_name,
    }.items():
        if not val:
            print(f"{var} 환경 변수가 필요합니다.", file=sys.stderr)
            sys.exit(1)

    # 사용자 입력이 정규화되지 않을 수 있으므로 normalize
    parts = raw_api_key.strip().split(" ", 1)
    if len(parts) == 2:
        from lib.api_utils import normalize_api_key
        api_key = normalize_api_key(parts[0], parts[1])
    else:
        api_key = raw_api_key
    if api_key != raw_api_key:
        print(f"[INFO] API Key 정규화: '{raw_api_key}' → '{api_key}'")

    reg_path = registry_path_for(repo_short)
    reg_rel = registry_rel_for(repo_short)
    registry = read_registry(reg_path)

    entry = registry.get(api_key)

    # registry에 없으면 fallback_draft_page_id로 신규 entry 구성
    if not entry or not isinstance(entry, dict):
        if not fallback_draft_page_id:
            print(
                f"[ERROR] registry에 '{api_key}' 항목이 없고 DRAFT_PAGE_ID도 없습니다.\n"
                f"  → 수동 실행 시 draft_page_id 입력값을 함께 제공하세요.",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"[INFO] registry 미등록 — DRAFT_PAGE_ID 로 신규 entry 생성: {api_key}")
        entry = {
            "status": "draft",
            "page_id": None,
            "draft_page_id": fallback_draft_page_id,
            "url_hint": "",
            "created_at": now_kst_iso(),
            "updated_at": now_kst_iso(),
            "deprecated_at": None,
        }
        registry[api_key] = entry

    draft_page_id = entry.get("draft_page_id") or fallback_draft_page_id
    if not draft_page_id:
        print(f"[ERROR] draft_page_id가 없습니다. 먼저 draft를 생성하세요.", file=sys.stderr)
        sys.exit(1)

    url_hint = entry.get("url_hint", "")
    existing_page_id = entry.get("page_id")

    # Draft 페이지 내용 fetch
    draft_title, draft_content = get_page(dooray_api_key, wiki_id, draft_page_id, base_url)
    publish_title = re.sub(r"^\[API Draft\](\[수정\]|\[신규\])?\s*", "", draft_title).strip()
    clean_content = strip_draft_meta(draft_content)

    if existing_page_id:
        # 수정: 기존 페이지 내용 fetch → 이력 추가 → update
        _, existing_content = get_page(dooray_api_key, wiki_id, existing_page_id, base_url)
        new_content = prepend_history(existing_content, api_key) + "\n\n---\n\n" + clean_content
        update_page(dooray_api_key, wiki_id, existing_page_id, publish_title, new_content, base_url)
        final_page_id = existing_page_id
        action = "updated"
        print(f"[INFO] 기존 페이지 업데이트: {api_key}")
    else:
        # 신규: 카테고리 → 레포 하위에 생성
        category_parent = get_category_parent(url_hint)
        repo_page_id = get_or_create_child_page(
            dooray_api_key, wiki_id, category_parent, repo_short, base_url
        )
        final_page_id = create_page(
            dooray_api_key, wiki_id, repo_page_id, publish_title, clean_content, base_url
        )
        action = "created"
        print(f"[INFO] 신규 페이지 생성: {api_key}")

    if not final_page_id:
        print("[ERROR] 페이지 ID를 가져올 수 없습니다.", file=sys.stderr)
        sys.exit(1)

    # registry 갱신
    registry[api_key] = {
        **entry,
        "status": "published",
        "page_id": final_page_id,
        "draft_page_id": None,
        "updated_at": now_kst_iso(),
    }
    write_registry(reg_path, registry)
    git_commit_and_push(
        "shared-config",
        [reg_rel],
        f"chore: publish api doc - {repo_short} {api_key} [skip ci]",
    )

    # Draft 페이지 삭제
    delete_page(dooray_api_key, wiki_id, draft_page_id, base_url)

    page_url = f"{base_url}/wiki/{project_id}/{final_page_id}"
    set_output("page_id", final_page_id)
    set_output("page_url", page_url)

    print(f"\n본 페이지 반영 완료 ({action})")
    print(f"  repo    : {repo_name}")
    print(f"  API Key : {api_key}")
    print(f"  제목    : {publish_title}")
    print(f"  URL     : {page_url}")


if __name__ == "__main__":
    main()
