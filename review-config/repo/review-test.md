# review-test 리뷰 규칙

## 기술 스택
- java-spring
- jpa

## 리뷰 제외
- `src/main/generated/**`
- `**/Q*.java`

## Rest API Naming 규칙

- 소문자만 사용, 구분자는 하이픈(`-`), URI에 확장자 포함 금지
- URL 구조: `{domain}/{version}/{path}/{resource}` (예: `api-pay.nhncloud.com/v1.0/payment/reservations/123`)
- Resource는 복수 명사 사용: `GET /reservations/123`, `POST /reservations`
- CRUD 불가능한 경우 Controller 사용: POST 고정, URI 맨 끝에 동사 배치
  - ID 특정 가능: `POST /reservations/123/cancel`
  - ID 특정 불가: `POST /reservation/cancel-by-order-no`
- Controller 동사: 단건 조회 `get`, 다건 조회 `find`, 수정 `modify`, 생성 `create` (`search`, `update`, `insert` 미사용)
- column 값 조회는 query parameter 사용 (`GET /reservations?userno=1`), document에 없는 값 조회는 controller 사용