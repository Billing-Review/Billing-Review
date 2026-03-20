# 공통 코딩 컨벤션

이 문서는 Organization 전체에 적용되는 코딩 컨벤션이다.
리뷰 시 아래 규칙 위반 여부를 확인한다.

---

## 네이밍 규칙

### 클래스 / 인터페이스
- PascalCase를 사용한다.
- 클래스명은 명사 또는 명사구로 작성한다.
- 인터페이스에 `I` 접두어를 사용하지 않는다.

### 메서드
- camelCase를 사용한다.
- 동사로 시작한다: `get`, `find`, `create`, `update`, `delete`, `validate`, `is`, `has`, `can`
- boolean 반환 메서드는 `is`, `has`, `can`, `should` 등으로 시작한다.

### 변수
- camelCase를 사용한다.
- 의미가 명확한 이름을 사용한다. `temp`, `data`, `info`, `result` 같은 모호한 이름을 피한다.
- 한 글자 변수는 람다의 짧은 파라미터 외에는 사용하지 않는다.

### 상수
- UPPER_SNAKE_CASE를 사용한다.
- 의미 있는 이름으로 정의한다: `MAX_RETRY_COUNT`, `DEFAULT_PAGE_SIZE`

### 패키지
- 전부 소문자를 사용한다.
- 도메인 역순 규칙을 따른다.

---

## 코드 구조

### 메서드
- 하나의 메서드는 하나의 책임만 갖는다.
- 메서드 길이는 50줄 이내를 권장한다.
- 파라미터는 3개 이하를 권장한다. 초과 시 객체로 묶는다.

### 중첩
- 중첩 깊이는 3단계 이내로 유지한다.
- Early Return 패턴을 적극 활용하여 중첩을 줄인다.

```java
// ❌ Bad — 깊은 중첩
public void process(Order order) {
    if (order != null) {
        if (order.isValid()) {
            if (order.hasItems()) {
                // 실제 로직
            }
        }
    }
}

// ✅ Good — Early Return
public void process(Order order) {
    if (order == null) return;
    if (!order.isValid()) return;
    if (!order.hasItems()) return;

    // 실제 로직
}
```

### 매직넘버
- 코드에 숫자 리터럴을 직접 사용하지 않는다.
- 의미 있는 상수로 정의한다.

```java
// ❌ Bad
if (retryCount > 3) { ... }
Thread.sleep(5000);

// ✅ Good
private static final int MAX_RETRY_COUNT = 3;
private static final long RETRY_DELAY_MS = 5_000L;

if (retryCount > MAX_RETRY_COUNT) { ... }
Thread.sleep(RETRY_DELAY_MS);
```

---

## 예외 처리

- 빈 catch 블록을 절대 사용하지 않는다.
- 예외를 잡을 때는 가능한 구체적인 예외 타입을 사용한다.
- 원인 예외(cause)를 반드시 체이닝한다.
- 비즈니스 예외와 시스템 예외를 구분한다.

```java
// ❌ Bad
try {
    process();
} catch (Exception e) {
    log.error("실패");
}

// ✅ Good
try {
    process();
} catch (IllegalArgumentException e) {
    throw new BusinessException("주문 처리 실패: 잘못된 파라미터", e);
} catch (IOException e) {
    throw new SystemException("주문 처리 실패: 외부 시스템 오류", e);
}
```

---

## Java 규칙

### Optional
- `Optional.get()`을 직접 호출하지 않는다.
- `orElse`, `orElseThrow`, `orElseGet`, `ifPresent` 등을 사용한다.
- `Optional`을 필드나 파라미터 타입으로 사용하지 않는다. 반환 타입에만 사용한다.

```java
// ❌ Bad
User user = userRepository.findById(id).get();

// ✅ Good
User user = userRepository.findById(id)
    .orElseThrow(() -> new NotFoundException("사용자를 찾을 수 없습니다: " + id));
```

### Stream
- Stream 내에서 부작용(side-effect)을 발생시키지 않는다.
- `forEach`에서 외부 상태를 변경하지 않는다.
- 복잡한 Stream 파이프라인은 의미 있는 메서드로 분리한다.

### 불변성
- DTO 클래스에는 `record` 또는 `@Value`(Lombok)를 사용한다.
- 컬렉션은 불변으로 반환한다: `List.of()`, `Map.of()`, `Collections.unmodifiable*()`
- 가능한 `final` 필드를 사용한다.

### Null 처리
- `null`을 반환하는 대신 빈 컬렉션(`List.of()`)이나 `Optional`을 반환한다.
- `@NonNull`, `@Nullable` 어노테이션을 활용하여 null 계약을 명시한다.

---

## 주석 / 문서화

### 작성 기준
- public API에는 Javadoc을 작성한다.
- **무엇(what)**보다 **왜(why)** 주석을 우선한다.
- 코드만으로 명확한 경우 주석을 달지 않는다.

### TODO
- TODO 주석에는 담당자와 간단한 설명을 포함한다.
- `// TODO(kim-cs): 결제 실패 재시도 로직 추가`

### 금지
- 주석 처리된 코드를 커밋하지 않는다. 필요하면 Git 히스토리에서 복원한다.
- 당연한 내용을 반복하는 주석을 달지 않는다.

```java
// ❌ Bad — 코드를 그대로 설명
// 사용자 이름을 가져온다
String name = user.getName();

// ✅ Good — 비즈니스 이유 설명
// 결제 완료 후 30일이 지나면 환불 불가 정책에 의해 만료 처리
if (payment.isExpiredForRefund()) { ... }
```

---

## 로깅

- 적절한 로그 레벨을 사용한다.
    - `ERROR`: 즉시 조치가 필요한 장애
    - `WARN`: 정상은 아니지만 시스템이 계속 동작하는 상태
    - `INFO`: 주요 비즈니스 이벤트 (주문 생성, 결제 완료 등)
    - `DEBUG`: 개발/디버깅용 상세 정보
- 민감 정보(비밀번호, 카드번호, 개인정보)를 로그에 남기지 않는다.
- 예외 로깅 시 스택트레이스를 포함한다: `log.error("메시지", exception)`

---

## Git 커밋 컨벤션

- 커밋 메시지는 아래 형식을 따른다: `type: 간결한 설명`
- type: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `style`, `perf`
- 한 커밋에 하나의 논리적 변경만 포함한다.