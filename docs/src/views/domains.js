import { h, mount, clear } from "../utils/dom.js";
import { toast } from "../utils/toast.js";
import {
  readServiceConfig,
  setServiceEntry,
  deleteServiceEntry,
  parseGatewayYml,
} from "../api/service-config.js";

const DEFAULT_ENV_KEYS = ["Alpha", "Beta", "Real"];

export async function renderDomains(root, selected /* optional serviceName */) {
  const listEl = h("div", { class: "sidebar__list" });
  const detailEl = h("div", { class: "detail" });
  const addBtn = h(
    "button",
    { class: "btn btn--small", title: "서비스 추가", onclick: openAddServiceModal },
    "+"
  );
  const refreshBtn = h(
    "button",
    { class: "btn btn--small", title: "새로고침", onclick: () => load() },
    "↻"
  );

  let json = {};
  let selectedName = selected || null;

  async function load() {
    clear(listEl);
    listEl.appendChild(
      h("div", { class: "empty", style: { padding: "16px" } },
        h("span", { class: "spinner" }), " 로딩 중...")
    );
    try {
      const r = await readServiceConfig();
      json = r.json || {};
      renderSidebar();
      renderDetail();
    } catch (err) {
      clear(listEl);
      listEl.appendChild(h("div", { class: "empty" }, `오류: ${err.message}`));
    }
  }

  function listServices() {
    return Object.keys(json).filter((k) => !k.startsWith("_")).sort();
  }

  function renderSidebar() {
    clear(listEl);
    const services = listServices();
    if (!services.length) {
      listEl.appendChild(h("div", { class: "empty" }, "등록된 서비스 없음"));
      return;
    }
    for (const name of services) {
      const entry = json[name] || {};
      const useGateway = !!entry.useGateway;
      const item = h(
        "a",
        {
          class: "sidebar__item" + (name === selectedName ? " is-active" : ""),
          href: `#/domains/${name}`,
        },
        h("span", { class: "name" }, name),
        h(
          "span",
          { class: `badge ${useGateway ? "partial" : "full"}` },
          useGateway ? "GW" : "direct"
        )
      );
      listEl.appendChild(item);
    }
  }

  function renderDetail() {
    clear(detailEl);
    if (!selectedName) {
      detailEl.appendChild(
        h("div", { class: "card empty" }, "← 왼쪽에서 서비스를 선택하세요")
      );
      return;
    }
    const entry = json[selectedName] || { useGateway: false, environments: {} };
    detailEl.appendChild(renderServiceCard(selectedName, entry));
  }

  function renderServiceCard(name, entry) {
    const useGatewayCheck = h("input", {
      type: "checkbox",
      checked: !!entry.useGateway,
    });

    const envInputs = {};
    const envContainer = h("div");
    const groupsContainer = h("div");

    function renderEnvForm() {
      clear(envContainer);
      const envs = (entry.environments && Object.keys(entry.environments).length)
        ? entry.environments
        : Object.fromEntries(DEFAULT_ENV_KEYS.map((k) => [k, ""]));
      // 입력 폼: 키/값 표
      for (const k of Object.keys(envs).length ? Object.keys(envs) : DEFAULT_ENV_KEYS) {
        if (!(k in envInputs)) {
          envInputs[k] = h("input", {
            type: "text",
            value: envs[k] || "",
            placeholder: `https://...`,
          });
        }
        envContainer.appendChild(
          h("div", { class: "env-row" },
            h("label", { class: "env-row__label" }, k),
            envInputs[k]
          )
        );
      }
    }

    function renderGroups() {
      clear(groupsContainer);
      if (!useGatewayCheck.checked) return;
      const groups = entry.groups || [];
      groupsContainer.appendChild(
        h("div", { class: "section-title", style: { marginTop: "16px" } },
          "Groups (패키지별 라우팅)",
          h("button", {
            class: "btn btn--small",
            style: { marginLeft: "auto" },
            onclick: () => openGroupEditor(null),
          }, "+ 그룹 추가")
        )
      );
      if (!groups.length) {
        groupsContainer.appendChild(
          h("div", { class: "empty", style: { padding: "16px" } },
            "그룹 없음. + 그룹 추가 를 누르세요. YML 붙여넣기로 한 번에 채울 수도 있어요.")
        );
        return;
      }
      const tbl = h("table", { class: "matrix-table" },
        h("thead", null,
          h("tr", null,
            h("th", null, "이름"),
            h("th", null, "패키지 prefix"),
            h("th", null, "internal"),
            h("th", null, "external"),
            h("th", { style: { width: "100px" } }, "")
          )
        ),
        h("tbody", null,
          ...groups.map((g, idx) =>
            h("tr", null,
              h("td", null, g.name || ""),
              h("td", null, h("code", null, g.packagePrefix || "")),
              h("td", null, h("code", null, g.internalUrlPrefix || "")),
              h("td", null, h("code", null, g.externalUrlPrefix || "")),
              h("td", null,
                h("button", { class: "btn btn--small", onclick: () => openGroupEditor(idx) }, "수정"),
                " ",
                h("button", {
                  class: "btn btn--small btn--danger",
                  onclick: () => removeGroup(idx),
                }, "×")
              )
            )
          )
        )
      );
      groupsContainer.appendChild(tbl);
    }

    function openGroupEditor(editIdx) {
      const existing = editIdx == null ? {} : (entry.groups || [])[editIdx] || {};
      const ymlInput = h("textarea", {
        rows: 6,
        placeholder: `붙여넣기 예:\n- id: pay-api\n  predicates:\n    - Path=/pay/**\n  filters:\n    - RewritePath=/pay/(?<segment>/?.*), /external/\${segment}`,
        style: { width: "100%", fontFamily: "monospace", fontSize: "12px" },
      });
      const nameIn = h("input", { type: "text", value: existing.name || "" });
      const pkgIn = h("input", { type: "text", value: existing.packagePrefix || "", placeholder: "com.bill.payment" });
      const intIn = h("input", { type: "text", value: existing.internalUrlPrefix || "", placeholder: "/external" });
      const extIn = h("input", { type: "text", value: existing.externalUrlPrefix || "", placeholder: "/pay" });
      const parseBtn = h("button", {
        class: "btn btn--small",
        onclick: () => {
          const parsed = parseGatewayYml(ymlInput.value);
          if (!parsed) {
            toast("YML 에서 routing 정보를 찾지 못했습니다", "error");
            return;
          }
          if (parsed.name && !nameIn.value) nameIn.value = parsed.name;
          if (parsed.externalUrlPrefix) extIn.value = parsed.externalUrlPrefix;
          if (parsed.internalUrlPrefix) intIn.value = parsed.internalUrlPrefix;
          toast("YML 파싱 완료", "success");
        },
      }, "YML 파싱해서 채우기");
      const okBtn = h("button", { class: "btn" }, editIdx == null ? "추가" : "저장");
      const cancelBtn = h("button", {
        class: "btn btn--ghost",
        style: { color: "#1f2328", border: "1px solid #d0d7de" },
      }, "취소");

      const backdrop = h("div", { class: "modal-backdrop" });
      const modal = h("div", { class: "modal", onclick: (e) => e.stopPropagation() },
        h("div", { class: "modal__header" },
          h("h3", { class: "modal__title" }, editIdx == null ? "그룹 추가" : "그룹 수정"),
        ),
        h("div", { style: { padding: "0 24px" } },
          h("div", { class: "field" },
            h("label", null, "Gateway YML (선택 — 붙여넣고 파싱 버튼)"),
            ymlInput,
            h("div", { style: { textAlign: "right", marginTop: "4px" } }, parseBtn)
          ),
          h("hr"),
          h("div", { class: "field" },
            h("label", null, "그룹 이름"), nameIn
          ),
          h("div", { class: "field" },
            h("label", null, "패키지 prefix"), pkgIn
          ),
          h("div", { class: "field" },
            h("label", null, "internal URL prefix (코드 path)"), intIn
          ),
          h("div", { class: "field" },
            h("label", null, "external URL prefix (외부 호출 path)"), extIn
          ),
        ),
        h("div", { class: "modal__actions" }, cancelBtn, okBtn)
      );

      cancelBtn.addEventListener("click", () => backdrop.remove());
      backdrop.addEventListener("click", (e) => { if (e.target === backdrop) backdrop.remove(); });

      okBtn.addEventListener("click", () => {
        const newGroup = {
          name: nameIn.value.trim(),
          packagePrefix: pkgIn.value.trim(),
          internalUrlPrefix: intIn.value.trim(),
          externalUrlPrefix: extIn.value.trim(),
        };
        if (!newGroup.name || !newGroup.packagePrefix) {
          toast("이름과 패키지 prefix 는 필수", "error");
          return;
        }
        entry.groups = entry.groups || [];
        if (editIdx == null) entry.groups.push(newGroup);
        else entry.groups[editIdx] = newGroup;
        renderGroups();
        backdrop.remove();
      });

      mount(backdrop, modal);
      document.body.appendChild(backdrop);
    }

    function removeGroup(idx) {
      if (!confirm("이 그룹을 삭제할까요?")) return;
      entry.groups.splice(idx, 1);
      renderGroups();
    }

    useGatewayCheck.addEventListener("change", () => renderGroups());

    const saveBtn = h("button", { class: "btn", onclick: async () => {
      const newEntry = {
        useGateway: useGatewayCheck.checked,
        environments: {},
      };
      for (const [k, inp] of Object.entries(envInputs)) {
        const v = inp.value.trim();
        if (v) newEntry.environments[k] = v;
      }
      if (useGatewayCheck.checked && entry.groups) {
        newEntry.groups = entry.groups;
      }
      saveBtn.disabled = true;
      saveBtn.textContent = "저장 중...";
      try {
        await setServiceEntry(name, newEntry);
        json[name] = newEntry;
        toast(`${name} 저장 완료`, "success");
      } catch (err) {
        toast(`저장 실패: ${err.message}`, "error", 5000);
      } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = "저장";
      }
    } }, "저장");

    const deleteBtn = h("button", {
      class: "btn btn--danger",
      onclick: async () => {
        if (!confirm(`서비스 "${name}" 의 도메인 설정을 삭제할까요?`)) return;
        try {
          await deleteServiceEntry(name);
          delete json[name];
          selectedName = null;
          renderSidebar();
          renderDetail();
          toast(`${name} 삭제 완료`, "success");
        } catch (err) {
          toast(`삭제 실패: ${err.message}`, "error", 5000);
        }
      },
    }, "삭제");

    renderEnvForm();
    renderGroups();

    return h("div", { class: "card" },
      h("div", {
        style: { display: "flex", justifyContent: "space-between", alignItems: "center" },
      },
        h("h2", { class: "card__title", style: { margin: 0 } }, name),
        deleteBtn
      ),
      h("div", { class: "meta" },
        h("label", { style: { display: "flex", alignItems: "center", gap: "6px" } },
          useGatewayCheck, " useGateway (게이트웨이 통해 노출)"
        )
      ),
      h("div", { class: "section-title" }, "환경별 Base URL"),
      h("p", { class: "card__desc" },
        useGatewayCheck.checked
          ? "게이트웨이 도메인을 입력하세요 (서비스 자체 도메인이 아니라 게이트웨이의 외부 도메인)."
          : "이 서비스의 도메인을 환경별로 입력하세요."
      ),
      envContainer,
      groupsContainer,
      h("div", { style: { textAlign: "right", marginTop: "16px" } }, saveBtn)
    );
  }

  function openAddServiceModal() {
    const nameInput = h("input", { type: "text", placeholder: "예) my-service" });
    const useGatewayCheck = h("input", { type: "checkbox" });
    const okBtn = h("button", { class: "btn" }, "추가");
    const cancelBtn = h("button", {
      class: "btn btn--ghost",
      style: { color: "#1f2328", border: "1px solid #d0d7de" },
    }, "취소");

    const backdrop = h("div", { class: "modal-backdrop" });
    const modal = h("div", { class: "modal", onclick: (e) => e.stopPropagation() },
      h("div", { class: "modal__header" },
        h("h3", { class: "modal__title" }, "서비스 추가"),
      ),
      h("div", { style: { padding: "0 24px" } },
        h("div", { class: "field" },
          h("label", null, "서비스 이름 (= GitHub 레포명)"),
          nameInput
        ),
        h("div", { class: "field" },
          h("label", null, useGatewayCheck, " useGateway (게이트웨이 통해 노출)")
        ),
      ),
      h("div", { class: "modal__actions" }, cancelBtn, okBtn)
    );

    cancelBtn.addEventListener("click", () => backdrop.remove());
    backdrop.addEventListener("click", (e) => { if (e.target === backdrop) backdrop.remove(); });

    okBtn.addEventListener("click", async () => {
      const name = nameInput.value.trim();
      if (!name) { toast("서비스 이름이 필요합니다", "error"); return; }
      if (json[name]) { toast("이미 존재하는 서비스", "error"); return; }
      const entry = {
        useGateway: useGatewayCheck.checked,
        environments: {},
      };
      try {
        await setServiceEntry(name, entry);
        json[name] = entry;
        selectedName = name;
        backdrop.remove();
        location.hash = `#/domains/${name}`;
        renderSidebar();
        renderDetail();
        toast(`${name} 추가 완료`, "success");
      } catch (err) {
        toast(`추가 실패: ${err.message}`, "error", 5000);
      }
    });

    mount(backdrop, modal);
    document.body.appendChild(backdrop);
    nameInput.focus();
  }

  // ── render layout ──
  mount(root,
    h("div", { class: "split" },
      h("aside", { class: "sidebar" },
        h("div", { class: "sidebar__head" },
          h("div", { style: { display: "flex", gap: "6px", alignItems: "center" } },
            h("strong", { style: { flex: 1 } }, "서비스 목록"),
            addBtn,
            refreshBtn
          )
        ),
        listEl
      ),
      detailEl
    )
  );

  await load();
}
