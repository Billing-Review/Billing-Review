# 두레이 위키 구조

## 위키 경로 분류 규칙

API 엔드포인트 URL 패턴을 기준으로 게시 위치를 자동 분류한다.

| URL 패턴 | 위키 카테고리 | 비고 |
|----------|--------------|------|
| `internal` 포함 | BILL-GATEWAY (사내) | 사내 시스템 간 연동 API |
| `external` 포함 | BILL-GATEWAY (사외) | 외부 파트너·클라이언트용 API |
| 해당 없음 | 빌링서비스실 내부 | 내부 관리용 또는 분류 불명 |

> 분류가 불명확하면 `빌링서비스실 내부` 로 기본 처리하고,
> 검토자가 publish 시 직접 올바른 위치로 이동한다.

---

## Draft → Publish 워크플로우

```
PR merge
  │
  ▼
[자동] reusable-doc-from-diff
  │  diff에서 API 변경 감지
  │  Claude로 문서 초안 생성
  ▼
[자동] reusable-publish-to-dooray
  │  Draft 페이지로 두레이에 업로드
  │  위치: DOORAY_DRAFT_PARENT_PAGE_ID 하위
  ▼
[수동] 담당자 검토 및 수정
  │
  ▼
[수동] publish workflow 실행
  │  Draft 페이지 → 본 위키 페이지로 이동
  │  Draft 페이지 삭제
  ▼
완료
```

---

## Draft 페이지 메타 정보

자동 생성된 Draft 페이지 상단에는 아래 정보가 추가된다.

```
> **[Draft]** 자동 생성된 API 문서입니다. 검토 후 publish 하세요.
> 생성 시각: YYYY-MM-DD HH:MM UTC | 위키 분류: [카테고리명]
```

---

## 위키 페이지 제목 규칙

| 상황 | 제목 형식 | 예시 |
|------|----------|------|
| diff 기반 자동 생성 | `[API Draft] {PR 제목}` | `[API Draft] 결제 취소 API 추가` |
| 코드 기반 수동 생성 | `[API Draft] {파일명} API 명세` | `[API Draft] OrderController API 명세` |
| publish 후 (사내) | `[사내] {API 그룹명} API 명세` | `[사내] 주문 API 명세` |
| publish 후 (사외) | `[사외] {API 그룹명} API 명세` | `[사외] 결제 API 명세` |

---

## Secrets (Org 레벨 관리)

| Secret 이름 | 용도 |
|-------------|------|
| `DOORAY_API_KEY` | 두레이 API 인증 키 |
| `DOORAY_MEMBER_ID` | 두레이 멤버 ID (인증 헤더 구성용) |
| `DOORAY_PROJECT_ID` | 위키가 속한 두레이 프로젝트 ID |
| `DOORAY_DRAFT_PARENT_PAGE_ID` | Draft 페이지가 생성될 부모 페이지 ID |

인증 헤더 형식: `Authorization: dooray-api {MEMBER_ID}:{API_KEY}`
