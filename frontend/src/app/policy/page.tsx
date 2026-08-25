"use client";

import React, { useState, useEffect } from "react";
import {
  Sliders,
  ShieldCheck,
  ShieldAlert,
  Clock,
  UserCheck,
  Cpu,
  Layers,
  Info,
  CheckCircle2,
  AlertTriangle,
  Sparkles,
  TrendingUp,
  RefreshCw,
  HelpCircle,
} from "lucide-react";

interface UseCaseProfile {
  id: string;
  name: string;
  channel_type: "customer_facing" | "internal" | "decision_support";
  latency_budget_ms: number;
  risk_tolerance: "low" | "medium" | "high";
  fail_mode: "fail_open" | "fail_closed";
  requires_human_review_above: number;
}

interface DetectorPerformanceStats {
  detector_name: string;
  total_evaluated_overrides: number;
  flagged_count: number;
  true_positive_count: number;
  false_positive_count: number;
  false_negative_count: number;
  false_positive_rate: number;
  accuracy_against_human_judgment: number;
  status: "calibrated" | "warning_high_fp" | "insufficient_data";
  suggested_threshold_adjustment?: string | null;
}

interface FeedbackPerformanceResponse {
  total_overrides_recorded: number;
  analyzed_at: string;
  detectors: DetectorPerformanceStats[];
  global_insights: string[];
}

const STATIC_POLICY_DETAILS: Record<string, {
  purpose: string;
  detectors: { name: string; weight: number; description: string }[];
  bands: { allow: [number, number]; edit: [number, number]; flag: [number, number]; block: [number, number] };
}> = {
  customer_support_bot: {
    purpose: "High-throughput customer service bot optimized for sub-second responses while preventing privacy leaks and brand damage.",
    detectors: [
      { name: "pii_entity_detector", weight: 35, description: "Scans for emails, phone numbers, and customer PII" },
      { name: "retrieval_verification_detector", weight: 30, description: "Verifies grounding against FAQ / Knowledge Base" },
      { name: "bias_heuristic_detector", weight: 25, description: "Prevents demographic stereotyping and offensive slurs" },
      { name: "statistical_anomaly_detector", weight: 10, description: "Detects unexpected domain drift and semantic outliers" },
    ],
    bands: {
      allow: [0.0, 0.30],
      edit: [0.30, 0.55],
      flag: [0.55, 0.75],
      block: [0.75, 1.0],
    },
  },
  wealth_advisor_copilot: {
    purpose: "Fiduciary-grade investment advisor copilot requiring strict ground-truth verification and independent AI-judge validation.",
    detectors: [
      { name: "retrieval_verification_detector", weight: 35, description: "Strict sentence-level grounding against financial prospectus" },
      { name: "ai_judge_detector", weight: 30, description: "Claude-based AI-as-a-Judge evaluating fiduciary compliance" },
      { name: "pii_entity_detector", weight: 20, description: "Guards against account numbers and SSN exposures" },
      { name: "bias_heuristic_detector", weight: 10, description: "Filters lending and demographic bias in wealth advice" },
      { name: "statistical_anomaly_detector", weight: 5, description: "Flags uncharacteristic financial model drift" },
    ],
    bands: {
      allow: [0.0, 0.15],
      edit: [0.15, 0.30],
      flag: [0.30, 0.50],
      block: [0.50, 1.0],
    },
  },
  internal_hr_assistant: {
    purpose: "Internal employee HR benefits and policy copilot prioritizing workplace fairness, inclusivity, and rapid answers.",
    detectors: [
      { name: "retrieval_verification_detector", weight: 35, description: "Verifies claims against official employee handbook" },
      { name: "bias_heuristic_detector", weight: 30, description: "Enforces equal opportunity & anti-bias language" },
      { name: "pii_entity_detector", weight: 25, description: "Protects employee salary & health data" },
      { name: "statistical_anomaly_detector", weight: 10, description: "Monitors internal query distribution shifts" },
    ],
    bands: {
      allow: [0.0, 0.40],
      edit: [0.40, 0.60],
      flag: [0.60, 0.80],
      block: [0.80, 1.0],
    },
  },
};

export default function PolicyPage() {
  const [profiles, setProfiles] = useState<UseCaseProfile[]>([]);
  const [performance, setPerformance] = useState<FeedbackPerformanceResponse | null>(null);
  const [loadingFeedback, setLoadingFeedback] = useState<boolean>(true);

  const apiUrl = (typeof process !== "undefined" && process.env && process.env.NEXT_PUBLIC_API_URL)
    ? process.env.NEXT_PUBLIC_API_URL
    : "http://127.0.0.1:8000";

  useEffect(() => {
    // Fetch active policies
    fetch(`${apiUrl}/v1/use-cases`)
      .then((res: Response) => res.json())
      .then((data: any) => {
        if (Array.isArray(data)) setProfiles(data);
      })
      .catch(() => {});

    // Fetch detector calibration statistics from feedback loop
    fetch(`${apiUrl}/v1/feedback/detector-performance`)
      .then((res: Response) => res.json())
      .then((data: FeedbackPerformanceResponse) => {
        setPerformance(data);
      })
      .catch(() => {})
      .finally(() => setLoadingFeedback(false));
  }, []);

  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-10 flex-1">
      {/* Page Header */}
      <div>
        <div className="flex items-center space-x-2 text-indigo-400 font-mono text-xs uppercase tracking-wider mb-1">
          <Sliders className="w-4 h-4" />
          <span>Governance & Policy Engine</span>
        </div>
        <h1 className="text-2xl font-bold text-slate-100 tracking-tight">Active Policy Profiles</h1>
        <p className="text-sm text-slate-400 mt-1 max-w-3xl">
          Declarative safety policies configured per enterprise deployment channel. These human-readable cards document
          latency budgets, fault-tolerance modes, detector weighting, and tier decision bands.
        </p>
      </div>

      {/* 3 Use Case Policy Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {Object.entries(STATIC_POLICY_DETAILS).map(([useCaseId, details]) => {
          const profile = profiles.find((p: UseCaseProfile) => p.id === useCaseId) || {
            id: useCaseId,
            name: useCaseId.replace(/_/g, " ").toUpperCase(),
            channel_type: "customer_facing" as const,
            latency_budget_ms: 350,
            risk_tolerance: "medium" as const,
            fail_mode: "fail_closed" as const,
            requires_human_review_above: 0.65,
          };

          return (
            <div
              key={useCaseId}
              className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col justify-between space-y-6 hover:border-slate-700 transition"
            >
              {/* Card Header */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 uppercase">
                    {profile.channel_type}
                  </span>
                  <span className={`text-xs px-2 py-0.5 rounded font-mono font-semibold ${
                    profile.fail_mode === "fail_closed"
                      ? "bg-rose-500/10 text-rose-300 border border-rose-500/20"
                      : "bg-emerald-500/10 text-emerald-300 border border-emerald-500/20"
                  }`}>
                    {profile.fail_mode === "fail_closed" ? "FAIL-CLOSED" : "FAIL-OPEN"}
                  </span>
                </div>

                <div>
                  <h3 className="text-lg font-bold text-white tracking-tight">{profile.name}</h3>
                  <p className="text-xs text-slate-400 mt-1 leading-relaxed">{details.purpose}</p>
                </div>
              </div>

              {/* Core Parameters */}
              <div className="grid grid-cols-2 gap-3 py-3 border-y border-slate-800/80 text-xs">
                <div className="space-y-0.5">
                  <span className="text-slate-500 flex items-center gap-1 font-mono">
                    <Clock className="w-3.5 h-3.5 text-slate-400" /> Latency Budget:
                  </span>
                  <span className="font-mono font-bold text-slate-200">{profile.latency_budget_ms} ms</span>
                </div>
                <div className="space-y-0.5">
                  <span className="text-slate-500 flex items-center gap-1 font-mono">
                    <UserCheck className="w-3.5 h-3.5 text-slate-400" /> Review Trigger:
                  </span>
                  <span className="font-mono font-bold text-amber-400">&gt; {(profile.requires_human_review_above * 100).toFixed(0)}% Risk</span>
                </div>
              </div>

              {/* Threshold Bands Spectrum Visualizer */}
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-slate-300">Decision Tier Bands</span>
                  <span className="text-[11px] text-slate-500 font-mono">0.0 ➔ 1.0</span>
                </div>

                {/* Progress bar visualizer */}
                <div className="h-3 w-full bg-slate-950 rounded-full overflow-hidden flex border border-slate-800">
                  <div
                    style={{ width: `${details.bands.allow[1] * 100}%` }}
                    className="bg-emerald-500 hover:opacity-80 transition"
                    title={`ALLOW: 0.0 - ${details.bands.allow[1]}`}
                  />
                  <div
                    style={{ width: `${(details.bands.edit[1] - details.bands.edit[0]) * 100}%` }}
                    className="bg-yellow-500 hover:opacity-80 transition"
                    title={`EDIT: ${details.bands.edit[0]} - ${details.bands.edit[1]}`}
                  />
                  <div
                    style={{ width: `${(details.bands.flag[1] - details.bands.flag[0]) * 100}%` }}
                    className="bg-orange-500 hover:opacity-80 transition"
                    title={`FLAG: ${details.bands.flag[0]} - ${details.bands.flag[1]}`}
                  />
                  <div
                    style={{ width: `${(1.0 - details.bands.block[0]) * 100}%` }}
                    className="bg-rose-500 hover:opacity-80 transition"
                    title={`BLOCK: ${details.bands.block[0]} - 1.0`}
                  />
                </div>

                {/* Legend */}
                <div className="grid grid-cols-4 gap-1 text-[10px] font-mono text-center pt-1 text-slate-400">
                  <div>
                    <span className="text-emerald-400 font-semibold">ALLOW</span>
                    <p>&lt; {details.bands.allow[1]}</p>
                  </div>
                  <div>
                    <span className="text-yellow-400 font-semibold">EDIT</span>
                    <p>&lt; {details.bands.edit[1]}</p>
                  </div>
                  <div>
                    <span className="text-orange-400 font-semibold">FLAG</span>
                    <p>&lt; {details.bands.flag[1]}</p>
                  </div>
                  <div>
                    <span className="text-rose-400 font-semibold">BLOCK</span>
                    <p>&ge; {details.bands.block[0]}</p>
                  </div>
                </div>
              </div>

              {/* Enabled Detectors and Weights */}
              <div className="space-y-2">
                <span className="text-xs font-semibold text-slate-300">Enabled Detectors & Weights</span>
                <div className="space-y-1.5">
                  {details.detectors.map((det: { name: string; weight: number; description: string }) => (
                    <div
                      key={det.name}
                      className="bg-slate-950/80 border border-slate-800/80 rounded-lg p-2 text-xs flex items-center justify-between"
                    >
                      <div className="truncate pr-2">
                        <span className="font-mono text-slate-300 font-medium block truncate">{det.name}</span>
                        <span className="text-[11px] text-slate-500 truncate block">{det.description}</span>
                      </div>
                      <span className="font-mono font-bold text-indigo-400 text-xs px-2 py-0.5 bg-indigo-500/10 rounded border border-indigo-500/20">
                        {det.weight}%
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Fail Mode Info Note */}
              <div className="bg-slate-950 border border-slate-800/80 rounded-xl p-3 text-[11px] text-slate-400 space-y-1">
                <span className="font-semibold text-slate-300 flex items-center gap-1">
                  <Info className="w-3.5 h-3.5 text-indigo-400" /> Fault-Tolerance Behavior
                </span>
                <p>
                  {profile.fail_mode === "fail_closed"
                    ? "If any detector times out or errors, pipeline treats the interaction as maximum risk (1.0) to prevent unverified data exposure."
                    : "If a detector times out, it is omitted from weighted scoring and logged in the audit rationale without blocking the response."}
                </p>
              </div>
            </div>
          );
        })}
      </div>

      {/* FEEDBACK LOOP & CALIBRATION SECTION */}
      <div className="space-y-6 pt-4 border-t border-slate-800">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center space-x-2 text-indigo-400 font-mono text-xs uppercase tracking-wider mb-1">
              <TrendingUp className="w-4 h-4" />
              <span>Feedback Loop & Calibration Engine</span>
            </div>
            <h2 className="text-xl font-bold text-slate-100 tracking-tight">
              Empirical Detector Accuracy & Threshold Calibration
            </h2>
            <p className="text-xs text-slate-400 mt-1 max-w-3xl">
              Computed from cumulative human auditor overrides in the review queue. Detectors with elevated false-positive
              rates surface suggested threshold and weight adjustments.
            </p>
          </div>

          <div className="text-right">
            <span className="text-xs text-slate-500 font-mono">
              Total Overrides Analyzed: <strong className="text-indigo-400">{performance?.total_overrides_recorded || 0}</strong>
            </span>
          </div>
        </div>

        {/* Human in the Loop Advisory Callout */}
        <div className="bg-indigo-950/30 border border-indigo-500/20 rounded-xl p-4 flex items-start gap-3 text-xs text-indigo-200">
          <UserCheck className="w-5 h-5 text-indigo-400 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <span className="font-semibold text-white block">
              Human-in-the-Loop Governance Notice
            </span>
            <p className="leading-relaxed text-indigo-300/90">
              The feedback engine produces empirical recommendations based on human override patterns, but <strong>does not auto-apply threshold mutations</strong>. A qualified compliance lead or prompt engineer must review these empirical insights and update declarative YAML policy configs intentionally.
            </p>
          </div>
        </div>

        {/* Detector Performance Table / Cards */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-slate-800 bg-slate-950/70 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                  <th className="py-3 px-4">Detector Name</th>
                  <th className="py-3 px-4 text-center">Flags</th>
                  <th className="py-3 px-4 text-center">True Positives</th>
                  <th className="py-3 px-4 text-center">False Positives</th>
                  <th className="py-3 px-4 text-right">FP Rate</th>
                  <th className="py-3 px-4 text-right">Human Alignment</th>
                  <th className="py-3 px-4">Status & Suggested Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono">
                {loadingFeedback ? (
                  <tr>
                    <td colSpan={7} className="py-8 text-center text-slate-400 font-sans">
                      <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-indigo-400" />
                      Computing calibration metrics from override log...
                    </td>
                  </tr>
                ) : !performance || performance.detectors.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-8 text-center text-slate-400 font-sans">
                      No override records found yet. Perform reviews in the queue to generate calibration statistics.
                    </td>
                  </tr>
                ) : (
                  performance.detectors.map((det: DetectorPerformanceStats) => {
                    const isWarning = det.status === "warning_high_fp";
                    const isCalibrated = det.status === "calibrated";

                    return (
                      <tr key={det.detector_name} className="hover:bg-slate-850/50 transition-colors">
                        <td className="py-3 px-4 font-semibold text-slate-200">{det.detector_name}</td>
                        <td className="py-3 px-4 text-center text-slate-400">{det.flagged_count}</td>
                        <td className="py-3 px-4 text-center text-emerald-400">{det.true_positive_count}</td>
                        <td className="py-3 px-4 text-center text-rose-400">{det.false_positive_count}</td>
                        <td className={`py-3 px-4 text-right font-bold ${
                          isWarning ? "text-amber-400" : "text-slate-300"
                        }`}>
                          {(det.false_positive_rate * 100).toFixed(0)}%
                        </td>
                        <td className="py-3 px-4 text-right text-indigo-400 font-bold">
                          {(det.accuracy_against_human_judgment * 100).toFixed(0)}%
                        </td>
                        <td className="py-3 px-4 font-sans max-w-sm">
                          {isWarning ? (
                            <div className="flex items-start gap-1.5 text-amber-300 bg-amber-500/10 border border-amber-500/20 p-2 rounded-lg text-[11px]">
                              <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                              <span>{det.suggested_threshold_adjustment}</span>
                            </div>
                          ) : isCalibrated ? (
                            <div className="flex items-center gap-1.5 text-emerald-300 text-[11px]">
                              <CheckCircle2 className="w-3.5 h-3.5 shrink-0 text-emerald-400" />
                              <span>{det.suggested_threshold_adjustment}</span>
                            </div>
                          ) : (
                            <span className="text-slate-500 text-[11px] italic">
                              {det.suggested_threshold_adjustment}
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
