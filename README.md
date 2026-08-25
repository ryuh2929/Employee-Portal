# Employee Portal

FastAPI, React, TypeScript, PostgreSQL 기반 직원 관리 애플리케이션입니다.

## 준비 사항

- Python 3.11 이상
- Node.js 22 이상 및 pnpm
- Docker Desktop 또는 PostgreSQL 17

루트의 `.env.example`을 `.env`로 복사하고 자리표시자 비밀번호를 개발 환경 값으로 변경합니다.

```powershell
Copy-Item .env.example .env
```

주요 환경변수:

| 변수 | 용도 |
| --- | --- |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | PostgreSQL 데이터베이스와 계정 |
| `POSTGRES_HOST`, `POSTGRES_PORT` | PostgreSQL 접속 주소 |
| `APP_ENV`, `APP_HOST`, `APP_PORT` | 백엔드 실행 환경과 주소 |
| `CORS_ORIGINS` | 허용할 프런트엔드 origin. 여러 값은 쉼표로 구분 |
| `SEED_ADMIN_PASSWORD`, `SEED_EMPLOYEE_PASSWORD` | 개발 seed 계정 비밀번호 |
| `BACKGROUND_CHECK_API_URL` | `swagger.yaml`의 외부 Background Check API base URL |
| `BACKGROUND_CHECK_TIMEOUT_SECONDS` | 외부 API 요청 제한 시간(초) |
| `VITE_API_BASE_URL` | 브라우저가 호출할 FastAPI 주소 |

## PostgreSQL

루트 디렉터리에서 실행합니다.

```powershell
docker compose up -d postgres
docker compose ps
```

중지는 `docker compose down`으로 수행합니다. DB 데이터는 Docker volume에 유지됩니다.

## 백엔드와 마이그레이션

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
python -m alembic upgrade head
python -m uvicorn app.main:app --reload
```

- API: http://localhost:8000
- API 문서: http://localhost:8000/docs
- 상태 확인: http://localhost:8000/health, http://localhost:8000/ready

마이그레이션 상태와 새 마이그레이션 생성 명령:

```powershell
python -m alembic current
python -m alembic heads
python -m alembic revision --autogenerate -m "describe change"
python -m alembic upgrade head
```

## 개발 seed 데이터

`.env`에서 `APP_ENV=development`와 두 `SEED_*_PASSWORD`를 설정한 뒤 실행합니다. 여러 번 실행해도 중복 생성되지 않습니다.

```powershell
cd backend
python -m app.seed
```

관리자 1명과 일반 직원 3명이 생성되며 비밀번호는 Argon2id 해시로만 저장됩니다.

Seed 로그인 계정:

| 구분 | 이메일 | 비밀번호 |
| --- | --- | --- |
| 관리자 | `admin@employee-portal.local` | `.env`의 `SEED_ADMIN_PASSWORD` |
| 일반 직원 | `minjun.park@employee-portal.local` | `.env`의 `SEED_EMPLOYEE_PASSWORD` |
| 일반 직원 | `seoyeon.lee@employee-portal.local` | `.env`의 `SEED_EMPLOYEE_PASSWORD` |
| 일반 직원 | `seojun.namgung@employee-portal.local` | `.env`의 `SEED_EMPLOYEE_PASSWORD` |

## 프런트엔드

새 터미널에서 실행합니다.

```powershell
cd frontend
pnpm install --frozen-lockfile
pnpm run dev
```

웹 UI: http://localhost:5173

## Background Check API

`BACKGROUND_CHECK_API_URL`을 외부 API base URL로 설정합니다. 기본 예시는 `swagger.yaml`의 서버 주소입니다. 브라우저는 외부 API를 직접 호출하지 않고 FastAPI를 통해서만 요청합니다.

```dotenv
BACKGROUND_CHECK_API_URL=https://54capvm12g.execute-api.ap-northeast-2.amazonaws.com
BACKGROUND_CHECK_TIMEOUT_SECONDS=10
```

## 테스트

PostgreSQL과 최신 마이그레이션이 준비된 상태에서 실행합니다.

```powershell
cd backend
python -m pytest

cd ..\frontend
pnpm run lint
pnpm test
pnpm run build
```
