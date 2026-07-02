"""
verify_results.py — Verify your ranking before submission
Run this to confirm your ranker is working correctly.

Usage:
    python verify_results.py
"""

import json
import csv
from pathlib import Path
from collections import Counter

SUBMISSION = Path("output/submission.csv")
CANDIDATES = Path("data/candidates.jsonl")

# ── Load submission CSV ────────────────────────────────────────────────
print("\n" + "="*60)
print("  REDROB RANKER — RESULT VERIFICATION")
print("="*60)

rows = []
with open(SUBMISSION, encoding="utf-8") as f:
    for row in csv.DictReader(f):
        rows.append(row)

print(f"\n✅ Submission file found: {len(rows)} candidates ranked\n")

# ── Score distribution ─────────────────────────────────────────────────
scores = [float(r["score"]) for r in rows]
print("── Score Distribution ───────────────────────────────────────")
print(f"   Highest score : {max(scores):.4f}  (Rank #1)")
print(f"   Lowest score  : {min(scores):.4f}  (Rank #100)")
print(f"   Average score : {sum(scores)/len(scores):.4f}")

# Check scores are non-increasing
bad_order = sum(1 for i in range(1, len(rows)) if float(rows[i]["score"]) > float(rows[i-1]["score"]))
if bad_order == 0:
    print(f"   Score order   : ✅ Correctly non-increasing (rank 1 → 100)")
else:
    print(f"   Score order   : ❌ {bad_order} scores out of order — problem!")

# ── Top 20 candidates ─────────────────────────────────────────────────
print("\n── Top 20 Ranked Candidates ─────────────────────────────────")
print(f"{'Rank':<6} {'Candidate ID':<16} {'Score':<8} {'Reasoning (first 70 chars)'}")
print("-"*60)
for r in rows[:20]:
    print(f"  #{r['rank']:<4} {r['candidate_id']:<16} {float(r['score']):.4f}  {r['reasoning'][:70]}")

# ── Load candidate details for top 10 ─────────────────────────────────
print("\n── Detailed Profile Check: Top 10 ──────────────────────────")
top_ids = {r["candidate_id"]: int(r["rank"]) for r in rows[:10]}
found = {}
with open(CANDIDATES, encoding="utf-8") as f:
    for line in f:
        c = json.loads(line.strip())
        if c["candidate_id"] in top_ids:
            found[c["candidate_id"]] = c
        if len(found) == len(top_ids):
            break

for r in rows[:10]:
    cid = r["candidate_id"]
    c = found.get(cid)
    if not c:
        continue
    p = c.get("profile", {})
    skills = c.get("skills", [])
    top_skills = ", ".join(s["name"] for s in sorted(skills, key=lambda x: x.get("endorsements",0), reverse=True)[:5])
    sig = c.get("redrob_signals", {}) or {}
    print(f"\n  Rank #{r['rank']} — {cid}")
    print(f"  Title      : {p.get('current_title')} @ {p.get('current_company')}")
    print(f"  Experience : {p.get('years_of_experience')} years")
    print(f"  Location   : {p.get('location')}")
    print(f"  Top Skills : {top_skills}")
    print(f"  Open2Work  : {sig.get('open_to_work_flag')}  |  Last active: {sig.get('last_active_date')}  |  Response rate: {sig.get('recruiter_response_rate')}")
    print(f"  Score      : {r['score']}")

# ── Trap / disqualifier check ──────────────────────────────────────────
print("\n── Trap Detection Checks ────────────────────────────────────")

# Check: are any off-target titles (Marketing, HR, etc.) in top 100?
off_target = ["marketing", "hr manager", "accountant", "sales", "content writer",
              "civil engineer", "mechanical engineer", "customer support"]
trap_ids = {}
with open(CANDIDATES, encoding="utf-8") as f:
    top100_ids = {r["candidate_id"] for r in rows}
    for line in f:
        c = json.loads(line.strip())
        if c["candidate_id"] in top100_ids:
            title = c["profile"].get("current_title", "").lower()
            if any(t in title for t in off_target):
                rank = next(r["rank"] for r in rows if r["candidate_id"] == c["candidate_id"])
                trap_ids[c["candidate_id"]] = (rank, c["profile"]["current_title"])

if trap_ids:
    print(f"  ❌ WARNING: {len(trap_ids)} off-target title(s) found in top 100:")
    for cid, (rank, title) in trap_ids.items():
        print(f"     Rank #{rank} — {cid} — {title}")
else:
    print(f"  ✅ No off-target titles (Marketing/HR/Sales etc.) in top 100")

# Check: score tie-break ordering (equal scores must be ascending candidate_id)
tie_errors = 0
for i in range(1, len(rows)):
    if rows[i]["score"] == rows[i-1]["score"]:
        if rows[i]["candidate_id"] < rows[i-1]["candidate_id"]:
            tie_errors += 1
if tie_errors == 0:
    print(f"  ✅ Tie-break ordering correct (ascending candidate_id at equal scores)")
else:
    print(f"  ❌ {tie_errors} tie-break ordering error(s) — re-run rank.py to fix")

# ── Final verdict ──────────────────────────────────────────────────────
print("\n── Final Verdict ────────────────────────────────────────────")
if bad_order == 0 and not trap_ids and tie_errors == 0:
    print("  ✅ ALL CHECKS PASSED — your submission.csv looks correct!")
    print("  📁 Submit this file: output/submission.csv")
else:
    print("  ⚠️  Some checks failed — review the warnings above before submitting.")

print("\n" + "="*60 + "\n")
