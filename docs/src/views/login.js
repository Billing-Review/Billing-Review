import { h, mount } from "../utils/dom.js";
import { ghFetch, GHError } from "../api/github.js";
import { setState, saveAuth } from "../state.js";
import { toast } from "../utils/toast.js";

export function renderLogin(root) {
  let busy = false;

  // ── Chrome 비밀번호 매니저가 인식·저장하도록 표준 form + autocomplete 속성 사용 ──
  const employeeInput = h("input", {
    type: "text",
    name: "username",
    id: "login-employee-id",
    autocomplete: "username",
    placeholder: "예) 20231234",
    required: true,
  });

  const patInput = h("input", {
    type: "password",
    name: "password",
    id: "login-pat",
    autocomplete: "current-password",
    placeholder: "ghp_xxxxxxxxxxxxxxxxxxxx",
    required: true,
  });

  const submitBtn = h(
    "button",
    { type: "submit", class: "btn" },
    "접속"
  );

  async function submit() {
    if (busy) return;
    const employeeId = employeeInput.value.trim();
    const pat = patInput.value.trim();
    if (!employeeId) {
      toast("사번을 입력하세요", "error");
      employeeInput.focus();
      return;
    }
    if (!pat) {
      toast("PAT를 입력하세요", "error");
      patInput.focus();
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
        employeeId,
      });
      toast(`환영합니다, ${user.login}님`, "success");
      // hash 변경 전에 form submit 이벤트가 자연스럽게 종료되도록 한 박자 양보
      setTimeout(() => { location.hash = "#/matrix"; }, 0);
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

  const form = h(
    "form",
    {
      id: "login-form",
      method: "post",
      // 실제 전송하지 않음 — Chrome 이 form 제출로 인식하도록 표준 형식 유지
      action: "#/matrix",
    },
    h(
      "div",
      { class: "card" },
      h("h2", { class: "card__title" }, "로그인"),
      h(
        "p",
        { class: "card__desc" },
        "사번과 사내 GitHub Enterprise PAT 를 입력하세요. ",
        "Chrome 이 저장 여부를 묻습니다. 탭을 닫으면 세션에서 자동 삭제됩니다."
      ),
      h(
        "div",
        { class: "field" },
        h("label", { for: "login-employee-id" }, "사번"),
        employeeInput
      ),
      h(
        "div",
        { class: "field" },
        h("label", { for: "login-pat" }, "Personal Access Token"),
        patInput,
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
  );

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    submit();
  });

  mount(root, h("div", { class: "login-wrap" }, form));

  setTimeout(() => {
    // 기존 입력값이 자동완성으로 채워진 경우 PAT 로 포커스, 아니면 사번부터
    if (employeeInput.value) patInput.focus();
    else employeeInput.focus();
  }, 50);
}
