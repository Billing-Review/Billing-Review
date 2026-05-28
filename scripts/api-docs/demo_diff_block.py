#!/usr/bin/env python3
"""
build_diff_block 동작 확인용 데모.

실행:
    python3 scripts/api-docs/demo_diff_block.py

실제 위키 Draft 가 만들어내는 것과 비슷한 마크다운을 before/after 로 두고
새 구조화 diff 출력이 어떻게 보이는지 확인할 수 있다.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.api_utils import build_diff_block  # noqa: E402


PREV = """## Description

* 결제 단건 조회 API 입니다.
* 결제 ID 로 결제 정보를 조회합니다.

## API Info

### 기본 정보

| Path | Method | Content-Type |
|---|---|---|
| /api/payments/{paymentId} | GET | application/json |

### Domain

| 환경 | URL |
|---|---|
| dev | https://dev-payment.example.com |
| prod | https://payment.example.com |

## Request

### Header

| 헤더 | 필수 | 설명 |
|---|---|---|
| clientOrigin | Y | 호출 origin |
| requestId | N | 요청 추적 ID |

### PathVariable

| 변수 | 타입 | 설명 |
|---|---|---|
| paymentId | Long | 조회할 결제 ID |

### Parameters

| 파라미터 | 필수 | 타입 | 기본값 | 설명 |
|---|---|---|---|---|
| page | N | int | 0 | 페이지 번호 |
| size | N | int | 20 | 페이지 크기 |

## Response

### Body

| 필드 | 타입 | 설명 |
|---|---|---|
| id | Long | 결제 ID |
| amount | Long | 결제 금액 |
| status | String | 상태 |

```json
{
  "id": 1,
  "amount": 1000,
  "status": "PAID"
}
```
"""


NEW = """## Description

* 결제 단건 조회 API 입니다.
* 결제 ID 로 결제 상세 정보를 조회합니다. 존재하지 않는 ID 는 404 를 반환합니다.

## API Info

### 기본 정보

| Path | Method | Content-Type |
|---|---|---|
| /api/payments/{paymentId} | GET | application/json |

### Domain

| 환경 | URL |
|---|---|
| dev | https://dev-payment.example.com |
| stage | https://stage-payment.example.com |
| prod | https://payment.example.com |

## Request

### Header

| 헤더 | 필수 | 설명 |
|---|---|---|
| clientOrigin | Y | 호출 origin |
| requestId | N | 요청 추적 ID |
| X-Trace-Id | N | 분산 추적 ID |

### PathVariable

| 변수 | 타입 | 설명 |
|---|---|---|
| paymentId | Long | 조회할 결제의 고유 식별자 |

### Parameters

| 파라미터 | 필수 | 타입 | 기본값 | 설명 |
|---|---|---|---|---|
| page | Y | int | 0 | 페이지 번호 (0-based) |
| status | N | String |  | 필터 상태 (PAID/CANCELED) |

## Response

### Body

| 필드 | 타입 | 설명 |
|---|---|---|
| id | Long | 결제 ID |
| amount | Long | 결제 금액 (원) |
| status | String | 결제 상태 |
| paidAt | String | 결제 완료 일시 (ISO-8601) |

```json
{
  "amount": 1000,
  "id": 1,
  "paidAt": "2026-05-28T10:00:00+09:00",
  "status": "PAID"
}
```

### Errors

| code | message |
|---|---|
| 404 | payment not found |
| 400 | invalid paymentId |
"""


def main():
    print("=" * 70)
    print("BEFORE (이전 published 버전)")
    print("=" * 70)
    print(PREV)
    print()
    print("=" * 70)
    print("AFTER (새 Draft)")
    print("=" * 70)
    print(NEW)
    print()
    print("=" * 70)
    print("build_diff_block 출력")
    print("=" * 70)
    out = build_diff_block(PREV, NEW)
    print(out if out else "(변경 없음)")


if __name__ == "__main__":
    main()
