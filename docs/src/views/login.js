import { h, mount } from "../utils/dom.js";
import { ghFetch, GHError } from "../api/github.js";
import { setState, saveAuth } from "../state.js";
import { toast } from "../utils/toast.js";

export function renderLogin(root) {
  let busy = false;

  const input = h("input", {
    type: "password",
    placeholder: "ghp_xxxxxxxxxxxxxxxxxxxx",
    autocomplete: "off",
  });

  const submitBtn = h(
    "button",
    { class: "btn", onclick: () => submit() },
    "접속"
  );

  async function submit() {
    if (busy) return;
    const pat = input.value.trim();
    if (!pat) {
      toast("PAT를 입력하세요", "error");
      return;
    }
    busy = true;
    submitBtn.disabled = true;
    submitBtn.textContent = "검증 중...";
    setState({ pat });
    try {
      const user = await ghFetch("/user");
      saveAuth(pat, {
        login: user.login,
        name: user.name,
        avatar_url: user.avatar_url,
      });
      toast(`환영합니다, ${user.login}님`, "success");
      location.hash = "#/matrix";
    } catch (err) {
      setState({ pat: null });
      const msg =
        err instanceof GHError && err.status === 401
          ? "유효하지 않은 PAT입니다"
          : `검증 실패: ${err.message}`;
      toast(msg, "error");
      busy = false;
      submitBtn.disabled = false;
      submitBtn.textContent = "접속";
    }
  }

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") submit();
  });

  mount(
    root,
    h(
      "div",
      { class: "login-wrap" },
      h(
        "div",
        { class: "card" },
        h("h2", { class: "card__title" }, "GitHub PAT 입력"),
        h(
          "p",
          { class: "card__desc" },
          "사내 GitHub Enterprise의 Personal Access Token이 필요합니다. ",
          "탭을 닫으면 자동으로 삭제됩니다."
        ),
        h(
          "div",
          { class: "field" },
          h("label", null, "Personal Access Token"),
          input,
          h(
            "div",
            { class: "help" },
            "필요 권한: ",
            h("code", null, "repo"),
            ", ",
            h("code", null, "workflow")
          )
        ),
        h("div", { style: { textAlign: "right" } }, submitBtn)
      )
    )
  );

  setTimeout(() => input.focus(), 50);
}
