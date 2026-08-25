"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ShieldAlert,
  Sliders,
  Inbox,
  Activity,
  BarChart3,
  CheckCircle2,
  AlertCircle,
  FileCheck2,
} from "lucide-react";

import { API_BASE_URL } from "@/lib/api";

export default function Navbar() {
  const pathname = usePathname();
  const [reviewCount, setReviewCount] = useState<number>(0);
  const [isBackendHealthy, setIsBackendHealthy] = useState<boolean>(true);

  const fetchReviewCount = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/v1/audit?tier=flag_for_review&limit=1`);
      if (res.ok) {
        const data = await res.json();
        setReviewCount(data.total || 0);
        setIsBackendHealthy(true);
      } else {
        setIsBackendHealthy(false);
      }
    } catch (_) {
      setIsBackendHealthy(false);
    }
  };

  useEffect(() => {
    fetchReviewCount();
    const interval = setInterval(fetchReviewCount, 10000);
    return () => clearInterval(interval);
  }, []);

  const navItems = [
    {
      name: "Live Audit Feed",
      href: "/dashboard",
      icon: Activity,
    },
    {
      name: "Policy Profiles",
      href: "/policy",
      icon: Sliders,
    },
    {
      name: "Review Queue",
      href: "/review",
      icon: Inbox,
      badge: reviewCount > 0 ? reviewCount : undefined,
    },
    {
      name: "Governance Metrics",
      href: "/metrics",
      icon: BarChart3,
    },
  ];

  return (
    <header className="border-b border-slate-800/80 bg-slate-950/75 backdrop-blur-md sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Brand Logo & Title */}
          <div className="flex items-center space-x-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 via-indigo-500 to-cyan-400 flex items-center justify-center shadow-lg shadow-indigo-500/20">
              <ShieldAlert className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-bold text-base text-slate-100 tracking-tight">ControlPlane.ai</span>
                <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                  Enterprise RAI
                </span>
              </div>
              <p className="text-[11px] text-slate-400">Responsible AI Guardrails & Audit Middleware</p>
            </div>
          </div>

          {/* Navigation Links */}
          <nav className="flex items-center space-x-1 sm:space-x-2">
            {navItems.map((item) => {
              const isActive = pathname === item.href || (item.href === "/dashboard" && pathname === "/");
              const Icon = item.icon;
              return (
                <Link
                  key={item.name}
                  href={item.href}
                  className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-medium transition ${
                    isActive
                      ? "bg-slate-800 text-white font-semibold shadow-inner border border-slate-700"
                      : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  <span>{item.name}</span>
                  {item.badge !== undefined && (
                    <span className="ml-1 px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-orange-500 text-slate-950 font-mono">
                      {item.badge}
                    </span>
                  )}
                </Link>
              );
            })}
          </nav>

          {/* Backend Status Indicator */}
          <div className="flex items-center space-x-2 text-xs">
            <div
              className={`flex items-center space-x-1.5 px-2.5 py-1 rounded-full border font-mono text-[11px] ${
                isBackendHealthy
                  ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                  : "bg-rose-500/10 text-rose-400 border-rose-500/20"
              }`}
            >
              <div
                className={`w-2 h-2 rounded-full ${
                  isBackendHealthy ? "bg-emerald-400 animate-pulse" : "bg-rose-400"
                }`}
              />
              <span>{isBackendHealthy ? "ENGINE ONLINE" : "ENGINE OFFLINE"}</span>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
