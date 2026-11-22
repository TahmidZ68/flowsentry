# FlowSentry — Local Development Guide

## Prerequisites
- Python 3.12+
- Node.js 20+ (Node 22+ recommended for `@supabase/supabase-js` future versions)
- Docker & Docker Compose (for PostgreSQL 16 + Redis 7 stack)

## 1. Environment Configuration
```bash
cp .env.example .env
python scripts/generate_keys.py
```
Paste the generated `ENCRYPTION_KEY` and `LOCAL_DEV_JWT_SECRET` into `.env`.

## 2. Backend Setup
```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

## 3. Background Worker & Beat (Optional locally if Redis is running)
```bash
celery -A app.workers.celery_app worker --loglevel=info
celery -A app.workers.celery_app beat --loglevel=info
```

## 4. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:3000`. In `local_dev` mode (`NEXT_PUBLIC_AUTH_MODE=local_dev`), you can sign in with any email address and use **Seed / Reset Demo** from the sidebar to evaluate the isolated demo sandbox.

## 5. Running Tests & Linters
```bash
# Backend
cd backend
pytest -v
ruff check app tests

# Frontend
cd frontend
npm run typecheck
npm test
npm run build
```
