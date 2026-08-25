"use client";

import React, { useState, useEffect } from "react";
import {
  BarChart3,
  TrendingUp,
  ShieldCheck,
  ShieldAlert,
  AlertTriangle,
  Clock,
  UserCheck,
  Activity,
  RefreshCw,
  Info,
  CheckCircle2,
  Layers,
  ArrowUpRight,
} from "lucide-react";

interface TierBreakdown {
  allow: number;
  edit: number;
  flag_for_review: number;
  block: number;
  total: number;
}

interface UseCaseMetricSummary {
  use_case_id: string;
  use_case_name: string;
  channel_type: string;
  latency_budget_ms: number;
  avg_latency_ms: number;
  latency_budget_compliance_pct: number;
  tier_counts: TierBreakdown;
  total_evaluations: number;
  overrides_count: number;
}

interface DetectorLatencyMetric {
  detector_name: string;
  avg_latency_ms: number;
  p95_latency_ms: number;
  sample_count: number;
}

interface EstimatedErrorRates {
  sample_size_human_reviews: number;
  estimated_false_positive_rate: number;
  estimated_false_negative_rate: number;
  disclaimer: string;
}

interface TimeSeriesPoint {
  timestamp: string;
  formatted_time: string;
  use_case_id: string;
  allow: number;
  edit: number;
  flag_for_review: number;
  block: number;
  total: number;
}

interface GovernanceMetricsResponse {
  generated_at: string;
  total_evaluations: number;
  total_overrides: number;
  use_cases: UseCaseMetricSummary[];
  overall_tier_breakdown: TierBreakdown;
  detector_latencies: DetectorLatencyMetric[];
  error_estimates: EstimatedErrorRates;
  trustworthiness_narrative: string;
  time_series_history: TimeSeriesPoint[];
}

export default function MetricsPage() {
  const [metrics, setMetrics] = useState<GovernanceMetricsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedUseCaseFilter, setSelectedUseCaseFilter] = useState<string>("all");

  const apiUrl = (typeof process !== "undefined" && process.env && process.env.NEXT_PUBLIC_API_URL)
    ? process.env.NEXT_PUBLIC_API_URL
    : "http://127.0.0.1:8000";

  const fetchMetrics = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${apiUrl}/v1/metrics/summary?hours=24`);
      if (res.ok) {
        const data = await res.json();
        setMetrics(data);
      }
    } catch (_) {
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMetrics();
  }, []);

  // Filter time series points
  const timePoints: TimeSeriesPoint[] = metrics?.time_series_history || [];
  const rawTimes = timePoints.map((p: TimeSeriesPoint) => p.formatted_time);
  const uniqueTimes: string[] = Array.from(new Set(rawTimes));

  // Aggregate by time point based on filter
  const chartData = uniqueTimes.map((timeStr: string) => {
    const matching = timePoints.filter((p: TimeSeriesPoint) => {
      const matchTime = p.formatted_time === timeStr;
      const matchUC = selectedUseCaseFilter === "all" || p.use_case_id === selectedUseCaseFilter;
      return matchTime && matchUC;
    });

    const allow = matching.reduce((acc: number, p: TimeSeriesPoint) => acc + p.allow, 0);
    const edit = matching.reduce((acc: number, p: TimeSeriesPoint) => acc + p.edit, 0);
    const flag = matching.reduce((acc: number, p: TimeSeriesPoint) => acc + p.flag_for_review, 0);
    const block = matching.reduce((acc: number, p: TimeSeriesPoint) => acc + p.block, 0);
    const total = allow + edit + flag + block;

    return {
      time: timeStr,
      allow,
      edit,
      flag,
      block,
      total,
    };
  });

  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-10 flex-1">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2 text-indigo-400 font-mono text-xs uppercase tracking-wider mb-1">
            <BarChart3 className="w-4 h-4" />
            <span>Operational Telemetry & Safety Auditing</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-100 tracking-tight">Governance & Safety Metrics</h1>
          <p className="text-sm text-slate-400 mt-1">
            System trustworthiness briefing, decision tier distributions over time, latency budgets, and human-bounded error rates.
          </p>
        </div>

        <button
          onClick={fetchMetrics}
          disabled={loading}
          className="self-start sm:self-auto flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-200 text-sm font-medium transition"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} /> Refresh Metrics
        </button>
      </div>

      {/* EXECUTIVE TRUSTWORTHINESS BRIEFING CARD */}
      <div className="bg-gradient-to-br from-indigo-950/40 via-slate-900/90 to-slate-950 border border-indigo-500/30 rounded-2xl p-6 sm:p-8 shadow-2xl space-y-4">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center space-x-2.5">
            <div className="w-8 h-8 rounded-lg bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 flex items-center justify-center">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <h2 className="text-base font-bold text-white tracking-tight">
              Executive System Trustworthiness Briefing
            </h2>
          </div>
          <span className="text-[11px] font-mono px-2.5 py-1 rounded bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
            AUDIT VERIFIED
          </span>
        </div>

        <p className="text-sm sm:text-base text-slate-200 leading-relaxed font-normal">
          {metrics?.trustworthiness_narrative || "Loading executive briefing..."}
        </p>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-4 border-t border-slate-800/80 text-xs">
          <div>
            <span className="text-slate-500 block">Total Evaluations</span>
            <span className="text-lg font-bold text-white font-mono">{metrics?.total_evaluations || 0}</span>
          </div>
          <div>
            <span className="text-slate-500 block">Human Reviews</span>
            <span className="text-lg font-bold text-indigo-400 font-mono">{metrics?.total_overrides || 0}</span>
          </div>
          <div>
            <span className="text-slate-500 block">Est. False-Positive Rate</span>
            <span className="text-lg font-bold text-amber-400 font-mono">
              {((metrics?.error_estimates.estimated_false_positive_rate || 0) * 100).toFixed(0)}%
            </span>
          </div>
          <div>
            <span className="text-slate-500 block">Est. False-Negative Rate</span>
            <span className="text-lg font-bold text-rose-400 font-mono">
              {((metrics?.error_estimates.estimated_false_negative_rate || 0) * 100).toFixed(0)}%
            </span>
          </div>
        </div>
      </div>

      {/* TIME SERIES DECISION VOLUME & TIER MIX */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
          <div>
            <h3 className="text-base font-bold text-white tracking-tight">Decision Volume & Tier Mix Over Time</h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Hourly interaction volume segmented by ALLOW, EDIT, FLAG, and BLOCK decisions.
            </p>
          </div>

          <div className="flex items-center space-x-2">
            <span className="text-xs text-slate-400 font-medium">Channel:</span>
            <select
              value={selectedUseCaseFilter}
              onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setSelectedUseCaseFilter(e.target.value)}
              className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
            >
              <option value="all">All Channels Combined</option>
              <option value="customer_support_bot">Customer Support Assistant</option>
              <option value="wealth_advisor_copilot">Wealth Advisory Copilot</option>
              <option value="internal_hr_assistant">Internal HR Assistant</option>
            </select>
          </div>
        </div>

        {/* Legend */}
        <div className="flex flex-wrap items-center justify-center gap-6 text-xs font-mono">
          <div className="flex items-center space-x-1.5">
            <span className="w-3 h-3 rounded-sm bg-emerald-500" />
            <span className="text-slate-300">ALLOW</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-3 h-3 rounded-sm bg-yellow-500" />
            <span className="text-slate-300">EDIT</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-3 h-3 rounded-sm bg-orange-500" />
            <span className="text-slate-300">FLAG FOR REVIEW</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-3 h-3 rounded-sm bg-rose-500" />
            <span className="text-slate-300">BLOCK</span>
          </div>
        </div>

        {/* Bar / Stack Visualizer */}
        <div className="space-y-3 pt-2">
          {chartData.map((d: { time: string; allow: number; edit: number; flag: number; block: number; total: number }, idx: number) => {
            const hasData = d.total > 0;
            return (
              <div key={idx} className="space-y-1">
                <div className="flex items-center justify-between text-xs font-mono text-slate-400">
                  <span>{d.time} UTC</span>
                  <span>{d.total} evaluations</span>
                </div>

                <div className="h-6 w-full bg-slate-950 rounded-lg overflow-hidden flex border border-slate-800/80">
                  {hasData ? (
                    <>
                      <div
                        style={{ width: `${(d.allow / d.total) * 100}%` }}
                        className="bg-emerald-500 transition-all hover:opacity-90"
                        title={`ALLOW: ${d.allow}`}
                      />
                      <div
                        style={{ width: `${(d.edit / d.total) * 100}%` }}
                        className="bg-yellow-500 transition-all hover:opacity-90"
                        title={`EDIT: ${d.edit}`}
                      />
                      <div
                        style={{ width: `${(d.flag / d.total) * 100}%` }}
                        className="bg-orange-500 transition-all hover:opacity-90"
                        title={`FLAG: ${d.flag}`}
                      />
                      <div
                        style={{ width: `${(d.block / d.total) * 100}%` }}
                        className="bg-rose-500 transition-all hover:opacity-90"
                        title={`BLOCK: ${d.block}`}
                      />
                    </>
                  ) : (
                    <div className="w-full flex items-center justify-center text-[10px] text-slate-600 font-mono">
                      No traffic in this interval
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* USE CASE METRICS GRID */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {metrics?.use_cases.map((uc: UseCaseMetricSummary) => {
          const allowPct = uc.total_evaluations > 0 ? (uc.tier_counts.allow / uc.total_evaluations) * 100 : 0;
          const editPct = uc.total_evaluations > 0 ? (uc.tier_counts.edit / uc.total_evaluations) * 100 : 0;
          const flagPct = uc.total_evaluations > 0 ? (uc.tier_counts.flag_for_review / uc.total_evaluations) * 100 : 0;
          const blockPct = uc.total_evaluations > 0 ? (uc.tier_counts.block / uc.total_evaluations) * 100 : 0;

          return (
            <div
              key={uc.use_case_id}
              className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-xl space-y-4 flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center justify-between text-xs text-indigo-400 font-mono mb-1">
                  <span className="uppercase">{uc.channel_type}</span>
                  <span>{uc.total_evaluations} calls</span>
                </div>
                <h4 className="text-base font-bold text-white tracking-tight">{uc.use_case_name}</h4>
              </div>

              {/* Latency Compliance */}
              <div className="bg-slate-950 p-3 rounded-xl border border-slate-800/80 text-xs space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-slate-400 flex items-center gap-1 font-mono">
                    <Clock className="w-3.5 h-3.5 text-slate-400" /> Latency Budget:
                  </span>
                  <span className="font-mono font-semibold text-slate-200">
                    {uc.avg_latency_ms}ms / {uc.latency_budget_ms}ms
                  </span>
                </div>
                <div className="h-1.5 w-full bg-slate-900 rounded-full overflow-hidden">
                  <div
                    style={{ width: `${Math.min(uc.latency_budget_compliance_pct, 100)}%` }}
                    className="h-full bg-emerald-500 rounded-full"
                  />
                </div>
                <span className="text-[10px] text-slate-500 font-mono block text-right">
                  {uc.latency_budget_compliance_pct.toFixed(0)}% within SLA budget
                </span>
              </div>

              {/* Tier Mix Progress Breakdown */}
              <div className="space-y-2 text-xs">
                <span className="font-semibold text-slate-300 block">Tier Mix Distribution</span>
                <div className="space-y-1 text-[11px] font-mono">
                  <div className="flex items-center justify-between text-emerald-400">
                    <span>ALLOW: {uc.tier_counts.allow}</span>
                    <span>{allowPct.toFixed(0)}%</span>
                  </div>
                  <div className="flex items-center justify-between text-yellow-400">
                    <span>EDIT: {uc.tier_counts.edit}</span>
                    <span>{editPct.toFixed(0)}%</span>
                  </div>
                  <div className="flex items-center justify-between text-orange-400">
                    <span>FLAG: {uc.tier_counts.flag_for_review}</span>
                    <span>{flagPct.toFixed(0)}%</span>
                  </div>
                  <div className="flex items-center justify-between text-rose-400">
                    <span>BLOCK: {uc.tier_counts.block}</span>
                    <span>{blockPct.toFixed(0)}%</span>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* DETECTOR LATENCIES & EMPIRICAL ERROR DISCLAIMER */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Detector Latencies */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
          <div className="flex items-center space-x-2">
            <Clock className="w-5 h-5 text-indigo-400" />
            <h3 className="text-base font-bold text-white">Detector Latency Telemetry</h3>
          </div>
          <p className="text-xs text-slate-400">
            Average and 95th percentile execution durations per risk detector across evaluated traffic.
          </p>

          <div className="space-y-2 pt-1 font-mono text-xs">
            {metrics?.detector_latencies.map((det: DetectorLatencyMetric) => (
              <div
                key={det.detector_name}
                className="bg-slate-950 border border-slate-800/80 rounded-xl p-3 flex items-center justify-between"
              >
                <div>
                  <span className="font-semibold text-slate-200 block">{det.detector_name}</span>
                  <span className="text-[11px] text-slate-500 font-sans">{det.sample_count} evaluations</span>
                </div>
                <div className="text-right">
                  <span className="text-indigo-300 font-bold block">{det.avg_latency_ms} ms avg</span>
                  <span className="text-[11px] text-slate-400">p95: {det.p95_latency_ms} ms</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Bounded Error Rates Disclaimer Box */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4 flex flex-col justify-between">
          <div className="space-y-3">
            <div className="flex items-center space-x-2 text-amber-400">
              <AlertTriangle className="w-5 h-5" />
              <h3 className="text-base font-bold text-white">Human Review Sample Bounding</h3>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              {metrics?.error_estimates.disclaimer}
            </p>
          </div>

          <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 space-y-3 text-xs">
            <span className="font-semibold text-slate-300 uppercase tracking-wider block text-[11px]">
              Empirical Methodology
            </span>
            <ul className="space-y-2 text-slate-400 list-disc list-inside">
              <li>
                <strong>Estimated FP Rate:</strong> Ratio of flagged/blocked interactions overturned to ALLOW by compliance auditors.
              </li>
              <li>
                <strong>Estimated FN Rate:</strong> Ratio of allowed interactions subsequently reported and overridden to BLOCK.
              </li>
              <li>
                <strong>Uncertainty Bound:</strong> As human auditor sample size (N) expands over time, statistical confidence bounds narrow.
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
