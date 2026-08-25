# Employee Portal

FastAPI, React, TypeScript, PostgreSQL 기반의 사내 직원 관리 애플리케이션입니다.

## 로컬 실행 준비

1. 루트의 `.env.example`을 `.env`로 복사합니다.
2. `POSTGRES_PASSWORD`를 로컬 개발용 값으로 변경합니다.
3. PostgreSQL을 실행합니다.

```shell
docker compose up -d postgres
```

## 백엔드

Python 3.11 이상이 필요합니다.

```shell
cd backend
python -m venv .venv
.venv/Scripts/activate
python -m pip install -e ".[test]"
alembic upgrade head
uvicorn app.main:app --reload
```

- API: http://localhost:8000
- OpenAPI 문서: http://localhost:8000/docs
- 프로세스 상태: http://localhost:8000/health
- DB 연결 상태: http://localhost:8000/ready

테스트는 `pytest`로 실행합니다.

## 프런트엔드

Node.js 22 이상이 필요합니다.

```shell
cd frontend
npm install
npm run dev
```

- 웹 UI: http://localhost:5173

검증 명령은 다음과 같습니다.

```shell
npm run lint
npm test
npm run build
```

## 마이그레이션

모델을 추가한 뒤 백엔드 디렉터리에서 새 마이그레이션을 생성하고 적용합니다.

```shell
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```
