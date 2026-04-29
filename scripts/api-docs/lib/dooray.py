import json
import sys
import urllib.error
import urllib.request


def dooray_request(method: str, url: str, api_key: str, payload: dict = None) -> dict:
    body_bytes = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(
        url,
        data=body_bytes,
        headers={
            "Authorization": f"dooray-api {api_key}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Dooray API 오류 [{method} {url}]: {e.code}\n{body}", file=sys.stderr)
        sys.exit(1)


def get_page(api_key: str, wiki_id: str, page_id: str, base_url: str) -> tuple:
    url = f"{base_url}/wiki/v1/wikis/{wiki_id}/pages/{page_id}"
    result = dooray_request("GET", url, api_key)
    r = result.get("result", {})
    return r.get("subject", ""), r.get("body", {}).get("content", "")


def create_page(api_key: str, wiki_id: str, parent_page_id: str,
                title: str, content: str, base_url: str) -> str:
    payload = {
        "parentPageId": parent_page_id,
        "subject": title,
        "body": {"content": content, "mimeType": "text/x-markdown"},
        "referrers": [],
    }
    url = f"{base_url}/wiki/v1/wikis/{wiki_id}/pages"
    result = dooray_request("POST", url, api_key, payload)
    return result.get("result", {}).get("id", "")


def update_page(api_key: str, wiki_id: str, page_id: str,
                title: str, content: str, base_url: str):
    payload = {
        "subject": title,
        "body": {"content": content, "mimeType": "text/x-markdown"},
    }
    url = f"{base_url}/wiki/v1/wikis/{wiki_id}/pages/{page_id}"
    dooray_request("PUT", url, api_key, payload)


def delete_page(api_key: str, wiki_id: str, page_id: str, base_url: str):
    if not page_id:
        return
    url = f"{base_url}/wiki/v1/wikis/{wiki_id}/pages/{page_id}"
    try:
        dooray_request("DELETE", url, api_key)
        print(f"[INFO] 페이지 삭제: pageId={page_id}")
    except SystemExit:
        print(f"[WARN] 페이지 삭제 실패 (이미 삭제됐을 수 있음): {page_id}")


def get_child_pages(api_key: str, wiki_id: str, parent_page_id: str, base_url: str) -> list:
    """페이지네이션을 고려해 모든 자식 페이지를 반환한다."""
    all_children, page = [], 0
    while True:
        url = f"{base_url}/wiki/v1/wikis/{wiki_id}/pages/{parent_page_id}/children?page={page}&size=100"
        try:
            result = dooray_request("GET", url, api_key)
        except SystemExit:
            break
        children = result.get("result", [])
        all_children.extend(children)
        if len(children) < 100:
            break
        page += 1
    return all_children


def get_or_create_child_page(api_key: str, wiki_id: str, parent_id: str,
                              name: str, base_url: str) -> str:
    """parent 하위에서 name과 일치하는 페이지를 찾거나 새로 만든다."""
    for child in get_child_pages(api_key, wiki_id, parent_id, base_url):
        if child.get("subject", "").strip() == name.strip():
            page_id = child.get("id", "")
            print(f"[INFO] 기존 페이지 재사용: {name} (id={page_id})")
            return page_id
    print(f"[INFO] 페이지 신규 생성: {name}")
    return create_page(api_key, wiki_id, parent_id, name, "", base_url)
