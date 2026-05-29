import { ghFetch, pLimitMap } from "./github.js";
import { decodeB64 } from "../utils/b64.js";
import {
  ORG,
  CONTEXT_REPO,
  CONTEXT_REPOS_JSON_PATH,
  CONTEXT_STATE_DIR,
  AI_CONTEXT_EXPECTED_FILES,
} from "../config.js";

// 인메모리 TTL 캐시 (60초)
//   - 같은 화면에서 다른 액션(예: 단일 행 새로고침) 후 빠른 재진입 시 호출 절약
//   - 새로고침 버튼은 loadAllStatus(true) 호출로 강제 갱신
const TTL_MS = 60_000;
let _cache = null;     // { result, ts }
let _inflight = null;

export function invalidateAiContextCache() {
  _cache = null;
  _inflight = null;
}

// billing-context/repos.json 읽기
async function loadReposJson() {
  const data = await ghFetch(
    `/repos/${ORG}/${CONTEXT_REPO}/contents/${CONTEXT_REPOS_JSON_PATH}`,
    { allow404: true }
  );
  if (!data || !data.content) {
    throw new Error(`${CONTEXT_REPO}/${CONTEXT_REPOS_JSON_PATH} 를 찾을 수 없습니다.`);
  }
  return JSON.parse(decodeB64(data.content));
}

// billing-context 의 전체 파일 트리를 한 번에 받아 repos.json 에 등록된
// 서비스에 한해 ai-context 파일 카운트와 state 파일 존재 여부를 추출한다.
// repos.json 에 없는 폴더(예: .claude, files 등)는 무시한다.
async function loadContextTree(allowedRepos) {
  const data = await ghFetch(
    `/repos/${ORG}/${CONTEXT_REPO}/git/trees/HEAD?recursive=1`,
    { allow404: true }
  );
  if (!data || !Array.isArray(data.tree)) return { byRepo: {}, truncated: false };

  const allowed = new Set(allowedRepos);
  const byRepo = {};
  for (const node of data.tree) {
    if (node.type !== "blob") continue;

    // state/{repo}.sha
    const stateMatch = node.path.match(/^state\/(.+)\.sha$/);
    if (stateMatch && allowed.has(stateMatch[1])) {
      const r = stateMatch[1];
      byRepo[r] = byRepo[r] || { files: [], hasState: false };
      byRepo[r].hasState = true;
      continue;
    }

    // {repo}/ai-context/{file}  ← repo 가 repos.json 에 있는 경우만
    const ctxMatch = node.path.match(/^([^/]+)\/ai-context\/([^/]+)$/);
    if (ctxMatch && allowed.has(ctxMatch[1])) {
      const r = ctxMatch[1];
      byRepo[r] = byRepo[r] || { files: [], hasState: false };
      byRepo[r].files.push(ctxMatch[2]);
    }
  }
  return { byRepo, truncated: Boolean(data.truncated) };
}

// billing-context/state/{repo}.sha 내용
async function readStateSha(repo) {
  const path = `${CONTEXT_STATE_DIR}/${repo}.sha`;
  const data = await ghFetch(
    `/repos/${ORG}/${CONTEXT_REPO}/contents/${path}`,
    { allow404: true }
  );
  if (!data || !data.content) return null;
  return decodeB64(data.content).trim();
}

// 서비스 레포의 현재 브랜치 SHA
async function readBranchSha(repo, branch) {
  const data = await ghFetch(
    `/repos/${ORG}/${repo}/branches/${encodeURIComponent(branch)}`,
    { allow404: true }
  );
  if (!data || !data.commit) return null;
  return data.commit.sha;
}

async function loadRepoStatus(entry, treeInfo) {
  const repo = entry.name;
  const branch = entry.branch || "develop";
  const treeEntry = treeInfo.byRepo[repo] || { files: [], hasState: false };

  const [stateSha, branchSha] = await Promise.all([
    treeEntry.hasState ? readStateSha(repo).catch(() => null) : Promise.resolve(null),
    readBranchSha(repo, branch).catch(() => null),
  ]);

  let status;
  if (!stateSha && treeEntry.files.length === 0) status = "missing";
  else if (!branchSha) status = "error";
  else if (stateSha === branchSha) status = "up-to-date";
  else status = "outdated";

  return {
    repo,
    branch,
    stateSha,
    branchSha,
    files: treeEntry.files,
    expectedFiles: AI_CONTEXT_EXPECTED_FILES,
    status,
  };
}

// 전체 상태 로드 (repos.json 에 등록된 서비스만 반환)
//   - force=true: 캐시 무시하고 새로 조회
//   - 호출 수: 1 (repos.json) + 1 (tree) + 2N (state + branch) = 2N+2
//     캐시 hit 시 0
export async function loadAllStatus(force = false) {
  if (!force && _cache && Date.now() - _cache.ts < TTL_MS) {
    return _cache.result;
  }
  if (_inflight) return _inflight;

  _inflight = (async () => {
    try {
      const json = await loadReposJson();
      const allowed = (json.repos || []).map((r) => r.name);
      const treeInfo = await loadContextTree(allowed);
      const rows = await pLimitMap(json.repos || [], 4, (e) =>
        loadRepoStatus(e, treeInfo)
      );
      const result = { reposJson: json, rows };
      _cache = { result, ts: Date.now() };
      return result;
    } finally {
      _inflight = null;
    }
  })();
  return _inflight;
}
