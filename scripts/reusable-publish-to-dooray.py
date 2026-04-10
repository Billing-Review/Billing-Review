#!/usr/bin/env python3
"""
reusable-publish-to-dooray.py

생성된 API 문서를 Dooray 위키 Draft 페이지에 게시합니다.

환경 변수:
  DOORAY_API_KEY              Dooray API 키
  DOORAY_MEMBER_ID            Dooray 멤버 ID
  DOORAY_PROJECT_ID           Dooray 프로젝트 ID
  DOORAY_DRAFT_PARENT_PAGE_ID Draft 페이지의 부모 페이지 ID
  TITLE                       위키 페이지 제목
  DOC_CONTENT                 마크다운 문서 본문
  URL_HINT                    위키 경로 분류 힌트 (internal/external/'')
  GITHUB_OUTPUT               GitHub Actions 출력 파일 경로
"""

import datetime
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import timezone


def set_output(name: str, value: str):
    output_file = os.environ.get("GITHUB_OUTPUT", "")
    if not output_file:
        print(f"OUTPUT {name}={value}")
        return
    with open(output_file, "a") as f:
        f.write(f"{name}={value}\n")


def classify_wiki_path(url_hint: str) -> str:
    if url_hint == "internal":
        return "BILL-GATEWAY(사내)"
    elif url_hint == "external":
        return "BILL-GATEWAY(사외)"
    return "빌링서비스실 내부"


def create_dooray_page(
    api_key: str,
    member_id: str,
    project_id: str,
    parent_page_id: str,
    title: str,
    content: str,
    base_url: str,
) -> dict:
    payload = {
        "title": title,
        "content": content,
        "parentPageId": parent_page_id,
    }
    url = f"{base_url}/wiki/v1/projects/{project_id}/pages"
    body_bytes = json.dumps(payload).encode()
    print(f"[INFO] Dooray API URL: {url}")
    print(f"[INFO] project_id: {project_id}")
    print(f"[INFO] parent_page_id: {parent_page_id}")
    print(f"[INFO] payload: {json.dumps({k: v[:30] + '...' if isinstance(v, str) and len(v) > 30 else v for k, v in payload.items()})}")
    req = urllib.request.Request(
        url,
        data=body_bytes,
        headers={
            "Authorization": f"dooray-api {member_id}:{api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Dooray API 오류: {e.code}\n{body}", file=sys.stderr)
        sys.exit(1)


def main():
    api_key = os.environ.get("DOORAY_API_KEY", "")
    member_id = os.environ.get("DOORAY_MEMBER_ID", "")
    project_id = os.environ.get("DOORAY_PROJECT_ID", "")
    parent_page_id = os.environ.get("DOORAY_DRAFT_PARENT_PAGE_ID", "")
    base_url = os.environ.get("DOORAY_BASE_URL", "https://nhnent.dooray.com")
    title = os.environ.get("TITLE", "")
    doc_content = os.environ.get("DOC_CONTENT", "")
    url_hint = os.environ.get("URL_HINT", "")

    required = {
        "DOORAY_API_KEY": api_key,
        "DOORAY_MEMBER_ID": member_id,
        "DOORAY_PROJECT_ID": project_id,
        "DOORAY_DRAFT_PARENT_PAGE_ID": parent_page_id,
        "TITLE": title,
        "DOC_CONTENT": doc_content,
    }
    for var, val in required.items():
        if not val:
            print(f"{var} 환경 변수가 필요합니다.", file=sys.stderr)
            sys.exit(1)

    wiki_category = classify_wiki_path(url_hint)

    now = datetime.datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    full_content = f"""> **[Draft]** 자동 생성된 API 문서입니다. 검토 후 publish 하세요.
> 생성 시각: {now} | 위키 분류: {wiki_category}

---

{doc_content}"""

    result = create_dooray_page(
        api_key, member_id, project_id, parent_page_id, title, full_content, base_url
    )

    page_id = result.get("result", {}).get("id", "")
    page_url = f"{base_url}/wiki/{project_id}/{page_id}"

    set_output("page_id", page_id)
    set_output("page_url", page_url)
    set_output("wiki_category", wiki_category)

    print("Dooray Draft 페이지 생성 완료")
    print(f"  제목: {title}")
    print(f"  분류: {wiki_category}")
    print(f"  페이지 ID: {page_id}")


if __name__ == "__main__":
    main()
