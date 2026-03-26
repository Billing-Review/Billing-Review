# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **centralized PR code review system** that uses Claude Code CLI to automatically review Pull Requests across an organization's repositories. It runs as a reusable GitHub Actions workflow that other repos call.

## Architecture

**Workflow**: `.github/workflows/claude-review.yml` — Reusable workflow (`workflow_call`) that receives `pr_number`, `repo_name`, and `manual_trigger` as inputs. Checks out the target repo and this shared config repo, then runs the Python review script.

**Review Script**: `scripts/claude_review.py` — Orchestrates the entire review pipeline:
1. Fetches PR info and diff via `gh` CLI
2. Supports incremental reviews (only new changes since last Claude review)
3. Filters diff to reviewable file extensions and applies repo-specific exclude patterns
4. Assembles a prompt from: review-prompt + PR info + conventions + auto-detected/declared skills + repo rules + diff
5. Calls `claude -p` with the assembled prompt
6. Parses JSON response and posts as a GitHub PR review with inline comments

**Config Structure** (`claude-review-config/`):
- `review-prompt.md` — Core system prompt defining review role, severity levels, output JSON format
- `conventions.md` — Organization-wide coding conventions (Korean, Java-focused)
- `skills/` — Technology-specific review knowledge (e.g., `java-spring.md`, `jpa.md`, `kafka.md`, `redis.md`)
- Per-repository config is stored in each repo's `.claude/rules/CODE_REVIEW.md`, declaring tech stack (maps to skills), exclude patterns, and repo-specific rules

## Key Design Decisions

- **Skill resolution**: If a repo config declares `## 기술 스택`, those skills are loaded. Otherwise, skills are auto-detected from file extensions in the diff (e.g., `.java` → `java-spring`).
- **Exclude patterns**: Repo configs can declare `## 리뷰 제외` with glob patterns (e.g., generated code, QueryDSL Q-classes).
- **Diff filtering**: Only files with recognized extensions are reviewed (see `EXTENSION_TO_FILE_TYPE` in the script).
- **Inline comment validation**: Comments are only posted if their file:line falls within the actual diff range.
- **All review output is in Korean**; code/technical terms stay in English.

## Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | Claude authentication | required |
| `ORG_GITHUB_TOKEN` / `GH_TOKEN` | GitHub API access | required |
| `CLAUDE_MODEL` | Model for review | `claude-opus-4-6` |
| `CLAUDE_TIMEOUT` | Review timeout (seconds) | `300` |
| `MAX_DIFF_LENGTH` | Max diff chars sent to Claude | `100000` |
| `MAX_SKILL_CHARS` | Max chars per skill file | `5000` |
| `MAX_SKILLS_TOTAL` | Max total chars for all skills | `15000` |

## Running Locally

```bash
# Run the review script directly
python3 scripts/claude_review.py <pr_number> <org/repo> [manual_trigger]

# Example
python3 scripts/claude_review.py 42 my-org/payment-api false
```

Requires `gh` CLI authenticated and `claude` CLI installed (`npm install -g @anthropic-ai/claude-code`).

## Adding a New Repository

Create `.claude/rules/CODE_REVIEW.md` in the target repository with:
- `## 기술 스택` section listing skill names (matching filenames in `skills/`)
- `## 리뷰 제외` section with glob patterns for files to skip
- Any additional repo-specific review rules

## Git Conventions

Commit format: `type: 간결한 설명` where type is one of `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `style`, `perf`.
