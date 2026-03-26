# Kafka 리뷰 가이드

## Producer

- `KafkaTemplate.send()` 반환값(`ListenableFuture` / `CompletableFuture`) 무시 금지 — 발송 실패 콜백 처리 필수
- 메시지 Key 설정 여부 확인 — 같은 Key는 같은 파티션으로 전달되어 순서 보장
- 대용량 메시지 전송 시 `max.request.size`, `message.max.bytes` 설정 확인
- 민감 데이터를 메시지 payload에 평문으로 포함하지 않도록 확인

---

## Consumer

### 설정
- `enable.auto.commit=false` 권장 — 수동 offset 커밋으로 메시지 유실 방지
- `AckMode` 명시적 설정 확인 (`MANUAL`, `MANUAL_IMMEDIATE`, `RECORD` 등)
- `max.poll.records`와 처리 시간을 고려하여 `max.poll.interval.ms` 설정

### 예외 처리
- `@KafkaListener` 내부 예외 처리 누락 시 Consumer가 중단될 수 있음
- `DefaultErrorHandler` 또는 `SeekToCurrentErrorHandler`로 재시도 정책 설정
- 처리 불가 메시지는 Dead Letter Topic(DLT)으로 전송하는 전략 권장
- 무한 재시도 방지 — `BackOff` 설정 및 최대 재시도 횟수 제한

### 멱등성
- Consumer 로직은 멱등성 보장 — 동일 메시지 재처리 시 중복 결과 방지
- DB 처리 전 중복 메시지 여부 확인 (offset, unique key 등 활용)

---

## 트랜잭션

- Kafka + DB 동시 처리 시 `@Transactional` + Kafka 트랜잭션 조합 주의
- `KafkaTransactionManager` 사용 시 DB 트랜잭션과의 묶음 처리 방식 확인
- Outbox 패턴 적용 여부 검토 — 분산 트랜잭션 문제 해결에 권장

---

## 성능

- Consumer의 처리 로직이 무거운 경우 `ConcurrentKafkaListenerContainerFactory`의 `concurrency` 설정 확인
- 파티션 수와 Consumer 수의 균형 확인 — Consumer 수 > 파티션 수면 유휴 Consumer 발생
- 배치 컨슘 처리 시 `BatchListener` 활용 고려
