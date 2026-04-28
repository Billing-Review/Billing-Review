#!/usr/bin/env python3
"""
deprecated_handler.py

삭제된 API 엔드포인트를 Dooray 위키 페이지에 @Deprecated 처리합니다.

환경 변수:
  DOORAY_API_KEY      Dooray API 토큰
  DOORAY_WIKI_ID      Dooray 위키 ID
  DELETED_ENDPOINTS   삭제된 엔드포인트 목록 (줄바꿈 구분)
  REPO_NAME           서비스 저장소 이름 (org/repo)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from lib.api_utils import (
    normalize_api_key, today_kst, now_kst_iso,
    read_registry, write_registry, write_summary,
    registry_path_for, registry_rel_for,
)
from lib.dooray import get_page, update_page
from lib.git_utils import git_commit_and_push


def main():
    dooray_api_key = os.environ.get("DOORAY_API_KEY", "")
    wiki_id = os.environ.get("DOORAY_WIKI_ID", "")
    base_url = os.environ.get("DOORAY_BASE_URL", "https://api.dooray.com")
    deleted_raw = os.environ.get("DELETED_ENDPOINTS", "")
    repo_name = os.environ.get("REPO_NAME", "")
    repo_short = repo_name.split("/")[-1] if repo_name else ""

    for var, val in {
        "DOORAY_API_KEY": dooray_api_key, "DOORAY_WIKI_ID": wiki_id, "REPO_NAME": repo_name,
    }.items():
        if not val:
            print(f"{var} 환경 변수가 필요합니다.", file=sys.stderr)
            sys.exit(1)

    # DELETED_ENDPOINTS는 "METHOD /path" 또는 normalize된 형식 모두 허용
    endpoints = [ep.strip() for ep in deleted_raw.splitlines() if ep.strip()]
    if not endpoints:
        print("[INFO] 삭제된 엔드포인트 없음 — 스킵")
        return

    reg_path = registry_path_for(repo_short)
    reg_rel = registry_rel_for(repo_short)
    registry = read_registry(reg_path)
    today = today_kst()
    marker = f"@Deprecated({today})\n\n"

    processed, skipped = [], []
    registry_changed = False

    for endpoint in endpoints:
        # 입력이 "GET /api/todos" 형식이면 normalize, 이미 normalized면 그대로
        parts = endpoint.split(" ", 1)
        if len(parts) == 2:
            api_key = normalize_api_key(parts[0], parts[1])
        else:
            api_key = endpoint

        entry = registry.get(api_key)
        if not entry:
            print(f"[INFO] registry 미등록 — 건너뜀: {api_key}")
            skipped.append(api_key)
            continue

        if isinstance(entry, dict):
            if entry.get("status") == "deprecated":
                print(f"[INFO] 이미 deprecated — 건너뜀: {api_key}")
                skipped.append(api_key)
                continue
            page_id = entry.get("page_id", "")
        else:
            page_id = str(entry)

        if not page_id:
            print(f"[WARN] page_id 없음 — 건너뜀: {api_key}")
            skipped.append(api_key)
            continue

        try:
            title, content = get_page(dooray_api_key, wiki_id, page_id, base_url)
            if marker.strip() not in content:
                update_page(dooray_api_key, wiki_id, page_id, title, marker + content, base_url)
            registry[api_key] = {
                **(entry if isinstance(entry, dict) else {"page_id": page_id}),
                "status": "deprecated",
                "deprecated_at": today,
                "updated_at": now_kst_iso(),
            }
            registry_changed = True
            processed.append(api_key)
            print(f"[INFO] Deprecated 처리 완료: {api_key}")
        except Exception as e:
            print(f"[WARN] {api_key} 처리 실패: {e}")
            skipped.append(api_key)

    if registry_changed:
        write_registry(reg_path, registry)
        git_commit_and_push(
            "shared-config",
            [reg_rel],
            f"chore: deprecated api - {repo_short} [skip ci]",
        )

    write_summary([
        f"## Deprecated 처리 결과 — {repo_name}",
        "",
        f"**처리 완료 ({len(processed)}건)**",
        *[f"- `{ep}` → `@Deprecated({today})` 추가" for ep in processed],
        *(["", f"**건너뜀 ({len(skipped)}건)**",
           *[f"- `{ep}`" for ep in skipped]] if skipped else []),
    ])


if __name__ == "__main__":
    main()
