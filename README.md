# ControlPlane.ai — Enterprise Responsible AI Middleware

ControlPlane.ai is a high-throughput, declarative guardrail and governance middleware for enterprise LLM applications. It evaluates model interactions concurrently across multiple risk dimensions (PII leakage, retrieval grounding hallucinations, demographic bias, and statistical distribution drift), applies customizable per-channel risk policies, records immutable audit trails, and closes the loop with human review calibration.

---

## 🚀 Quick Start (Local Development)

### 1. Prerequisites
- Python 3.10+
- Node.js 18+ (for frontend dashboard)

### 2. Installation
```bash
# Install backend dependencies
pip install -r backend/requirements.txt
python -m spacy download en_core_web_sm

# Install frontend dependencies
cd frontend && npm install && cd ..
```

### 3. Environment Variables
Copy `.env.example` to `.env` and fill in your keys:
```bash
cp .env.example .env
```
Key variables:
- `ANTHROPIC_API_KEY`: Anthropic Claude API key for AI-as-a-Judge evaluations.
- `ALLOWED_ORIGINS`: Comma-separated list of origins (defaults to `http://localhost:3000`).
- `DATABASE_URL`: Database connection string (defaults to local SQLite `sqlite:///./controlplane.db`).

### 4. Running Locally
Using the Makefile:
```bash
# Start backend on http://127.0.0.1:8000
make backend

# Start frontend dashboard on http://localhost:3000
make frontend

# Seed synthetic test traffic
make seed
```

Or manually:
```bash
# Backend
uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir backend --reload

# Frontend
cd frontend && npm run dev
```

---

## ☁️ Deployment on Render (Web Service)

### Deployment Architecture & Persistence Notice
> [!NOTE]
> **Ephemeral Storage Notice:** Render Web Services use an ephemeral filesystem. On the free tier or standard web service instances without attached persistent disks, local SQLite databases (`controlplane.db`) reset on restarts and redeploys.
> 
> *Audit data is ephemeral in this deployment; a production version would use a persistent database (e.g. Render Postgres or an external managed DB).*
>
> To enable persistence on Render, provision a **Render PostgreSQL** database and configure the `DATABASE_URL` environment variable in the Render dashboard.

### Deploying with Render Blueprint (`render.yaml`)
1. Push this repository to GitHub.
2. In the **Render Dashboard**, click **New > Blueprint**.
3. Select this repository. Render will automatically detect `render.yaml` and configure the backend service with:
   - **Runtime**: Python
   - **Build Command**: `pip install -r backend/requirements.txt && python -m spacy download en_core_web_sm`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --app-dir backend`
   - **Health Check Path**: `/health`
4. Under the service's **Environment** tab on Render, add:
   - `ANTHROPIC_API_KEY`: Your Anthropic API key.
   - `ALLOWED_ORIGINS`: The URL of your deployed frontend (e.g., `https://your-frontend.vercel.app`).
   - `DATABASE_URL` *(Optional)*: Internal connection string to a Render PostgreSQL instance.

---

## 🧪 Local Dry Run Simulation

To simulate Render's dynamic `$PORT` injection and module loading from the repo root before deploying:
```bash
# Run from repository root
PORT=10000 uvicorn app.main:app --host 0.0.0.0 --port $PORT --app-dir backend
```
Test the health endpoint:
```bash
curl http://localhost:10000/health
```

Expected output:
```json
{
  "status": "ok",
  "service": "ControlPlane.ai",
  "version": "0.1.0",
  "timestamp": "2026-08-25T..."
}
```

---

## 🏛️ Architecture & Governance

For full technical specifications, detector pipelines, decision tier thresholds, and feedback loop mechanics, refer to [`ARCHITECTURE.md`](./ARCHITECTURE.md).