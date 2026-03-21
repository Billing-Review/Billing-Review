# Redis 리뷰 가이드

## 기본 사용

- `RedisTemplate` 사용 시 직렬화 설정(`KeySerializer`, `ValueSerializer`) 명시 확인
- Key 네이밍 규칙 준수 — `{서비스}:{도메인}:{식별자}` 형식 권장 (예: `order:session:12345`)
- TTL(만료 시간) 설정 여부 확인 — TTL 없는 Key는 메모리 누수 원인
- 민감 정보(비밀번호, 개인정보 등) Redis 저장 금지

---

## 캐시 (`@Cacheable`)

- `@Cacheable`, `@CacheEvict`, `@CachePut` 적용 대상과 조건 확인
- Cache Key 표현식(`key = "#id"`)이 충돌 없이 유일한지 확인
- `@CacheEvict`의 `allEntries = true` 남용 금지 — 필요한 Key만 명시적으로 삭제
- 캐시 히트 시 DB 조회가 실제로 생략되는지 트랜잭션 경계 확인
- 캐시 갱신 전략(Cache-Aside, Write-Through 등) 명확히 정의

---

## 분산 락

- `SETNX` 또는 Redisson `RLock` 사용 여부 확인
- 락 TTL 설정 필수 — 프로세스 비정상 종료 시 락 해제 보장
- 락 획득 실패 시 처리 로직(재시도, 예외 등) 확인
- Redisson 사용 시 `tryLock(waitTime, leaseTime, TimeUnit)` 파라미터 적절성 확인
- 락 범위를 최소화 — 락 안에서 외부 API 호출, 무거운 연산 금지

---

## 데이터 구조

- 사용 목적에 맞는 자료구조 선택 여부 확인
  - 단순 캐시 → `String`
  - 세션 / 설정 → `Hash`
  - 순위표 → `ZSet (Sorted Set)`
  - 중복 제거 집합 → `Set`
  - 큐 / 스택 → `List`
- `KEYS *` 명령어 사용 금지 (운영 환경 성능 저하) → `SCAN` 사용

---

## 성능 / 안정성

- `@Cacheable` 메서드에서 대용량 객체 캐싱 시 메모리 사용량 확인
- Pipeline / Batch 명령어로 다수의 Redis 명령을 묶어 처리 고려
- Redis 장애 시 fallback 처리 여부 확인 — 캐시 미스 시 DB 직접 조회 등
- Connection Pool 설정(`maxTotal`, `maxIdle`, `minIdle`) 적절성 확인
