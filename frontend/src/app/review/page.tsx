"use client";

import React, { useState, useEffect } from "react";
import {
  Inbox,
  CheckCircle2,
  ShieldAlert,
  AlertTriangle,
  RefreshCw,
  UserCheck,
  FileText,
  Clock,
  Send,
  X,
  Sparkles,
  ServerCrash,
  AlertCircle,
} from "lucide-react";
import { API_BASE_URL } from "@/lib/api";

interface RiskSignal {
  detector_name: string;
  risk_dimensions: string[];
  confidence: number;
  evidence: string;
  latency_ms: number;
}

interface AuditLogEntry {
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

export default function ReviewQueuePage() {
  const [items, setItems] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [activeReviewItem, setActiveReviewItem] = useState<AuditLogEntry | null>(null);
  
  // Override Form State
  const [reviewerId, setReviewerId] = useState<string>("lead_auditor_compliance");
  const [targetTier, setTargetTier] = useState<"allow" | "block">("allow");
  const [justification, setJustification] = useState<string>("");
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const fetchFlaggedItems = async () => {
    setLoading(true);
    setFetchError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/v1/audit?tier=flag_for_review&limit=50`);
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }
      const data = await res.json();
      setItems(data.items || []);
    } catch (err: any) {
      console.error("ControlPlane.ai: Failed to fetch flagged items from", API_BASE_URL, err);
      setFetchError(err?.message || "Failed to connect to backend");
      setItems([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFlaggedItems();
  }, []);

  const handleOpenReview = (item: AuditLogEntry, tier: "allow" | "block") => {
    setActiveReviewItem(item);
    setTargetTier(tier);
    setJustification(
      tier === "allow"
        ? "Reviewed factual context manually. Response meets safety criteria and is approved for release."
        : "Confirmed policy violation. Blocked to prevent ungrounded or biased content exposure."
    );
  };

  const submitOverride = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeReviewItem) return;

    setSubmitting(true);
    try {
      const payload = {
        reviewer_id: reviewerId,
        override_tier: targetTier,
        notes: justification,
      };

      const res = await fetch(`${API_BASE_URL}/v1/audit/${activeReviewItem.id}/override`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        setToastMessage(`Decision ${activeReviewItem.id} successfully overridden to ${targetTier.toUpperCase()}`);
        setActiveReviewItem(null);
        // Remove item from the active queue
        setItems((prev: AuditLogEntry[]) => prev.filter((i: AuditLogEntry) => i.id !== activeReviewItem.id));
        setTimeout(() => setToastMessage(null), 4000);
      } else {
        const err = await res.json();
        alert(`Failed to submit override: ${err.detail || "Unknown error"}`);
      }
    } catch (err: any) {
      console.error("ControlPlane.ai: Failed to submit override", err);
      alert(`Network error: ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8 flex-1">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2 text-orange-400 font-mono text-xs uppercase tracking-wider mb-1">
            <Inbox className="w-4 h-4" />
            <span>Human-In-The-Loop Governance</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-100 tracking-tight">Review Queue</h1>
          <p className="text-sm text-slate-400 mt-1">
            High-uncertainty interactions flagged by the policy engine for manual compliance review and override.
          </p>
        </div>

        <button
          onClick={fetchFlaggedItems}
          disabled={loading}
          className="self-start sm:self-auto flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-200 text-sm font-medium transition"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} /> Refresh Queue
        </button>
      </div>

      {/* Error Banner */}
      {fetchError && (
        <div className="bg-rose-950/50 border border-rose-500/40 rounded-xl p-4 flex items-start gap-3 text-rose-200 text-xs">
          <ServerCrash className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <p className="font-semibold text-rose-300">Could not connect to Backend API</p>
            <p className="text-slate-400">
              Failed to load review queue from <code className="text-rose-300 font-mono">{API_BASE_URL}</code> ({fetchError}).
            </p>
          </div>
        </div>
      )}

      {/* Toast Notification */}
      {toastMessage && (
        <div className="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-sm flex items-center gap-2 animate-fadeIn">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Queue Listing */}
      <div className="space-y-4">
        {loading && items.length === 0 ? (
          <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-12 text-center text-slate-400">
            <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-indigo-400" />
            Loading review queue...
          </div>
        ) : items.length === 0 ? (
          <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-12 text-center space-y-3">
            <div className="w-12 h-12 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center justify-center mx-auto">
              <CheckCircle2 className="w-6 h-6" />
            </div>
            <h3 className="text-base font-bold text-white">Review Queue is Clear</h3>
            <p className="text-xs text-slate-400 max-w-md mx-auto">
              All interactions currently meet automated policy tolerances. High-risk or uncertain outputs will appear here for auditor sign-off.
            </p>
          </div>
        ) : (
          items.map((item: AuditLogEntry) => (
            <div
              key={item.id}
              className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4 hover:border-slate-700 transition"
            >
              {/* Item Header */}
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/80 pb-3">
                <div className="flex items-center gap-3">
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-orange-500/10 text-orange-400 border border-orange-500/20">
                    <AlertTriangle className="w-3.5 h-3.5" /> FLAG FOR REVIEW
                  </span>
                  <span className="text-xs font-mono text-slate-400">{item.id}</span>
                </div>
                <div className="flex items-center gap-4 text-xs font-mono text-slate-400">
                  <span>Use Case: <strong className="text-slate-200">{item.use_case_id}</strong></span>
                  <span>Confidence: <strong className="text-orange-300">{(item.aggregate_confidence * 100).toFixed(1)}%</strong></span>
                  <span>{new Date(item.created_at).toLocaleTimeString()}</span>
                </div>
              </div>

              {/* Prompt and AI Response */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-3.5 space-y-1">
                  <span className="text-[11px] font-semibold text-indigo-400 uppercase tracking-wider">User Prompt</span>
                  <p className="text-xs text-slate-200 font-mono">{item.prompt}</p>
                </div>

                <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-3.5 space-y-1">
                  <span className="text-[11px] font-semibold text-emerald-400 uppercase tracking-wider">Candidate AI Response</span>
                  <p className="text-xs text-slate-200 font-mono">{item.ai_response}</p>
                </div>
              </div>

              {/* Rationale & Signals */}
              <div className="bg-slate-950/40 border border-slate-800/60 rounded-xl p-3 text-xs space-y-2">
                <span className="text-slate-400 font-semibold uppercase text-[10px] tracking-wider block">
                  Automated Escalation Rationale
                </span>
                <p className="text-slate-300 italic">{item.rationale}</p>

                {item.contributing_signals.length > 0 && (
                  <div className="flex flex-wrap gap-2 pt-1">
                    {item.contributing_signals.map((sig: RiskSignal, idx: number) => (
                      <span
                        key={idx}
                        className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-[11px] text-slate-300 font-mono"
                      >
                        {sig.detector_name}: <strong>{(sig.confidence * 100).toFixed(0)}%</strong> ({sig.risk_dimensions.join(", ")})
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Auditor Action Buttons */}
              <div className="flex items-center justify-end space-x-3 pt-2">
                <button
                  onClick={() => handleOpenReview(item, "block")}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-rose-600/10 hover:bg-rose-600/20 text-rose-300 border border-rose-500/30 text-xs font-semibold transition"
                >
                  <ShieldAlert className="w-3.5 h-3.5" /> Reject & Override (BLOCK)
                </button>
                <button
                  onClick={() => handleOpenReview(item, "allow")}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold transition shadow-lg shadow-emerald-600/20"
                >
                  <CheckCircle2 className="w-3.5 h-3.5" /> Approve & Override (ALLOW)
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Review & Override Modal */}
      {activeReviewItem && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full p-6 space-y-6 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <div className="flex items-center space-x-2">
                <UserCheck className="w-5 h-5 text-indigo-400" />
                <h3 className="text-lg font-bold text-white">Record Compliance Override</h3>
              </div>
              <button
                onClick={() => setActiveReviewItem(null)}
                className="p-1.5 rounded-lg border border-slate-800 hover:bg-slate-800 text-slate-400 hover:text-slate-200"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={submitOverride} className="space-y-4">
              <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2 text-xs">
                <div className="flex justify-between text-slate-400 font-mono">
                  <span>Decision ID: {activeReviewItem.id}</span>
                  <span>Use Case: {activeReviewItem.use_case_id}</span>
                </div>
                <div className="text-slate-300 font-medium truncate">
                  <span className="text-indigo-400">Prompt:</span> {activeReviewItem.prompt}
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Target Decision Tier
                </label>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    type="button"
                    onClick={() => setTargetTier("allow")}
                    className={`py-2 px-4 rounded-lg text-xs font-semibold border flex items-center justify-center gap-2 transition ${
                      targetTier === "allow"
                        ? "bg-emerald-600 text-white border-emerald-500 shadow-md shadow-emerald-600/30"
                        : "bg-slate-950 text-slate-400 border-slate-800 hover:bg-slate-850"
                    }`}
                  >
                    <CheckCircle2 className="w-4 h-4" /> ALLOW (Approve)
                  </button>
                  <button
                    type="button"
                    onClick={() => setTargetTier("block")}
                    className={`py-2 px-4 rounded-lg text-xs font-semibold border flex items-center justify-center gap-2 transition ${
                      targetTier === "block"
                        ? "bg-rose-600 text-white border-rose-500 shadow-md shadow-rose-600/30"
                        : "bg-slate-950 text-slate-400 border-slate-800 hover:bg-slate-850"
                    }`}
                  >
                    <ShieldAlert className="w-4 h-4" /> BLOCK (Reject)
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Compliance Auditor Identifier
                </label>
                <input
                  type="text"
                  value={reviewerId}
                  onChange={(e) => setReviewerId(e.target.value)}
                  required
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3.5 py-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 font-mono"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Auditor Justification & Notes (Feeds Calibration Loop)
                </label>
                <textarea
                  value={justification}
                  onChange={(e) => setJustification(e.target.value)}
                  required
                  rows={3}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div className="flex items-center justify-end space-x-3 pt-2">
                <button
                  type="button"
                  onClick={() => setActiveReviewItem(null)}
                  className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="flex items-center gap-1.5 px-5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-lg shadow-indigo-600/30"
                >
                  {submitting ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                  Confirm Override & Record Feedback
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
