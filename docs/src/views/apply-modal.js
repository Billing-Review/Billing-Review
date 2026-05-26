import { h, mount, clear } from "../utils/dom.js";
import { getFileContent, putFile, getRepo } from "../api/repos.js";
import { ORG, SHARED_WORKFLOWS_REPO } from "../config.js";
import { readServiceEntry, upsertServiceEntry } from "../api/service-config.js";
import { toast } from "../utils/toast.js";
import { buildEnvForm } from "../utils/env-form.js";

// 적용 모달.
//   feature : FEATURES[i]
//   targetRepo: { name, owner: { login }, default_branch }
//   onDone : 성공 후 호출 (매트릭스 재조회)
export function openApplyModal(feature, targetRepo, onDone) {
  const backdrop = h("div", { class: "modal-backdrop" });

  const closeModal = () => backdrop.remove();
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) closeModal();
  });

  const statusBox = h("div");
  const applyBtn = h("button", { class: "btn" }, "적용");
  const cancelBtn = h(
    "button",
    {
      class: "btn btn--ghost",
      style: { color: "#1f2328", border: "1px solid #d0d7de" },
      onclick: closeModal,
    },
    "닫기"
  );

  const fileList = h(
    "ul",
    { style: { paddingLeft: "20px", margin: "8px 0" } },
    ...feature.files.map((f) => h("li", null, h("code", null, f.target)))
  );

  // ─── extraSetup === "service-config" 인 경우 env URL 입력 폼 ───
  let envForm = null;
  let envFormEl = null;
  let needsServiceConfig = feature.extraSetup === "service-config";

  if (needsServiceConfig) {
    envForm = buildEnvForm({}, { serviceName: targetRepo.name });
    envFormEl = h(
      "div",
      { class: "env-form" },
      h(
        "div",
        { class: "section-title", style: { marginTop: "16px" } },
        "서버 URL 등록"
      ),
      h(
        "p",
        { style: { fontSize: "12px", color: "#656d76", margin: "0 0 8px 0" } },
        `shared-workflows/rest-api-docs/service-config.json 에 "${targetRepo.name}" 항목으로 저장됩니다. 환경명·URL 자유롭게 추가/삭제 가능.`
      ),
      envForm.container,
      h("div", { style: { marginTop: "6px" } }, envForm.addBtn)
    );

    // 기존 값이 있으면 미리 채워넣기
    readServiceEntry(targetRepo.name)
      .then((entry) => {
        if (entry && entry.environments && Object.keys(entry.environments).length) {
          envForm.reset(entry.environments);
        }
      })
      .catch(() => {});
  }

  applyBtn.addEventListener("click", async () => {
    applyBtn.disabled = true;
    applyBtn.textContent = "적용 중...";
    try {
      await applyFeature(feature, targetRepo, statusBox);

      if (needsServiceConfig) {
        const environments = envForm.getValues();
        appendStatus(statusBox, `→ service-config.json 갱신 중...`);
        await upsertServiceEntry(targetRepo.name, environments);
        appendStatus(statusBox, `✓ service-config.json 갱신 완료`);
      }

      toast(`${feature.label} 적용 완료`, "success");
      closeModal();
      onDone && onDone();
    } catch (err) {
      toast(`적용 실패: ${err.message}`, "error", 5000);
      applyBtn.disabled = false;
      applyBtn.textContent = "재시도";
    }
  });

  mount(
    backdrop,
    h(
      "div",
      { class: "modal", onclick: (e) => e.stopPropagation() },
      h("div", { class: "modal__header" },
        h("h3", { class: "modal__title" }, `${feature.label} 적용`),
      ),
      h(
        "div",
        { class: "modal__body" },
        h(
          "p",
          null,
          h("strong", null, `${ORG}/${targetRepo.name}`),
          " 의 default branch에 다음 파일을 추가합니다:"
        ),
        fileList,
        h(
          "p",
          { style: { fontSize: "12px", color: "#656d76", marginTop: "12px" } },
          "이미 존재하는 파일은 내용이 덮어쓰기됩니다."
        ),
        envFormEl,
        statusBox
      ),
      h("div", { class: "modal__actions" }, cancelBtn, applyBtn)
    )
  );

  document.body.appendChild(backdrop);
}

// ── 모달 없이 단일 레포에 적용 (deploy view 일괄 적용용) ──
//   service-config 등 extraSetup 이 필요한 feature 는 일괄 적용 시
//   환경 URL 을 받을 수 없으므로 파일만 복사한다. 적용 후 사용자에게
//   개별 모달로 service-config 등록을 안내한다.
export async function applyFeatureToRepo(feature, targetRepo) {
  let defaultBranch = targetRepo.default_branch;
  if (!defaultBranch) {
    const meta = await getRepo(targetRepo.owner.login, targetRepo.name);
    defaultBranch = meta.default_branch;
  }
  for (const file of feature.files) {
    const source = await getFileContent(ORG, SHARED_WORKFLOWS_REPO, file.source);
    if (!source) throw new Error(`템플릿 없음: ${file.source}`);
    const existing = await getFileContent(
      targetRepo.owner.login,
      targetRepo.name,
      file.target,
      defaultBranch
    );
    await putFile(targetRepo.owner.login, targetRepo.name, file.target, {
      contentB64: source.content.replace(/\n/g, ""),
      message: `chore: apply ${feature.id} workflow (${file.target.split("/").pop()})`,
      sha: existing ? existing.sha : undefined,
      branch: defaultBranch,
    });
  }
}

function appendStatus(box, msg) {
  const pre = box.querySelector("pre");
  if (pre) {
    pre.textContent = (pre.textContent || "") + "\n" + msg;
    pre.scrollTop = pre.scrollHeight;
  } else {
    const newPre = h(
      "pre",
      {
        style: {
          background: "#f6f8fa",
          padding: "8px 12px",
          borderRadius: "6px",
          fontSize: "12px",
          margin: "12px 0 0",
          maxHeight: "200px",
          overflow: "auto",
        },
      },
      msg
    );
    box.appendChild(newPre);
  }
}

async function applyFeature(feature, targetRepo, statusBox) {
  // default branch 확보 (목록 응답에 들어있긴 한데 안전하게 다시 조회)
  let defaultBranch = targetRepo.default_branch;
  if (!defaultBranch) {
    const meta = await getRepo(targetRepo.owner.login, targetRepo.name);
    defaultBranch = meta.default_branch;
  }

  for (const file of feature.files) {
    appendStatus(statusBox, `→ ${file.source} 읽는 중...`);
    const source = await getFileContent(
      ORG,
      SHARED_WORKFLOWS_REPO,
      file.source
    );
    if (!source) throw new Error(`템플릿 없음: ${file.source}`);

    const existing = await getFileContent(
      targetRepo.owner.login,
      targetRepo.name,
      file.target,
      defaultBranch
    );

    appendStatus(statusBox, `✓ 읽음. ${file.target} 커밋 중...`);
    await putFile(targetRepo.owner.login, targetRepo.name, file.target, {
      contentB64: source.content.replace(/\n/g, ""),
      message: `chore: apply ${feature.id} workflow (${file.target.split("/").pop()})`,
      sha: existing ? existing.sha : undefined,
      branch: defaultBranch,
    });
    appendStatus(statusBox, `✓ ${file.target}`);
  }
  appendStatus(statusBox, "워크플로우 파일 적용 완료");
}
