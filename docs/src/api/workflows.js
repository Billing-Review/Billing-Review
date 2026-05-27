import { ghFetch } from "./github.js";
import { ORG } from "../config.js";

// 워크플로우 dispatch 트리거 (서비스 레포 기준)
//   repo : 서비스 레포명
//   workflowFile : "api-doc-publish.yml" 등
//   ref : 실행 기준 브랜치
//   inputs : { ... } workflow_dispatch inputs
export async function dispatchWorkflow(repo, workflowFile, ref, inputs) {
  await ghFetch(
    `/repos/${ORG}/${repo}/actions/workflows/${encodeURIComponent(workflowFile)}/dispatches`,
    {
      method: "POST",
      body: { ref, inputs },
    }
  );
}

// 최근 실행 목록 (페이지 지원). 응답에 total_count 도 있지만 호출부에서
// 다음 페이지 유무만 알면 충분하므로 runs 만 반환.
export async function listWorkflowRuns(repo, workflowFile, perPage = 10, page = 1) {
  const base = workflowFile
    ? `/repos/${ORG}/${repo}/actions/workflows/${encodeURIComponent(workflowFile)}/runs`
    : `/repos/${ORG}/${repo}/actions/runs`;
  const path = `${base}?per_page=${perPage}&page=${page}`;
  const data = await ghFetch(path);
  return data && data.workflow_runs ? data.workflow_runs : [];
}
