#!/usr/bin/env python3
"""
Claude PR Review Script

공통 Skills + repo별 추가 규칙을 합쳐서 Claude에게 코드 리뷰를 요청하고
결과를 GitHub Code Review API로 인라인 코멘트 + PR 전체 리뷰로 게시한다.

디렉토리 구조 (Organization .github 리포지토리):
    review-config/
    ├── base-rules.md              ← 공통 리뷰 규칙
    ├── conventions.md             ← 공통 코딩 컨벤션
    ├── prompt-template.md         ← Claude 역할/톤 정의 (선택)
    ├── skills/                    ← 파일 타입별 Skills (선택)
    │   ├── java-spring.md
    │   ├── mybatis.md
    │   ├── vue3-frontend.md
    │   ├── github-actions.md
    │   └── xml-config.md
    └── repo/
        ├── payment-service.md     ← 리포별 추가 규칙 (선택)
        └── order-api.md

사용법:
    python3 claude_review.py <pr_number> <repo_full_name> [--dry-run]

예시:
    python3 claude_review.py 42 dev-team/payment-service
    python3 claude_review.py 42 dev-team/payment-service --dry-run
"""

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Set

# ============================================================
# 상수
# ============================================================

SHARED_CONFIG_DIR = os.environ.get("SHARED_CONFIG_DIR", ".shared-config/review-config")

BASE_RULES_PATH      = os.path.join(SHARED_CONFIG_DIR, "base-rules.md")
CONVENTIONS_PATH     = os.path.join(SHARED_CONFIG_DIR, "conventions.md")
PROMPT_TEMPLATE_PATH = os.path.join(SHARED_CONFIG_DIR, "prompt-template.md")
SKILLS_DIR           = os.path.join(SHARED_CONFIG_DIR, "skills")
REPO_CONFIG_DIR      = os.path.join(SHARED_CONFIG_DIR, "repo")

MAX_DIFF_LENGTH  = int(os.environ.get("MAX_DIFF_LENGTH", "100000"))
MAX_SKILL_CHARS  = int(os.environ.get("MAX_SKILL_CHARS", "5000"))
MAX_SKILLS_TOTAL = int(os.environ.get("MAX_SKILLS_TOTAL", "15000"))
CLAUDE_MODEL     = os.environ.get("CLAUDE_MODEL", "claude-opus-4-5-20251101")
CLAUDE_TIMEOUT   = int(os.environ.get("CLAUDE_TIMEOUT", "300"))

MAX_SUMMARY_FALLBACK_LENGTH = 5000

DIFF_GIT_PATTERN = re.compile(r"diff --git a/(.+?) b/(.+?)$")

SEVERITY_EMOJI = {
    "CRITICAL":   "🔴",
    "HIGH":       "🟠",
    "MEDIUM":     "🟡",
    "LOW":        "🔵",
    "SUGGESTION": "💡",
}

EXTENSION_TO_FILE_TYPE: Dict[str, str] = {
    ".java":       "java",
    ".vue":        "vue",
    ".js":         "javascript",
    ".ts":         "javascript",
    ".css":        "css",
    ".scss":       "css",
    ".yml":        "yaml",
    ".yaml":       "yaml",
    ".json":       "json",
    ".xml":        "xml",
    ".properties": "properties",
    ".py":         "python",
    ".sh":         "shell",
    ".sql":        "sql",
}

ALL_REVIEWABLE_EXTENSIONS: Set[str] = set(EXTENSION_TO_FILE_TYPE.keys())

FILE_TYPE_TO_SKILL: Dict[str, str] = {
    "java":       "java-spring",
    "vue":        "vue3-frontend",
    "javascript": "vue3-frontend",
    "yaml":       "github-actions",
    "xml":        "mybatis",
}


# ============================================================
# 데이터 클래스
# ============================================================

@dataclass
class DiffAnalysis:
    filtered_diff: str
    files: Set[str]
    file_types: Set[str]


# ============================================================
# 인증 확인
# ============================================================

def verify_claude_auth() -> None:
    oauth_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if oauth_token:
        print("[INFO] Claude 인증: CLAUDE_CODE_OAUTH_TOKEN 환경변수 사용")
    else:
        print("[WARN] CLAUDE_CODE_OAUTH_TOKEN 미설정 → 로컬 claude login 세션으로 시도", file=sys.stderr)


def verify_gh_auth() -> None:
    gh_host = os.environ.get("GH_HOST", "github.com")
    gh_token = os.environ.get("GH_TOKEN") or os.environ.get("GH_ENTERPRISE_TOKEN")
    if gh_token:
        print(f"[INFO] GH 인증: token 사용 ({gh_host}), prefix={gh_token[:4]}...")
    else:
        print("[WARN] GH_TOKEN 미설정 → 로컬 gh auth 사용", file=sys.stderr)


# ============================================================
# GitHub CLI 래퍼
# ============================================================

def run_gh(args: list) -> str:
    result = subprocess.run(["gh"] + args, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ERROR] gh {' '.join(args)}\n  stderr: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return result.stdout


def get_pr_info(pr_number: str) -> dict:
    output = run_gh([
        "pr", "view", pr_number,
        "--json", "headRefOid,baseRefOid,headRepository,headRepositoryOwner,title,body",
    ])
    data = json.loads(output)
    return {
        "owner":      data["headRepositoryOwner"]["login"],
        "repo":       data["headRepository"]["name"],
        "commit_sha": data["headRefOid"],
        "base_sha":   data["baseRefOid"],
        "title":      data.get("title", ""),
        "body":       data.get("body", "") or "",
    }


def get_pr_diff(pr_number: str) -> str:
    return run_gh(["pr", "diff", pr_number])


def get_existing_claude_review_commit(pr_number: str, pr_info: dict) -> Optional[str]:
    """이전 Claude 리뷰의 마지막 커밋 SHA를 반환한다."""
    owner, repo = pr_info["owner"], pr_info["repo"]
    try:
        result = subprocess.run(
            [
                "gh", "api",
                f"repos/{owner}/{repo}/pulls/{pr_number}/reviews",
                "--paginate", "-q",
                '.[] | select(.body | contains("🤖 AI 코드 리뷰"))',
            ],
            capture_output=True, text=True,
        )
        last_commit = None
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                review = json.loads(line)
                if review.get("commit_id"):
                    last_commit = review["commit_id"]
            except json.JSONDecodeError:
                pass
        return last_commit
    except Exception as e:
        print(f"[WARN] 기존 리뷰 조회 실패: {e}", file=sys.stderr)
        return None


def get_incremental_diff(pr_number: str, since_commit: str, head_commit: str) -> Optional[str]:
    result = subprocess.run(
        ["git", "diff", f"{since_commit}..{head_commit}"],
        capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout
    return None


def post_review(pr_number: str, pr_info: dict, review_data: dict, diff_mappings: dict) -> None:
    """
    GitHub Code Review API로 게시한다.
    - body: PR 전체 마크다운 리뷰 (요약, 잘한점, Must Fix 등)
    - comments: 코드 인라인 코멘트 (Must Fix / Should Fix 항목)
    """
    owner, repo, commit_sha = pr_info["owner"], pr_info["repo"], pr_info["commit_sha"]

    # 인라인 코멘트 유효성 검증
    valid_comments = []
    skipped = []
    for c in review_data.get("comments", []):
        path, line = c.get("path", ""), c.get("line", 0)
        if path in diff_mappings and line in diff_mappings[path]:
            emoji = SEVERITY_EMOJI.get(c.get("severity", ""), "💡")
            inline_body = c.get("body", "").replace("\\n", "\n