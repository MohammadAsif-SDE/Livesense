.PHONY: setup setup-backend setup-frontend run-backend run-frontend test lint clean

# ── Setup ──────────────────────────────────────────────────────────── #

setup: setup-backend setup-frontend
	@echo "✓ Setup complete. Copy .env.example → .env and set your HF_TOKEN."

setup-backend:
	@echo "→ Creating Python venv …"
	python3.12 -m venv backend/.venv
	backend/.venv/bin/pip install --upgrade pip
	backend/.venv/bin/pip install -r backend/requirements.txt
	cp backend/.env.example backend/.env 2>/dev/null || true
	@echo "✓ Backend ready. Edit backend/.env and set HF_TOKEN."

setup-frontend:
	@echo "→ Installing frontend dependencies …"
	cd frontend && npm install
	cd frontend && npm approve-scripts esbuild fsevents 2>/dev/null || true
	cd frontend && npm install
	@echo "✓ Frontend ready."

# ── Run ───────────────────────────────────────────────────────────── #

run-backend:
	@echo "→ Starting FastAPI server on http://localhost:8000 …"
	@lsof -ti:8000 | xargs kill -9 2>/dev/null || true
	$(PWD)/backend/.venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload --timeout-graceful-shutdown 3 --app-dir $(PWD)/backend

run-frontend:
	@echo "→ Starting React dashboard on http://localhost:5173 …"
	cd frontend && npm run dev

# ── Test ──────────────────────────────────────────────────────────── #

test:
	cd backend && .venv/bin/pytest -v

# ── Lint ──────────────────────────────────────────────────────────── #

lint:
	cd backend && .venv/bin/python -m ruff check .
	cd frontend && npm run lint

# ── Clean ─────────────────────────────────────────────────────────── #

clean:
	rm -rf backend/.venv frontend/node_modules frontend/dist
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "✓ Clean done."
