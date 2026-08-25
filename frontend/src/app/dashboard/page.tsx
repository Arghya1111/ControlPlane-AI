"use client";

import React, { useState, useEffect } from "react";
import {
  ShieldCheck,
  ShieldAlert,
  AlertTriangle,
  Activity,
  Filter,
  Search,
  RefreshCw,
  Eye,
  Sliders,
  Clock,
  CheckCircle2,
  FileText,
  UserCheck,
  Database,
  ArrowUpRight,
  X,
  AlertCircle,
  Terminal,
  ServerCrash,
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

const USE_CASE_LABELS: Record<string, string> = {
  customer_support_bot: "Customer Support Assistant",
  wealth_advisor_copilot: "Wealth Advisory Copilot",
  internal_hr_assistant: "Internal HR Assistant",
};

export default function DashboardPage() {
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [fetchError, setFetchError] = useState<string | null>(null);
  
  // Filters
  const [selectedUseCase, setSelectedUseCase] = useState<string>("");
  const [selectedTier, setSelectedTier] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Detail Modal
  const [selectedEntry, setSelectedEntry] = useState<AuditLogEntry | null>(null);

  const fetchAuditLogs = async () => {
    setLoading(true);
    setFetchError(null);
    try {
      const params = new URLSearchParams();
      if (selectedUseCase) params.append("use_case_id", selectedUseCase);
      if (selectedTier) params.append("tier", selectedTier);
      params.append("limit", "100");

      const res = await fetch(`${API_BASE_URL}/v1/audit?${params.toString()}`);
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }
      const data = await res.json();
      setLogs(data.items || []);
      setTotalCount(data.total || 0);
    } catch (err: any) {
      console.error("ControlPlane.ai: Failed to fetch audit logs from backend at", API_BASE_URL, err);
      setFetchError(err?.message || "Failed to connect to backend");
      setLogs([]);
      setTotalCount(0);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAuditLogs();
  }, [selectedUseCase, selectedTier]);

  // Client-side search filtering
  const filteredLogs = logs.filter((item: AuditLogEntry) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      item.id.toLowerCase().includes(q) ||
      item.request_id.toLowerCase().includes(q) ||
      item.prompt.toLowerCase().includes(q) ||
      item.ai_response.toLowerCase().includes(q) ||
      item.rationale.toLowerCase().includes(q)
    );
  });

  // Calculate summary stats
  const allowCount = logs.filter((l: AuditLogEntry) => l.tier === "allow").length;
  const flagCount = logs.filter((l: AuditLogEntry) => l.tier === "flag_for_review").length;
  const blockCount = logs.filter((l: AuditLogEntry) => l.tier === "block").length;
  const editCount = logs.filter((l: AuditLogEntry) => l.tier === "edit").length;

  const renderTierBadge = (tier: string, isOverride?: boolean) => {
    switch (tier) {
      case "allow":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <CheckCircle2 className="w-3.5 h-3.5" /> ALLOW {isOverride && "(OVERRIDE)"}
          </span>
        );
      case "edit":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-yellow-500/10 text-yellow-400 border border-yellow-500/20">
            <AlertTriangle className="w-3.5 h-3.5" /> EDIT {isOverride && "(OVERRIDE)"}
          </span>
        );
      case "flag_for_review":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-orange-500/10 text-orange-400 border border-orange-500/20">
            <Activity className="w-3.5 h-3.5" /> FLAG FOR REVIEW
          </span>
        );
      case "block":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20">
            <ShieldAlert className="w-3.5 h-3.5" /> BLOCK {isOverride && "(OVERRIDE)"}
          </span>
        );
      default:
        return <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-800 text-slate-300">{tier}</span>;
    }
  };

  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8 flex-1">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 tracking-tight">Audit Trail & Governance Feed</h1>
          <p className="text-sm text-slate-400 mt-1">
            Real-time immutable log of all Responsible AI interactions, multi-detector signals, and policy decisions.
          </p>
        </div>
        <button
          onClick={fetchAuditLogs}
          disabled={loading}
          className="self-start sm:self-auto flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-200 text-sm font-medium transition"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} /> Refresh Feed
        </button>
      </div>

      {/* Ephemeral DB & Demo Notice Banner */}
      <div className="bg-indigo-950/40 border border-indigo-500/30 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-indigo-200">
        <div className="flex items-start sm:items-center gap-2.5">
          <Database className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5 sm:mt-0" />
          <span>
            <strong>Ephemeral Demo Storage:</strong> Demo data resets when the backend restarts. If this feed is empty, re-run the seed script.
          </span>
        </div>
        <div className="bg-slate-950/80 border border-indigo-500/20 px-2.5 py-1 rounded font-mono text-[11px] text-slate-300 select-all shrink-0">
          python demo/simulate_traffic.py --url {API_BASE_URL}
        </div>
      </div>

      {/* Fetch Error Banner */}
      {fetchError && (
        <div className="bg-rose-950/50 border border-rose-500/40 rounded-xl p-4 flex items-start gap-3 text-rose-200">
          <ServerCrash className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
          <div className="space-y-1 text-xs">
            <p className="font-semibold text-rose-300">Could not connect to Backend API</p>
            <p className="text-slate-400">
              Failed to reach <code className="text-rose-300 font-mono">{API_BASE_URL}</code> ({fetchError}).
              Please check your network connection or verify that CORS permits this domain.
            </p>
          </div>
        </div>
      )}

      {/* KPI Metric Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4">
          <p className="text-xs font-medium text-slate-400">Total Evaluations</p>
          <p className="text-2xl font-bold text-slate-100 mt-1">{totalCount}</p>
        </div>
        <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4">
          <p className="text-xs font-medium text-emerald-400">Allowed</p>
          <p className="text-2xl font-bold text-emerald-400 mt-1">{allowCount}</p>
        </div>
        <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4">
          <p className="text-xs font-medium text-yellow-400">Edited</p>
          <p className="text-2xl font-bold text-yellow-400 mt-1">{editCount}</p>
        </div>
        <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4">
          <p className="text-xs font-medium text-orange-400">Flagged For Review</p>
          <p className="text-2xl font-bold text-orange-400 mt-1">{flagCount}</p>
        </div>
        <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4 col-span-2 lg:col-span-1">
          <p className="text-xs font-medium text-rose-400">Blocked</p>
          <p className="text-2xl font-bold text-rose-400 mt-1">{blockCount}</p>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 flex flex-col md:flex-row gap-4 items-stretch md:items-center justify-between shadow-sm">
        <div className="flex flex-wrap items-center gap-3 flex-1">
          <div className="relative flex-1 min-w-[220px]">
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search prompt, response, or ID..."
              value={searchQuery}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSearchQuery(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500 transition"
            />
          </div>

          <select
            value={selectedUseCase}
            onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setSelectedUseCase(e.target.value)}
            className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
          >
            <option value="">All Use Cases</option>
            <option value="customer_support_bot">Customer Support Assistant</option>
            <option value="wealth_advisor_copilot">Wealth Advisory Copilot</option>
            <option value="internal_hr_assistant">Internal HR Assistant</option>
          </select>

          <select
            value={selectedTier}
            onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setSelectedTier(e.target.value)}
            className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
          >
            <option value="">All Tiers</option>
            <option value="allow">ALLOW</option>
            <option value="edit">EDIT</option>
            <option value="flag_for_review">FLAG FOR REVIEW</option>
            <option value="block">BLOCK</option>
          </select>
        </div>

        <span className="text-xs text-slate-500 font-mono text-right">
          Showing {filteredLogs.length} of {totalCount} records
        </span>
      </div>

      {/* Audit Log Table */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-950/70 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                <th className="py-3 px-4">Timestamp & ID</th>
                <th className="py-3 px-4">Use Case</th>
                <th className="py-3 px-4">Prompt & Response Snippet</th>
                <th className="py-3 px-4">Decision Tier</th>
                <th className="py-3 px-4 text-right">Confidence</th>
                <th className="py-3 px-4 text-center">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-sm">
              {loading && logs.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-slate-400">
                    <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-indigo-400" />
                    Loading audit records...
                  </td>
                </tr>
              ) : filteredLogs.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-slate-400">
                    {fetchError ? (
                      <div className="space-y-1">
                        <AlertCircle className="w-6 h-6 text-rose-400 mx-auto mb-2" />
                        <p className="text-slate-300 font-medium">Failed to load audit records</p>
                        <p className="text-xs text-slate-500">Check that the backend is online and reachable.</p>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        <Database className="w-6 h-6 text-slate-600 mx-auto mb-2" />
                        <p className="text-slate-300 font-medium">No audit records found</p>
                        <p className="text-xs text-slate-500 max-w-md mx-auto">
                          The backend database currently contains 0 records. Run the traffic simulation script to populate realistic interactions.
                        </p>
                      </div>
                    )}
                  </td>
                </tr>
              ) : (
                filteredLogs.map((entry: AuditLogEntry) => (
                  <tr
                    key={entry.id}
                    onClick={() => setSelectedEntry(entry)}
                    className="hover:bg-slate-850/60 cursor-pointer transition-colors group"
                  >
                    <td className="py-3.5 px-4 font-mono text-xs text-slate-400">
                      <div>{new Date(entry.created_at).toLocaleTimeString()}</div>
                      <div className="text-[11px] text-slate-500">{entry.id}</div>
                    </td>
                    <td className="py-3.5 px-4">
                      <span className="text-xs font-medium text-slate-200">
                        {USE_CASE_LABELS[entry.use_case_id] || entry.use_case_id}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 max-w-md">
                      <div className="text-xs text-slate-300 font-medium truncate">
                        <span className="text-indigo-400 font-mono">Q:</span> {entry.prompt}
                      </div>
                      <div className="text-xs text-slate-400 truncate mt-0.5">
                        <span className="text-emerald-400 font-mono">A:</span> {entry.ai_response}
                      </div>
                    </td>
                    <td className="py-3.5 px-4">
                      {renderTierBadge(entry.tier, entry.override)}
                    </td>
                    <td className="py-3.5 px-4 text-right font-mono text-xs font-semibold text-slate-300">
                      {(entry.aggregate_confidence * 100).toFixed(1)}%
                    </td>
                    <td className="py-3.5 px-4 text-center">
                      <button
                        onClick={(e: React.MouseEvent) => {
                          e.stopPropagation();
                          setSelectedEntry(entry);
                        }}
                        className="p-1.5 rounded-lg border border-slate-800 group-hover:border-slate-700 bg-slate-950 group-hover:bg-slate-800 text-slate-400 group-hover:text-slate-200 transition"
                        title="View Full Evaluation Details"
                      >
                        <Eye className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Detailed Modal / Inspection Drawer */}
      {selectedEntry && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-3xl w-full max-h-[90vh] overflow-y-auto shadow-2xl p-6 space-y-6">
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <div>
                <span className="text-xs font-mono text-slate-400">Audit Record: {selectedEntry.id}</span>
                <h3 className="text-lg font-bold text-white mt-0.5">
                  {USE_CASE_LABELS[selectedEntry.use_case_id] || selectedEntry.use_case_id}
                </h3>
              </div>
              <button
                onClick={() => setSelectedEntry(null)}
                className="p-1.5 rounded-lg border border-slate-800 hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Decision Status Banner */}
            <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 flex items-center justify-between">
              <div>
                <span className="text-xs text-slate-400 uppercase tracking-wider font-semibold">Synthesized Decision</span>
                <div className="mt-1.5">{renderTierBadge(selectedEntry.tier, selectedEntry.override)}</div>
              </div>
              <div className="text-right">
                <span className="text-xs text-slate-400 uppercase tracking-wider font-semibold">Aggregate Risk Confidence</span>
                <p className="text-xl font-bold text-slate-100 font-mono mt-1">
                  {(selectedEntry.aggregate_confidence * 100).toFixed(1)}%
                </p>
              </div>
            </div>

            {/* Decision Rationale */}
            <div className="space-y-1.5">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Decision Rationale & Governance Audit</span>
              <p className="text-sm text-slate-200 bg-slate-950/80 border border-slate-800 rounded-lg p-3.5 leading-relaxed">
                {selectedEntry.rationale}
              </p>
            </div>

            {/* Prompt and AI Response */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">User Prompt</span>
                <div className="bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs font-mono text-slate-300 min-h-[80px]">
                  {selectedEntry.prompt}
                </div>
              </div>
              <div className="space-y-1.5">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">AI Response</span>
                <div className="bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs font-mono text-slate-300 min-h-[80px]">
                  {selectedEntry.ai_response}
                </div>
              </div>
            </div>

            {/* Retrieved Context if present */}
            {selectedEntry.retrieved_context && selectedEntry.retrieved_context.length > 0 && (
              <div className="space-y-1.5">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Retrieved Grounding Context</span>
                <div className="bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs font-mono text-slate-400 space-y-1">
                  {selectedEntry.retrieved_context.map((ctx: string, idx: number) => (
                    <p key={idx}>[{idx + 1}] {ctx}</p>
                  ))}
                </div>
              </div>
            )}

            {/* Contributing Detector Signals */}
            <div className="space-y-3">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Active Detector Signals ({selectedEntry.contributing_signals.length})
              </span>
              <div className="space-y-2">
                {selectedEntry.contributing_signals.map((sig: RiskSignal, idx: number) => (
                  <div
                    key={idx}
                    className="bg-slate-950 border border-slate-800/80 rounded-xl p-3.5 flex flex-col gap-2"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <span className="text-xs font-bold text-slate-200 font-mono">{sig.detector_name}</span>
                        {sig.risk_dimensions.map((dim: string) => (
                          <span
                            key={dim}
                            className="px-2 py-0.5 rounded text-[10px] uppercase font-mono bg-indigo-500/10 text-indigo-400 border border-indigo-500/20"
                          >
                            {dim}
                          </span>
                        ))}
                      </div>
                      <div className="flex items-center space-x-3 text-xs font-mono">
                        <span className="text-slate-400">{sig.latency_ms.toFixed(1)}ms</span>
                        <span className={`font-bold ${sig.confidence > 0.6 ? "text-rose-400" : sig.confidence > 0.3 ? "text-yellow-400" : "text-emerald-400"}`}>
                          {(sig.confidence * 100).toFixed(1)}% risk
                        </span>
                      </div>
                    </div>
                    <p className="text-xs text-slate-400 leading-normal">{sig.evidence}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* Human Override Metadata if present */}
            {selectedEntry.override && (
              <div className="bg-indigo-950/30 border border-indigo-500/30 rounded-xl p-4 space-y-2">
                <div className="flex items-center space-x-2 text-indigo-400">
                  <UserCheck className="w-4 h-4" />
                  <span className="text-xs font-bold uppercase tracking-wider">Human Override Applied</span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs text-slate-300">
                  <div><span className="text-slate-500">Reviewer:</span> {selectedEntry.reviewed_by}</div>
                  <div><span className="text-slate-500">Target Tier:</span> {selectedEntry.override_tier?.toUpperCase()}</div>
                </div>
                {selectedEntry.override_notes && (
                  <p className="text-xs text-slate-400 bg-slate-950/60 p-2.5 rounded border border-indigo-500/20">
                    <span className="font-semibold text-slate-300">Auditor Justification:</span> {selectedEntry.override_notes}
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
