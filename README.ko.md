**한국어** | [English](README.md)

# long-xls

**65,536행 제한을 초과한 XLS 파일에서 데이터를 복원합니다.**

일부 프로그램 — 증권 트레이딩 플랫폼, 산업용 데이터 로거, 레거시 리포팅
도구 — 은 XLS 행 제한을 넘어서도 BIFF 셀 레코드를 계속 기록합니다.
데이터는 파일 안에 *물리적으로 존재*하지만, 표준 도구(Excel, pandas, xlrd)는
잘라버리거나 에러를 냅니다.

**long-xls**는 BIFF 바이너리 스트림을 직접 읽고, 65,536 경계에서의
row index wrap-around를 감지하여 전체 데이터셋을 복원합니다.

## 문제 상황

```
┌──────────────────────────────────────────────────────┐
│  당신의 XLS 파일 (예: 37만행의 체결 데이터)            │
│                                                      │
│  Row 1 ............ ✓ Excel에서 보임                  │
│  Row 65,536 ....... ✓ Excel에서 보임                  │
│  Row 65,537 ....... ✗ 안 보임 — 데이터는 있음          │
│  Row 370,000 ...... ✗ 안 보임 — 하지만 복원 가능!      │
└──────────────────────────────────────────────────────┘
```

Excel은 65,536행만 보여줍니다. **long-xls는 37만행 전부를 복원합니다.**

## 설치

```bash
pip install long-xls              # xlsx 출력 (기본)
pip install "long-xls[parquet]"   # + parquet 지원
pip install "long-xls[all]"       # 전부
```

또는 [Releases](https://github.com/seonhwa17kim/long-xls/releases)에서
**독립 실행파일**을 다운로드하세요 — Python 설치 불필요.

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

## 지원 범위

| 기능 | 상태 |
|---|---|
| BIFF2 LABEL (문자열 셀) | 지원 |
| BIFF2 NUMBER (실수 셀) | 지원 |
| BIFF2 INTEGER (정수 셀) | 지원 |
| 65,536행 경계 wrap-around | 자동 감지 |
| 컬럼-메이저 저장 순서 | 자동 감지 |
| 다중 인코딩 (CP949 / EUC-KR / UTF-8) | 자동 fallback |
| Standalone BIFF 스트림 (OLE2 없음) | 지원 |
| OLE2 컨테이너 파일 | 미지원 |

## 동작 원리

표준 XLS (BIFF) 형식은 시트당 65,536행으로 제한됩니다. 일부 프로그램은
이 제한을 무시하고 셀 레코드를 계속 기록합니다. 16비트 unsigned integer로
저장되는 row index는 경계에서 0으로 돌아갑니다.

long-xls는 컬럼별 wrap 횟수를 추적하여 논리적 행 번호를 복원합니다:

```
logical_row = raw_row + (wrap_count * 65536)
```

이 파일들의 데이터는 **컬럼-메이저 순서**로 저장됩니다 — 컬럼 0의 모든 값,
그다음 컬럼 1의 모든 값 순서입니다. long-xls는 이를 투명하게 처리합니다.

## 독립 실행파일 빌드

```bash
pip install pyinstaller
python build_exe.py          # dist/long-xls.exe (Windows) 생성
```

## 라이선스

[MIT](LICENSE)
