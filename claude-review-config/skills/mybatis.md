# MyBatis 리뷰 가이드

## Mapper 인터페이스

- `@Mapper` 어노테이션 필수
- 메서드명은 동사로 시작: `select*`, `insert*`, `update*`, `delete*`, `count*`
- 파라미터가 2개 이상이면 `@Param` 어노테이션으로 명시
- DTO/VO 반환 타입을 명확히 지정 — `Map<String, Object>` 반환 지양

---

## XML Mapper

### SQL 작성
- `SELECT *` 금지 — 필요한 컬럼만 명시
- 동적 쿼리는 `<if>`, `<choose>`, `<foreach>` 태그 활용
- `<foreach>`의 `collection` 속성값과 `@Param` 명칭 일치 여부 확인
- SQL Injection 방지 — 파라미터 바인딩은 `#{}` 사용, `${}` 사용 시 이유 명시

### ResultMap
- 컬럼명과 필드명이 다를 경우 `<resultMap>` 명시적 정의
- 중첩 결과(`association`, `collection`) 사용 시 N+1 주의
- `<resultMap>` 재사용 시 `extends` 활용

### 공통
- 반복되는 SQL 조각은 `<sql>` + `<include>` 로 추출
- namespace는 Mapper 인터페이스 전체 경로와 일치
- `id`는 Mapper 인터페이스 메서드명과 정확히 일치

---

## 성능

- 대량 INSERT는 `<foreach>`로 배치 처리
- 불필요한 전체 조회 후 애플리케이션 필터링 금지 — WHERE 절 조건 추가
- 페이징 쿼리에 `LIMIT/OFFSET` 또는 `ROW_NUMBER()` 적용 여부 확인
- 인덱스를 활용할 수 없는 `LIKE '%keyword'` 패턴 지양

---

## 트랜잭션

- MyBatis + Spring 조합 시 `@Transactional`로 트랜잭션 관리
- 여러 Mapper 메서드를 하나의 트랜잭션으로 묶어야 할 경우 Service 레이어에서 처리
