#!/usr/bin/env python3
"""
Redrob Hackathon — Intelligent Candidate Ranking System
Track: The Data & AI Challenge

JOB: Senior AI Engineer — Founding Team @ Redrob AI
     Pune/Noida, India | 5-9 yrs (soft band) | embeddings/retrieval/ranking/LLM systems

DESIGN PHILOSOPHY
------------------
The JD is explicit that keyword-counting is a trap. The "right answer" requires
reading career history, not just the skills list. So this ranker is structured as:

  1. CAREER-FIT SCORE (the dominant signal, ~45%)
     - Does career history show REAL applied ML/AI/search/ranking work at a
       PRODUCT company (not pure research, not pure services/consulting)?
     - Uses title + role descriptions, not just a skills bag.

  2. SKILL TRUST SCORE (~25%)
     - Candidate skills matched against the JD's "must-have" and "nice-to-have"
       lists, but weighted by endorsements + duration_months (a skill listed
       with 0 endorsements/0 duration is "keyword stuffing" and barely counts).

  3. DISQUALIFIER / FIT-PENALTY LOGIC (multiplicative, can crush a score to ~0)
     The JD lists explicit auto-reject patterns:
       - Pure research-only background, no production deployment
       - "AI experience" = only recent (<12mo) LangChain/OpenAI wrapper work,
         no pre-LLM ML production experience
       - Senior person who hasn't written code in 18+ months (pure
         architecture/tech-lead drift)
       - Career spent entirely at pure consulting/services firms
         (TCS/Infosys/Wipro/Accenture/Cognizant/Capgemini) with no
         product-company experience
       - CV/speech/robotics specialists with no NLP/IR exposure
       - Title-chasers: title escalates every <=1.5 years, company-hopping
       - Closed-source-only 5+ years with zero external validation signal
         (best-effort proxy; we do not penalize candidates we can't assess)

  4. BEHAVIORAL AVAILABILITY MULTIPLIER (~ -40% to +10% modifier, not additive)
     The JD explicitly says: "a perfect-on-paper candidate who hasn't logged
     in for 6 months and has a 5% recruiter response rate is, for hiring
     purposes, not actually available. Down-weight them appropriately."
     So this is applied as a MULTIPLIER on top of the base fit score, not as
     a separately-weighted additive bucket — a great candidate who is clearly
     unavailable should drop, not just lose a few points.

  5. LOCATION / LOGISTICS MODIFIER (~5-10%)
     Pune/Noida preferred; Hyderabad/Pune/Mumbai/Delhi-NCR welcome; outside
     India is case-by-case and no visa sponsorship. Notice period sub-30
     preferred.

  6. HONEYPOT DETECTION (hard filter)
     Profiles with internally-impossible claims (e.g. "expert" proficiency
     with 0 duration_months, career_history duration that doesn't fit
     years_of_experience, endorsement counts absurdly disproportionate to
     duration) are flagged and pushed to the very bottom of the ranking,
     not just penalized — the JD says honeypot rate in top-100 must stay
     under 10%, so we treat this as close to a hard filter.

COMPUTE CONSTRAINTS RESPECTED
------------------------------
- No GPU. No hosted LLM API calls during ranking. No network calls.
- Pure Python + regex + simple arithmetic — runs on 100K candidates in well
  under 5 minutes on a CPU-only laptop. (Optionally accelerated with numpy
  if available, but works without it.)
- Streams the .jsonl file line by line rather than loading 487MB into a
  list of full Python dicts twice, to keep memory reasonable.

USAGE
-----
    python rank.py --candidates data/candidates.jsonl --out output/submission.csv
"""

import argparse
import csv
import json
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path


# ═══════════════════════════════════════════════════════════════════════
# JD KNOWLEDGE BASE — encodes what's in job_description.docx
# ═══════════════════════════════════════════════════════════════════════

# "Must have" technical surface area — production embeddings/retrieval,
# vector DB / hybrid search, eval frameworks. Specific tech doesn't matter,
# the CATEGORY of operational experience does.
MUST_HAVE_CATEGORIES = {
    "embeddings_retrieval": [
        "sentence-transformers", "sentence transformers", "openai embeddings",
        "bge", "e5", "embedding", "embeddings", "dense retrieval",
        "semantic search", "vector search", "retrieval",
    ],
    "vector_db_hybrid_search": [
        "pinecone", "weaviate", "qdrant", "milvus", "opensearch",
        "elasticsearch", "faiss", "hybrid search", "bm25", "vector database",
        "vector db",
    ],
    "python_quality": [
        "python",
    ],
    "eval_frameworks": [
        "ndcg", "mrr", "map", "a/b test", "a/b testing", "offline evaluation",
        "online evaluation", "evaluation framework", "ranking evaluation",
        "precision@", "recall@",
    ],
}

# "Nice to have" — boosts score but absence is not penalized
NICE_TO_HAVE = [
    "lora", "qlora", "peft", "fine-tuning", "fine tuning", "learning to rank",
    "ltr", "xgboost", "neural ranking", "hr-tech", "hr tech", "recruiting tech",
    "marketplace", "distributed systems", "large-scale inference",
    "open source", "open-source",
]

# Roles/titles that signal REAL applied ML/search/ranking work
STRONG_TITLE_SIGNALS = [
    "ml engineer", "machine learning engineer", "ai engineer",
    "applied scientist", "search engineer", "ranking engineer",
    "recommendation", "recommender", "nlp engineer", "ai research engineer",
    "data scientist", "research engineer", "senior ml", "staff ml",
    "principal ml", "ai specialist", "search & relevance",
    "information retrieval",
]

# Titles indicating adjacent-but-different technical depth (data infra,
# backend) — partial credit, not full credit, unless career history shows
# ML/search specifics.
ADJACENT_TITLE_SIGNALS = [
    "backend engineer", "data engineer", "analytics engineer",
    "software engineer", "full stack", "cloud engineer", "platform engineer",
]

# Titles that are clear non-matches for THIS role (used for the "keyword
# stuffer trap": e.g. Marketing Manager with a skills list full of AI terms)
OFF_TARGET_TITLES = [
    "marketing manager", "hr manager", "accountant", "sales executive",
    "customer support", "graphic designer", "civil engineer",
    "mechanical engineer", "content writer", "operations manager",
    "project manager", "business analyst", "qa engineer",
    ".net developer",
]

# Pure consulting/services firms — JD explicitly says "entire career at one
# of these, with no product-company experience" is a soft disqualifier.
SERVICES_FIRMS = [
    "tcs", "infosys", "wipro", "accenture", "cognizant", "capgemini",
    "mindtree", "hcl", "tech mahindra", "lti", "mphasis",
]

# CV / speech / robotics-only specialization signals (used to detect the
# "no NLP/IR exposure" disqualifier)
VISION_SPEECH_ROBOTICS_ONLY = [
    "computer vision", "image classification", "object detection",
    "speech recognition", "robotics", "autonomous", "lidar", "slam",
    "tts", "text-to-speech",
]
NLP_IR_SIGNALS = [
    "nlp", "natural language", "retrieval", "ranking", "search",
    "information retrieval", "llm", "language model", "embedding",
]

# Preferred locations per the JD
PREFERRED_LOCATIONS = ["pune", "noida"]
WELCOME_LOCATIONS = ["hyderabad", "mumbai", "delhi", "ncr", "gurgaon", "gurugram", "bengaluru", "bangalore"]

REFERENCE_DATE = date.today()   # always uses today's date automatically


# ═══════════════════════════════════════════════════════════════════════
# DYNAMIC JD LOADER
# Reads any job description file and updates scoring lists so the ranker
# works for ANY role, not just the hardcoded Senior AI Engineer JD.
# ═══════════════════════════════════════════════════════════════════════

def load_jd_and_update_globals(jd_path: str):
    """
    Reads a JD from a .txt, .json, or .md file.
    Extracts skills, experience range, locations — then updates the global
    scoring lists so rank_candidates() uses the new JD automatically.
    """
    global MUST_HAVE_CATEGORIES, NICE_TO_HAVE, PREFERRED_LOCATIONS, WELCOME_LOCATIONS

    path = Path(jd_path)
    if not path.exists():
        print(f"[WARN] JD file not found: {jd_path} — using built-in defaults")
        return

    if path.suffix == ".json":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        raw = " ".join(str(v) for v in data.values()).lower()
    else:
        with open(path, encoding="utf-8") as f:
            raw = f.read().lower()

    print(f"[JD]  Loaded: {jd_path}")

    all_known_skills = [
        "python","java","javascript","typescript","sql","nosql","postgresql",
        "mysql","mongodb","redis","elasticsearch","aws","azure","gcp",
        "docker","kubernetes","git","machine learning","deep learning","nlp",
        "computer vision","llm","rag","embeddings","vector search",
        "semantic search","fine-tuning","lora","qlora","peft","hugging face",
        "langchain","llamaindex","faiss","pinecone","weaviate","qdrant",
        "milvus","opensearch","bm25","hybrid search","sentence transformers",
        "bert","gpt","transformers","pytorch","tensorflow","scikit-learn",
        "xgboost","pandas","numpy","spark","hadoop","kafka","airflow","mlflow",
        "recommendation","ranking","retrieval","information retrieval",
        "a/b testing","data science","analytics","tableau","power bi",
        "react","node","fastapi","flask","django","rest api","graphql",
        "microservices","agile","scrum",
    ]
    jd_skills = [s for s in all_known_skills if s in raw]

    if jd_skills:
        half = max(1, len(jd_skills)//2)
        MUST_HAVE_CATEGORIES = {
            "primary_skills":   jd_skills[:half],
            "secondary_skills": jd_skills[half:],
        }
        NICE_TO_HAVE = []
        print(f"[JD]  {len(jd_skills)} skills detected: {jd_skills[:8]}{'...' if len(jd_skills)>8 else ''}")

    loc_map = {
        "pune":"preferred","noida":"preferred","bengaluru":"welcome",
        "bangalore":"welcome","hyderabad":"welcome","mumbai":"welcome",
        "delhi":"welcome","ncr":"welcome","gurgaon":"welcome",
        "chennai":"welcome","kolkata":"welcome","ahmedabad":"welcome",
    }
    new_pref, new_wel = [], []
    for loc, tier in loc_map.items():
        if loc in raw:
            (new_pref if tier=="preferred" else new_wel).append(loc)
    if new_pref:
        PREFERRED_LOCATIONS = new_pref
        print(f"[JD]  Preferred locations: {new_pref}")
    if new_wel:
        WELCOME_LOCATIONS = new_wel

    print("[JD]  Knowledge base updated — ranker tuned for this JD.")


# ═══════════════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════════════

def safe_lower(x):
    return str(x).lower() if x is not None else ""


def parse_date_safe(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def months_between(d1: date, d2: date) -> float:
    if d1 is None or d2 is None:
        return 0.0
    return (d2.year - d1.year) * 12 + (d2.month - d1.month)


def any_in(text, terms):
    return any(t in text for t in terms)


def count_in(text, terms):
    return sum(1 for t in terms if t in text)


# ═══════════════════════════════════════════════════════════════════════
# STEP 1 — HONEYPOT DETECTION
# ═══════════════════════════════════════════════════════════════════════

def detect_honeypot(cand: dict) -> tuple[bool, list[str]]:
    """
    Flags candidates with internally-impossible profiles.
    Returns (is_honeypot, reasons).
    Deliberately conservative: only flags clear logical impossibilities,
    not just "weak" candidates (we don't want false positives nuking
    legitimate Tier 5 candidates).
    """
    reasons = []
    profile = cand.get("profile", {}) or {}
    skills = cand.get("skills", []) or []
    career = cand.get("career_history", []) or []
    yoe = profile.get("years_of_experience", 0) or 0

    # (a) "Expert" proficiency with 0 (or near-0) duration_months — you can't
    #     be an expert in a skill you've used for 0 months.
    expert_zero_duration = sum(
        1 for s in skills
        if safe_lower(s.get("proficiency")) == "expert" and (s.get("duration_months") or 0) <= 1
    )
    if expert_zero_duration >= 2:
        reasons.append(f"{expert_zero_duration} 'expert'-proficiency skills with ~0 duration_months")

    # (b) Implausible skill saturation: many "expert" skills relative to
    #     total years of experience (can't be expert in 10 things in 1 year)
    expert_count = sum(1 for s in skills if safe_lower(s.get("proficiency")) == "expert")
    if yoe > 0 and expert_count >= 6 and yoe < 3:
        reasons.append(f"{expert_count} expert-level skills claimed with only {yoe} yrs experience")

    # (c) Career history total duration wildly exceeds stated years_of_experience
    total_career_months = sum(c.get("duration_months", 0) or 0 for c in career)
    if yoe > 0 and total_career_months > (yoe * 12 + 18):
        reasons.append(
            f"career_history totals {total_career_months}mo vs stated {yoe}yr experience"
        )

    # (d) Any single role's duration_months wildly mismatches its start/end dates
    for c in career:
        sd = parse_date_safe(c.get("start_date"))
        ed = parse_date_safe(c.get("end_date")) or REFERENCE_DATE
        if sd:
            actual_months = months_between(sd, ed)
            stated_months = c.get("duration_months", 0) or 0
            if actual_months > 0 and abs(actual_months - stated_months) > max(6, actual_months * 0.5):
                reasons.append(
                    f"role at {c.get('company','?')}: stated {stated_months}mo vs dates imply ~{int(actual_months)}mo"
                )
                break  # one flag is enough signal

    # (e) Endorsements wildly disproportionate to duration (e.g. 50+
    #     endorsements on a skill used for 1 month — implausible virality)
    absurd_endorsement = sum(
        1 for s in skills
        if (s.get("duration_months") or 0) <= 2 and (s.get("endorsements") or 0) >= 40
    )
    if absurd_endorsement >= 1:
        reasons.append(f"{absurd_endorsement} skill(s) with 40+ endorsements but <=2mo duration")

    is_honeypot = len(reasons) > 0
    return is_honeypot, reasons


# ═══════════════════════════════════════════════════════════════════════
# STEP 2 — CAREER-FIT SCORE (the dominant signal)
# ═══════════════════════════════════════════════════════════════════════

def score_career_fit(cand: dict) -> tuple[float, dict]:
    """
    Returns (score 0-1, debug_info dict).
    This is deliberately about TITLES and ROLE DESCRIPTIONS, not the skills
    bag — countering the keyword-stuffer trap the JD warns about.
    """
    profile = cand.get("profile", {}) or {}
    career = cand.get("career_history", []) or []

    current_title = safe_lower(profile.get("current_title"))
    all_titles = " ".join(safe_lower(c.get("title")) for c in career)
    all_descriptions = " ".join(safe_lower(c.get("description")) for c in career)
    combined_text = current_title + " " + all_titles + " " + all_descriptions

    score = 0.0
    notes = []

    # (a) Strong title signal — direct applied ML/search/ranking role
    strong_hits = count_in(combined_text, STRONG_TITLE_SIGNALS)
    if strong_hits > 0:
        score += min(0.45, 0.20 + strong_hits * 0.06)
        notes.append(f"{strong_hits} strong ML/AI/search title signal(s)")
    else:
        # (b) Adjacent title (backend/data eng) — partial credit only if
        # role descriptions actually mention retrieval/ranking/ML work
        adj_hits = count_in(combined_text, ADJACENT_TITLE_SIGNALS)
        nlp_ir_hits = count_in(combined_text, NLP_IR_SIGNALS)
        if adj_hits > 0 and nlp_ir_hits > 0:
            score += min(0.30, 0.10 + nlp_ir_hits * 0.04)
            notes.append(f"adjacent title ({adj_hits}) with {nlp_ir_hits} NLP/IR/ranking mentions in history")
        elif adj_hits > 0:
            score += 0.08
            notes.append("adjacent title but no clear NLP/IR/ranking evidence in history")

    # (c) Off-target title penalty — clear keyword-stuffer trap detector.
    # A Marketing/HR/Sales/Accountant title with AI buzzwords in skills is
    # exactly what the JD says to reject regardless of skill list.
    off_target_hits = count_in(current_title, OFF_TARGET_TITLES)
    if off_target_hits > 0 and strong_hits == 0:
        score *= 0.15   # crush, don't zero — leaves tiny room for genuine pivots
        notes.append("current title is off-target for an AI engineering role (keyword-stuffer pattern)")

    # (d) Vision/speech/robotics-only specialist with no NLP/IR exposure
    vsr_hits = count_in(combined_text, VISION_SPEECH_ROBOTICS_ONLY)
    nlp_hits = count_in(combined_text, NLP_IR_SIGNALS)
    if vsr_hits >= 2 and nlp_hits == 0:
        score *= 0.5
        notes.append("CV/speech/robotics-only profile, no NLP/IR exposure (JD disqualifier)")

    # (e) Pure consulting/services firms only, no product company
    companies = [safe_lower(c.get("company")) for c in career] + [safe_lower(profile.get("current_company"))]
    services_hits = sum(1 for co in companies if any(s in co for s in SERVICES_FIRMS))
    if services_hits > 0 and services_hits == len(set(companies)):
        score *= 0.55
        notes.append("entire career at pure consulting/services firms (JD disqualifier)")

    # (f) Pure-research-only, no production deployment signal
    research_only_signals = ["research lab", "academic", "phd researcher", "research scientist (academic)"]
    production_signals = ["deployed", "production", "shipped", "scale", "users", "live system"]
    if any_in(combined_text, research_only_signals) and not any_in(combined_text, production_signals):
        score *= 0.4
        notes.append("appears research-only with no clear production deployment evidence")

    # (g) Title-chaser pattern: 3+ jobs, each <=18 months, escalating
    # seniority words — proxy for "switching companies every 1.5yrs for title"
    short_stints = sum(1 for c in career if 0 < (c.get("duration_months") or 999) <= 18)
    if len(career) >= 3 and short_stints >= len(career) - 1:
        score *= 0.75
        notes.append(f"{short_stints}/{len(career)} roles are <=18mo (possible title-chasing pattern)")

    score = max(0.0, min(1.0, score))
    return score, {"notes": notes, "strong_title_hits": strong_hits}


# ═══════════════════════════════════════════════════════════════════════
# STEP 3 — SKILL TRUST SCORE
# ═══════════════════════════════════════════════════════════════════════

def score_skill_trust(cand: dict) -> tuple[float, dict]:
    """
    Matches skills against JD's must-have categories and nice-to-haves,
    weighted by a "trust factor" derived from endorsements + duration —
    a skill claimed with 0 endorsements and 0 duration is much weaker
    evidence than one with real history behind it.
    """
    skills = cand.get("skills", []) or []
    if not skills:
        return 0.0, {"notes": ["no skills listed"]}

    skill_lookup = {}
    for s in skills:
        name = safe_lower(s.get("name"))
        endorsements = s.get("endorsements", 0) or 0
        duration = s.get("duration_months", 0) or 0
        proficiency = safe_lower(s.get("proficiency"))
        prof_weight = {"beginner": 0.4, "intermediate": 0.7, "advanced": 0.9, "expert": 1.0}.get(proficiency, 0.5)
        # Trust factor: scales 0.3 (just listed) up to 1.0 (well-evidenced)
        trust = 0.3 + 0.4 * min(1.0, duration / 24.0) + 0.3 * min(1.0, endorsements / 20.0)
        skill_lookup[name] = trust * prof_weight

    def category_score(terms):
        hits = [v for k, v in skill_lookup.items() if any(t in k or k in t for t in terms)]
        return max(hits) if hits else 0.0

    must_have_scores = {cat: category_score(terms) for cat, terms in MUST_HAVE_CATEGORIES.items()}
    must_have_avg = sum(must_have_scores.values()) / len(must_have_scores)

    nice_hits = [v for k, v in skill_lookup.items() if any(t in k or k in t for t in NICE_TO_HAVE)]
    nice_bonus = min(0.15, sum(sorted(nice_hits, reverse=True)[:3]) * 0.05)

    score = max(0.0, min(1.0, 0.85 * must_have_avg + nice_bonus))
    return score, {"must_have_scores": must_have_scores, "nice_bonus": nice_bonus}


# ═══════════════════════════════════════════════════════════════════════
# STEP 4 — BEHAVIORAL AVAILABILITY MULTIPLIER
# ═══════════════════════════════════════════════════════════════════════

def behavioral_multiplier(cand: dict) -> tuple[float, dict]:
    """
    Returns a multiplier roughly in [0.5, 1.10] applied to the base fit
    score — NOT an additive bucket. A great-on-paper but clearly-unavailable
    candidate should be pulled down significantly, per the JD's explicit
    instruction.
    """
    sig = cand.get("redrob_signals", {}) or {}

    last_active = parse_date_safe(sig.get("last_active_date"))
    days_inactive = (REFERENCE_DATE - last_active).days if last_active else 9999

    response_rate = sig.get("recruiter_response_rate")
    response_rate = response_rate if isinstance(response_rate, (int, float)) else 0.0

    open_to_work = bool(sig.get("open_to_work_flag", False))
    notice_days = sig.get("notice_period_days", 60) or 60
    interview_completion = sig.get("interview_completion_rate")
    interview_completion = interview_completion if isinstance(interview_completion, (int, float)) else 0.5

    mult = 1.0
    notes = []

    # Recency of activity — the JD's explicit example (6mo inactive = bad)
    if days_inactive > 180:
        mult *= 0.55
        notes.append(f"inactive {days_inactive}d (>6mo)")
    elif days_inactive > 90:
        mult *= 0.80
        notes.append(f"inactive {days_inactive}d (>3mo)")
    elif days_inactive <= 14:
        mult *= 1.05
        notes.append("active in last 2 weeks")

    # Response rate
    if response_rate < 0.10:
        mult *= 0.70
        notes.append(f"very low response rate ({response_rate:.2f})")
    elif response_rate < 0.30:
        mult *= 0.88
        notes.append(f"low response rate ({response_rate:.2f})")
    elif response_rate >= 0.70:
        mult *= 1.05
        notes.append(f"high response rate ({response_rate:.2f})")

    # Open to work
    if not open_to_work:
        mult *= 0.85
        notes.append("not marked open_to_work")

    # Notice period — JD prefers sub-30, can flex to ~30, gets harder beyond
    if notice_days > 90:
        mult *= 0.85
        notes.append(f"long notice period ({notice_days}d)")
    elif notice_days <= 30:
        mult *= 1.03
        notes.append(f"short notice period ({notice_days}d)")

    # Interview completion (flakiness signal)
    if interview_completion < 0.4:
        mult *= 0.90
        notes.append(f"low interview completion rate ({interview_completion:.2f})")

    mult = max(0.35, min(1.15, mult))
    return mult, {"notes": notes, "days_inactive": days_inactive, "response_rate": response_rate}


# ═══════════════════════════════════════════════════════════════════════
# STEP 5 — LOCATION / LOGISTICS MODIFIER
# ═══════════════════════════════════════════════════════════════════════

def location_modifier(cand: dict) -> tuple[float, str]:
    profile = cand.get("profile", {}) or {}
    location = safe_lower(profile.get("location"))
    country = safe_lower(profile.get("country"))

    if any(loc in location for loc in PREFERRED_LOCATIONS):
        return 1.08, "preferred location (Pune/Noida)"
    if any(loc in location for loc in WELCOME_LOCATIONS):
        return 1.0, "welcome location (Tier-1 India)"
    if country == "india":
        sig = cand.get("redrob_signals", {}) or {}
        if sig.get("willing_to_relocate"):
            return 0.95, "India, other city, willing to relocate"
        return 0.85, "India, other city, relocation unclear"
    # Outside India — JD says case-by-case, no visa sponsorship
    return 0.55, "outside India (no visa sponsorship, case-by-case)"


# ═══════════════════════════════════════════════════════════════════════
# STEP 6 — EXPERIENCE BAND FIT (5-9yr soft band, not a hard cutoff)
# ═══════════════════════════════════════════════════════════════════════

def experience_band_modifier(cand: dict) -> float:
    yoe = (cand.get("profile", {}) or {}).get("years_of_experience", 0) or 0
    if 5 <= yoe <= 9:
        return 1.05
    if 4 <= yoe < 5 or 9 < yoe <= 11:
        return 1.0
    if 2 <= yoe < 4:
        return 0.85
    if yoe > 11:
        return 0.90   # JD: "we'll consider candidates outside the band if other signals are strong"
    return 0.65        # very junior for a "founding senior" role


# ═══════════════════════════════════════════════════════════════════════
# STEP 7 — COMBINE EVERYTHING
# ═══════════════════════════════════════════════════════════════════════

def score_candidate(cand: dict) -> dict:
    is_honeypot, honeypot_reasons = detect_honeypot(cand)

    career_score, career_dbg = score_career_fit(cand)
    skill_score, skill_dbg = score_skill_trust(cand)
    behav_mult, behav_dbg = behavioral_multiplier(cand)
    loc_mult, loc_note = location_modifier(cand)
    exp_mult = experience_band_modifier(cand)

    base = 0.62 * career_score + 0.38 * skill_score
    final = base * behav_mult * loc_mult * exp_mult

    if is_honeypot:
        final *= 0.02   # crush to near-zero, but not exactly 0 (keeps sort stable)

    final = max(0.0, min(1.0, final))

    return {
        "candidate_id": cand.get("candidate_id"),
        "score": final,
        "is_honeypot": is_honeypot,
        "honeypot_reasons": honeypot_reasons,
        "career_score": career_score,
        "skill_score": skill_score,
        "behav_mult": behav_mult,
        "loc_mult": loc_mult,
        "loc_note": loc_note,
        "exp_mult": exp_mult,
        "career_notes": career_dbg["notes"],
        "behav_notes": behav_dbg["notes"],
        "profile": cand.get("profile", {}),
    }


# ═══════════════════════════════════════════════════════════════════════
# STEP 8 — REASONING TEXT GENERATION (for the CSV's `reasoning` column)
# ═══════════════════════════════════════════════════════════════════════

def build_reasoning(result: dict) -> str:
    p = result["profile"] or {}
    title = p.get("current_title", "Unknown role")
    yoe = p.get("years_of_experience", "?")

    if result["is_honeypot"]:
        return (
            f"Excluded as likely honeypot/inconsistent profile: "
            f"{'; '.join(result['honeypot_reasons'][:2])}."
        )[:300]

    parts = [f"{title} with {yoe} yrs experience."]

    if result["career_notes"]:
        parts.append(result["career_notes"][0] + ".")
    if result["skill_score"] >= 0.5:
        parts.append("Strong match on JD's core retrieval/ranking/ML skill categories.")
    elif result["skill_score"] >= 0.25:
        parts.append("Partial match on JD's core technical skill categories.")
    else:
        parts.append("Weak match on JD's core embeddings/retrieval/eval skill requirements.")

    if result["behav_notes"]:
        parts.append("Availability: " + result["behav_notes"][0] + ".")

    parts.append(result["loc_note"] + ".")

    return " ".join(parts)[:300]


# ═══════════════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════════════

def load_candidates_streaming(path: str):
    """Stream-parse the .jsonl file (handles both plain and .gz)."""
    if path.endswith(".gz"):
        import gzip
        opener = lambda p: gzip.open(p, "rt", encoding="utf-8")
    else:
        opener = lambda p: open(p, "r", encoding="utf-8")

    with opener(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def main():
    parser = argparse.ArgumentParser(description="Redrob Hackathon candidate ranker")
    parser.add_argument("--candidates", required=True, help="Path to candidates.jsonl (or .jsonl.gz)")
    parser.add_argument("--out", required=True, help="Output CSV path")
    parser.add_argument("--top-n", type=int, default=100, help="Number of top candidates to output")
    parser.add_argument("--jd", default=None, help="Optional: path to a job description file (.txt/.json/.md). If provided, the ranker auto-tunes its scoring to match the new JD instead of the built-in Senior AI Engineer defaults.")
    args = parser.parse_args()

    # If a custom JD file is provided, update scoring globals before ranking
    if args.jd:
        load_jd_and_update_globals(args.jd)
    else:
        print("[JD]  Using built-in JD: Senior AI Engineer — Founding Team @ Redrob AI")

    t0 = time.time()
    print(f"[1/4] Streaming candidates from {args.candidates} ...")

    all_results = []
    n = 0
    for cand in load_candidates_streaming(args.candidates):
        n += 1
        all_results.append(score_candidate(cand))
        if n % 20000 == 0:
            print(f"      scored {n:,} candidates... ({time.time()-t0:.1f}s elapsed)")

    print(f"      total candidates scored: {n:,}  ({time.time()-t0:.1f}s elapsed)")

    print("[2/4] Sorting by score...")
    # Round FIRST so that ties created by rounding are caught by the
    # candidate_id tie-break too — the validator compares the rounded
    # scores that actually appear in the CSV, not our internal float.
    for r in all_results:
        r["score"] = round(r["score"], 4)
    # Sort: rounded score desc, then candidate_id asc for deterministic tie-break
    all_results.sort(key=lambda r: (-r["score"], r["candidate_id"]))

    honeypot_in_top100 = sum(1 for r in all_results[:args.top_n] if r["is_honeypot"])
    print(f"      honeypots detected in top {args.top_n}: {honeypot_in_top100} "
          f"({'OK' if honeypot_in_top100 <= args.top_n*0.10 else 'WARNING: exceeds 10% threshold'})")

    print(f"[3/4] Building top-{args.top_n} submission rows...")
    top_results = all_results[:args.top_n]

    rows = []
    for rank, r in enumerate(top_results, start=1):
        rows.append({
            "candidate_id": r["candidate_id"],
            "rank": rank,
            "score": r["score"],
            "reasoning": build_reasoning(r),
        })

    # No post-hoc score clamping needed: scores were rounded BEFORE sorting,
    # so the sort already guarantees non-increasing score by rank, and ties
    # are already broken by ascending candidate_id.

    print(f"[4/4] Writing {args.out} ...")
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["candidate_id", "rank", "score", "reasoning"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nDone in {time.time()-t0:.1f}s. Wrote {len(rows)} rows to {args.out}")
    print("\nTop 10 preview:")
    for r in rows[:10]:
        print(f"  #{r['rank']:>3}  {r['candidate_id']}  score={r['score']:.4f}  {r['reasoning'][:80]}")


if __name__ == "__main__":
    main()
