#!/usr/bin/env python3
"""
Claude PR Review Script

공통 Skills + repo별 추가 규칙을 합쳐서 Claude에게 코드 리뷰를 요청하고
결과를 GitHub Code Review API로 인라인 코멘트로 게시한다.

디렉토리 구조 (Organization .github 리포지토리):
    review-config/
    ├── base-rules.md              ← 공통 리뷰 규칙
    ├── conventions.md             ← 공통 코딩 컨벤션
    ├── prompt-template.md         ← 시스템 프롬프트
    ├── skills/                    ← 파일 타입별 Skills
    │   ├── java-spring.md
    │   ├── mybatis.md
    │   ├── vue3-frontend.md
    │   ├── github-actions.md
    │   └── xml-config.md
    └── repo/
        ├── payment-service.md     ← 리포별 추가 규칙
        └── order-api.md

사용법:
    python3 claude_review.py <pr_number> [--dry-run]
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

BASE_RULES_PATH       = os.path.join(SHARED_CONFIG_DIR, "base-rules.md")
CONVENTIONS_PATH      = os.path.join(SHARED_CONFIG_DIR, "conventions.md")
PROMPT_TEMPLATE_PATH  = os.path.join(SHARED_CONFIG_DIR, "prompt-template.md")
SKILLS_DIR            = os.path.join(SHARED_CONFIG_DIR, "skills")
REPO_CONFIG_DIR       = os.path.join(SHARED_CONFIG_DIR, "repo")

MAX_DIFF_LENGTH   = int(os.environ.get("MAX_DIFF_LENGTH", "100000"))
MAX_SKILL_CHARS   = int(os.environ.get("MAX_SKILL_CHARS", "5000"))   # skill 1개당 최대
MAX_SKILLS_TOTAL  = int(os.environ.get("MAX_SKILLS_TOTAL", "15000"))  # 전체 skills 합산 최대
CLAUDE_MODEL      = os.environ.get("CLAUDE_MODEL", "claude-opus-4-5-20251101")
CLAUDE_TIMEOUT    = int(os.environ.get("CLAUDE_TIMEOUT", "300"))

MAX_SUMMARY_FALLBACK_LENGTH = 500

DIFF_GIT_PATTERN = re.compile(r"diff --git a/(.+?) b/(.+?)$")

SEVERITY_EMOJI = {
    "CRITICAL": "🔴",
    "HIGH":     "🟠",
    "MEDIUM":   "🟡",
    "LOW":      "🔵",
    "SUGGESTION": "💡",
}

# 확장자 → 파일 타입
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

# 파일 타입 → Skills 파일명 매핑
# 감지된 파일 타입에 해당하는 skill만 주입된다
FILE_TYPE_TO_SKILL: Dict[str, str] = {
    "java":       "java-spring",
    "vue":        "vue3-frontend",
    "javascript": "vue3-frontend",
    "yaml":       "github-actions",   # .github/ 경로일 때만 (필터링은 코드에서)
    "xml":        "mybatis",          # mybatis 키워드 있을 때만 (필터링은 코드에서)
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
        print(f"[INFO] GH 인증: token 환경변수 사용 ({gh_host}), prefix={gh_token[:4]}...")
    else:
        print(f"[WARN] GH_TOKEN 미설정 → 로컬 gh auth 사용", file=sys.stderr)


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
        "--json", "headRefOid,baseRefOid,headRepository,headRepositoryOwner",
    ])
    data = json.loads(output)
    return {
        "owner":      data["headRepositoryOwner"]["login"],
        "repo":       data["headRepository"]["name"],
        "commit_sha": data["headRefOid"],
        "base_sha":   data["baseRefOid"],
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
                '.[] | select(.body | contains("Claude Code Review"))',
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
    owner, repo, commit_sha = pr_info["owner"], pr_info["repo"], pr_info["commit_sha"]

    valid_comments = []
    for c in review_data.get("comments", []):
        path, line = c.get("path", ""), c.get("line", 0)
        if path in diff_mappings and line in diff_mappings[path]:
            emoji = SEVERITY_EMOJI.get(c.get("severity", ""), "💡")
            valid_comments.append({
                "path": path,
                "line": line,
                "body": f"{emoji} **{c.get('severity', '')}**\n\n{c.get('body', '')}",
            })

    summary = review_data.get("summary", "코드 리뷰가 완료되었습니다.")
    payload = {
        "commit_id": commit_sha,
        "body": f"## 🤖 Claude Code Review\n\n{summary}\n\n---\n_Automated review by Claude_",
        "event": "COMMENT",
        "comments": valid_comments,
    }

    try:
        result = subprocess.run(
            [
                "gh", "api",
                f"repos/{owner}/{repo}/pulls/{pr_number}/reviews",
                "-X", "POST",
                "-H", "Accept: application/vnd.github+json",
                "--input", "-",
            ],
            input=json.dumps(payload),
            capture_output=True, text=True, check=True,
        )
        print(f"[INFO] Code review 게시 완료 (인라인 {len(valid_comments)}개)")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] 리뷰 게시 실패: {e.stderr}", file=sys.stderr)
        sys.exit(1)


# ============================================================
# Diff 처리
# ============================================================

def analyze_diff(diff: str) -> DiffAnalysis:
    """diff 1회 순회 → 필터링된 diff + 파일 목록 + 파일 타입 동시 추출."""
    files: Set[str] = set()
    file_types: Set[str] = set()
    filtered_lines = []
    include_file = False

    for line in diff.split("\n"):
        if line.startswith("diff --git"):
            match = DIFF_GIT_PATTERN.search(line)
            if match:
                file_path = match.group(2)
                files.add(file_path)
                ext = os.path.splitext(file_path)[1]
                file_type = EXTENSION_TO_FILE_TYPE.get(ext)
                if file_type:
                    file_types.add(file_type)
                include_file = ext in ALL_REVIEWABLE_EXTENSIONS
            else:
                include_file = False
        if include_file:
            filtered_lines.append(line)

    return DiffAnalysis(
        filtered_diff="\n".join(filtered_lines),
        files=files,
        file_types=file_types,
    )


def parse_exclude_patterns(repo_config_content: str) -> list:
    """repo별 md에서 '리뷰 제외' 섹션의 패턴을 파싱한다."""
    patterns = []
    in_section = False
    for line in repo_config_content.split("\n"):
        stripped = line.strip()
        if "리뷰 제외" in stripped or "리뷰에서 제외" in stripped:
            in_section = True
            continue
        if in_section:
            if stripped.startswith("#"):
                break
            if stripped.startswith("- "):
                p = stripped[2:].strip().strip("`")
                if p:
                    patterns.append(p)
    return patterns


def filter_diff_by_patterns(diff: str, patterns: list) -> str:
    """제외 패턴에 해당하는 파일 diff를 제거한다."""
    from fnmatch import fnmatch
    if not patterns:
        return diff
    filtered, skip = [], False
    for line in diff.split("\n"):
        if line.startswith("diff --git"):
            file_path = line.split(" b/")[-1] if " b/" in line else ""
            skip = any(fnmatch(file_path, p) for p in patterns)
        if not skip:
            filtered.append(line)
    return "\n".join(filtered)


def parse_diff_line_mapping(diff: str) -> dict:
    """diff에서 파일별 변경된 라인 번호를 추출한다 (인라인 코멘트 유효성 검증용)."""
    mappings: Dict[str, dict] = {}
    current_file = None
    current_line = 0
    for line in diff.split("\n"):
        if line.startswith("diff --git"):
            match = DIFF_GIT_PATTERN.search(line)
            if match:
                current_file = match.group(2)
                mappings[current_file] = {}
        elif line.startswith("@@"):
            match = re.search(r"\+(\d+)", line)
            if match:
                current_line = int(match.group(1))
        elif current_file:
            if not line.startswith("-"):
                if line.startswith("+"):
                    mappings[current_file][current_line] = True
                current_line += 1
    return mappings


# ============================================================
# 설정 파일 로드
# ============================================================

def read_file_safe(path: str) -> str:
    p = Path(path)
    if p.exists():
        content = p.read_text(encoding="utf-8").strip()
        print(f"[INFO] Loaded: {path}")
        return content
    print(f"[WARN] Not found: {path}", file=sys.stderr)
    return ""


def load_skills(file_types: Set[str], files: Set[str], diff: str) -> Dict[str, str]:
    """
    감지된 파일 타입에 해당하는 skill만 선택적으로 로드한다.
    - yaml: .github/ 경로일 때만
    - xml:  mybatis 키워드 있을 때만
    각 skill은 MAX_SKILL_CHARS, 전체 합산은 MAX_SKILLS_TOTAL로 제한.
    """
    skills: Dict[str, str] = {}
    total_chars = 0

    for file_type in sorted(file_types):
        skill_name = FILE_TYPE_TO_SKILL.get(file_type)
        if not skill_name:
            continue

        # yaml → github-actions: .github/ 경로 파일이 있을 때만
        if file_type == "yaml" and not any(".github/" in f for f in files):
            continue

        # xml → mybatis: mybatis 관련 키워드가 diff에 있을 때만
        if file_type == "xml" and not any(
            kw in diff for kw in ["<mapper", "<select", "<insert", "<update", "<delete", "mybatis"]
        ):
            skill_name = "xml-config"  # mybatis 아닌 일반 xml

        skill_path = os.path.join(SKILLS_DIR, f"{skill_name}.md")
        content = read_file_safe(skill_path)
        if not content:
            continue

        # 길이 제한
        if len(content) > MAX_SKILL_CHARS:
            content = content[:MAX_SKILL_CHARS] + "\n...(이하 생략)"

        if total_chars + len(content) > MAX_SKILLS_TOTAL:
            print(f"[WARN] Skills 총 길이 초과로 '{skill_name}' 생략", file=sys.stderr)
            break

        skills[skill_name] = content
        total_chars += len(content)

    return skills


def find_repo_config(repo_full_name: str) -> str:
    repo_name = repo_full_name.split("/")[-1]
    return read_file_safe(os.path.join(REPO_CONFIG_DIR, f"{repo_name}.md"))


# ============================================================
# 프롬프트 조립
# ============================================================

def build_prompt(diff: str, pr_info: dict, repo_full_name: str,
                 file_types: Set[str], files: Set[str]) -> str:
    sections = []

    # 1) 시스템 프롬프트
    template = read_file_safe(PROMPT_TEMPLATE_PATH)
    if template:
        sections.append(template)

    # 2) 공통 규칙
    base_rules = read_file_safe(BASE_RULES_PATH)
    if base_rules:
        sections.append(f"## 공통 리뷰 규칙\n\n{base_rules}")

    conventions = read_file_safe(CONVENTIONS_PATH)
    if conventions:
        sections.append(f"## 공통 코딩 컨벤션\n\n{conventions}")

    # 3) Skills (파일 타입별 선택 주입)
    skills = load_skills(file_types, files, diff)
    if skills:
        skill_block = "\n\n".join(
            f"### {name}\n{content}" for name, content in skills.items()
        )
        sections.append(f"## 리뷰 참고 자료 (Skills)\n\n{skill_block}")
        print(f"[INFO] 주입된 Skills: {list(skills.keys())}")
    else:
        print("[INFO] 주입된 Skills: 없음")

    # 4) repo별 추가 규칙 (있을 때만)
    repo_config = find_repo_config(repo_full_name)
    if repo_config:
        sections.append(f"## 이 리포지토리 추가 규칙\n\n{repo_config}")

    # 5) 출력 규칙 + diff
    diff_limited = diff[:MAX_DIFF_LENGTH]
    if len(diff) > MAX_DIFF_LENGTH:
        diff_limited += f"\n\n...(이하 {len(diff) - MAX_DIFF_LENGTH}자 생략)"

    sections.append(f"""## 출력 규칙 (필수)
1. 순수 JSON만 출력 (코드블록 사용 금지)
2. 코멘트는 최대 5개까지만
3. body는 한 줄, 100자 이내
4. line은 diff에서 + 로 시작하는 라인 번호만 사용

## JSON 형식
{{"summary":"요약 2문장","comments":[{{"path":"파일경로","line":숫자,"severity":"HIGH","body":"이모지 내용"}}]}}

severity별 이모지: CRITICAL=🔴 HIGH=🟠 MEDIUM=🟡 LOW=🔵 SUGGESTION=💡

## PR Diff
```diff