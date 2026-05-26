import { getFileContent, putFile } from "./repos.js";
import { ORG, SHARED_WORKFLOWS_REPO, REPO_LIST_PATH } from "../config.js";
import { encodeB64, decodeB64 } from "../utils/b64.js";

// 인메모리 TTL 캐시.
// - 30 초 안에 재호출 시 API 호출 없이 캐시 반환
// - writeRepoList 성공 시 캐시 즉시 갱신 → write-after-read stale 없음
// - invalidateRepoListCache() 로 강제 갱신 가능 (refresh 버튼 등)
const TTL_MS = 30_000;
let _cache = null;        // { list, ts }
let _inflight = null;     // 동시 호출 시 동일 promise 재사용

export function invalidateRepoListCache() {
  _cache = null;
  _inflight = null;
}

export async function readRepoList() {
  if (_cache && Date.now() - _cache.ts < TTL_MS) {
    return { list: _cache.list && _cache.list.length ? _cache.list : null };
  }
  if (_inflight) return _inflight;

  _inflight = (async () => {
    try {
      const data = await getFileContent(ORG, SHARED_WORKFLOWS_REPO, REPO_LIST_PATH);
      let list = null;
      if (data && data.content) {
        try {
          const parsed = JSON.parse(decodeB64(data.content));
          list = Array.isArray(parsed) ? parsed : null;
        } catch {}
      }
      _cache = { list: list || [], ts: Date.now() };
      return { list: list && list.length ? list : null };
    } finally {
      _inflight = null;
    }
  })();
  return _inflight;
}

export async function writeRepoList(list) {
  const current = await getFileContent(ORG, SHARED_WORKFLOWS_REPO, REPO_LIST_PATH);
  const content = JSON.stringify(list ?? [], null, 2) + "\n";
  await putFile(ORG, SHARED_WORKFLOWS_REPO, REPO_LIST_PATH, {
    contentB64: encodeB64(content),
    message: `chore: update repo list`,
    sha: current?.sha || undefined,
  });
  // 캐시 즉시 갱신
  _cache = { list: list || [], ts: Date.now() };
}
