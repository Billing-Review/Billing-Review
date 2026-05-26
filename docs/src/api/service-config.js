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

// 특정 서비스 entry 를 upsert 하고 파일을 PUT (간단한 environments 등록용)
export async function upsertServiceEntry(serviceName, environments) {
  const { json, sha } = await readServiceConfig();
  json[serviceName] = { ...(json[serviceName] || {}), environments };
  const newContent = JSON.stringify(json, null, 2) + "\n";
  await putFile(ORG, SHARED_WORKFLOWS_REPO, PATH, {
    contentB64: encodeB64(newContent),
    message: `chore: register service-config for ${serviceName}`,
    sha: sha || undefined,
  });
}

// 서비스 entry 전체를 통째로 저장 (useGateway, environments, groups 등 모두)
export async function setServiceEntry(serviceName, entry) {
  const { json, sha } = await readServiceConfig();
  json[serviceName] = entry;
  const newContent = JSON.stringify(json, null, 2) + "\n";
  await putFile(ORG, SHARED_WORKFLOWS_REPO, PATH, {
    contentB64: encodeB64(newContent),
    message: `chore: update service-config for ${serviceName}`,
    sha: sha || undefined,
  });
}

// 서비스 entry 삭제
export async function deleteServiceEntry(serviceName) {
  const { json, sha } = await readServiceConfig();
  if (!(serviceName in json)) return;
  delete json[serviceName];
  const newContent = JSON.stringify(json, null, 2) + "\n";
  await putFile(ORG, SHARED_WORKFLOWS_REPO, PATH, {
    contentB64: encodeB64(newContent),
    message: `chore: remove service-config for ${serviceName}`,
    sha: sha || undefined,
  });
}

// Spring Cloud Gateway 라우트 YML 한 블록을 파싱해 group 후보 dict 반환.
// 입력 예:
//   - id: pay-api
//     uri: lb://bill-pay-api
//     predicates:
//       - Path=/pay/**
//     filters:
//       - RewritePath=/pay/(?<segment>/?.*), /external/${segment}
// 결과: { name, externalUrlPrefix, internalUrlPrefix }
export function parseGatewayYml(text) {
  if (!text) return null;
  const result = { name: "", externalUrlPrefix: "", internalUrlPrefix: "" };

  // id
  const idMatch = text.match(/(?:^|\n)\s*-?\s*id:\s*([\w.-]+)/);
  if (idMatch) result.name = idMatch[1].trim();

  // Path=/xxx/** → externalUrlPrefix = /xxx
  const pathMatch = text.match(/Path\s*=\s*([^\s,'"\]]+)/);
  if (pathMatch) {
    result.externalUrlPrefix = pathMatch[1].replace(/\/\*+$/, "").replace(/\*+$/, "").replace(/\/+$/, "");
  }

  // RewritePath=/xxx/..., /yyy/${seg} → internalUrlPrefix = /yyy
  const rewriteMatch = text.match(/RewritePath\s*=\s*[^,]+,\s*([^\s'"\]]+)/);
  if (rewriteMatch) {
    let dest = rewriteMatch[1];
    dest = dest.replace(/\$\{[^}]+\}/g, "");
    dest = dest.replace(/\/$/, "");
    result.internalUrlPrefix = dest;
  }

  if (!result.externalUrlPrefix && !result.internalUrlPrefix) return null;
  return result;
}
