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
- `GEMINI_API_KEY`: Google Gemini API key for AI-as-a-Judge evaluations.
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
   - **Build Command**: `pip install -r backend/requirements.txt`
   - **Start Command**: `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`
   - **Health Check Path**: `/health`
4. Under the service's **Environment** tab on Render, configure:
   - `ALLOWED_ORIGINS`: `https://control-plane-ai.vercel.app,http://localhost:3000` *(Vercel preview branch URLs `https://*.vercel.app` are also automatically supported via regex)*
   - `GEMINI_API_KEY`: Your Google Gemini API key.
   - `DATABASE_URL` *(Optional)*: Internal connection string to a Render PostgreSQL instance.

---

## 🌐 Frontend Deployment on Vercel

1. Import the repository into **Vercel**.
2. Set the **Root Directory** to `frontend/`.
3. In **Project Settings > Environment Variables**, add for the **Production** and **Preview** environments:
   - **Key**: `NEXT_PUBLIC_API_URL`
   - **Value**: `https://controlplane-ai-8eyi.onrender.com` *(or your deployed Render backend URL, without trailing slash)*

> [!IMPORTANT]
> Variables set only in local `.env.local` will NOT carry over to Vercel. Always add `NEXT_PUBLIC_API_URL` in the Vercel dashboard and trigger a redeploy so the build picks up the variable.

---

## 🚀 Reseeding Demo Traffic

Because Render Web Services use ephemeral storage on the free tier, local SQLite records reset when the container spins down or redeploys. To seed rich, realistic enterprise interactions into the deployed backend at any time:

```bash
# Seed against deployed Render backend:
python demo/simulate_traffic.py --url https://controlplane-ai-8eyi.onrender.com

# Or pass via environment variable:
API_BASE_URL=https://controlplane-ai-8eyi.onrender.com python demo/simulate_traffic.py
```

---

## 🎤 Before Your Pitch — Deployment Smoke Test Checklist

Run through this checklist **10–15 minutes before presenting or pitching** to ensure warm containers and populated feeds:

- [ ] **1. Wake up Render Cold-Start**:
  Render free-tier instances sleep after 15 minutes of inactivity. Ping the health endpoint:
  ```bash
  curl -I https://controlplane-ai-8eyi.onrender.com/health
  ```
  Wait until you receive `HTTP 200 OK`.

- [ ] **2. Reseed Live Demo Traffic**:
  Populate realistic enterprise audit records across all 3 channels:
  ```bash
  python demo/simulate_traffic.py --url https://controlplane-ai-8eyi.onrender.com
  ```
  Confirm output prints `[OK] Demo seeding complete!` and summary metrics.

- [ ] **3. Verify Live Dashboard**:
  Open `https://control-plane-ai.vercel.app/dashboard` in an incognito window (or hard-refresh `Ctrl+Shift+R`).
  - Verify **ENGINE ONLINE** status pill in the navbar.
  - Verify non-zero counts for **Total Evaluations**, **Allowed**, **Edited**, **Flagged**, and **Blocked**.
  - Click through the use case filter dropdowns and confirm live filtering.

- [ ] **4. Check Review Queue & Overrides**:
  Navigate to `https://control-plane-ai.vercel.app/review` and confirm flagged items appear with auditor action buttons.

- [ ] **5. Check Governance Metrics**:
  Navigate to `https://control-plane-ai.vercel.app/metrics` and verify the executive briefing and hourly time-series charts.

---

## 🧪 Local Dry Run Simulation

To test the backend locally:
```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```
Run tests:
```bash
python -m pytest backend/tests/ -v
```

---

## 🏛️ Architecture & Governance

For full technical specifications, detector pipelines, decision tier thresholds, and feedback loop mechanics, refer to [`ARCHITECTURE.md`](./ARCHITECTURE.md).