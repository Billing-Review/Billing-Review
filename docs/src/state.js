// 간단한 글로벌 상태 + 옵저버
const listeners = new Set();

const state = {
  pat: null,
  user: null,         // { login, name, avatar_url }
  rateLimit: null,    // { remaining, limit, reset }
  matrixCache: null,  // { ts, rows }
};

export function getState() {
  return state;
}

export function setState(patch) {
  Object.assign(state, patch);
  listeners.forEach((fn) => fn(state));
}

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

// =============================================================
// PAT 저장/복원 (sessionStorage)
// =============================================================
const PAT_KEY = "gh.pat";
const USER_KEY = "gh.user";

export function loadAuth() {
  try {
    const pat = sessionStorage.getItem(PAT_KEY);
    const userJson = sessionStorage.getItem(USER_KEY);
    if (pat && userJson) {
      setState({ pat, user: JSON.parse(userJson) });
      return true;
    }
  } catch {}
  return false;
}

export function saveAuth(pat, user) {
  sessionStorage.setItem(PAT_KEY, pat);
  sessionStorage.setItem(USER_KEY, JSON.stringify(user));
  setState({ pat, user });
}

export function clearAuth() {
  sessionStorage.removeItem(PAT_KEY);
  sessionStorage.removeItem(USER_KEY);
  setState({ pat: null, user: null, matrixCache: null });
}
