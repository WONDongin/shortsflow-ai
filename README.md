<!-- 로컬 실행, 환경 설정, 영상 API, PostgreSQL 검증 -->
# ShortsFlow AI

AI 기반 숏폼 영상 편집 및 워크플로우 자동화. MP4에서 WAV 음성과 JPG 프레임을 추출하고, 로컬 Whisper로 시간 구간이 포함된 자막 JSON을 생성할 수 있습니다.

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
| `POST /api/videos/{video_id}/extract-frame` | 작업 UUID, 선택 쿼리 `timestamp_seconds`(기본값 0) | `200`, 해당 시간에서 추출한 JPG 경로 |
| `GET /api/videos/{video_id}/download/{kind}` | 작업 UUID와 파일 종류 `source`, `audio`, `frame`, `transcript` | `200`, MP4·WAV·JPG·JSON 파일. 파일이 없으면 `404` |

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

GPT 구간 추천은 10단계, SRT 변환과 영상에 자막 입히기는 11단계에서 진행합니다.

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
