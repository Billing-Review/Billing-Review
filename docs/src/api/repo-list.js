import { getFileContent, putFile } from "./repos.js";
import { ORG, SHARED_WORKFLOWS_REPO, REPO_LIST_PATH } from "../config.js";
import { encodeB64, decodeB64 } from "../utils/b64.js";

// GitHub Contents API 로 직접 읽음. Pages 빌드 지연·정적 파일 캐시와 무관하게
// 커밋 직후 즉시 최신 값을 반환한다.
export async function readRepoList() {
  const data = await getFileContent(ORG, SHARED_WORKFLOWS_REPO, REPO_LIST_PATH);
  if (!data || !data.content) return { list: null };
  try {
    const parsed = JSON.parse(decodeB64(data.content));
    const list = Array.isArray(parsed) && parsed.length > 0 ? parsed : null;
    return { list };
  } catch {
    return { list: null };
  }
}

// GitHub Contents API 로 커밋. 직전 sha 를 조회해 race condition 방지.
export async function writeRepoList(list) {
  const current = await getFileContent(ORG, SHARED_WORKFLOWS_REPO, REPO_LIST_PATH);
  const content = JSON.stringify(list ?? [], null, 2) + "\n";
  await putFile(ORG, SHARED_WORKFLOWS_REPO, REPO_LIST_PATH, {
    contentB64: encodeB64(content),
    message: `chore: update repo list`,
    sha: current?.sha || undefined,
  });
}
