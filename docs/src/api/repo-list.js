import { getFileContent, putFile } from "./repos.js";
import { ORG, SHARED_WORKFLOWS_REPO, REPO_LIST_PATH } from "../config.js";
import { encodeB64 } from "../utils/b64.js";

// 세션 내 메모리 캐시. write 직후 fetch 가 stale 상태이므로 (Pages 빌드/로컬
// 정적 파일 모두 즉시 반영되지 않음) 메모리에 들고있다 우선 사용한다.
let _memList = undefined; // undefined = 미설정, null = 비어있음, array = 값

// 로컬 파일 / 메모리 캐시 우선
export async function readRepoList() {
  if (_memList !== undefined) {
    return { list: _memList && _memList.length > 0 ? _memList : null };
  }
  try {
    const res = await fetch("./repo-list.json?ts=" + Date.now());
    if (!res.ok) {
      _memList = null;
      return { list: null };
    }
    const parsed = await res.json();
    _memList = Array.isArray(parsed) ? parsed : null;
    return { list: _memList && _memList.length > 0 ? _memList : null };
  } catch {
    _memList = null;
    return { list: null };
  }
}

// 쓰기는 GitHub API로 커밋. 성공 시 메모리 캐시도 갱신해 즉시 반영.
export async function writeRepoList(list) {
  const current = await getFileContent(ORG, SHARED_WORKFLOWS_REPO, REPO_LIST_PATH);
  const content = JSON.stringify(list ?? [], null, 2) + "\n";
  await putFile(ORG, SHARED_WORKFLOWS_REPO, REPO_LIST_PATH, {
    contentB64: encodeB64(content),
    message: `chore: update repo list`,
    sha: current?.sha || undefined,
  });
  _memList = list ?? [];
}
