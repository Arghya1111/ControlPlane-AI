/**
 * ControlPlane.ai API Client & Configuration
 *
 * Provides typed methods and base URL resolution for communicating with
 * the ControlPlane.ai FastAPI backend on Render.
 */

// Base API URL resolution from NEXT_PUBLIC_API_URL environment variable
export const API_BASE_URL: string = (() => {
  const envUrl = process.env.NEXT_PUBLIC_API_URL;
  if (envUrl && envUrl.trim().length > 0) {
    return envUrl.trim().replace(/\/+$/, "");
  }
  if (
    typeof window !== "undefined" &&
    (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")
  ) {
    return "http://127.0.0.1:8000";
  }
  // Default to deployed Render backend if no env var is configured
  return "https://controlplane-ai-8eyi.onrender.com";
})();

export function getApiBaseUrl(): string {
  return API_BASE_URL;
}

/**
 * Standard HTTP error class with status code and detailed message
 */
export class ApiError extends Error {
  status: number;
  data?: any;

  constructor(message: string, status: number, data?: any) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

/**
 * Generic fetch wrapper with timeout, JSON parsing, and error handling
 */
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status}: ${response.statusText}`;
    let errorData = null;
    try {
      errorData = await response.json();
      if (errorData?.detail) {
        errorDetail = typeof errorData.detail === "string" ? errorData.detail : JSON.stringify(errorData.detail);
      }
    } catch (_) {
      // Body was not JSON
    }
    throw new ApiError(errorDetail, response.status, errorData);
  }

  return response.json() as Promise<T>;
}

// ============================================================================
// Types
// ============================================================================

export interface RiskSignal {
  detector_name: string;
  risk_dimensions: string[];
  confidence: number;
  evidence: string;
  latency_ms: number;
}

export interface AuditLogEntry {
  id: string;
  request_id: string;
  use_case_id: string;
  prompt: string;
  ai_response: string;
  retrieved_context?: string[] | null;
  conversation_history?: string[] | null;
  metadata?: Record<string, any>;
  tier: "allow" | "edit" | "flag_for_review" | "block";
  aggregate_confidence: number;
  contributing_signals: RiskSignal[];
  rationale: string;
  reviewed_by?: string | null;
  override: boolean;
  override_tier?: string | null;
  override_notes?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AuditLogQueryResponse {
  total: number;
  items: AuditLogEntry[];
}

export interface OverrideRequestPayload {
  reviewer_id: string;
  override_tier: "allow" | "edit" | "flag_for_review" | "block";
  notes: string;
}

export interface UseCaseProfile {
  id: string;
  name: string;
  channel_type: string;
  latency_budget_ms: number;
  fail_mode: string;
  requires_human_review_above: number;
  blocks_above: number;
  active_detectors: string[];
  risk_dimension_weights: Record<string, number>;
}

export interface DetectorPerformanceStats {
  detector_name: string;
  total_evaluations: number;
  false_positives: number;
  false_negatives: number;
  accuracy: number;
  avg_latency_ms: number;
  current_weight: number;
}

export interface FeedbackPerformanceResponse {
  detectors: DetectorPerformanceStats[];
  total_human_overrides: number;
  last_updated: string;
}

export interface GovernanceMetricsResponse {
  total_evaluations_24h: number;
  overall_tier_breakdown: {
    allow: number;
    edit: number;
    flag_for_review: number;
    block: number;
    total: number;
  };
  detector_latencies: Array<{
    detector_name: string;
    avg_latency_ms: number;
    p95_latency_ms: number;
  }>;
  error_estimates: {
    estimated_false_positive_rate: number;
    estimated_false_negative_rate: number;
    confidence_interval_low: number;
    confidence_interval_high: number;
  };
  trustworthiness_narrative: string;
  time_series_history: Array<{
    timestamp: string;
    formatted_time: string;
    use_case_id: string;
    allow: number;
    edit: number;
    flag_for_review: number;
    block: number;
    total: number;
  }>;
}

// ============================================================================
// API Endpoint Functions
// ============================================================================

/**
 * Health Check: GET /health
 */
export async function checkHealth(): Promise<{ status: string; service: string; version: string; timestamp: string }> {
  return request<{ status: string; service: string; version: string; timestamp: string }>("/health");
}

/**
 * Query Audit Logs: GET /v1/audit
 */
export async function fetchAuditLogs(params?: {
  use_case_id?: string;
  tier?: string;
  from?: string;
  to?: string;
  limit?: number;
  offset?: number;
}): Promise<AuditLogQueryResponse> {
  const searchParams = new URLSearchParams();
  if (params?.use_case_id) searchParams.append("use_case_id", params.use_case_id);
  if (params?.tier) searchParams.append("tier", params.tier);
  if (params?.from) searchParams.append("from", params.from);
  if (params?.to) searchParams.append("to", params.to);
  if (params?.limit) searchParams.append("limit", params.limit.toString());
  if (params?.offset) searchParams.append("offset", params.offset.toString());

  const qs = searchParams.toString();
  return request<AuditLogQueryResponse>(`/v1/audit${qs ? `?${qs}` : ""}`);
}

/**
 * Count Audit Logs: GET /v1/audit/count
 */
export async function fetchAuditCount(params?: { use_case_id?: string; tier?: string }): Promise<{ total: number }> {
  const searchParams = new URLSearchParams();
  if (params?.use_case_id) searchParams.append("use_case_id", params.use_case_id);
  if (params?.tier) searchParams.append("tier", params.tier);

  const qs = searchParams.toString();
  return request<{ total: number }>(`/v1/audit/count${qs ? `?${qs}` : ""}`);
}

/**
 * Record Human Override: POST /v1/audit/{decision_id}/override
 */
export async function submitAuditOverride(
  decisionId: string,
  payload: OverrideRequestPayload
): Promise<AuditLogEntry> {
  return request<AuditLogEntry>(`/v1/audit/${decisionId}/override`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/**
 * List Governance Use Cases: GET /v1/use-cases
 */
export async function fetchUseCases(): Promise<UseCaseProfile[]> {
  return request<UseCaseProfile[]>("/v1/use-cases");
}

/**
 * Get Use Case Details: GET /v1/use-cases/{use_case_id}
 */
export async function fetchUseCase(useCaseId: string): Promise<UseCaseProfile> {
  return request<UseCaseProfile>(`/v1/use-cases/${useCaseId}`);
}

/**
 * Get Feedback & Detector Performance: GET /v1/feedback/detector-performance
 */
export async function fetchDetectorPerformance(): Promise<FeedbackPerformanceResponse> {
  return request<FeedbackPerformanceResponse>("/v1/feedback/detector-performance");
}

/**
 * Get Governance Telemetry Summary: GET /v1/metrics/summary
 */
export async function fetchGovernanceMetrics(hours: number = 24): Promise<GovernanceMetricsResponse> {
  return request<GovernanceMetricsResponse>(`/v1/metrics/summary?hours=${hours}`);
}

/**
 * Evaluate Interaction Check: POST /v1/check
 */
export async function evaluateCheck(payload: {
  id: string;
  use_case_id: string;
  prompt: string;
  ai_response: string;
  retrieved_context?: string[];
  conversation_history?: string[];
  metadata?: Record<string, any>;
}): Promise<any> {
  return request<any>("/v1/check", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
