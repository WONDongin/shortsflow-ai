# ShortsFlow AI

AI 기반 숏폼 영상 편집 및 워크플로우 자동화. 현재는 MP4를 업로드하고 메타데이터, WAV 음성, JPG 프레임을 추출할 수 있습니다.

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
영상 처리에는 FFmpeg와 FFprobe가 필요합니다. 현재 PowerShell에서 `ffmpeg -version` 또는 `ffprobe -version`이 실패하면 백엔드 시작 전에 아래처럼 설치 경로를 지정합니다.

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

## 환경변수

- `CORS_ORIGINS`는 백엔드에서 허용할 프론트엔드 출처 목록입니다. 기본값은 `http://localhost:5173,http://127.0.0.1:5173`이며 여러 출처는 쉼표로 구분합니다.
- `VITE_API_BASE_URL`은 프론트엔드에서 사용하는 백엔드 주소입니다. 기본값은 `http://127.0.0.1:8000`입니다. 환경변수 변경 후 해당 개발 서버를 다시 시작합니다.
- `FFMPEG_PATH`, `FFPROBE_PATH`는 실행 파일 경로입니다. 생략하면 시스템 PATH에서 명령을 찾습니다.
- `VIDEO_STORAGE_DIR`는 영상 작업 디렉터리입니다. 기본 경로는 `backend/storage/videos`입니다.
- 초기 상태 확인에는 API 키가 필요하지 않습니다. OpenAI 연동 시 `OPENAI_API_KEY`는 백엔드 프로세스의 환경변수로 전달합니다. `VITE_` 변수는 브라우저에 공개됩니다.

프론트엔드 디렉터리에서 `npm.cmd run build`로 타입 검사와 빌드를 실행할 수 있습니다.

## 영상 처리 API

Swagger UI(`http://127.0.0.1:8000/docs`)에서 **videos → POST /api/videos → Try it out**을 열고 `file`에 MP4를 선택한 뒤 **Execute**를 누릅니다. 반환된 `video_id`를 조회와 추출 요청에 사용합니다.

| 요청 | 입력 | 성공 응답 |
| --- | --- | --- |
| `POST /api/videos` | `multipart/form-data`의 `file`에 MP4 첨부, 최대 100 MiB(104,857,600바이트) | `201`, 작업 UUID와 메타데이터 |
| `GET /api/videos/{video_id}` | 작업 UUID | `200`, 파일 크기, 메타데이터 및 생성 결과 경로 |
| `POST /api/videos/{video_id}/extract-audio` | 작업 UUID | `200`, 16kHz 모노 PCM 16비트 WAV 경로 |
| `POST /api/videos/{video_id}/extract-frame` | 작업 UUID, 선택 쿼리 `timestamp_seconds`(기본값 0) | `200`, 해당 시간에서 추출한 JPG 경로 |

```powershell
$api = 'http://127.0.0.1:8000/api/videos'
$upload = curl.exe --fail -sS -F 'file=@C:\Videos\sample.mp4' $api | ConvertFrom-Json
$job = "$api/$($upload.video_id)"
Invoke-RestMethod -Method Post -Uri "$job/extract-audio"
Invoke-RestMethod -Method Post -Uri "$job/extract-frame?timestamp_seconds=1"
Invoke-RestMethod -Uri $job | ConvertTo-Json -Depth 4
```

메타데이터에는 `duration_seconds`, `width`, `height`, `fps`, `video_codec`, `has_audio`가 포함됩니다. 반환된 경로는 저장소 디렉터리 기준의 상대 파일 경로입니다. 추출은 요청이 끝나기 전에 완료되며, 프레임을 다시 추출하면 같은 작업의 `frame.jpg`를 교체합니다. 생성 전에는 조회 응답의 해당 경로가 `null`입니다.

오류 응답의 `detail`에서 원인을 확인할 수 있습니다. 작업을 찾을 수 없으면 `404`, 크기 제한 초과는 `413`, 확장자 불일치는 `415`, 손상된 MP4·음성 트랙 없음·잘못된 시간은 `422`입니다. 도구를 실행할 수 없으면 `503`, 처리 시간 초과는 `504`, 저장 또는 추출 실패는 `500`입니다.
