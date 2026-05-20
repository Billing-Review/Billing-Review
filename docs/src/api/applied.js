import { listOrgRepos, listWorkflowFiles } from "./repos.js";
import { pLimitMap } from "./github.js";
import { FEATURES } from "../config.js";
import { getState, setState } from "../state.js";

const CACHE_TTL_MS = 60_000;

// 한 레포의 워크플로우 파일 set으로부터 feature 상태 계산
// returns { [featureId]: "applied" | "partial" | "missing" }
export function computeStatus(workflowFiles) {
  const status = {};
  for (const feat of FEATURES) {
    const required = feat.files.map((f) => f.target.split("/").pop());
    const present = required.filter((n) => workflowFiles.has(n)).length;
    if (present === 0) status[feat.id] = "missing";
    else if (present === required.length) status[feat.id] = "applied";
    else status[feat.id] = "partial";
  }
  return status;
}

// 전체 매트릭스 로딩 (캐시 사용)
//   force=true 면 캐시 무시하고 새로 조회
export async function loadMatrix(force = false) {
  const cache = getState().matrixCache;
  if (!force && cache && Date.now() - cache.ts < CACHE_TTL_MS) {
    return cache.rows;
  }
  const repos = await listOrgRepos();
  const wfSets = await pLimitMap(repos, 6, (r) =>
    listWorkflowFiles(r.owner.login, r.name).catch(() => new Set())
  );
  const rows = repos.map((repo, i) => ({
    repo,
    workflowFiles: wfSets[i],
    status: computeStatus(wfSets[i]),
  }));
  setState({ matrixCache: { ts: Date.now(), rows } });
  return rows;
}

// 적용 통계: { [featureId]: { applied: [...], partial: [...], missing: [...] } }
export function summarizeByFeature(rows) {
  const summary = {};
  for (const feat of FEATURES) {
    summary[feat.id] = { applied: [], partial: [], missing: [] };
  }
  for (const row of rows) {
    for (const feat of FEATURES) {
      summary[feat.id][row.status[feat.id]].push(row.repo);
    }
  }
  return summary;
}

// 한 레포의 적용 요약: "2/3" 같은 문자열
export function appliedCount(row) {
  let n = 0;
  for (const feat of FEATURES) {
    if (row.status[feat.id] === "applied") n++;
  }
  return { applied: n, total: FEATURES.length };
}
