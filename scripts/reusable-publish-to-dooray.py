#!/usr/bin/env python3
"""
reusable-publish-to-dooray.py

생성된 API 문서를 Dooray 위키 Draft 페이지에 게시하고,
rest-api-docs repo의 draft-registry를 업데이트합니다.

환경 변수:
  DOORAY_API_KEY              Dooray API 토큰 (appId:token 형식)
  DOORAY_WIKI_ID              Dooray 위키 ID
  DOORAY_PROJECT_ID           Dooray 프로젝트 ID
  DOORAY_DRAFT_PARENT_PAGE_ID Draft 페이지의 부모 페이지 ID
  TITLE                       위키 페이지 제목
  DOC_CONTENT                 마크다운 문서 본문
  URL_HINT                    위키 경로 분류 힌트 (internal/external/'')
  API_KEY                     레지스트리 키 (예: GET /api/v1/todos)
  ORG_GITHUB_TOKEN            GitHub 인증 토큰 (rest-api-docs repo push용)
  GITHUB_OUTPUT               GitHub Actions 출력 파일 경로
"""

import datetime
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import timezone

DOCS_REPO = "dev-billing/rest-api-docs"
DOCS_REPO_DIR = "rest-api-docs"
DRAFT_REGISTRY_PATH = "registry/api-docs-draft-registry.json"


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


def create_dooray_page(api_key: str, wiki_id: str, parent_page_id: str,
                       title: str, content: str, base_url: str) -> dict:
    payload = {
        "parentPageId": parent_page_id,
        "subject": title,
        "body": {"content": content, "mimeType": "text/x-markdown"},
        "referrers": [],
    }
    url = f"{base_url}/wiki/v1/wikis/{wiki_id}/pages"
    print(f"[INFO] Draft 페이지 생성: {title}")
    return dooray_request("POST", url, api_key, payload)


def delete_dooray_page(api_key: str, wiki_id: str, page_id: str, base_url: str):
    url = f"{base_url}/wiki/v1/wikis/{wiki_id}/pages/{page_id}"
    print(f"[INFO] 기존 Draft 삭제: pageId={page_id}")
    try:
        dooray_request("DELETE", url, api_key)
    except SystemExit:
        print(f"[WARN] 기존 Draft 삭제 실패 (이미 삭제됐을 수 있음): {page_id}")


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


def git_commit_and_push(repo_dir: str, files: list, message: str):
    env = {**os.environ}

    def run(cmd):
        result = subprocess.run(cmd, cwd=repo_dir, capture_output=True, text=True, env=env)
        if result.returncode != 0:
            print(f"[WARN] git 명령 실패: {' '.join(cmd)}\n{result.stderr}")
        return result

    run(["git", "config", "user.name", "github-actions[bot]"])
    run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"])
    for f in files:
        run(["git", "add", f])
    result = run(["git", "commit", "-m", message])
    if "nothing to commit" in result.stdout + result.stderr:
        print("[INFO] registry 변경 없음 — 커밋 스킵")
        return
    push = run(["git", "push"])
    if push.returncode != 0:
        print(f"[WARN] registry push 실패: {push.stderr}")
    else:
        print("[INFO] registry 커밋 완료")


def checkout_docs_repo(token: str):
    if os.path.exists(DOCS_REPO_DIR):
        import shutil
        shutil.rmtree(DOCS_REPO_DIR)
    url = f"https://x-access-token:{token}@github.com/{DOCS_REPO}.git"
    result = subprocess.run(
        ["git", "clone", "--depth=1", url, DOCS_REPO_DIR],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"[WARN] rest-api-docs repo checkout 실패: {result.stderr}")
        return False
    print(f"[INFO] rest-api-docs repo checkout 완료")
    return True


def main():
    api_key = os.environ.get("DOORAY_API_KEY", "")
    wiki_id = os.environ.get("DOORAY_WIKI_ID", "")
    project_id = os.environ.get("DOORAY_PROJECT_ID", "")
    parent_page_id = os.environ.get("DOORAY_DRAFT_PARENT_PAGE_ID", "")
    base_url = os.environ.get("DOORAY_BASE_URL", "https://api.dooray.com")
    title = os.environ.get("TITLE", "")
    doc_content = os.environ.get("DOC_CONTENT", "")
    url_hint = os.environ.get("URL_HINT", "")
    registry_key = os.environ.get("API_KEY", "")
    repo_name = os.environ.get("REPO_NAME", "")
    github_token = os.environ.get("ORG_GITHUB_TOKEN", "")

    required = {
        "DOORAY_API_KEY": api_key,
        "DOORAY_WIKI_ID": wiki_id,
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

    # rest-api-docs repo checkout (registry 업데이트용)
    registry_available = False
    if github_token:
        registry_available = checkout_docs_repo(github_token)

    # draft-registry에서 기존 draft 확인 → 있으면 먼저 삭제
    draft_registry_file = os.path.join(DOCS_REPO_DIR, DRAFT_REGISTRY_PATH)
    draft_registry = {}
    if registry_available:
        draft_registry = read_registry(draft_registry_file)
        if registry_key and repo_name:
            existing = draft_registry.get(repo_name, {}).get(registry_key)
            if existing:
                delete_dooray_page(api_key, wiki_id, existing["page_id"], base_url)

    # 새 Draft 페이지 생성
    result = create_dooray_page(api_key, wiki_id, parent_page_id, title, full_content, base_url)
    page_id = result.get("result", {}).get("id", "")
    page_url = f"{base_url}/wiki/{project_id}/{page_id}"

    # draft-registry 업데이트
    if registry_available and registry_key and repo_name and page_id:
        if repo_name not in draft_registry:
            draft_registry[repo_name] = {}
        draft_registry[repo_name][registry_key] = {"page_id": page_id, "url_hint": url_hint}
        write_registry(draft_registry_file, draft_registry)
        git_commit_and_push(
            DOCS_REPO_DIR,
            [DRAFT_REGISTRY_PATH],
            f"chore: update draft registry - {registry_key} [skip ci]",
        )

    set_output("page_id", page_id)
    set_output("page_url", page_url)
    set_output("wiki_category", wiki_category)
    set_output("draft_page_id", page_id)
    set_output("api_key", registry_key)

    print("Dooray Draft 페이지 생성 완료")
    print(f"  제목: {title}")
    print(f"  분류: {wiki_category}")
    print(f"  페이지 ID: {page_id}")
    print(f"  API Key: {registry_key or '없음'}")


if __name__ == "__main__":
    main()
