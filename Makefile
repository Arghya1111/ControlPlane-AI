.PHONY: help install backend frontend demo seed test

help:
	@echo "ControlPlane.ai — Enterprise Responsible AI Middleware"
	@echo ""
	@echo "Available commands:"
	@echo "  make install    - Install backend dependencies (pip) and frontend packages (npm)"
	@echo "  make backend    - Start the FastAPI checking middleware backend on http://127.0.0.1:8000"
	@echo "  make frontend   - Start the Next.js ops dashboard on http://localhost:3000"
	@echo "  make seed       - Send 85+ realistic synthetic enterprise interactions across 3 use cases"
	@echo "  make demo       - Seed traffic and display live demo dashboard endpoints"
	@echo "  make test       - Run backend test suite with pytest"

install:
	@echo "Installing backend dependencies..."
	pip install -r backend/requirements.txt
	@echo "Installing frontend dependencies..."
	cd frontend && npm install

backend:
	@echo "Starting ControlPlane.ai FastAPI Backend on port 8000..."
	cd backend && uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

frontend:
	@echo "Starting ControlPlane.ai Next.js Dashboard on port 3000..."
	cd frontend && npm run dev

seed:
	@echo "Generating realistic synthetic interactions and seeding database..."
	python demo/simulate_traffic.py --url http://127.0.0.1:8000

demo: seed

test:
	@echo "Running test suite with pytest..."
	python -m pytest backend/tests/ -v
