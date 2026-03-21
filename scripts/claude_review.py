#!/usr/bin/env python3
"""
Claude PR Review Script

GitHub Actions에서 실행되며, Claude에게 코드 리뷰를 요청하고
결과를 GitHub Code Review API로 인라인 코멘트 + PR 전체 리뷰로 게시한다.

디렉토리 구조 (Organization .github 리포지토리):
    review-config/
    ├── review-prompt.md           ← 역할 + 리뷰 규칙 + 출력 형식 통합
    ├── conventions.md             ← 공통 코딩 컨벤션
    ├── skills/                    ← 기술스택별 리뷰 가이드
    │   ├── java-spring.md
    │   ├── jpa.md
    │   ├── mybatis.md
    │   ├── spring-batch.md
    │   ├── kafka.md
    │   └── redis.md
    └── repo/
        └── payment-api.md     ← 리포별 기술스택 + 추가 규칙

repo별 md 형식:
    # payment-api 리뷰 규칙

    ## 기술 스택
    - java-spring
    - jpa
    - kafka
    - redis

    ## 리뷰 제외
    - `src/main/generated/**`
    - `**/Q*.java`

    ## 추가 규칙
    - 결제 금액 필드는 반드시 BigDecimal 사용

Skills 로드 우선순위:
    1순위) repo md의 '기술 스택' 섹션에 선언된 skill 목록 사용
    2순위) repo md가 없거나 '기술 스택' 선언이 없으면 diff 확장자 기반 기본 skill 자동 로드
           .java 감지 → java-spring.md 자동 로드
           .vue / .js / .ts 감지 → vue3-frontend.md 자동 로드
"""

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

# ============================================================
# 상수
# ============================================================

SHARED_CONFIG_DIR = os.environ.get("SHARED_CONFIG_DIR", ".shared-config/review-config")

REVIEW_PROMPT_PATH = os.path.join(SHARED_CONFIG_DIR, "review-prompt.md")
CONVENTIONS_PATH   = os.path.join(SHARED_CONFIG_DIR, "conventions.md")
SKILLS_DIR         = os.path.join(SHARED_CONFIG_DIR, "skills")
REPO_CONFIG_DIR    = os.path.join(SHARED_CONFIG_DIR, "repo")

MAX_DIFF_LENGTH  = int(os.environ.get("MAX_DIFF_LENGTH", "100000"))
MAX_SKILL_CHARS  = int(os.environ.get("MAX_SKILL_CHARS", "5000"))
MAX_SKILLS_TOTAL = int(os.environ.get("MAX_SKILLS_TOTAL", "15000"))
CLAUDE_MODEL     = os.environ.get("CLAUDE_MODEL", "claude-opus-4-6")
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
    ".gradle":     "gradle",
    ".kts":        "gradle",
    ".py":         "python",
    ".sh":         "shell",
    ".sql":        "sql",
}

ALL_REVIEWABLE_EXTENSIONS: Set[str] = set(EXTENSION_TO_FILE_TYPE.keys())

# repo 설정 없을 때 확장자 기반으로 자동 로드할 기본 skill 매핑
# - yaml은 application.yml 등 Spring 설정 파일이 대부분이므로 제외
#   (GitHub Actions가 필요한 repo는 repo md에 명시적으로 선언)
# - jpa, kafka, redis 등 도메인 특화 skill도 repo md에서 명시적으로 선언
DEFAULT_SKILL_BY_FILE_TYPE: Dict[str, str] = {
    "java":       "java-spring",
    "vue":        "vue3-frontend",
    "javascript": "vue3-frontend",
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
        print("[WARN] CLAUDE_CODE_OAUTH_TOKEN 미설정", file=sys.stderr)


def verify_gh_auth() -> None:
    gh_host = os.environ.get("GH_HOST", "github.com")
    gh_token = os.environ.get("GH_TOKEN") or os.environ.get("GH_ENTERPRISE_TOKEN")
    if gh_token:
        print(f"[INFO] GH 인증: token 사용 ({gh_host}), prefix={gh_token[:4]}...")
    else:
        print("[WARN] GH_TOKEN 미설정", file=sys.stderr)


# ============================================================
# GitHub CLI 래퍼
# ============================================================

def run_gh(args: list) -> str:
    result = subprocess.run(["gh"] + args, capture_output=True, encoding="utf-8")
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
            capture_output=True, encoding="utf-8",
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
        capture_output=True, encoding="utf-8",
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout
    return None


def post_review(pr_number: str, pr_info: dict, review_data: dict, diff_mappings: dict) -> None:
    """GitHub Code Review API로 리뷰를 게시한다."""
    owner, repo, commit_sha = pr_info["owner"], pr_info["repo"], pr_info["commit_sha"]

    # 인라인 코멘트 유효성 검증
    valid_comments = []
    skipped = []
    for c in review_data.get("comments", []):
        path, line = c.get("path", ""), c.get("line", 0)
        if path in diff_mappings and line in diff_mappings[path]:
            emoji = SEVERITY_EMOJI.get(c.get("severity", ""), "💡")
            inline_body = c.get("body", "").replace("\\n", "\n")
            valid_comments.append({
                "path": path,
                "line": line,
                "body": f"{emoji} **{c.get('severity', '')}**\n\n{inline_body}",
            })
        else:
            skipped.append(f"  - {path}:{line} (not in diff)")

    if skipped:
        print(f"[WARN] 인라인 코멘트 {len(skipped)}개 스킵 (diff 범위 밖):")
        for s in skipped[:5]:
            print(s)

    print(f"[INFO] 유효한 인라인 코멘트: {len(valid_comments)}개")

    review_body = review_data.get("review", "## 🤖 AI 코드 리뷰\n\n리뷰가 완료되었습니다.")
    review_body = review_body.replace("\\n", "\n").replace("\\t", "\t")

    payload = {
        "commit_id": commit_sha,
        "body": review_body,
        "event": "COMMENT",
        "comments": valid_comments,
    }

    try:
        subprocess.run(
            [
                "gh", "api",
                f"repos/{owner}/{repo}/pulls/{pr_number}/reviews",
                "-X", "POST",
                "-H", "Accept: application/vnd.github+json",
                "--input", "-",
            ],
            input=json.dumps(payload),
            capture_output=True, encoding="utf-8", check=True,
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


def find_repo_config(repo_full_name: str) -> str:
    repo_name = repo_full_name.split("/")[-1]
    return read_file_safe(os.path.join(REPO_CONFIG_DIR, f"{repo_name}.md"))


def parse_skill_names(repo_config_content: str) -> List[str]:
    """repo md의 '기술 스택' 섹션에서 skill 이름 목록을 파싱한다."""
    skill_names = []
    in_section = False
    for line in repo_config_content.split("\n"):
        stripped = line.strip()
        if stripped == "## 기술 스택":
            in_section = True
            continue
        if in_section:
            if stripped.startswith("#"):
                break
            if stripped.startswith("- "):
                name = stripped[2:].strip()
                if name:
                    skill_names.append(name)
    return skill_names


def resolve_skill_names(repo_config: str, file_types: Set[str]) -> List[str]:
    """Skills 로드 우선순위를 결정한다.

    1순위) repo md에 '기술 스택' 선언이 있으면 해당 목록 사용
    2순위) 선언이 없으면 diff 확장자 기반으로 DEFAULT_SKILL_BY_FILE_TYPE에서 자동 선택
    """
    if repo_config:
        skill_names = parse_skill_names(repo_config)
        if skill_names:
            print("[INFO] Skills 로드: repo 기술 스택 선언 기반")
            return skill_names

    fallback_names = []
    for file_type in sorted(file_types):
        skill_name = DEFAULT_SKILL_BY_FILE_TYPE.get(file_type)
        if skill_name and skill_name not in fallback_names:
            fallback_names.append(skill_name)

    if fallback_names:
        print(f"[INFO] Skills 로드: repo 설정 없음 → 확장자 기반 자동 선택 {fallback_names}")
    else:
        print("[INFO] Skills 로드: 매핑되는 기본 skill 없음")

    return fallback_names


def load_skills(skill_names: List[str]) -> Dict[str, str]:
    """skill 이름 목록을 순서대로 로드한다."""
    skills: Dict[str, str] = {}
    total_chars = 0

    for skill_name in skill_names:
        skill_path = os.path.join(SKILLS_DIR, f"{skill_name}.md")
        content = read_file_safe(skill_path)
        if not content:
            continue

        if len(content) > MAX_SKILL_CHARS:
            content = content[:MAX_SKILL_CHARS] + "\n...(이하 생략)"

        if total_chars + len(content) > MAX_SKILLS_TOTAL:
            print(f"[WARN] Skills 총 길이 초과로 '{skill_name}' 생략", file=sys.stderr)
            break

        skills[skill_name] = content
        total_chars += len(content)

    return skills


def _extract_repo_rules(repo_config_content: str) -> str:
    """repo config에서 '기술 스택' 섹션을 제외한 나머지 내용을 반환한다."""
    lines = repo_config_content.split("\n")
    result = []
    skip_section = False

    for line in lines:
        stripped = line.strip()
        if stripped == "## 기술 스택":
            skip_section = True
            continue
        if skip_section and stripped.startswith("## "):
            skip_section = False
        if not skip_section:
            result.append(line)

    return "\n".join(result).strip()


# ============================================================
# 프롬프트 조립
# ============================================================

def build_prompt(diff: str, pr_info: dict, repo_full_name: str,
                 file_types: Set[str]) -> str:
    sections = []

    # 1) 역할 + 리뷰 규칙 + 출력 형식
    review_prompt = read_file_safe(REVIEW_PROMPT_PATH)
    if not review_prompt:
        print("[ERROR] review-prompt.md 없음 → 종료", file=sys.stderr)
        sys.exit(1)
    sections.append(review_prompt)

    # 2) PR 정보
    sections.append(
        f"## PR 정보\n"
        f"- 제목: {pr_info.get('title', '')}\n"
        f"- 설명: {pr_info.get('body', '없음') or '없음'}"
    )

    # 3) 공통 코딩 컨벤션
    conventions = read_file_safe(CONVENTIONS_PATH)
    if conventions:
        sections.append(f"## 공통 코딩 컨벤션\n\n{conventions}")

    # 4) Skills 로드 (1순위: repo 선언 / 2순위: 확장자 기반 자동 선택)
    repo_config = find_repo_config(repo_full_name)
    skill_names = resolve_skill_names(repo_config, file_types)
    skills = load_skills(skill_names)

    if skills:
        skill_block = "\n\n".join(
            f"### {name}\n{content}" for name, content in skills.items()
        )
        sections.append(f"## 리뷰 참고 자료 (Skills)\n\n{skill_block}")
        print(f"[INFO] 주입된 Skills: {list(skills.keys())}")
    else:
        print("[INFO] 주입된 Skills: 없음")

    # 5) repo별 추가 규칙 (기술 스택 섹션 제외)
    if repo_config:
        repo_rules = _extract_repo_rules(repo_config)
        if repo_rules:
            sections.append(f"## 이 리포지토리 추가 규칙\n\n{repo_rules}")

    # 6) PR Diff
    diff_limited = diff[:MAX_DIFF_LENGTH]
    if len(diff) > MAX_DIFF_LENGTH:
        diff_limited += f"\n\n...(이하 {len(diff) - MAX_DIFF_LENGTH}자 생략)"

    backtick = "`" * 3
    sections.append(f"## PR Diff\n{backtick}diff\n{diff_limited}\n{backtick}")

    return "\n\n---\n\n".join(sections)


# ============================================================
# Claude 호출
# ============================================================

def extract_json(output: str) -> dict:
    """Claude 응답에서 JSON을 추출한다."""

    # 1) ```json ... ``` 블록 우선 시도
    m = re.search(r"```json\s*([\s\S]*?)\s*```", output)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 2) ``` ... ``` 블록 시도
    m = re.search(r"```\s*([\s\S]*?)\s*```", output)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3) JSONDecoder.raw_decode로 정확하게 파싱
    start = output.find("{")
    if start != -1:
        decoder = json.JSONDecoder()
        try:
            obj, _ = decoder.raw_decode(output, start)
            return obj
        except json.JSONDecodeError as e:
            print(f"[WARN] JSONDecoder 파싱 실패: {e}", file=sys.stderr)
            print(f"  실패 위치 컨텍스트: {output[max(0, e.pos-80):e.pos+80]!r}", file=sys.stderr)

    print("[WARN] JSON 추출 실패 → fallback", file=sys.stderr)
    return {"review": output[:MAX_SUMMARY_FALLBACK_LENGTH], "comments": []}


def call_claude(prompt: str) -> dict:
    home = os.path.expanduser("~")
    print(f"[INFO] Claude 호출 (model={CLAUDE_MODEL}, timeout={CLAUDE_TIMEOUT}s)")
    print(f"[INFO] 프롬프트 길이: {len(prompt)} chars")

    env = {
        **os.environ,
        "HOME": home,
        "PYTHONIOENCODING": "utf-8",
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
    }

    try:
        result = subprocess.run(
            [
                "claude", "-p", prompt,
                "--model", CLAUDE_MODEL,
            ],
            capture_output=True,
            check=True,
            timeout=CLAUDE_TIMEOUT,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        output = result.stdout.strip()
        print(f"[INFO] Claude 응답: {len(output)} chars")
        print(f"[DEBUG] Claude 응답 전체:\n{output}")
        return extract_json(output)

    except subprocess.CalledProcessError as e:
        err = (e.stdout or "") + (e.stderr or "")
        if "Not logged in" in err or "/login" in err:
            print("[ERROR] Claude 인증 실패. CLAUDE_CODE_OAUTH_TOKEN 확인 필요", file=sys.stderr)
        else:
            print(f"[ERROR] Claude CLI 실패 (exit {e.returncode})", file=sys.stderr)
            print(f"  stdout: {e.stdout[:500]}", file=sys.stderr)
            print(f"  stderr: {e.stderr[:500]}", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(f"[ERROR] Claude 타임아웃 ({CLAUDE_TIMEOUT}s)", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print("[ERROR] claude 명령어 없음. npm install -g @anthropic-ai/claude-code", file=sys.stderr)
        sys.exit(1)


# ============================================================
# 메인
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Claude PR Review")
    parser.add_argument("pr_number", help="PR 번호")
    parser.add_argument("repo_full_name", help="org/repo 형식 (예: dev-team/payment-service)")
    parser.add_argument("--dry-run", action="store_true", help="PR 코멘트 없이 결과만 터미널 출력")
    args = parser.parse_args()

    gh_host = os.environ.get("GH_HOST", "github.com")
    os.environ["GH_HOST"] = gh_host

    verify_gh_auth()
    verify_claude_auth()

    print(f"[INFO] === Claude PR Review ===")
    print(f"[INFO] PR: #{args.pr_number} in {args.repo_full_name}")
    print(f"[INFO] Dry run: {args.dry_run}")

    # 1. PR 정보
    pr_info = get_pr_info(args.pr_number)
    print(f"[INFO] commit: {pr_info['commit_sha'][:8]}")
    print(f"[INFO] title: {pr_info['title']}")

    # 2. 이전 리뷰 커밋 조회
    last_commit = get_existing_claude_review_commit(args.pr_number, pr_info)
    if last_commit:
        print(f"[INFO] 이전 리뷰 커밋: {last_commit[:8]}")
    else:
        print("[INFO] 이전 리뷰 없음 → 전체 diff 사용")

    # 3. diff 수집 (incremental 우선)
    diff = None
    if last_commit and last_commit != pr_info["commit_sha"]:
        diff = get_incremental_diff(args.pr_number, last_commit, pr_info["commit_sha"])
        if diff:
            print("[INFO] Incremental diff 사용")
    if not diff:
        diff = get_pr_diff(args.pr_number)
        print("[INFO] 전체 diff 사용")

    if not diff.strip():
        print("[WARN] 변경 사항 없음 → 종료")
        return

    # 4. diff 분석 및 제외 패턴 필터링
    analysis = analyze_diff(diff)
    print(f"[INFO] 감지된 파일 타입: {sorted(analysis.file_types)}")

    repo_config_content = find_repo_config(args.repo_full_name)
    exclude_patterns = parse_exclude_patterns(repo_config_content) if repo_config_content else []
    if exclude_patterns:
        print(f"[INFO] repo 제외 패턴: {exclude_patterns}")
        analysis = DiffAnalysis(
            filtered_diff=filter_diff_by_patterns(analysis.filtered_diff, exclude_patterns),
            files=analysis.files,
            file_types=analysis.file_types,
        )

    if not analysis.filtered_diff.strip():
        print("[WARN] 필터링 후 리뷰 대상 없음 → 종료")
        return

    print(f"[INFO] 필터링된 diff 크기: {len(analysis.filtered_diff)} chars")

    # diff 라인 매핑
    diff_mappings = parse_diff_line_mapping(diff)

    # 5. 프롬프트 조립
    prompt = build_prompt(
        analysis.filtered_diff,
        pr_info,
        args.repo_full_name,
        analysis.file_types,
    )
    print(f"[INFO] 최종 프롬프트 길이: {len(prompt)} chars")

    # 6. Claude 호출
    review_data = call_claude(prompt)

    print(f"[INFO] === 리뷰 결과 ===")
    review_preview = review_data.get("review", "")[:200].replace("\n", " ")
    print(f"[INFO] Review 미리보기: {review_preview}...")
    print(f"[INFO] Comments: {len(review_data.get('comments', []))}개")
    for i, c in enumerate(review_data.get("comments", []), 1):
        print(f"  [{i}] {c.get('severity')} {c.get('path')}:{c.get('line')} - {c.get('body', '')[:60]}")

    # 7. 게시
    if args.dry_run:
        print("[INFO] Dry run → PR 코멘트 생략")
        print(json.dumps(review_data, ensure_ascii=False, indent=2))
    else:
        post_review(args.pr_number, pr_info, review_data, diff_mappings)


if __name__ == "__main__":
    main()