<!-- 로컬 실행, 환경 설정, 영상 API, PostgreSQL 검증 -->
# ShortsFlow AI

AI 기반 숏폼 영상 편집 및 워크플로우 자동화. MP4에서 WAV 음성과 JPG 프레임을 추출하고, 로컬 Whisper 자막을 생성한 뒤 GPT로 쇼츠 후보를 최대 한 개 선정할 수 있습니다.

<!-- 백엔드·프론트엔드 실행 -->
## 로컬 실행

Windows PowerShell에서 Python 3.12와 Node.js 22.17.1로 실행합니다. 아래 두 명령 블록은 각각 저장소 루트에서 시작합니다.

### 백엔드

```powershell
Set-Location backend
$python = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
& $python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Python 설치 위치가 다르면 `$python`을 해당 `python.exe` 경로로 바꿉니다.
영상 처리에는 FFmpeg와 FFprobe가 필요합니다. Windows에서 `winget install --id Gyan.FFmpeg -e`로 설치한 뒤 새 PowerShell에서 `ffmpeg -version`과 `ffprobe -version`을 확인합니다. PATH에서 실행 파일을 찾지 못하면 백엔드 시작 전에 아래처럼 설치 경로를 지정합니다.

```powershell
$env:FFMPEG_PATH = 'C:\설치경로\bin\ffmpeg.exe'
$env:FFPROBE_PATH = 'C:\설치경로\bin\ffprobe.exe'
```

같은 PowerShell에서 백엔드를 시작합니다.

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 프론트엔드

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run dev
```

브라우저에서 `http://127.0.0.1:5173`을 열면 API 연결 상태가 표시됩니다. `http://127.0.0.1:8000/api/health`에 GET 요청을 보내면 HTTP 200과 `{"status":"ok"}`가 반환됩니다. FastAPI API 문서는 `http://127.0.0.1:8000/docs`에서 열 수 있습니다.

<!-- PostgreSQL 및 영상 처리 환경변수 -->
## 환경변수

PostgreSQL 연결을 확인하려면 `backend/.env.example`을 `backend/.env`로 복사하고 `DB_PASSWORD`에 로컬 계정의 비밀번호를 지정합니다. 기본 연결 대상은 `localhost:5432`의 `shortsflow` 데이터베이스와 `shortsflow_user` 계정입니다. 설정을 바꾼 뒤 백엔드를 다시 시작합니다.

`GET /api/health/db`는 기존 `shortsflow_app.videos`와 `shortsflow_app.video_artifacts`에 읽기 쿼리를 실행합니다. 두 쿼리가 성공하면 빈 테이블도 HTTP 200과 `{"status":"ok"}`를 반환합니다. 연결 또는 읽기에 실패하면 HTTP 503을 반환합니다.

- `CORS_ORIGINS`는 백엔드에서 허용할 프론트엔드 출처 목록입니다. 기본값은 `http://localhost:5173,http://127.0.0.1:5173`이며 여러 출처는 쉼표로 구분합니다.
- `VITE_API_BASE_URL`은 프론트엔드에서 사용하는 백엔드 주소입니다. 기본값은 `http://127.0.0.1:8000`입니다. 환경변수 변경 후 해당 개발 서버를 다시 시작합니다.
- `FFMPEG_PATH`, `FFPROBE_PATH`는 실행 파일 경로입니다. 생략하면 시스템 PATH에서 명령을 찾습니다.
- `VIDEO_STORAGE_DIR`는 영상 작업 디렉터리입니다. 기본 경로는 `backend/storage/videos`입니다.
- `WHISPER_MODEL`은 선택 사항인 PowerShell 환경변수입니다. 기본값은 한국어를 지원하는 다국어 `small`이며 CPU와 `int8`을 사용합니다. 첫 자막 요청에서 모델을 로드하고 이후 같은 백엔드 프로세스에서 재사용합니다. 캐시가 비어 있으면 첫 요청에서 Hugging Face 모델 가중치를 내려받으므로 인터넷 연결이 필요합니다. 오프라인 환경에서는 백엔드를 시작하기 전에 `$env:WHISPER_MODEL = 'C:\Models\faster-whisper-small'`처럼 미리 저장한 CTranslate2 모델 디렉터리를 지정할 수 있습니다. 추론은 로컬에서 실행됩니다.
- 초기 상태 확인에는 API 키가 필요하지 않습니다. OpenAI 연동 시 `OPENAI_API_KEY`는 백엔드 프로세스의 환경변수로 전달합니다. `VITE_` 변수는 브라우저에 공개됩니다.

프론트엔드 디렉터리에서 `npm.cmd run build`와 `npm.cmd run lint`로 타입 검사·빌드와 린트를 실행할 수 있습니다.

<!-- 영상 API 요청과 응답 -->
## 영상 처리 API

Swagger UI(`http://127.0.0.1:8000/docs`)에서 **videos → POST /api/videos → Try it out**을 열고 `file`에 MP4를 선택한 뒤 **Execute**를 누릅니다. 반환된 `video_id`를 조회와 추출 요청에 사용합니다.

| 요청 | 입력 | 성공 응답 |
| --- | --- | --- |
| `POST /api/videos` | `multipart/form-data`의 `file`에 MP4 첨부, 최대 100 MiB(104,857,600바이트) | `201`, 작업 UUID와 메타데이터 |
| `GET /api/videos/{video_id}` | 작업 UUID | `200`, 파일 크기, 메타데이터 및 생성 결과 경로 |
| `POST /api/videos/{video_id}/extract-audio` | 작업 UUID | `200`, 16kHz 모노 PCM 16비트 WAV 경로 |
| `POST /api/videos/{video_id}/transcribe` | 작업 UUID, 추출된 WAV 필요 | `200`, 생성한 자막과 감지 언어 |
| `GET /api/videos/{video_id}/transcript` | 작업 UUID | `200`, 저장된 자막. 영상이나 자막이 없으면 `404` |
| `POST /api/videos/{video_id}/analyze` | 작업 UUID | `202`, 새 분석 또는 진행 중인 분석 |
| `GET /api/videos/{video_id}/analysis` | 작업 UUID, 선택 쿼리 `analysis_id` | `200`, 지정한 분석 또는 최신 분석의 상태와 결과. 없으면 `404` |
| `POST /api/videos/{video_id}/extract-frame` | 작업 UUID, 선택 쿼리 `timestamp_seconds`(기본값 0) | `200`, 해당 시간에서 추출한 JPG 경로 |
| `POST /api/videos/{video_id}/generate-shorts` | 작업 UUID와 쿼리 `analysis_id` | `200`, 음성과 화면 자막이 포함된 쇼츠 및 썸네일 생성 결과 |
| `GET /api/videos/{video_id}/shorts` | 작업 UUID와 쿼리 `analysis_id` | `200`, 생성된 두 파일의 경로와 원본 기준 타임스탬프 |
| `GET /api/videos/{video_id}/download/{kind}` | 작업 UUID와 파일 종류 `source`, `audio`, `frame`, `transcript`, `shorts`, `thumbnail`. 마지막 두 종류는 쿼리 `analysis_id` 필요 | `200`, MP4·WAV·JPG·JSON 파일. 파일이 없으면 `404` |

```powershell
$api = 'http://127.0.0.1:8000/api/videos'
$upload = curl.exe --fail -sS -F 'file=@C:\Videos\sample.mp4' $api | ConvertFrom-Json
$job = "$api/$($upload.video_id)"
Invoke-RestMethod -Method Post -Uri "$job/extract-audio"
Invoke-RestMethod -Method Post -Uri "$job/transcribe" | ConvertTo-Json -Depth 4
Invoke-RestMethod -Uri "$job/transcript" | ConvertTo-Json -Depth 4
Invoke-WebRequest -Uri "$job/download/transcript" -OutFile transcript.json
Invoke-RestMethod -Method Post -Uri "$job/extract-frame?timestamp_seconds=1"
Invoke-RestMethod -Uri $job | ConvertTo-Json -Depth 4
```

메타데이터에는 `duration_seconds`, `width`, `height`, `fps`, `video_codec`, `has_audio`가 포함됩니다. 반환된 경로는 영상 저장소 루트(기본값 `backend/storage/videos`) 기준의 상대 경로입니다. 추출은 요청이 끝나기 전에 완료되며, 프레임을 다시 추출하면 같은 작업의 `frame.jpg`와 DB의 추출 시점이 갱신됩니다. 생성 전에는 조회 응답의 해당 경로가 `null`입니다.

오류 응답의 `detail`에서 원인을 확인할 수 있습니다. 작업을 찾을 수 없으면 `404`, 크기 제한 초과는 `413`, 확장자 불일치는 `415`, 손상된 MP4·음성 트랙 없음·잘못된 시간은 `422`입니다. DB 작업이 실패하거나 도구를 실행할 수 없으면 `503`, 처리 시간 초과는 `504`, 파일 저장 또는 추출 실패는 `500`입니다.

신규 작업은 PostgreSQL에 메타데이터와 상대 경로를 기록합니다. 실제 파일은 영상 저장소에 저장합니다. 기존 `metadata.json` 작업은 같은 UUID로 조회·다운로드할 수 있습니다. 기존 작업에서 처음 추출하면 영상 행을 등록하고 원본명은 기존 저장 파일명인 `source.mp4`로 기록합니다.

### 09단계 Whisper 자막 검증

1. `http://127.0.0.1:8000/docs`의 **videos**에서 `POST /api/videos`를 열고 한국어 대사가 있는 짧은 MP4를 업로드합니다. 응답의 `video_id`를 복사합니다.
2. `POST /api/videos/{video_id}/extract-audio`를 실행하고 `audio.wav` 경로를 확인합니다.
3. `POST /api/videos/{video_id}/transcribe`를 실행합니다. HTTP `200`, 같은 `video_id`, `language: "ko"`, 대사가 담긴 `segments`를 확인합니다. WAV 생성 전에 호출하면 `409`, 없는 UUID는 `404`, Whisper 모델을 불러오지 못하면 `503`과 모델 오류 메시지를 반환합니다.
4. `GET /api/videos/{video_id}/transcript`에서 같은 JSON이 반환되는지 확인합니다. `GET /api/videos/{video_id}/download/{kind}`에서 `kind`를 `transcript`로 선택하고 `transcript.json`을 내려받아 내용을 확인합니다.
5. React에서도 업로드 → 음성 추출 → WAV 다운로드 옆 **자막 생성**을 실행합니다. 생성 중 상태와 완료된 자막 표를 확인합니다. 새로고침하거나 같은 UUID를 조회한 뒤 자막이 다시 보이고 **자막 JSON 다운로드**가 동작하는지 확인합니다.

`transcript.json`은 영상의 UUID 폴더에 저장되며 PostgreSQL 스키마 변경은 필요 없습니다. 시작과 종료는 원본 MP4의 첫 영상 프레임을 0초로 삼습니다. 영상과 음성 트랙의 시작 시각이 다르면 그 차이를 반영합니다. 예를 들어 영상보다 음성이 2초 늦게 시작하면 WAV의 1초에 감지된 대사는 영상의 3초에 표시됩니다.

음성 감지 필터를 적용한 결과에 자막 구간이 없으면 원본 WAV를 필터 없이 한 번 더 분석합니다. 이미 저장된 자막은 React의 **자막 생성**을 다시 눌러 갱신합니다.

```json
{
  "video_id": "f737d3c1-346c-4f42-89aa-d793375617d2",
  "language": "ko",
  "segments": [
    {
      "start_seconds": 72.0,
      "end_seconds": 76.0,
      "text": "배포 서버에서 localhost는 서버 자기 자신을 가리킵니다."
    }
  ]
}
```

### 10단계 GPT 콘텐츠 분석

기존 PostgreSQL 영상 테이블이 준비된 상태에서 `backend` 디렉터리의 PowerShell로 마이그레이션을 적용합니다. 같은 마이그레이션을 다시 실행할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
@'
from pathlib import Path
from app.db import get_engine

sql = Path("sql/010_video_analyses.sql").read_text(encoding="utf-8")
with get_engine().begin() as connection:
    connection.exec_driver_sql(sql)
'@ | .\.venv\Scripts\python.exe -
```

실제 GPT 분석을 사용하려면 `backend/.env`에서 `ANALYSIS_MOCK_MODE=false`로 설정하고, `backend/.env` 또는 서버 프로세스 환경변수에 `OPENAI_API_KEY`를 지정합니다. `OPENAI_MODEL`의 기본값은 `gpt-5.4-mini`입니다. 키와 모델은 프로세스 환경변수가 `.env`보다 우선합니다. 모델을 변경할 때는 Responses API의 Structured Outputs를 지원하는 모델을 선택합니다. [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses)

1. [Swagger](http://127.0.0.1:8000/docs)의 `GET /api/videos/{video_id}/transcript`에서 자막이 저장된 영상의 UUID와 구간 시간을 확인합니다.
2. `POST /api/videos/{video_id}/analyze`에 같은 `video_id`를 넣고 실행합니다. HTTP `202`의 `analysis_id`를 복사합니다. 진행 중에 다시 요청하면 같은 `analysis_id`가 반환됩니다.
3. `GET /api/videos/{video_id}/analysis`에 `video_id`와 `analysis_id`를 넣고 실행합니다. `queued` 또는 `running`이면 다시 조회합니다. `analysis_id`를 생략하면 해당 영상의 최신 분석을 조회합니다.
4. `succeeded` 응답의 `candidate.start_seconds`와 `candidate.end_seconds`를 각각 첫 구간의 시작과 마지막 구간의 종료에 대조합니다. 기존 자막에 ID가 없으면 배열 순서대로 1부터 부여하며, 자막 파일은 분석 중 읽기만 합니다.

일반 영상은 15~30초 구간을 허용합니다. 원본이 30초 미만이면 원본 범위 내의 양수 길이도 허용합니다. HTTP `200` 조회에서 적합한 구간이 없으면 `status: "no_candidate"`와 `candidate: null`이 반환됩니다. `failed`일 때는 `error.code`와 `error.message`에서 원인을 확인할 수 있습니다.

| 오류 코드 | 원인 |
| --- | --- |
| `transcript_not_ready` | 저장된 자막이 없음 |
| `invalid_transcript` | 자막 JSON, 영상 UUID 또는 기존 구간 ID가 잘못됨 |
| `input_too_long` | 정리된 자막 입력이 100,000 UTF-8 바이트 또는 모델 입력 한도를 초과함 |
| `api_error` | API 키 누락, API 요청 실패, 거절 또는 잘못된 응답 |
| `invalid_segment` | 모델이 선택한 ID, 순서, 영상 범위 또는 길이가 잘못됨 |
| `interrupted` | 대기 또는 실행 상태가 10분 이상 지속됨. 다음 조회나 요청에서 실패로 기록되며 새 분석을 요청할 수 있음 |
| `internal_error` | 백엔드 분석 처리 중 예상 밖의 오류 발생 |

성공 응답의 후보 예시는 다음과 같습니다.

```json
{
  "start_segment_id": 1,
  "end_segment_id": 3,
  "start_seconds": 0.021995,
  "end_seconds": 22.021995,
  "title": "사랑한다는 말보다 먼저 나오는 말",
  "thumbnail_text": "하루 종일 보고 싶다",
  "reason": "궁금증을 여는 첫 문장에 이어 어떤 말인지 답이 나온다."
}
```

API 키 없이 검증하려면 마이그레이션을 적용한 로컬 테스트 DB에 연결하고 `backend`에서 아래 명령을 실행합니다. 테스트는 OpenAI 응답을 모의하고 FastAPI 경로와 PostgreSQL 저장·조회를 실제로 실행합니다. 테스트 영상 행은 종료 시 정리됩니다.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

### 10단계 Mock 분석과 11단계 쇼츠 생성

`backend/.env`에서 `ANALYSIS_MOCK_MODE=true`로 설정합니다. 항목을 생략해도 기본값은 `true`입니다. 이미 실행 중인 백엔드는 새 분석을 처리할 때 이 값을 다시 읽습니다.

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Mock 모드는 예제 자막의 두 연속 구간을 찾고 기존 분석 테이블에 후보를 저장합니다. 구간이 일치하지 않으면 `no_candidate`를 반환합니다. 실제 분석 모드로 전환하려면 `backend/.env`에서 `ANALYSIS_MOCK_MODE=false`로 바꾼 뒤 새 분석을 요청합니다.

1. [Swagger](http://127.0.0.1:8000/docs)에서 자막을 생성한 Mock 테스트 영상의 `video_id`로 `POST /api/videos/{video_id}/analyze`를 실행합니다.
2. `GET /api/videos/{video_id}/analysis`에서 같은 영상 UUID와 새 `analysis_id`로 조회합니다. `succeeded`와 구간 `22.021995`~`41.521995`초를 확인합니다.
3. `POST /api/videos/{video_id}/generate-shorts`에 두 UUID를 입력합니다. `duration_seconds`는 `19.5`, `thumbnail_timestamp_seconds`는 `25.021995`입니다. 3초 이하 후보는 썸네일에 구간의 중간 프레임을 씁니다.
4. `GET /api/videos/{video_id}/shorts`에서 두 파일을 조회합니다. `GET /api/videos/{video_id}/download/{kind}`를 같은 UUID들로 두 번 실행합니다. `kind`는 각각 `shorts`와 `thumbnail`입니다.

FFmpeg에는 `libx264` 인코더와 `drawtext` 필터가 필요합니다. 쇼츠에는 09단계 자막 중 선택 구간과 겹치는 부분을 클립 시작 기준으로 맞춰 영상에 직접 입힙니다. Windows에서는 맑은 고딕 Bold를 사용합니다. 다른 한글 글꼴을 쓰려면 서버 실행 전에 `THUMBNAIL_FONT_PATH`에 글꼴 파일 경로를 지정합니다. 자막이 들어간 새 결과는 영상별로 `shorts/<analysis_id>/captioned/` 아래에 저장됩니다. 이전에 생성한 결과도 같은 분석 ID로 3번을 다시 실행하면 자막 버전을 다운로드할 수 있습니다.

## n8n 자동 편집

### Windows PowerShell에서 연결

1. 위의 로컬 실행 방법에 따라 Python, FFmpeg·FFprobe, PostgreSQL과 프론트엔드 의존성을 준비합니다. 기존 `shortsflow_app.videos`, `shortsflow_app.video_artifacts` 테이블이 있는 DB에 연결합니다. `backend/.env`에 `ANALYSIS_MOCK_MODE=true`를 지정하면 OpenAI API 키 없이 실행할 수 있습니다.
2. 저장소의 `backend` 폴더에서 분석 및 워크플로우 마이그레이션을 적용합니다. 두 스크립트 모두 다시 적용할 수 있습니다.

```powershell
@'
from pathlib import Path
from app.db import get_engine

with get_engine().begin() as connection:
    for path in ("sql/010_video_analyses.sql", "sql/011_video_workflows.sql"):
        connection.exec_driver_sql(Path(path).read_text(encoding="utf-8"))
'@ | .\.venv\Scripts\python.exe -
```

3. 별도 PowerShell에서 n8n 2.x를 실행합니다. Node.js 22.17.1을 사용할 수 있습니다. [n8n npm 설치 문서](https://docs.n8n.io/deploy/host-n8n/install-options/install-with-npm.md)

```powershell
$env:N8N_LISTEN_ADDRESS = '127.0.0.1'
$env:N8N_HOST = '127.0.0.1'
$env:N8N_PORT = '5678'
npx.cmd --yes n8n@2
```

4. `http://127.0.0.1:5678`에서 워크플로우를 만들고, 메뉴의 **Import from File**로 [shortsflow-workflow.json](n8n/shortsflow-workflow.json)을 가져옵니다. **Publish**를 누른 뒤 **ShortsFlow webhook** 노드에서 Production URL을 확인합니다.
5. 기본 주소는 FastAPI `http://127.0.0.1:8000`, n8n 웹훅 `http://127.0.0.1:5678/webhook/shortsflow`입니다. 포트나 호스트를 변경했다면 n8n의 **FastAPI URL** 노드에서 `base_url`을 바꾸고 다시 게시합니다. FastAPI가 호출할 웹훅은 `backend/.env`의 `N8N_WEBHOOK_URL`로 지정합니다. 프론트엔드가 호출할 FastAPI 주소는 `VITE_API_BASE_URL`로 설정합니다.
6. FastAPI와 Vite를 시작하고 `http://127.0.0.1:5173`을 엽니다. MP4를 선택하고 **업로드**를 한 번 클릭합니다. **영상 편집 완료!** 팝업을 닫은 다음 **편집 영상 다운로드**를 클릭합니다. 실패하거나 후보가 없으면 팝업에서 원인을 확인할 수 있습니다.

업로드 응답의 `video_id`로 `POST /api/videos/{video_id}/workflow`를 호출하면 FastAPI가 n8n에 작업을 전달합니다. 동일 영상의 시작 요청을 반복하면 기존 작업 상태를 반환합니다. React는 `GET /api/videos/{video_id}/workflow`의 `stage`, `analysis_id`, `error`를 읽어 진행과 결과를 표시합니다. n8n은 분석이 대기 중이거나 실행 중이면 2초 간격으로 같은 분석을 조회합니다. Whisper 요청 제한은 25분이며, 쇼츠 요청 제한은 FFprobe·FFmpeg의 처리 제한 합계를 고려해 5분으로 설정했습니다.

### Mock 테스트 MP4

PR #5에서 사용한 원본 MP4로 검증합니다. 기존 로컬 작업에 원본이 있으면 해당 폴더의 `source.mp4`를 업로드 파일로 선택합니다. Mock 분석은 자막의 두 연속 구간이 `22.021995–36.021995초`의 “그냥 네가 보고 싶다 보고 싶다 보고 싶다”와 `36.021995–41.521995초`의 “참 많이 보고 싶다”에 일치할 때 후보를 반환합니다. 이 원본을 기본 `small` 모델로 전사하면 자막 경계가 달라져 `no_candidate`가 표시될 수 있습니다.

이 원본의 Mock 후보에 일치하는 자막을 생성하려면 백엔드를 시작할 PowerShell에서 `$env:WHISPER_MODEL = 'medium'`을 지정한 뒤 Uvicorn을 실행합니다. `medium`이 캐시되어 있으면 모델 이름이나 해당 모델 디렉터리의 경로를 지정할 수 있습니다.

다운로드한 `shorts.mp4`를 재생해 원본 음성과 화면에 합성된 자막을 확인합니다. 아래 명령으로 영상 길이와 오디오 스트림도 확인할 수 있습니다. 예상 길이는 약 19.5초입니다.

```powershell
ffprobe -v error -show_entries 'format=duration:stream=codec_type,codec_name' -of json .\shorts.mp4
```

<!-- 영상 처리 테스트와 DBeaver 저장 확인 -->
### 로컬에서 영상 연동 확인

1. 백엔드와 프론트엔드를 실행하고 `GET /api/health/db`가 HTTP 200을 반환하는지 확인합니다.
2. React 화면에서 길이가 1초보다 길고 음성 트랙이 있는 MP4를 올립니다. 영상 정보와 원본 MP4 다운로드를 확인합니다.
3. 음성을 추출하고 프레임을 0초에서 추출한 뒤 WAV와 JPG를 다운로드해 열어봅니다.
4. 영상 길이 안의 다른 시점에서 프레임을 다시 추출합니다. JPG를 다시 다운로드하고 새로고침 뒤 같은 UUID와 다운로드 버튼이 복원되는지 확인합니다.
5. DBeaver에서 아래 두 쿼리의 UUID를 화면의 UUID로 바꿉니다. 영상 행 1건과 결과물 행 2건을 확인합니다. 재추출 후에도 FRAME 행은 1건이고 `timestamp_seconds`는 마지막 추출 시점이어야 합니다.

```sql
SELECT id, original_filename, file_path, file_size, duration_seconds
FROM shortsflow_app.videos
WHERE id = '<UUID>'::uuid;

SELECT artifact_type, count(*) AS row_count,
       max(file_path) AS file_path, max(timestamp_seconds) AS timestamp_seconds
FROM shortsflow_app.video_artifacts
WHERE video_id = '<UUID>'::uuid
GROUP BY artifact_type
ORDER BY artifact_type;
```
