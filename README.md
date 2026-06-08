**한국어** | [English](README.en.md)

# long-xls

**65,536행 제한을 초과한 XLS 파일의 데이터를 복원하는 간단한 도구**

원래 XLS 파일은 구조적으로 65,536행 제한이 있어 그 이상의 행을 기록할 수 없다.
그러나 일부 프로그램 — legacy reporting utils, converting tools, 증권사 HTS
exporters 등 — 은 XLS 행 제한을 넘어서도 BIFF 셀 레코드를 계속 기록하는 경우가
있다. 이 경우 실제 데이터는 파일 안에 존재하지만, 대부분의 프로그램이나
라이브러리(Excel, pandas, xlrd 등)에서는 뒷부분을 잘라 버리거나 에러를 내기
때문에 저장된 데이터를 읽을 방법이 없다.

**long-xls**는 BIFF 바이너리 스트림을 직접 읽고, 65,536 경계에서의
row index wrap-around를 감지하여 전체 데이터셋을 복원하는 도구이다.

## 문제 상황

```
┌──────────────────────────────────────────────────────┐
│  XLS 파일 (예: 37만 행의 데이터)           │
│                                                      │
│  Row 1 ............ ✓ Excel에서 보임                  │
│  Row 65,536 ....... ✓ Excel에서 보임                  │
│  Row 65,537 ....... ✗ 안 보임 — 데이터는 있음          │
│  Row 370,000 ...... ✗ 안 보임 — 하지만 복원 가능!      │
└──────────────────────────────────────────────────────┘
```

## 설치

```bash
pip install long-xls              # xlsx 출력 (기본)
pip install "long-xls[parquet]"   # + parquet 지원
pip install "long-xls[all]"       # 전부
```

또는 [Releases](https://github.com/seonhwa17kim/long-xls/releases)에서
**독립 실행파일**을 다운로드 — Python 설치 불필요.

## 빠른 시작

```bash
# xlsx로 변환 (기본)
long-xls data.xls

# csv로 변환
long-xls data.xls -f csv

# parquet으로 변환
long-xls data.xls -f parquet

# JSON 스키마 파일도 함께 생성
long-xls data.xls --schema

# 여러 파일 일괄 변환
long-xls *.xls -f csv -o output/
```

## 명령어

| 명령 | 설명 |
|---|---|
| `long-xls data.xls` | xlsx로 변환 (기본) |
| `long-xls data.xls -f csv` | csv로 변환 |
| `long-xls data.xls -f parquet` | parquet으로 변환 |
| `long-xls data.xls --schema` | `.schema.json` 파일도 생성 |
| `long-xls schema data.xls` | JSON 스키마를 stdout으로 출력 |
| `long-xls scan data.xls` | 빠른 파일 스캔 (레코드 수만 확인) |

### 옵션

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `-f`, `--format` | `xlsx` | 출력 형식: `xlsx`, `csv`, `parquet` |
| `-o`, `--output-dir` | 입력 파일과 동일 | 출력 디렉토리 |
| `-e`, `--encoding` | `cp949` | 문자열 셀의 텍스트 인코딩 |
| `-y`, `--force` | 끔 | 기존 파일 무조건 덮어쓰기 |
| `--schema` | 끔 | 출력 파일과 함께 `.schema.json` 생성 |

## Python API

```python
from long_xls import parse, parse_to_dataframe, schema_json

# 파싱 및 확인
sheet = parse("data.xls")
print(f"{sheet.num_data_rows:,}행 복원됨")

# pandas DataFrame으로 변환
df, sheet = parse_to_dataframe("data.xls")

# 스키마를 JSON으로 출력
import json
print(json.dumps(schema_json(sheet), indent=2))
```

## 스키마 출력 예시

```json
{
  "file": "data.xls",
  "file_size": 29736094,
  "encoding": "cp949",
  "num_columns": 4,
  "num_data_rows": 371700,
  "row_limit_exceeded": true,
  "wraps": {"0": 5, "1": 5, "2": 5, "3": 5},
  "columns": [
    {"index": 0, "name": "date", "type": "string", "non_null_count": 371700},
    {"index": 1, "name": "time", "type": "string", "non_null_count": 371700},
    {"index": 2, "name": "price", "type": "float", "non_null_count": 371700},
    {"index": 3, "name": "volume", "type": "integer", "non_null_count": 371700}
  ]
}
```

## 테스트 파일

### 합성 테스트 파일 (생성기 포함)

`tests/generate_test_xls.py`를 실행하면 다양한 크기의 long-XLS 테스트 파일을
자동으로 생성한다. BIFF2 레코드를 직접 써서 row wrap-around를 재현한다.

```bash
python tests/generate_test_xls.py
```

| 파일 | 행 수 | Wraps | 인코딩 | 용도 |
|---|---|---|---|---|
| `test_100k_rows.xls` | 100,000 | 1 | UTF-8 | 기본 복원 검증 |
| `test_200k_rows.xls` | 200,000 | 3 | UTF-8 | 다중 wrap 검증 |
| `test_70k_cp949.xls` | 70,000 | 1 | CP949 | 한국어 인코딩 검증 |

### 실제 사례: 키움증권 HTS 차트 데이터

키움증권 HTS에서 내보낸 선물 틱 차트 데이터로, 371,700행이 기록되어 있으나
Excel에서는 65,535행까지만 보인다. long-xls로 전체 복원이 가능하다.

- `20240808_KOSPI200_Tick_Kiwoom.xls` — 371,700행 (5회 wrap), 29.7MB

## 독립 실행파일 빌드

```bash
pip install pyinstaller
python build_exe.py          # dist/long-xls.exe (Windows) 생성
```

## 개발자

seonhwa17kim (GPT-o3, Gemini 2.5 Pro, Claude Opus 4 도움)

## 라이선스

[MIT](LICENSE) Copyright (c) 2026 seonhwa17kim
