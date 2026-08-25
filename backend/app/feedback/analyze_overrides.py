#!/usr/bin/env python3
"""CLI utility to analyze accumulated human overrides and report per-detector calibration accuracy."""

import sys
import os

# Ensure project root & backend root are on sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

from app.db import SessionLocal, init_db
from app.feedback.loop import compute_detector_performance


def print_override_analysis(use_case_id: str = None) -> None:
    init_db()
    db = SessionLocal()
    try:
        report = compute_detector_performance(db, use_case_id=use_case_id)
        
        print("\n" + "=" * 80)
        print("  CONTROLPLANE.AI — DETECTOR ACCURACY & HUMAN OVERRIDE REPORT")
        print("=" * 80)
        print(f" Total Overrides Analyzed: {report.total_overrides_recorded}")
        print(f" Analysis Timestamp:       {report.analyzed_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        if use_case_id:
            print(f" Target Use Case Filter:   {use_case_id}")
        print("-" * 80)
        print(
            f"{'Detector Name':<34} | {'Flags':<6} | {'TP':<4} | {'FP':<4} | {'FP Rate':<8} | {'Accuracy':<8} | {'Status'}"
        )
        print("-" * 80)

        for det in report.detectors:
            fp_pct = f"{int(det.false_positive_rate * 100)}%"
            acc_pct = f"{int(det.accuracy_against_human_judgment * 100)}%"
            print(
                f"{det.detector_name:<34} | {det.flagged_count:<6} | {det.true_positive_count:<4} | "
                f"{det.false_positive_count:<4} | {fp_pct:<8} | {acc_pct:<8} | {det.status}"
            )

        print("-" * 80)
        print("\n[!] CALIBRATION & THRESHOLD RECOMMENDATIONS:")
        for det in report.detectors:
            if det.status == "warning_high_fp":
                print(f"  * [ACTION REQUIRED] {det.suggested_threshold_adjustment}")
            elif det.status == "calibrated" and det.total_evaluated_overrides >= 3:
                print(f"  * [OPTIMAL] {det.detector_name}: {det.suggested_threshold_adjustment}")
        
        print("\n[i] Note: Keep humans in the loop. Review recommendations before adjusting YAML policies.\n")
        print("=" * 80 + "\n")

    finally:
        db.close()


if __name__ == "__main__":
    target_uc = sys.argv[1] if len(sys.argv) > 1 else None
    print_override_analysis(use_case_id=target_uc)
