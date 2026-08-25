# ControlPlane.ai — Pipeline Architecture & Technical Design

This document details the end-to-end dataflow, concurrent orchestration mechanics, governance model, and continuous calibration feedback loop for **ControlPlane.ai**.

---

## 🏛️ End-to-End Pipeline & Dataflow

```mermaid
flowchart TD
    subgraph Ingestion ["1. Interaction Interception"]
        ClientApp["Client Application\n(Chatbot / Copilot / Loan Tool)"]
        CheckReq["CheckRequest\n(prompt, response, context, metadata)"]
        ClientApp -->|POST /v1/check| CheckReq
    end

    subgraph PolicyLookup ["2. Governance Policy Lookup"]
        PolicyStore[("Declarative YAML Policies\n(Latency, Fail-Mode, Weights, Bands)")]
        CheckReq --> PolicyStore
    end

    subgraph Detectors ["3. Concurrent Risk Detectors (asyncio.gather)"]
        D1["PII Entity Detector\n(Dual-tag Privacy + Hallucination)"]
        D2["Retrieval Verification\n(Sentence-Level Grounding)"]
        D3["AI-as-a-Judge\n(Claude 3.5 Sonnet / Rubric)"]
        D4["Bias Heuristic Detector\n(Stereotype + Statistical Guard)"]
        D5["Statistical Anomaly\n(Cosine Distance vs SQLite Pool)"]
        
        PolicyStore --> D1
        PolicyStore --> D2
        PolicyStore --> D3
        PolicyStore --> D4
        PolicyStore --> D5
    end

    subgraph Engine ["4. Decision Engine & Confidence Aggregation"]
        Orchestrator["Orchestrator\n- Timeout Enforcement\n- Fail-Closed / Fail-Open Handler\n- Weighted Confidence Synthesis\n- Human Review Escalation (> Threshold)"]
        D1 --> Orchestrator
        D2 --> Orchestrator
        D3 --> Orchestrator
        D4 --> Orchestrator
        D5 --> Orchestrator
    end

    subgraph Tiers ["5. Policy Tier Decision"]
        TierDecision{"Synthesized Tier"}
        Orchestrator --> TierDecision
        TierDecision -->|Confidence <= AllowMax| T_ALLOW["ALLOW\n(Pass to User)"]
        TierDecision -->|AllowMax < Conf <= EditMax| T_EDIT["EDIT\n(Sanitize PII / Redact)"]
        TierDecision -->|EditMax < Conf <= FlagMax\nOR > ReviewThreshold| T_FLAG["FLAG_FOR_REVIEW\n(Route to Human Review Queue)"]
        TierDecision -->|Conf > BlockMin| T_BLOCK["BLOCK\n(Suppress Response)"]
    end

    subgraph Audit ["6. Immutable Governance Trail"]
        AuditDB[("SQLite audit_log Table\n(Full Request, All Signals, Tier, Rationale)")]
        T_ALLOW --> AuditDB
        T_EDIT --> AuditDB
        T_FLAG --> AuditDB
        T_BLOCK --> AuditDB
    end

    subgraph Feedback ["7. Human Review Queue & Feedback Loop"]
        ReviewQueue["Human Review Queue\n(/review)"]
        T_FLAG -.->|Pending Items| ReviewQueue
        Auditor["Compliance Auditor / Operator"]
        Auditor -->|POST /v1/audit/{id}/override| ReviewQueue
        
        FeedbackStore[("feedback_examples Table\n(Labeled Training Records)")]
        ReviewQueue --> FeedbackStore
        
        CalibrationEngine["Calibration Engine\n- Per-Detector Accuracy\n- Empirical FP / FN Rates"]
        FeedbackStore --> CalibrationEngine
        
        Recommendation["Policy Threshold Suggestion\n(Human-in-the-Loop Review on /policy)"]
        CalibrationEngine --> Recommendation
    end
```

---

## 🧩 Architectural Component Breakdown

### 1. Interception Layer (`backend/app/main.py`)
- FastAPI application exposing high-throughput asynchronous endpoints:
  - `POST /v1/check`: Single interaction guardrail evaluation.
  - `POST /v1/check/batch`: Concurrent batch evaluation for offline datasets or high-load endpoints.
  - `GET /v1/audit`: Filterable query interface for compliance teams.
  - `POST /v1/audit/{decision_id}/override`: Human reviewer decision override mechanism.
  - `GET /v1/feedback/detector-performance`: Empirical detector accuracy telemetry.
  - `GET /v1/metrics/summary`: System trustworthiness executive narrative and operational metrics.

### 2. Orchestration & Decision Engine (`backend/app/engine/orchestrator.py`)
- **Parallel Dispatch**: Evaluates all enabled detectors concurrently using `asyncio.gather(*tasks)` wrapped in `asyncio.wait_for(..., timeout=budget_seconds)`.
- **Latency Budget Enforcement**:
  - `customer_support_bot`: 350 ms budget
  - `internal_hr_assistant`: 800 ms budget
  - `wealth_advisor_copilot`: 1,500 ms budget
- **Fault-Tolerance Handlers**:
  - **`fail_closed`**: Timeout or detector error synthesizes a maximum risk signal (`confidence=1.0`), preventing unverified data leakage in external/fiduciary channels.
  - **`fail_open`**: Times out detectors gracefully, omits them from weighted calculation, logs a governance disclaimer in the rationale, and allows internal workflows to proceed.
- **Weighted Confidence Synthesis**:
  $$\text{Aggregate Confidence} = \frac{\sum (w_i \times c_i)}{\sum w_i}$$
- **Forced Human Escalation**: Regardless of the weighted confidence score, if $\text{Aggregate Confidence} \ge \text{requires\_human\_review\_above}$, the decision is immediately escalated to `flag_for_review`.

### 3. Five-Tier Risk Detector Layer (`backend/app/detectors/`)
1. **`PIIEntityDetector`**: Identifies structured entities (Emails, Phone Numbers, SSNs, Credit Cards, Bank Accounts, Addresses). Dual-tags unprompted PII as `["privacy", "hallucination"]` when personal details are fabricated.
2. **`RetrievalVerificationDetector`**: Breaks candidate responses into claim sentences and computes maximum grounding similarity against `retrieved_context`. Returns explicit `confidence=0.0` with `"no ground truth available"` when context is absent.
3. **`AIJudgeDetector`**: Calls Anthropic Claude (`claude-sonnet-4-6`) with a strict scoring rubric, bounded by request-level timeouts (~70% of total budget) and graceful error fallback.
4. **`BiasHeuristicDetector`**: Scans for demographic slurs, exclusionary generalizations, and stereotypes. Applies a `0.3x` confidence discount when factual statements include statistical qualifiers (numbers, percentages, *"on average"*).
5. **`StatisticalAnomalyDetector`**: Compares dense embeddings against a rolling SQLite baseline pool (capped at 500 records). Features a cold-start guard (&lt;10 historical samples returns `confidence=0.0`).

### 4. Immutable Audit & Compliance Layer (`backend/app/governance/audit.py`)
- **Core Invariant**: *Nothing is evaluated without leaving an immutable audit trail.*
- **Schema (`audit_log` Table)**:
  - `id`: Unique decision ID (`dec_req-xxx`)
  - `request_id`: Originating client request ID
  - `use_case_id`: Targeted deployment channel
  - `prompt` & `ai_response`: Full raw text strings
  - `retrieved_context`: JSON array of grounding chunks
  - `tier`: Final decision tier (`allow`, `edit`, `flag_for_review`, `block`)
  - `aggregate_confidence`: Synthesized risk score (`0.0 - 1.0`)
  - `contributing_signals`: JSON array of detector names, dimensions, scores, latencies, and evidence
  - `rationale`: Complete human-readable governance explanation
  - `override`, `override_tier`, `reviewed_by`, `override_notes`: Auditor sign-off metadata
  - `created_at` & `updated_at`: UTC timestamps

### 5. Continuous Calibration & Feedback Loop (`backend/app/feedback/loop.py`)
- Every human override in `/review` writes a labeled record to `feedback_examples`.
- The Calibration Engine tracks:
  - $\text{False Positive Rate} = \frac{\text{False Positives}}{\text{Total Flags}}$
  - $\text{Human Alignment Accuracy} = \frac{\text{True Positives} + \text{True Negatives}}{\text{Total Overrides}}$
- If a detector's false-positive rate crosses 35%, the system surfaces a threshold/weight adjustment recommendation on the `/policy` dashboard.
- **Human-in-the-Loop Guarantee**: System recommendations are purely advisory and never silently auto-apply to runtime configurations.

---

## 📊 Database Schema Overview

```
 ┌───────────────────────────────────────┐
 │               audit_log               │
 ├───────────────────────────────────────┤
 │ id (PK)                               │
 │ request_id                            │
 │ use_case_id                           │
 │ prompt                                │
 │ ai_response                           │
 │ retrieved_context (JSON)              │
 │ conversation_history (JSON)           │
 │ metadata_payload (JSON)               │
 │ tier                                  │
 │ aggregate_confidence                  │
 │ contributing_signals (JSON)           │
 │ rationale                             │
 │ reviewed_by                           │
 │ override (Boolean)                    │
 │ override_tier                         │
 │ override_notes                        │
 │ created_at (UTC)                      │
 │ updated_at (UTC)                      │
 └───────────────────────────────────────┘
                     │
                     │ Human Override Action
                     ▼
 ┌───────────────────────────────────────┐
 │           feedback_examples           │
 ├───────────────────────────────────────┤
 │ id (PK)                               │
 │ decision_id (FK)                      │
 │ use_case_id                           │
 │ original_tier                         │
 │ corrected_tier                        │
 │ reviewer_id                           │
 │ justification                         │
 │ prompt                                │
 │ ai_response                           │
 │ contributing_signals (JSON)           │
 │ created_at (UTC)                      │
 └───────────────────────────────────────┘
```
