#!/usr/bin/env python3
"""
Step4-B Top-1 Candidate Picker (meta-only)
Purpose: Select top-1 candidate from report.tsv based on EVAL_RULES
Output: top1_candidate.json (meta-only: numbers/knob values/status only)
"""
import json
import sys
import csv
from pathlib import Path

def main():
    if len(sys.argv) < 2:
        print("Usage: step4b_pick_top1_candidate.py <report.tsv> [output.json]", file=sys.stderr)
        sys.exit(1)
    
    report_tsv = sys.argv[1]
    output_json = sys.argv[2] if len(sys.argv) > 2 else "/tmp/step4b-top1-candidate.json"
    
    # Required columns (fail-closed if missing)
    REQUIRED_COLS = [
        "timestamp", "strict_rc", "eligible_rc",
        "HIT_MOVED_UP", "HIT_MOVED_DOWN", "HIT_SAME", "HIT_MISSING", "FIRST_HIT_DELTA_SUM"
    ]
    
    if not Path(report_tsv).exists():
        print(f"FAIL: report.tsv not found: {report_tsv}", file=sys.stderr)
        sys.exit(1)
    
    # Read report.tsv
    candidates = []
    with open(report_tsv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        header = reader.fieldnames
        
        # Verify required columns (fail-closed)
        missing_cols = [col for col in REQUIRED_COLS if col not in (header or [])]
        if missing_cols:
            print(f"FAIL: report.tsv missing required columns: {missing_cols}", file=sys.stderr)
            sys.exit(1)
        
        for row in reader:
            # Convert numeric fields
            try:
                strict_rc = int(row.get("strict_rc", "1"))
                eligible_rc = int(row.get("eligible_rc", "1"))
                hit_moved_up = int(row.get("HIT_MOVED_UP", "0"))
                hit_moved_down = int(row.get("HIT_MOVED_DOWN", "0"))
                hit_same = int(row.get("HIT_SAME", "0"))
                hit_missing = int(row.get("HIT_MISSING", "0"))
                first_hit_delta_sum = int(row.get("FIRST_HIT_DELTA_SUM", "0"))
                timestamp = row.get("timestamp", "")
            except (ValueError, KeyError) as e:
                print(f"FAIL: invalid row in report.tsv: {e}", file=sys.stderr)
                sys.exit(1)
            
            candidates.append({
                "timestamp": timestamp,
                "strict_rc": strict_rc,
                "eligible_rc": eligible_rc,
                "HIT_MOVED_UP": hit_moved_up,
                "HIT_MOVED_DOWN": hit_moved_down,
                "HIT_SAME": hit_same,
                "HIT_MISSING": hit_missing,
                "FIRST_HIT_DELTA_SUM": first_hit_delta_sum,
            })
    
    if not candidates:
        # No candidates: status=NO_ELIGIBLE, exit 0 (loop prevention)
        result = {
            "status": "NO_ELIGIBLE",
            "reason": "no_candidates_in_report",
            "timestamp": "",
            "strict_rc": 1,
            "eligible_rc": 1,
            "HIT_MOVED_UP": 0,
            "HIT_MOVED_DOWN": 0,
            "HIT_SAME": 0,
            "HIT_MISSING": 0,
            "FIRST_HIT_DELTA_SUM": 0,
        }
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0)
    
    # EVAL_RULES: Select top-1 candidate
    # Priority:
    # 1) strict_rc=0 AND eligible_rc=0 (strict improvement + eligible PASS)
    # 2) strict_rc=0 (strict improvement only)
    # 3) eligible_rc=0 (eligible PASS only)
    # 4) HIT_MOVED_UP > 0 (hit movement improvement)
    # 5) FIRST_HIT_DELTA_SUM < 0 (negative delta = improvement)
    # 6) Most recent timestamp
    
    def score_candidate(c):
        # Higher score = better candidate
        score = 0
        
        # Priority 1: strict_rc=0 AND eligible_rc=0 (best)
        if c["strict_rc"] == 0 and c["eligible_rc"] == 0:
            score += 10000
        
        # Priority 2: strict_rc=0
        if c["strict_rc"] == 0:
            score += 1000
        
        # Priority 3: eligible_rc=0
        if c["eligible_rc"] == 0:
            score += 100
        
        # Priority 4: HIT_MOVED_UP > 0
        if c["HIT_MOVED_UP"] > 0:
            score += 10
        
        # Priority 5: FIRST_HIT_DELTA_SUM < 0 (negative = improvement)
        if c["FIRST_HIT_DELTA_SUM"] < 0:
            score += 1
        
        # Priority 6: Prefer lower HIT_MOVED_DOWN (less regression)
        score -= c["HIT_MOVED_DOWN"] * 0.1
        
        return score
    
    # Score all candidates
    scored = [(score_candidate(c), c) for c in candidates]
    
    # Sort by score (descending), then by timestamp (descending, most recent first)
    scored.sort(key=lambda x: (-x[0], x[1]["timestamp"]), reverse=False)
    
    # Select top-1
    top1 = scored[0][1] if scored else None
    
    if not top1:
        # No eligible candidate: status=NO_ELIGIBLE, exit 0
        result = {
            "status": "NO_ELIGIBLE",
            "reason": "no_eligible_candidate_after_scoring",
            "timestamp": "",
            "strict_rc": 1,
            "eligible_rc": 1,
            "HIT_MOVED_UP": 0,
            "HIT_MOVED_DOWN": 0,
            "HIT_SAME": 0,
            "HIT_MISSING": 0,
            "FIRST_HIT_DELTA_SUM": 0,
        }
    else:
        # Determine status
        if top1["strict_rc"] == 0 and top1["eligible_rc"] == 0:
            status = "STRICT_ELIGIBLE"
        elif top1["strict_rc"] == 0:
            status = "STRICT_ONLY"
        elif top1["eligible_rc"] == 0:
            status = "ELIGIBLE_ONLY"
        elif top1["HIT_MOVED_UP"] > 0:
            status = "HIT_IMPROVEMENT"
        else:
            status = "BASELINE"
        
        result = {
            "status": status,
            "timestamp": top1["timestamp"],
            "strict_rc": top1["strict_rc"],
            "eligible_rc": top1["eligible_rc"],
            "HIT_MOVED_UP": top1["HIT_MOVED_UP"],
            "HIT_MOVED_DOWN": top1["HIT_MOVED_DOWN"],
            "HIT_SAME": top1["HIT_SAME"],
            "HIT_MISSING": top1["HIT_MISSING"],
            "FIRST_HIT_DELTA_SUM": top1["FIRST_HIT_DELTA_SUM"],
        }
    
    # Write output (meta-only)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0)

if __name__ == "__main__":
    main()

