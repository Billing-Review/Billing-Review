import { h, mount, clear } from "../utils/dom.js";
import { getFileContent, putFile, getRepo } from "../api/repos.js";
import { ORG, SHARED_WORKFLOWS_REPO } from "../config.js";
import { toast } from "../utils/toast.js";

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
  const cancelBtn = h("button", { class: "btn btn--ghost", onclick: closeModal }, "닫기");
  cancelBtn.style.color = "#1f2328";
  cancelBtn.style.border = "1px solid #d0d7de";

  applyBtn.addEventListener("click", async () => {
    applyBtn.disabled = true;
    applyBtn.textContent = "적용 중...";
    try {
      await applyFeature(feature, targetRepo, statusBox);
      toast(`${feature.label} 적용 완료`, "success");
      closeModal();
      onDone && onDone();
    } catch (err) {
      toast(`적용 실패: ${err.message}`, "error", 5000);
      applyBtn.disabled = false;
      applyBtn.textContent = "재시도";
    }
  });

  const fileList = h(
    "ul",
    { style: { paddingLeft: "20px", margin: "8px 0" } },
    ...feature.files.map((f) =>
      h("li", null, h("code", null, f.target))
    )
  );

  mount(
    backdrop,
    h(
      "div",
      { class: "modal", onclick: (e) => e.stopPropagation() },
      h("h3", { class: "modal__title" }, `${feature.label} 적용`),
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
      statusBox,
      h("div", { class: "modal__actions" }, cancelBtn, applyBtn)
    )
  );

  document.body.appendChild(backdrop);
}

// 모달 없이 단일 레포에 적용 (deploy view 일괄 적용용)
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

async function applyFeature(feature, targetRepo, statusBox) {
  // default branch 확보 (목록 응답에 들어있긴 한데 안전하게 다시 조회)
  let defaultBranch = targetRepo.default_branch;
  if (!defaultBranch) {
    const meta = await getRepo(targetRepo.owner.login, targetRepo.name);
    defaultBranch = meta.default_branch;
  }

  const lines = [];
  const setStatus = (msg) => {
    lines.push(msg);
    clear(statusBox);
    statusBox.appendChild(
      h(
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
        lines.join("\n")
      )
    );
  };

  for (const file of feature.files) {
    setStatus(`→ ${file.source} 읽는 중...`);
    const source = await getFileContent(
      ORG,
      SHARED_WORKFLOWS_REPO,
      file.source
    );
    if (!source) throw new Error(`템플릿 없음: ${file.source}`);

    // 대상 파일 sha 확인 (이미 존재하면 덮어쓰기에 필요)
    const existing = await getFileContent(
      targetRepo.owner.login,
      targetRepo.name,
      file.target,
      defaultBranch
    );

    setStatus(`✓ 읽음. ${file.target} 커밋 중...`);
    await putFile(targetRepo.owner.login, targetRepo.name, file.target, {
      contentB64: source.content.replace(/\n/g, ""),
      message: `chore: apply ${feature.id} workflow (${file.target.split("/").pop()})`,
      sha: existing ? existing.sha : undefined,
      branch: defaultBranch,
    });
    setStatus(`✓ ${file.target}`);
  }
  setStatus("모든 파일 적용 완료");
}
