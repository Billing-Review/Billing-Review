import { API_BASE_URL } from "../config.js";
import { getState, setState, clearAuth } from "../state.js";

class GHError extends Error {
  constructor(message, status, body) {
    super(message);
    this.status = status;
    this.body = body;
  }
}
export { GHError };

// 단일 fetch wrapper.
//   path : "/user", "/orgs/{org}/repos" 같이 leading slash 포함
//   opts : { method, body, headers, raw=false }
export async function ghFetch(path, opts = {}) {
  const { pat } = getState();
  if (!pat) throw new GHError("PAT 미설정", 401);

  const method = opts.method || "GET";
  // GitHub Contents API 는 max-age=60 의 Cache-Control 을 반환해 브라우저가
  // 디스크 캐시에서 응답을 돌려줄 수 있다. 쓰기 직후 읽기에서 stale 한 값을
  // 보지 않도록 GET 은 캐시버스터 쿼리 + fetch cache:'no-store' 사용.
  // (Cache-Control / Pragma 요청 헤더는 GitHub CORS 가 허용 안 해 사용 불가)
  const cacheBuster = method === "GET" ? (path.includes("?") ? "&" : "?") + "_=" + Date.now() : "";
  const url = `${API_BASE_URL}${path}${cacheBuster}`;
  const headers = {
    "Accept": "application/vnd.github+json",
    "Authorization": `Bearer ${pat}`,
    "X-GitHub-Api-Version": "2022-11-28",
    ...(opts.headers || {}),
  };
  if (opts.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(url, {
    method,
    headers,
    body: opts.body ? (typeof opts.body === "string" ? opts.body : JSON.stringify(opts.body)) : undefined,
    cache: method === "GET" ? "no-store" : "default",
  });

  // rate limit 헤더 추적
  const remaining = res.headers.get("x-ratelimit-remaining");
  const limit = res.headers.get("x-ratelimit-limit");
  const reset = res.headers.get("x-ratelimit-reset");
  if (remaining != null) {
    setState({
      rateLimit: {
        remaining: Number(remaining),
        limit: Number(limit),
        reset: Number(reset),
      },
    });
  }

  if (res.status === 204) return null;
  if (res.status === 404 && opts.allow404) return null;

  let body = null;
  const text = await res.text();
  try { body = text ? JSON.parse(text) : null; } catch { body = text; }

  if (!res.ok) {
    if (res.status === 401) {
      clearAuth();
      location.hash = "#/login";
    }
    const msg = (body && body.message) || `HTTP ${res.status}`;
    throw new GHError(msg, res.status, body);
  }

  return body;
}

// 동시성 제한 헬퍼
export async function pLimitMap(items, limit, fn) {
  const results = new Array(items.length);
  let idx = 0;
  const workers = Array(Math.min(limit, items.length)).fill(0).map(async () => {
    while (true) {
      const i = idx++;
      if (i >= items.length) return;
      results[i] = await fn(items[i], i);
    }
  });
  await Promise.all(workers);
  return results;
}
