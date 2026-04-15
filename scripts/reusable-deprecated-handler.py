#!/usr/bin/env python3
"""
reusable-deprecated-handler.py

삭제된 API 엔드포인트를 Dooray 위키 페이지에 @Deprecated 처리합니다.

동작:
  1. DELETED_ENDPOINTS 환경 변수에서 엔드포인트 목록 읽기 (줄바꿈 구분)
  2. per-repo registry(api-docs-registry.json)에서 각 URL 조회
  3. Registry에 있는 URL의 Dooray 페이지 상단에 @Deprecated(날짜) 추가
  4. Registry 항목에 deprecated: true, deprecated_at 기록
  5. registry 변경 커밋 ([skip ci])
  6. Actions Summary에 처리 결과 출력

환경 변수:
  DOORAY_API_KEY    Dooray API 토큰
  DOORAY_WIKI_ID    Dooray 위키 ID
  DELETED_ENDPOINTS 삭제된 엔드포인트 목록 (줄바꿈 구분, 예: "GET /api/v1/todos\nPOST /api/v1/todos")
  REPO_NAME         서비스 저장소 이름 (org/repo)
  GITHUB_STEP_SUMMARY GitHub Actions Summary 출력 파일 경로
"""

import datetime
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import timezone, timedelta

GIT_REPO_DIR = "shared-config"
DOCS_REPO_DIR = "rest-api-docs"

KST = timezone(timedelta(hours=9))


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
        raise


def get_dooray_page(api_key: str, wiki_id: str, page_id: str, base_url: str):
    url = f"{base_url}/wiki/v1/wikis/{wiki_id}/pages/{page_id}"
    result = dooray_request("GET", url, api_key)
    result_data = result.get("result", {})
    title = result_data.get("subject", "")
    content = result_data.get("body", {}).get("content", "")
    return title, content


def update_dooray_page(api_key: str, wiki_id: str, page_id: str,
                       title: str, content: str, base_url: str):
    payload = {
        "subject": title,
        "body": {"content": content, "mimeType": "text/x-markdown"},
    }
    url = f"{base_url}/wiki/v1/wikis/{wiki_id}/pages/{page_id}"
    dooray_request("PUT", url, api_key, payload)


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


def write_summary(lines: list):
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY", "")
    content = "\n".join(lines) + "\n"
    if summary_file:
        with open(summary_file, "a") as f:
            f.write(content)
    else:
        print(content)


def main():
    dooray_api_key = os.environ.get("DOORAY_API_KEY", "")
    wiki_id = os.environ.get("DOORAY_WIKI_ID", "")
    base_url = os.environ.get("DOORAY_BASE_URL", "https://api.dooray.com")
    deleted_endpoints_raw = os.environ.get("DELETED_ENDPOINTS", "")
    repo_name = os.environ.get("REPO_NAME", "")
    repo_short_name = repo_name.split("/")[-1] if repo_name else ""

    for var, val in {"DOORAY_API_KEY": dooray_api_key, "DOORAY_WIKI_ID": wiki_id, "REPO_NAME": repo_name}.items():
        if not val:
            print(f"{var} 환경 변수가 필요합니다.", file=sys.stderr)
            sys.exit(1)

    deleted_endpoints = [ep.strip() for ep in deleted_endpoints_raw.splitlines() if ep.strip()]
    if not deleted_endpoints:
        print("[INFO] 삭제된 엔드포인트 없음 — 스킵")
        return

    registry_rel = os.path.join(DOCS_REPO_DIR, repo_short_name, "api-docs-registry.json")
    registry_path = os.path.join(GIT_REPO_DIR, registry_rel)
    registry = read_registry(registry_path)

    today = datetime.datetime.now(KST).strftime("%Y-%m-%d")
    deprecated_marker = f"@Deprecated({today})\n\n"

    processed = []
    skipped = []
    registry_changed = False

    for endpoint in deleted_endpoints:
        entry = registry.get(endpoint)
        if not entry:
            print(f"[INFO] registry 미등록 — 건너뜀: {endpoint}")
            skipped.append(endpoint)
            continue

        # entry가 문자열(page_id)이거나 dict일 수 있음
        if isinstance(entry, dict):
            page_id = entry.get("page_id", "")
            if entry.get("deprecated"):
                print(f"[INFO] 이미 Deprecated 처리됨 — 건너뜀: {endpoint}")
                skipped.append(endpoint)
                continue
        else:
            page_id = str(entry)

        if not page_id:
            print(f"[WARN] page_id 없음 — 건너뜀: {endpoint}")
            skipped.append(endpoint)
            continue

        try:
            title, content = get_dooray_page(dooray_api_key, wiki_id, page_id, base_url)
            if deprecated_marker.strip() not in content:
                new_content = deprecated_marker + content
                update_dooray_page(dooray_api_key, wiki_id, page_id, title, new_content, base_url)
                print(f"[INFO] Deprecated 처리 완료: {endpoint} (pageId={page_id})")
            else:
                print(f"[INFO] 이미 Deprecated 마커 존재: {endpoint}")

            # registry 상태 업데이트
            registry[endpoint] = {
                "page_id": page_id,
                "deprecated": True,
                "deprecated_at": today,
            }
            registry_changed = True
            processed.append(endpoint)
        except Exception as e:
            print(f"[WARN] {endpoint} 처리 실패: {e}")
            skipped.append(endpoint)

    if registry_changed:
        write_registry(registry_path, registry)
        git_commit_and_push(
            GIT_REPO_DIR,
            [registry_rel],
            f"chore: deprecated api - {repo_name} [skip ci]",
        )

    # Actions Summary 출력
    summary_lines = [
        f"## Deprecated 처리 결과 — {repo_name}",
        "",
        f"**처리된 엔드포인트 ({len(processed)}건)**",
    ]
    for ep in processed:
        summary_lines.append(f"- `{ep}` → `@Deprecated({today})` 추가")
    if skipped:
        summary_lines.append("")
        summary_lines.append(f"**건너뜀 ({len(skipped)}건, registry 미등록 또는 이미 처리됨)**")
        for ep in skipped:
            summary_lines.append(f"- `{ep}`")

    write_summary(summary_lines)


if __name__ == "__main__":
    main()
