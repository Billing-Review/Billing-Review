#!/usr/bin/env python3
"""
reusable-publish-final.py

Draft 페이지를 검토 후 본 API 문서 위키에 반영합니다.

동작:
  1. 서비스 repo에서 main-registry 조회
     - api_key가 있으면 → 기존 페이지 내용 업데이트
     - 없으면 → url_hint 기반 parent 하위에 새 페이지 생성
  2. main-registry 추가/갱신 + draft-registry에서 제거 후 커밋
  3. Dooray Draft 페이지 삭제

환경 변수:
  DOORAY_API_KEY                  Dooray API 토큰
  DOORAY_WIKI_ID                  Dooray 위키 ID
  DOORAY_PROJECT_ID               Dooray 프로젝트 ID
  DOORAY_DRAFT_PAGE_ID            삭제할 Draft 페이지 ID
  DOORAY_INTERNAL_PARENT_PAGE_ID  사내 API 위키 부모 페이지 ID
  DOORAY_EXTERNAL_PARENT_PAGE_ID  사외 API 위키 부모 페이지 ID
  DOORAY_DEFAULT_PARENT_PAGE_ID   기본 위키 부모 페이지 ID
  TITLE                           위키 페이지 제목
  DOC_CONTENT                     마크다운 문서 본문
  URL_HINT                        위키 경로 분류 힌트
  API_KEY                         레지스트리 키 (예: GET /api/v1/todos)
  REPO_NAME                       서비스 저장소 이름 (org/repo)
  ORG_GITHUB_TOKEN                GitHub 인증 토큰
  GITHUB_OUTPUT                   GitHub Actions 출력 파일 경로
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

MAIN_REGISTRY_PATH = ".github/api-docs-registry.json"
DRAFT_REGISTRY_PATH = ".github/api-docs-draft-registry.json"
SERVICE_REPO_DIR = "service-repo"


def set_output(name: str, value: str):
    output_file = os.environ.get("GITHUB_OUTPUT", "")
    if not output_file:
        print(f"OUTPUT {name}={value}")
        return
    with open(output_file, "a") as f:
        f.write(f"{name}={value}\n")


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
                       title: str, content: str, base_url: str) -> str:
    payload = {
        "parentPageId": parent_page_id,
        "subject": title,
        "body": {"content": content, "mimeType": "text/x-markdown"},
        "referrers": [],
    }
    url = f"{base_url}/wiki/v1/wikis/{wiki_id}/pages"
    print(f"[INFO] 본 페이지 생성: {title}")
    result = dooray_request("POST", url, api_key, payload)
    return result.get("result", {}).get("id", "")


def update_dooray_page(api_key: str, wiki_id: str, page_id: str,
                       title: str, content: str, base_url: str):
    payload = {
        "subject": title,
        "body": {"content": content, "mimeType": "text/x-markdown"},
    }
    url = f"{base_url}/wiki/v1/wikis/{wiki_id}/pages/{page_id}"
    print(f"[INFO] 본 페이지 업데이트: pageId={page_id}")
    dooray_request("PUT", url, api_key, payload)


def delete_dooray_page(api_key: str, wiki_id: str, page_id: str, base_url: str):
    if not page_id:
        return
    url = f"{base_url}/wiki/v1/wikis/{wiki_id}/pages/{page_id}"
    print(f"[INFO] Draft 페이지 삭제: pageId={page_id}")
    try:
        dooray_request("DELETE", url, api_key)
    except SystemExit:
        print(f"[WARN] Draft 삭제 실패 (이미 삭제됐을 수 있음): {page_id}")


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


def checkout_service_repo(repo_name: str, token: str) -> bool:
    if os.path.exists(SERVICE_REPO_DIR):
        import shutil
        shutil.rmtree(SERVICE_REPO_DIR)
    url = f"https://x-access-token:{token}@github.com/{repo_name}.git"
    result = subprocess.run(
        ["git", "clone", "--depth=1", url, SERVICE_REPO_DIR],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"[ERROR] 서비스 repo checkout 실패: {result.stderr}", file=sys.stderr)
        return False
    print(f"[INFO] 서비스 repo checkout 완료: {repo_name}")
    return True


def get_target_parent(url_hint: str) -> str:
    if url_hint == "internal":
        parent = os.environ.get("DOORAY_INTERNAL_PARENT_PAGE_ID", "")
    elif url_hint == "external":
        parent = os.environ.get("DOORAY_EXTERNAL_PARENT_PAGE_ID", "")
    else:
        parent = os.environ.get("DOORAY_DEFAULT_PARENT_PAGE_ID", "")

    if not parent:
        print(f"[WARN] url_hint='{url_hint}'에 대응하는 PARENT_PAGE_ID 환경 변수가 없음 — DOORAY_DEFAULT_PARENT_PAGE_ID 사용")
        parent = os.environ.get("DOORAY_DEFAULT_PARENT_PAGE_ID", "")
    if not parent:
        print("[ERROR] 본 페이지 부모 ID를 찾을 수 없습니다.", file=sys.stderr)
        sys.exit(1)
    return parent


def main():
    dooray_api_key = os.environ.get("DOORAY_API_KEY", "")
    wiki_id = os.environ.get("DOORAY_WIKI_ID", "")
    project_id = os.environ.get("DOORAY_PROJECT_ID", "")
    draft_page_id = os.environ.get("DOORAY_DRAFT_PAGE_ID", "")
    base_url = os.environ.get("DOORAY_BASE_URL", "https://api.dooray.com")
    title = os.environ.get("TITLE", "")
    doc_content = os.environ.get("DOC_CONTENT", "")
    url_hint = os.environ.get("URL_HINT", "")
    registry_key = os.environ.get("API_KEY", "")
    repo_name = os.environ.get("REPO_NAME", "")
    github_token = os.environ.get("ORG_GITHUB_TOKEN", "")

    required = {
        "DOORAY_API_KEY": dooray_api_key,
        "DOORAY_WIKI_ID": wiki_id,
        "DOORAY_PROJECT_ID": project_id,
        "TITLE": title,
        "DOC_CONTENT": doc_content,
        "REPO_NAME": repo_name,
        "ORG_GITHUB_TOKEN": github_token,
    }
    for var, val in required.items():
        if not val:
            print(f"{var} 환경 변수가 필요합니다.", file=sys.stderr)
            sys.exit(1)

    # 서비스 repo checkout
    if not checkout_service_repo(repo_name, github_token):
        sys.exit(1)

    main_registry_file = os.path.join(SERVICE_REPO_DIR, MAIN_REGISTRY_PATH)
    draft_registry_file = os.path.join(SERVICE_REPO_DIR, DRAFT_REGISTRY_PATH)

    main_registry = read_registry(main_registry_file)
    draft_registry = read_registry(draft_registry_file)

    # 본 페이지 제목에서 [API Draft] 접두사 제거
    publish_title = title.replace("[API Draft] ", "").replace("[API Draft]", "").strip()

    # 기존 페이지 있으면 업데이트, 없으면 생성
    if registry_key and registry_key in main_registry:
        existing_page_id = main_registry[registry_key]
        update_dooray_page(dooray_api_key, wiki_id, existing_page_id, publish_title, doc_content, base_url)
        final_page_id = existing_page_id
        action = "updated"
    else:
        target_parent = get_target_parent(url_hint)
        final_page_id = create_dooray_page(dooray_api_key, wiki_id, target_parent, publish_title, doc_content, base_url)
        action = "created"

    if not final_page_id:
        print("[ERROR] 페이지 ID를 가져올 수 없습니다.", file=sys.stderr)
        sys.exit(1)

    # registry 업데이트
    if registry_key:
        main_registry[registry_key] = final_page_id
        write_registry(main_registry_file, main_registry)

        if registry_key in draft_registry:
            del draft_registry[registry_key]
            write_registry(draft_registry_file, draft_registry)

        git_commit_and_push(
            SERVICE_REPO_DIR,
            [MAIN_REGISTRY_PATH, DRAFT_REGISTRY_PATH],
            f"chore: publish api doc - {registry_key} [skip ci]",
        )

    # Draft 삭제
    delete_dooray_page(dooray_api_key, wiki_id, draft_page_id, base_url)

    page_url = f"{base_url}/wiki/{project_id}/{final_page_id}"
    set_output("page_id", final_page_id)
    set_output("page_url", page_url)

    print(f"\n본 페이지 반영 완료 ({action})")
    print(f"  제목: {publish_title}")
    print(f"  API Key: {registry_key or '없음'}")
    print(f"  페이지 ID: {final_page_id}")


if __name__ == "__main__":
    main()
