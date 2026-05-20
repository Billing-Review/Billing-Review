import { ghFetch } from "./github.js";
import { ORG, SHARED_WORKFLOWS_REPO } from "../config.js";
import { decodeB64 } from "../utils/b64.js";

// shared-workflows 레포의 rest-api-docs/{service}/api-docs-registry.json 읽기
export async function readRegistry(serviceName) {
  const path = `rest-api-docs/${serviceName}/api-docs-registry.json`;
  const data = await ghFetch(
    `/repos/${ORG}/${SHARED_WORKFLOWS_REPO}/contents/${path}`,
    { allow404: true }
  );
  if (!data || !data.content) return {};
  const text = decodeB64(data.content);
  try {
    return JSON.parse(text);
  } catch {
    return {};
  }
}

// 메타 키 (__repo_page_id__ 등) 제외하고 실제 API 엔트리만
export function entriesOf(registry) {
  return Object.entries(registry).filter(([k]) => !k.startsWith("__"));
}

// API 키 → { method, path } 파싱
export function parseApiKey(apiKey) {
  const [method, ...rest] = apiKey.split(" ");
  return { method, path: rest.join(" ") };
}
