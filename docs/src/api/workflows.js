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

// 최근 실행 목록
export async function listWorkflowRuns(repo, workflowFile, perPage = 10) {
  const path = workflowFile
    ? `/repos/${ORG}/${repo}/actions/workflows/${encodeURIComponent(workflowFile)}/runs?per_page=${perPage}`
    : `/repos/${ORG}/${repo}/actions/runs?per_page=${perPage}`;
  const data = await ghFetch(path);
  return data && data.workflow_runs ? data.workflow_runs : [];
}
