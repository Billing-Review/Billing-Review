# API 문서 자동화를 위한 Javadoc 작성 가이드

자동화 시스템은 Controller 메서드와 DTO 필드의 Javadoc 주석을 읽어 API 문서를 생성합니다.
아래 규칙에 맞게 주석을 작성하면, PR 머지 시 Dooray 위키 Draft가 자동으로 생성됩니다.

---

## Controller 메서드 주석

```java
/**
 * [1] API 제목 (필수) — 위키 페이지 이름으로 사용됩니다
 * @apiScope [2] external | internal | private  (필수)
 *
 * [3] API 상세 설명 (선택) — 동작 방식, 예외 케이스 등
 *
 * @path   [4] PathVariable명  설명  (@PathVariable, 필수)
 * @header [5] 헤더명          설명  (@RequestHeader, 필수)
 * @param  [6] QueryParam명    설명  (@RequestParam, 필수)
 * @body   [7] 변수명          설명  (@RequestBody / @ModelAttribute, 필수)
 * @return [8] 응답 설명 (선택)
 */
```

| 번호 | 태그 | Spring 어노테이션 | 필수 | 문서 반영 위치 |
|------|------|---|------|------|
| 1 | API 제목 | — | ✅ | 위키 페이지 제목 |
| 2 | `@apiScope` | — | ✅ | `external` (사외) / `internal` (사내) / `private` (팀 내부) |
| 3 | 상세 설명 | — | - | Claude에게 추가 컨텍스트 제공 |
| 4 | `@path` | `@PathVariable` | ✅ | Request > URL (Path Variable 비고) |
| 5 | `@header` | `@RequestHeader` | ✅ | Request > Header |
| 6 | `@param` | `@RequestParam` | ✅ | Request > Parameters (Query 비고) |
| 7 | `@body` | `@RequestBody` / `@ModelAttribute` | ✅ | Request > Body. **인자 변수의 역할/용도를 간단히 설명** (DTO 필드의 상세 스펙은 DTO Javadoc 에서 자동 추출되지만, 변수가 무엇을 받는지는 메서드 시점에 명시) |
| 8 | `@return` | — | - | Response 설명 |

---

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


// @RequestBody → @body 로 변수의 역할 명시 (필드 스펙은 DTO Javadoc 에서 자동 추출)
/**
 * Todo 생성
 * @apiScope external
 *
 * @body request 생성할 Todo 정보 (title/content/dueDate/priority)
 * @return 생성된 Todo 정보
 */
@PostMapping
public TodoResponse create(@RequestBody TodoCreateRequest request) { ... }


// @ModelAttribute → 동일하게 @body 작성
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
| `@apiScope` | `internal` / `external` / `private` 중 하나여야 함 |
| `@path` | `@PathVariable` 파라미터 각각 필요 |
| `@param` | `@RequestParam` 파라미터 각각 필요 |
| `@header` | `@RequestHeader` 파라미터 각각 필요 |
| `@body` | `@RequestBody` / `@ModelAttribute` 파라미터 각각 필요 |

실패 시 Actions 로그에 누락 항목이 명시됩니다.

```
[ERROR] [GET] /api/v1/todos/{id} — API 문서 주석이 불충분합니다:
  • Javadoc 첫 줄에 API 제목이 없습니다
  • @apiScope 태그가 없거나 올바르지 않습니다
  • @path id 설명이 없습니다
```

---

## IntelliJ Live Templates

**설정 위치**: `Preferences → Editor → Live Templates → Java`

태그 조합 순서는 `@path → @header → @param → @body → @return` 을 유지합니다.
태그가 여러 개면 해당 줄을 복사해 추가합니다.

---

### `apidoc` — RequestBody / ModelAttribute (path·param·header 없는 경우)

**Abbreviation**: `apidoc`

```
/**
 * $TITLE$
 * @apiScope $SCOPE$
 *
 * $DESC$
 *
 * @return $RETURN$
 */
```

---

### `apidoc-path` — PathVariable 포함

**Abbreviation**: `apidoc-path`

```
/**
 * $TITLE$
 * @apiScope $SCOPE$
 *
 * $DESC$
 *
 * @path $NAME$ $NAME_DESC$
 * @return $RETURN$
 */
```

---

### `apidoc-param` — RequestParam 포함

**Abbreviation**: `apidoc-param`

```
/**
 * $TITLE$
 * @apiScope $SCOPE$
 *
 * $DESC$
 *
 * @param $NAME$ $NAME_DESC$
 * @return $RETURN$
 */
```

---

### `apidoc-header` — RequestHeader 포함

**Abbreviation**: `apidoc-header`

```
/**
 * $TITLE$
 * @apiScope $SCOPE$
 *
 * $DESC$
 *
 * @header $NAME$ $NAME_DESC$
 * @return $RETURN$
 */
```

---

### `apidto` — DTO 필드 주석

**Abbreviation**: `apidto`

```
/**
 * $DESC$
 * @ex $EXAMPLE$
 */
```

---

### 등록 방법

1. `Preferences → Editor → Live Templates` 열기
2. 우측 `+` → `Template Group` 으로 `API Doc` 그룹 생성
3. 그룹 선택 후 `+` → `Live Template`
4. Abbreviation / Template text 입력
5. 하단 **Define** 클릭 → `Java` 체크 (적용 컨텍스트)
6. **Edit variables** 에서 `$SCOPE$` 기본값을 `"external"` 로 설정
7. **OK** 저장

**사용법**: 메서드 위에서 약어 입력 후 `Tab` 키
