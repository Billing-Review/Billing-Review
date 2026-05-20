import { loadAuth, getState, subscribe, clearAuth } from "./state.js";
import { renderLogin } from "./views/login.js";
import { renderRepos } from "./views/repos.js";
import { renderOverview } from "./views/overview.js";
import { renderDeploy } from "./views/deploy.js";
import { mount, h } from "./utils/dom.js";

const root = document.getElementById("app");
const userInfo = document.getElementById("user-info");
const rateInfo = document.getElementById("rate-limit");
const logoutBtn = document.getElementById("logout-btn");
const mainNav = document.getElementById("main-nav");

logoutBtn.addEventListener("click", () => {
  clearAuth();
  location.hash = "#/login";
});

subscribe((state) => {
  if (state.user) {
    userInfo.textContent = `@${state.user.login}`;
    logoutBtn.style.display = "";
    mainNav.style.display = "";
  } else {
    userInfo.textContent = "";
    logoutBtn.style.display = "none";
    mainNav.style.display = "none";
  }
  if (state.rateLimit) {
    rateInfo.textContent = `API ${state.rateLimit.remaining}/${state.rateLimit.limit}`;
  }
});

// 현재 라우트에 맞춰 nav 활성화 표시
function updateNavActive(hash) {
  const navItems = mainNav.querySelectorAll(".nav-item");
  navItems.forEach((el) => {
    const target = el.dataset.route;
    let active = false;
    if (target === "#/repos" && hash.startsWith("#/repos")) active = true;
    if (target === "#/overview" && hash.startsWith("#/overview")) active = true;
    if (target === "#/deploy" && hash.startsWith("#/deploy")) active = true;
    el.classList.toggle("is-active", active);
  });
}

async function navigate() {
  const hash = location.hash || "#/login";
  const { pat } = getState();

  if (!pat) {
    if (hash !== "#/login") {
      location.hash = "#/login";
      return;
    }
    updateNavActive("");
    renderLogin(root);
    return;
  }

  if (hash === "#/login") {
    location.hash = "#/repos";
    return;
  }

  updateNavActive(hash);

  // 레포 관리
  if (hash === "#/repos") return renderRepos(root);
  const repoMatch = hash.match(/^#\/repos\/([^/]+)$/);
  if (repoMatch) return renderRepos(root, decodeURIComponent(repoMatch[1]));

  // 적용 현황
  if (hash === "#/overview") return renderOverview(root);

  // 기능 배포
  if (hash === "#/deploy") return renderDeploy(root);
  const deployMatch = hash.match(/^#\/deploy\/([^/]+)$/);
  if (deployMatch) return renderDeploy(root, decodeURIComponent(deployMatch[1]));

  // 디테일 화면 (사이드바 뷰에서 진입)
  const apiDocsMatch = hash.match(/^#\/api-docs\/([^/]+)$/);
  if (apiDocsMatch) {
    const { renderApiDocs } = await import("./views/api-docs.js");
    return renderApiDocs(root, decodeURIComponent(apiDocsMatch[1]));
  }
  const runsMatch = hash.match(/^#\/runs\/([^/]+)$/);
  if (runsMatch) {
    const { renderRuns } = await import("./views/runs.js");
    return renderRuns(root, decodeURIComponent(runsMatch[1]));
  }

  // 기본 (또는 #/matrix 등 구 라우트)
  if (hash === "#/matrix" || hash === "#/") {
    location.hash = "#/repos";
    return;
  }

  mount(root, h("div", { class: "card empty" }, `알 수 없는 경로: ${hash}`));
}

window.addEventListener("hashchange", navigate);
window.addEventListener("DOMContentLoaded", () => {
  loadAuth();
  navigate();
});
if (document.readyState !== "loading") {
  loadAuth();
  navigate();
}
