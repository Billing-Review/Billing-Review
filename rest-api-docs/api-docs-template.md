# API 문서 템플릿

아래 구조를 그대로 사용한다. 괄호 안 설명은 작성 가이드이며 실제 출력에서 제거한다.

**주의**
- **H1 / 부제 / `### 확인사항` 섹션은 절대 작성하지 않는다** — 시스템이 자동으로 주입한다.
- 한 문서는 **단일 엔드포인트**만 다룬다. 여러 엔드포인트를 한 문서에 합치지 않는다.
- `@apiScope` 분류 라벨(`[사외]`/`[사내]`/`[내부]`)도 작성하지 않는다 (시스템이 자동 부착).

---

## 개요

(이 엔드포인트의 목적과 사용 시나리오를 2~3줄로 설명한다)

---

## 서버 URL

| 환경 | Base URL |
|------|----------|
| Alpha | https://alpha-{서비스}.example.com |
| Real  | https://{서비스}.example.com |

---

## 요청

| 항목 | 값 |
|------|-----|
| Method | GET \| POST \| PUT \| PATCH \| DELETE |
| URL | /api/경로 |
| Content-Type | application/json |
| 인증 | Bearer Token \| 없음 |

**Path Variables** (없으면 생략)

| 변수명 | 타입 | 설명 |
|--------|------|------|
| id | Long | 리소스 식별자 |

**Query Parameters** (없으면 생략)

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|----------|------|------|--------|------|
| page | Integer | N | 0 | 페이지 번호 (0-based) |

**Request Body** (GET·DELETE 등 body 없으면 생략)

| 필드명 | 타입 | 필수 | 설명 |
|--------|------|------|------|
| fieldName | String | Y | 설명 |

**요청 예시**

```json
{
  "fieldName": "값"
}
```

---

## 응답

| 필드명 | 타입 | 설명 |
|--------|------|------|
| code | String | 결과 코드 (SUCCESS / ERROR) |
| message | String | 결과 메시지 |
| data | Object | 응답 데이터 |
| data.fieldName | String | 설명 |

**응답 예시**

```json
{
  "code": "SUCCESS",
  "message": "처리되었습니다.",
  "data": {
    "fieldName": "값"
  }
}
```

---

## 오류 코드 (주요 케이스만)

| HTTP Status | 코드 | 설명 |
|-------------|------|------|
| 400 | INVALID_PARAM | 요청 파라미터 오류 |
| 401 | UNAUTHORIZED | 인증 실패 |
| 404 | NOT_FOUND | 리소스 없음 |
| 500 | INTERNAL_ERROR | 서버 오류 |
