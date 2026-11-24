# ShortsFlow AI

AI 기반 숏폼 영상 편집 및 워크플로우 자동화. MP4 영상에서 자막, 쇼츠 영상, 썸네일을 생성하는 서비스입니다. 현재는 FastAPI와 React 사이의 연결을 확인할 수 있습니다.

## 로컬 실행

Windows PowerShell에서 Python 3.12와 Node.js 22.17.1로 실행합니다. 아래 두 명령 블록은 각각 저장소 루트에서 시작합니다.

### 백엔드

```powershell
Set-Location backend
$python = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
& $python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Python 설치 위치가 다르면 `$python`을 해당 `python.exe` 경로로 바꿉니다.

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
- 초기 상태 확인에는 API 키가 필요하지 않습니다. OpenAI 연동 시 `OPENAI_API_KEY`는 백엔드 프로세스의 환경변수로 전달합니다. `VITE_` 변수는 브라우저에 공개됩니다.

프론트엔드 디렉터리에서 `npm.cmd run build`로 타입 검사와 빌드를 실행할 수 있습니다.
