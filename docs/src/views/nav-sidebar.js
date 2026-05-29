import { h, mount } from "../utils/dom.js";

// 사이드바 nav 정의 — 카테고리별 그룹
const groups = [
  {
    title: "📊 대시보드",
    items: [
      {
        label: "적용 현황",
        href: "#/overview",
        matches: (h) => h.startsWith("#/overview"),
      },
      {
        label: "AI Context",
        href: "#/ai-context",
        matches: (h) => h.startsWith("#/ai-context"),
      },
    ],
  },
  {
    title: "📦 레포지토리",
    items: [
      {
        label: "레포 관리",
        href: "#/repos",
        matches: (h) => h.startsWith("#/repos"),
      },
    ],
  },
  {
    title: "⚡ 기능 배포",
    items: [
      {
        label: "기능 배포",
        href: "#/deploy",
        matches: (h) => h.startsWith("#/deploy"),
      },
    ],
  },
  {
    title: "⚙️ 설정",
    items: [
      {
        label: "도메인 관리",
        href: "#/domains",
        matches: (h) => h.startsWith("#/domains"),
      },
    ],
  },
];

export function renderNavSidebar(el, currentHash) {
  mount(
    el,
    groups.map((g) =>
      h(
        "div",
        { class: "nav-group" },
        h("div", { class: "nav-group__title" }, g.title),
        h(
          "div",
          { class: "nav-group__items" },
          g.items.map((it) =>
            h(
              "a",
              {
                class: "nav-item" + (it.matches(currentHash) ? " is-active" : ""),
                href: it.href,
              },
              it.label
            )
          )
        )
      )
    )
  );
}
