# Java & Spring Boot 리뷰 가이드

## Java

### 필수 확인
- `Optional.get()` 직접 호출 금지 → `orElseThrow()`, `orElse()` 사용
- `null` 반환 금지 → 빈 컬렉션(`List.of()`) 또는 `Optional` 반환
- Stream 내부에서 외부 상태 변경(side-effect) 금지
- `instanceof` 후 캐스팅 시 패턴 매칭 활용 (Java 16+)
- `var` 남용 금지 — 타입이 불명확한 경우 명시적 타입 선언

### 불변성
- DTO는 `record` 또는 `@Value`(Lombok) 사용
- 컬렉션 반환 시 `List.of()`, `Collections.unmodifiableList()` 등 불변으로 반환
- 가능한 `final` 필드 사용

### 예외 처리
- 빈 `catch` 블록 금지
- 원인 예외(cause) 반드시 체이닝: `new BusinessException("msg", e)`
- `Exception`, `RuntimeException` 포괄 catch 지양 → 구체적인 예외 타입 사용
- 비즈니스 예외와 시스템 예외 분리

---

## Spring Boot

### Bean / DI
- 필드 주입(`@Autowired`) 금지 → 생성자 주입 사용
- `@RequiredArgsConstructor` + `final` 필드 조합 권장
- 순환 의존성 발생 시 설계 재검토

### Controller
- `@RestController` + `@RequestMapping` 클래스 레벨 경로 설정
- 요청 DTO에 `@Valid` 누락 여부 확인
- 응답은 `ResponseEntity<T>` 또는 공통 응답 래퍼 사용
- 비즈니스 로직을 Controller에 작성 금지

### Service
- `@Transactional(readOnly = true)` 클래스 레벨 기본 적용
- 쓰기 메서드에만 `@Transactional` 오버라이드
- 트랜잭션 경계 밖에서 지연 로딩(Lazy Loading) 접근 금지

### 예외 처리
- `@RestControllerAdvice` + `@ExceptionHandler`로 전역 처리
- `Exception` 전역 핸들러에서 `e.getMessage()` 클라이언트 직접 노출 금지
- 커스텀 예외 클래스로 비즈니스 예외 명확히 분리

### 설정
- 민감 정보(DB 비밀번호, API Key 등) `application.yml` 하드코딩 금지 → 환경 변수(`${ENV_VAR}`) 사용
- `@Value` 보다 `@ConfigurationProperties` 바인딩 권장
