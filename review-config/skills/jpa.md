# JPA 리뷰 가이드

## Entity 설계

### 기본 규칙
- `@Entity` 클래스에 `@NoArgsConstructor(access = AccessLevel.PROTECTED)` 필수
- `public` 기본 생성자 금지 — 무분별한 인스턴스 생성 방지
- 생성 팩토리 메서드(`of()`, `create()`) 또는 `@Builder` 사용
- `@Setter` 전체 금지 — 변경 메서드를 명시적으로 정의

### 연관관계
- 양방향 연관관계보다 단방향 우선 검토
- 양방향 사용 시 연관관계 편의 메서드 필수
- `@OneToMany` 기본 fetch는 `LAZY` — `EAGER` 사용 금지
- `toString()`, `equals()`, `hashCode()`에 연관관계 필드 포함 금지 (순환 참조)

### 상속
- `@Inheritance(strategy = InheritanceType.JOINED)` 또는 `SINGLE_TABLE` 선택 근거 확인
- `@MappedSuperclass`로 공통 필드(`createdAt`, `updatedAt`) 추출 권장

---

## 성능

### N+1 문제
- 컬렉션 연관관계 조회 시 `fetch join` 또는 `@EntityGraph` 적용 여부 확인
- `@OneToMany` + `fetch join` 다중 사용 시 `MultipleBagFetchException` 주의
- 다중 컬렉션 fetch 필요 시 `@BatchSize` 또는 별도 쿼리로 분리

### 페이징
- `fetch join` + `Pageable` 동시 사용 시 `HibernateJpaDialect` 경고 확인
- 카운트 쿼리 분리(`countQuery`) 여부 확인
- 대용량 페이징은 커서 기반(No-Offset) 방식 권장

### 변경 감지 vs 병합
- `merge()` 사용 금지 → 변경 감지(Dirty Checking) 사용
- 업데이트 시 Entity 조회 후 변경 메서드 호출 패턴 확인

---

## Repository

- `JpaRepository` 상속 기본
- 복잡한 동적 쿼리는 `QueryDSL` 또는 `Specification` 사용
- `@Query`의 JPQL에서 `fetch join` + `distinct` 누락 여부 확인
- 네이티브 쿼리(`nativeQuery = true`) 사용 시 이유 명시 주석 필요

---

## 트랜잭션

- `@Transactional` 범위 내에서만 지연 로딩 접근
- `readOnly = true` 트랜잭션에서 변경 감지 비활성화 확인
- 트랜잭션 전파(`propagation`) 변경 시 의도 명확히 확인
