# API 문서 템플릿

빌링개발팀 "API 작성 템플릿"(`https://nhnent.dooray.com/project/pages/3656018975257559391`) 형식을 따른다.
괄호 안 설명은 작성 가이드이며 실제 출력에서 제거한다.

**주의 (시스템이 자동 처리하는 부분 — 절대 작성 금지)**
- **H1**: `[사외] / [사내] / [내부]` 라벨 + Javadoc 제목 (자동 주입)
- **하단 `### 확인사항` 체크리스트** (자동 부착)
- **출력 첫 줄은 반드시 `## Description` 이어야 한다**. H1, 인사말·서두·"코드 분석 완료" 같은 멘트 금지.
- Method/URL 은 본문 `## API Info` 표에서 다룬다 (별도 부제 작성 금지).
- 한 문서는 **단일 엔드포인트**만 다룬다.

---

## Description

* (이 엔드포인트가 하는 일을 1~3줄로 설명)
* (호출 시점, 비즈니스 컨텍스트 등 보충 설명이 있으면 bullet 추가)

## ACL

* ACL 요청 필요 - (해당 시 ACL 요청 위키 링크. 불필요 시 `해당 없음` 으로 작성)

## API Info

| 항목 | 값 |
| --- | --- |
| Path | (예: `/external/api/todo-list/{id}`) |
| Method | (예: `POST` / `GET` / `DELETE` / `PUT` / `PATCH`) |
| Content-Type | `application/json` |

**Domain** (service-config.json 에 정의된 환경만 행으로 추가)

| 환경 | URL |
| --- | --- |
| 알파 | (service-config.json 의 Alpha 환경 URL) |
| 베타 | (해당 시. service-config 에 없으면 행 생략) |
| 리얼 | (service-config.json 의 Real 환경 URL) |

## Request

> 어노테이션별로 표를 분리한다. **사용하지 않는 섹션은 헤딩까지 통째로 출력하지 않는다** (예: PathVariable 이 없으면 `### PathVariable` 자체를 작성하지 않음). Header 는 공통 헤더가 항상 있으므로 항상 출력한다.

### Header

(`@RequestHeader` — 항상 공통 헤더 2 개를 포함하고, 추가 인증 헤더가 있으면 행을 더한다)

| 항목명 | 필수여부 | 타입 | 의미 |
| --- | ---- | --- | --- |
| clientOrigin | Y | String | 호출처(빌링개발팀에 문의) [https://nhnent.dooray.com/share/pages/WIcRkRY9RdSwwP9_l5OskA/3657213289294964605](https://nhnent.dooray.com/share/pages/WIcRkRY9RdSwwP9_l5OskA/3657213289294964605) |
| requestId | N | String | 요청 uuid (로그 추적이나 확인 요청 시 사용됨) |

### PathVariable

(`@PathVariable`)

| 변수명 | 타입 | 설명 |
| --- | --- | --- |
| id | Long | 리소스 식별자 |

### Parameters

(`@RequestParam` — 쿼리스트링)

| 파라미터 | 필수여부 | 타입 | 기본값 | 설명 |
| --- | ---- | --- | --- | --- |
| page | N | Integer | `0` | 페이지 번호 (0-based) |

### Body

(`@RequestBody` / `@ModelAttribute` — DTO/Map 의 필드 또는 인자 자체 설명. 필드는 DTO 클래스의 Javadoc 에서 추출됨)

| 필드명 | 필수여부 | 타입 | 설명 |
| --- | ---- | --- | --- |
| title | Y | String | Todo 제목 (최대 100자) |
| dueDate | N | LocalDate | 마감일 (yyyy-MM-dd) |

### Example

```json
{
  "title": "오늘 할 일 목록 정리",
  "dueDate": "2026-05-10"
}
```

(GET·DELETE 등 body 가 없으면 `### Body` 와 `### Example` 섹션 자체를 출력하지 않는다)

## Response

### Header

| 필드명 | 필수여부 | 타입 | 설명 | 비고 |
| --- | ---- | --- | --- | --- |
| code | Y | String | 결과 코드<br>success : 성공<br>에러 코드 : [공통 에러코드](dooray://1387695619080878080/pages/3657213124062842835) |  |
| message | Y | String | 응답 메시지 |  |
| requestId | Y | String | 로그 확인 및 추적용 | request 시 요청했던 requestId<br>없다면 신규 requestId 를 생성 |

### Body

(응답 데이터 필드 정리. 없으면 `(없음)`)

| 필드명 | 필수여부 | 타입 | 설명 | 비고 |
| --- | ---- | --- | --- | --- |
| id | Y | Long | 생성된 리소스 식별자 |  |
| title | Y | String | Todo 제목 |  |
| status | Y | String | 현재 상태 | `TODO`/`IN_PROGRESS`/`DONE` |

### Example

```json
{
  "header": {
    "code": "success",
    "message": "success",
    "requestId": "bill-api-b15f7e69-d68b-4704-95b4-2f45543c384a"
  },
  "body": {
    "id": 42,
    "title": "오늘 할 일 목록 정리",
    "status": "TODO"
  }
}
```

## Error code

* 공통 에러 코드 : https://nhnent.dooray.com/share/pages/WIcRkRY9RdSwwP9_l5OskA/3657213124062842835
* (이 API 고유의 비즈니스 에러 코드가 있으면 아래에 표로 추가)

| 코드 | HTTP Status | 설명 |
| --- | ---- | --- |
| INVALID_PARAM | 400 | 요청 파라미터 오류 |
| NOT_FOUND | 404 | 리소스 없음 |
