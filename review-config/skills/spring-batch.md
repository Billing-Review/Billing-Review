# Spring Batch 리뷰 가이드

## Job / Step 설계

- Job은 단일 책임 — 하나의 Job이 여러 도메인을 처리하지 않도록 설계
- Step 간 데이터 공유는 `JobExecutionContext` 또는 `StepExecutionContext` 사용
- `JobParameter`로 실행 시점 값 전달 — 코드에 하드코딩 금지
- 멱등성(Idempotency) 보장 여부 확인 — 동일 Job 재실행 시 중복 처리 방지

---

## Chunk 처리

### Reader
- `JpaPagingItemReader` 사용 시 `pageSize`와 `chunkSize` 일치 권장
- `JdbcCursorItemReader` 사용 시 Connection 유지 시간 고려
- `JpaPagingItemReader`에서 정렬 기준(`ORDER BY`) 누락 시 페이징 결과 불일치 주의

### Processor
- `ItemProcessor`는 단일 변환 책임만 가진다
- `null` 반환 시 해당 아이템이 Writer로 전달되지 않음 — 의도적 필터링에만 사용

### Writer
- `JpaItemWriter` 사용 시 `EntityManager.merge()` 호출됨 — 의도치 않은 INSERT 주의
- 대량 처리 시 `JdbcBatchItemWriter` 성능이 더 우수
- Writer에서 예외 발생 시 Chunk 단위로 롤백됨을 인지

---

## 트랜잭션

- Chunk 단위로 트랜잭션 커밋 — `chunkSize` 설정값 확인
- Step에 `@Transactional` 직접 선언 금지 — Batch가 트랜잭션을 자체 관리
- `SkipPolicy`, `RetryPolicy` 설정 시 트랜잭션 경계 명확히 확인

---

## 성능

- `chunkSize`는 메모리와 DB 부하를 고려하여 적절히 설정 (기본 10은 대부분 너무 작음)
- 대용량 처리 시 `Partitioning` 또는 `Multi-threaded Step` 고려
- `Multi-threaded Step` 사용 시 `ItemReader`의 thread-safe 여부 필수 확인
- `JpaPagingItemReader`는 thread-safe하지 않음 → `SynchronizedItemStreamReader`로 감싸기

---

## 모니터링 / 안정성

- `JobExecutionListener`, `StepExecutionListener`로 실행 이력 로깅
- 배치 메타 테이블(`BATCH_JOB_INSTANCE` 등) 정상 관리 여부 확인
- 실패한 Job 재시작 시 `RestartPolicy` 및 `allowStartIfComplete` 설정 확인
- 스케줄러(`@Scheduled`, Quartz 등)와 Batch Job 연동 시 중복 실행 방지 처리
