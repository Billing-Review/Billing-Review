# API 문서 자동화를 위한 Javadoc 작성 가이드

자동화 시스템은 Controller 메서드와 DTO 필드의 Javadoc 주석을 읽어 API 문서를 생성합니다.
아래 규칙에 맞게 주석을 작성하면, PR 머지 시 Dooray 위키 Draft가 자동으로 생성됩니다.

---

## Controller 메서드 주석

```java
/**
 * [1] API 제목 (필수) — 위키 페이지 이름으로 사용됩니다
 * @apiScope [2] external | internal  (필수)
 *
 * [3] API 상세 설명 (선택) — 동작 방식, 예외 케이스 등
 *
 * @param [4] 파라미터명  파라미터 설명 (Path/Query 파라미터는 필수)
 * @return [5] 응답 설명 (선택)
 */
```

| 번호 | 항목 | 필수 | 설명 |
|------|------|------|------|
| 1 | API 제목 | ✅ | 첫 번째 비어있지 않은 줄. 위키 페이지 제목이 됩니다 |
| 2 | `@apiScope` | ✅ | `external` (사외) 또는 `internal` (사내) |
| 3 | 상세 설명 | - | 빈 줄 이후 본문. Claude에게 추가 컨텍스트 제공 |
| 4 | `@param` | ✅* | `@PathVariable`, `@RequestParam` 파라미터는 필수 |
| 5 | `@return` | - | 응답 내용 설명 |

> **`@RequestBody` 파라미터는 `@param`을 작성하지 않아도 됩니다.** DTO 필드 주석으로 대체합니다.

### 작성 예시

```java
/**
 * Todo 단건 조회
 * @apiScope external
 *
 * 지정한 ID의 Todo 항목을 반환합니다.
 * 존재하지 않는 ID 요청 시 404를 반환합니다.
 *
 * @param id 조회할 Todo의 고유 식별자
 * @return 조회된 Todo 정보
 */
@GetMapping("/{id}")
public TodoResponse getById(@PathVariable Long id) { ... }

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

/**
 * Todo 생성
 * @apiScope external
 *
 * @param request 생성할 Todo 정보
 * @return 생성된 Todo 정보
 */
@PostMapping
public TodoResponse create(@RequestBody TodoCreateRequest request) { ... }
```

---

## DTO 필드 주석

Request / Response DTO의 각 필드에 `/** */` 주석과 `@ex` 태그로 예시값을 제공합니다.

```java
/**
 * 필드 설명
 * @ex 예시값
 */
private String fieldName;
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

Response DTO는 한 줄 인라인 형식도 허용합니다.

```java
public class TodoResponse {
    /** Todo 고유 식별자. @ex 42 */
    private Long id;

    /** 현재 상태 (TODO / IN_PROGRESS / DONE). @ex "TODO" */
    private TodoStatus status;
}
```

---

## 검증 규칙 (미충족 시 GitHub Actions 실패)

| 항목 | 조건 |
|------|------|
| API 제목 | Javadoc 첫 줄이 비어있으면 실패 |
| `@apiScope` | `internal` 또는 `external` 중 하나여야 함 |
| `@param` | `@PathVariable`, `@RequestParam` 파라미터 각각 필요 |

실패 시 Actions 로그에 누락 항목이 명시됩니다.

```
[ERROR] [GET] /api/v1/todos/{id} — API 문서 주석이 불충분합니다:
  • Javadoc 첫 줄에 API 제목이 없습니다
  • @apiScope 태그가 없거나 올바르지 않습니다
  • @param id 설명이 없습니다
```
