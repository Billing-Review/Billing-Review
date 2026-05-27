# Javadoc 작성 가이드

## Controller 메서드

```java
/**
 * [1] API 제목 (필수)
 * @apiScope [2] external | internal | private  (필수)
 *
 * [3] API 상세 설명 (선택) — 동작 방식, 예외 케이스 등
 *
 * @path   [4] PathVariable명  설명
 * @header [5] 헤더명          설명
 * @param  [6] QueryParam명    설명
 * @body   [7] 변수명          설명
 * @return [8] 응답 설명 (선택)
 */
```

| 태그 | 필수 조건 |
|------|-----------|
| 첫 줄 (제목) | 필수 |
| `@apiScope` | 필수 — `external` / `internal` / `private` |
| `@path` | `@PathVariable` 파라미터가 있으면 각각 필수 |
| `@header` | `@RequestHeader` 파라미터가 있으면 각각 필수 |
| `@param` | `@RequestParam` 파라미터가 있으면 각각 필수 |
| `@body` | `@RequestBody` / `@ModelAttribute` 파라미터가 있으면 각각 필수 |
| `@return` | 선택 |

### 작성 예시

```java
// @PathVariable → @path
/**
 * Todo 단건 조회
 * @apiScope external
 *
 * 지정한 ID의 Todo 항목을 반환합니다.
 * 존재하지 않는 ID 요청 시 404를 반환합니다.
 *
 * @path id 조회할 Todo의 고유 식별자
 * @return 조회된 Todo 정보
 */
@GetMapping("/{id}")
public TodoResponse getById(@PathVariable Long id) { ... }


// @RequestParam → @param
/**
 * Todo 목록 조회
 * @apiScope external
 *
 * @param status 필터링할 상태값 (TODO / IN_PROGRESS / DONE), 미입력 시 전체
 * @param page 페이지 번호 (0-based)
 * @return 페이지네이션된 Todo 목록
 */
@GetMapping
public Page<TodoResponse> findAll(
        @RequestParam(required = false) TodoStatus status,
        @RequestParam(defaultValue = "0") int page) { ... }


// @RequestHeader → @header
/**
 * Todo 단건 조회 (내부 시스템)
 * @apiScope internal
 *
 * @path id 조회할 Todo의 고유 식별자
 * @header X-System-Id 호출 시스템 식별자
 * @return 조회된 Todo 정보
 */
@GetMapping("/{id}")
public TodoResponse getById(
        @PathVariable Long id,
        @RequestHeader("X-System-Id") String systemId) { ... }


// @RequestBody → @body (DTO 필드 스펙은 DTO Javadoc에서 자동 추출, 여기서는 변수 역할만 명시)
/**
 * Todo 생성
 * @apiScope external
 *
 * @body request 생성할 Todo 정보 (title/content/dueDate/priority)
 * @return 생성된 Todo 정보
 */
@PostMapping
public TodoResponse create(@RequestBody TodoCreateRequest request) { ... }


// @ModelAttribute → @body 동일
/**
 * Todo 검색
 * @apiScope internal
 *
 * @body request 검색 조건 (keyword/status/page/size)
 * @return 검색된 Todo 목록
 */
@GetMapping("/search")
public Page<TodoResponse> search(@ModelAttribute TodoSearchRequest request) { ... }
```

---

## DTO 필드

각 필드에 설명과 `@ex` 예시값을 작성한다.

```java
/**
 * 필드 설명
 * @ex 예시값
 */
private Type fieldName;
```

### 작성 예시

```java
public class TodoCreateRequest {

    /**
     * Todo 제목. 최대 100자.
     * @ex "오늘 할 일 목록 정리"
     */
    private String title;

    /**
     * 마감일 (yyyy-MM-dd).
     * @ex "2026-05-10"
     */
    private LocalDate dueDate;

    /**
     * 우선순위. 1~5 권장, 숫자가 높을수록 중요.
     * @ex 3
     */
    private Integer priority;
}
```

Response DTO는 한 줄 인라인 형식도 허용한다.

```java
public class TodoResponse {
    /** Todo 고유 식별자. @ex 42 */
    private Long id;

    /** 현재 상태 (TODO / IN_PROGRESS / DONE). @ex "TODO" */
    private TodoStatus status;
}
```
