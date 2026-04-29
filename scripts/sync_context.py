#!/usr/bin/env python3
"""
billing-context AI Context 동기화 스크립트.
각 서비스 레포의 변경을 감지하고 Claude로 ai-context를 생성/업데이트한다.
"""

import os
import sys
import json
import subprocess
from pathlib import Path


def run_claude(prompt: str, timeout: int = 600) -> int:
    result = subprocess.run(
        ["claude", "-p", "--dangerously-skip-permissions", prompt],
        timeout=timeout,
    )
    return result.returncode


def get_latest_sha(full_repo: str, branch: str) -> str:
    result = subprocess.run(
        ["gh", "api", f"repos/{full_repo}/commits/{branch}", "--jq", ".sha"],
        capture_output=True,
        text=True,
        env={**os.environ, "GH_HOST": os.environ.get("GITHUB_SERVER_URL", "").replace("https://", "").strip("/") or "github.com"},
    )
    if result.returncode != 0:
        print(f"    gh api 실패 (rc={result.returncode}): {result.stderr.strip()}")
    return result.stdout.strip() if result.returncode == 0 else ""


def clone_repo(full_repo: str, branch: str, target_dir: str) -> bool:
    gh_token = os.environ.get("GH_TOKEN", "")
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com").rstrip("/").replace("https://", "")
    url = f"https://x-access-token:{gh_token}@{server}/{full_repo}.git"
    result = subprocess.run(
        ["git", "clone", "--depth=5", f"--branch={branch}", url, target_dir],
    )
    return result.returncode == 0


def get_changed_files(source_dir: str) -> str:
    result = subprocess.run(
        ["git", "-C", source_dir, "diff", "HEAD~1", "--name-only"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def sync_repo(repo_name: str, org: str, branch: str, force: bool) -> bool:
    full_repo = f"{org}/{repo_name}"

    latest_sha = get_latest_sha(full_repo, branch)
    if not latest_sha:
        print(f"  ⚠️  {repo_name}: SHA 조회 실패 — 스킵")
        return False

    state_file = Path(f"state/{repo_name}.sha")
    stored_sha = state_file.read_text().strip() if state_file.exists() else ""

    if latest_sha == stored_sha and not force:
        print(f"  ↩️  변경 없음 — 스킵")
        return False

    short_old = stored_sha[:7] if stored_sha else "없음"
    short_new = latest_sha[:7]
    print(f"  🔄 변경 감지 ({short_old}... → {short_new}...)")

    source_dir = f"_source/{repo_name}"
    subprocess.run(["rm", "-rf", source_dir])
    if not clone_repo(full_repo, branch, source_dir):
        print(f"  ❌ {repo_name}: 클론 실패 — 스킵")
        return False

    context_exists = Path(f"{repo_name}/ai-context/domain-overview.md").exists()

    if context_exists and not force:
        print(f"  📝 부분 업데이트 실행 (기존 context 있음)")
        changed_files = get_changed_files(source_dir)
        prompt = f"""\
_source/{repo_name}/ 디렉토리에 {repo_name} 레포의 {branch} 브랜치 소스코드가 있다.
.claude/commands/update-ai-context.md 절차에 따라
아래 변경된 파일을 분석해서 관련 ai-context만 부분 업데이트해줘.

변경된 파일 목록:
{changed_files}

소스 기준 경로: _source/{repo_name}/
기존 ai-context 경로: {repo_name}/ai-context/
업데이트된 파일은 {repo_name}/ai-context/ 에 저장해줘.
완료 후 업데이트된 파일 목록을 출력해줘."""
    else:
        print(f"  🆕 최초 생성 실행")
        Path(f"{repo_name}/ai-context").mkdir(parents=True, exist_ok=True)
        prompt = f"""\
_source/{repo_name}/ 디렉토리에 {repo_name} 레포의 {branch} 브랜치 소스코드가 있다.
.claude/commands/generate-ai-context.md 절차에 따라
이 레포의 ai-context를 처음부터 생성해줘.
소스 기준 경로: _source/{repo_name}/
생성된 파일은 {repo_name}/ai-context/ 에 저장해줘.
완료 후 생성된 파일 목록을 출력해줘."""

    rc = run_claude(prompt)
    if rc != 0:
        print(f"  ❌ Claude 실행 실패 (종료 코드: {rc}) — SHA 저장 안 함")
        return False

    state_file.parent.mkdir(exist_ok=True)
    state_file.write_text(latest_sha)
    print(f"  ✅ {repo_name} 완료")
    return True


def update_root_context():
    print("\n🌐 루트 ai-context 갱신 중...")
    prompt = """\
billing-context 레포 구조:
- 각 서비스 ai-context: {서비스명}/ai-context/
- 루트 ai-context 저장 위치: .claude/ai-context/

.claude/commands/generate-root-ai-context.md 절차에 따라
각 서비스의 ai-context를 읽어 루트 ai-context를 생성/갱신해줘.
대상 파일: .claude/ai-context/service-map.md, dependency-graph.md, interface-contracts.json, routing-guide.md
변경이 없는 파일은 수정하지 말 것."""
    run_claude(prompt)


def main():
    with open("repos.json") as f:
        config = json.load(f)

    org = config["org"]
    target_repo = os.environ.get("INPUT_REPO", "").strip()
    force = os.environ.get("INPUT_FORCE", "false").lower() == "true"

    repos = config["repos"]
    if target_repo:
        repos = [r for r in repos if r["name"] == target_repo]

    if not repos:
        print("❌ 처리할 레포가 없습니다 (repos.yml 확인 또는 repo-name 입력값 확인)")
        sys.exit(1)

    changed_count = 0
    for repo in repos:
        name = repo["name"]
        branch = repo.get("branch", "develop")
        print(f"\n════════════════════════════════════")
        print(f"🔍 {name} 확인 중...")

        if sync_repo(name, org, branch, force):
            changed_count += 1

    if changed_count > 0:
        update_root_context()

    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"changed_count={changed_count}\n")

    print(f"\n✅ 완료 — 업데이트된 레포: {changed_count}개")


if __name__ == "__main__":
    main()
