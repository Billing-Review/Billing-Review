import { getFileContent, putFile } from "./repos.js";
import { ORG, SHARED_WORKFLOWS_REPO } from "../config.js";
import { decodeB64, encodeB64 } from "../utils/b64.js";

const PATH = "rest-api-docs/service-config.json";

// 전체 service-config 객체를 읽어 { content, sha, json } 반환
export async function readServiceConfig() {
  const data = await getFileContent(ORG, SHARED_WORKFLOWS_REPO, PATH);
  if (!data || !data.content) {
    return { content: "{}", sha: null, json: {} };
  }
  const content = decodeB64(data.content);
  let json = {};
  try { json = JSON.parse(content); } catch {}
  return { content, sha: data.sha, json };
}

// 특정 서비스 entry 반환 (없으면 null)
export async function readServiceEntry(serviceName) {
  const { json } = await readServiceConfig();
  return json[serviceName] || null;
}

// 특정 서비스 entry 를 upsert 하고 파일을 PUT
export async function upsertServiceEntry(serviceName, environments) {
  const { json, sha } = await readServiceConfig();
  json[serviceName] = { environments };
  const newContent = JSON.stringify(json, null, 2) + "\n";
  await putFile(ORG, SHARED_WORKFLOWS_REPO, PATH, {
    contentB64: encodeB64(newContent),
    message: `chore: register service-config for ${serviceName}`,
    sha: sha || undefined,
  });
}
