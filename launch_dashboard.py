#!/usr/bin/env python3
"""
launch_dashboard.py
Run this after rank.py to open the results dashboard in your browser.

    python launch_dashboard.py
"""

import csv
import json
import os
import webbrowser
from pathlib import Path

SUBMISSION = Path("output/submission.csv")
OUTPUT_HTML = Path("output/dashboard.html")

# ── Read real submission CSV ──────────────────────────────────────────
rows = []
with open(SUBMISSION, encoding="utf-8") as f:
    for row in csv.DictReader(f):
        rows.append({
            "rank":      int(row["rank"]),
            "id":        row["candidate_id"],
            "score":     float(row["score"]),
            "reasoning": row["reasoning"],
        })

candidates_json = json.dumps(rows)

# ── Build HTML ────────────────────────────────────────────────────────
html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Redrob AI — Candidate Ranking Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --green: #1D9E75; --green-light: #E1F5EE; --green-dark: #0F6E56;
    --blue: #2a78d6; --purple: #4a3aa7; --amber: #eda100;
    --bg: #f8f8f6; --surface: #ffffff; --border: rgba(0,0,0,0.08);
    --text: #0b0b0b; --muted: #888780; --secondary: #52514e;
    --radius: 8px;
  }}
  body {{ font-family: 'Inter', sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }}

  .topbar {{ background: var(--surface); border-bottom: 1px solid var(--border); padding: 14px 32px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 10; }}
  .logo-row {{ display: flex; align-items: center; gap: 10px; }}
  .logo-box {{ width: 34px; height: 34px; border-radius: 8px; background: var(--green); display: flex; align-items: center; justify-content: center; font-size: 18px; }}
  .brand {{ font-size: 15px; font-weight: 600; }}
  .brand span {{ color: var(--green); }}
  .jd-badge {{ font-size: 12px; background: var(--green-light); color: var(--green-dark); padding: 4px 12px; border-radius: 20px; font-weight: 500; }}

  .main {{ max-width: 1100px; margin: 0 auto; padding: 28px 24px; }}

  .kpi-row {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }}
  .kpi {{ background: var(--surface); border-radius: 12px; border: 1px solid var(--border); padding: 16px 20px; }}
  .kpi-label {{ font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 6px; }}
  .kpi-value {{ font-size: 26px; font-weight: 600; color: var(--text); line-height: 1; }}
  .kpi-sub {{ font-size: 12px; color: var(--secondary); margin-top: 4px; }}

  .charts-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 24px; }}
  .chart-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 18px 20px; }}
  .chart-title {{ font-size: 13px; font-weight: 500; margin-bottom: 14px; color: var(--text); }}

  .table-section {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }}
  .table-header {{ padding: 14px 20px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }}
  .section-title {{ font-size: 13px; font-weight: 500; }}
  .filters {{ display: flex; gap: 6px; flex-wrap: wrap; }}
  .chip {{ padding: 4px 12px; border-radius: 20px; font-size: 12px; cursor: pointer; border: 1px solid var(--border); background: transparent; color: var(--secondary); transition: all 0.12s; font-family: inherit; }}
  .chip.active {{ background: var(--green-light); border-color: var(--green); color: var(--green-dark); font-weight: 500; }}
  .chip:hover:not(.active) {{ border-color: #b0b0a8; }}
  .search-box {{ padding: 6px 12px; border: 1px solid var(--border); border-radius: var(--radius); font-size: 13px; font-family: inherit; outline: none; width: 200px; }}
  .search-box:focus {{ border-color: var(--green); }}

  table {{ width: 100%; border-collapse: collapse; }}
  thead {{ background: #f8f8f6; }}
  th {{ padding: 10px 16px; text-align: left; font-size: 11px; font-weight: 500; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 1px solid var(--border); white-space: nowrap; }}
  td {{ padding: 12px 16px; font-size: 13px; border-bottom: 1px solid var(--border); vertical-align: middle; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: #fafaf8; }}

  .rank-badge {{ width: 26px; height: 26px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 600; }}
  .r1 {{ background: #FAC775; color: #633806; }}
  .r2 {{ background: #D3D1C7; color: #444441; }}
  .r3 {{ background: #F5C4B3; color: #712B13; }}
  .rn {{ background: #f0f0ee; color: var(--muted); }}

  .cand-id {{ font-weight: 500; font-size: 13px; }}
  .reasoning-text {{ font-size: 12px; color: var(--secondary); max-width: 380px; line-height: 1.5; }}

  .score-wrap {{ display: flex; align-items: center; gap: 8px; min-width: 120px; }}
  .bar-bg {{ flex: 1; height: 6px; background: #f0f0ee; border-radius: 3px; overflow: hidden; }}
  .bar-fill {{ height: 100%; border-radius: 3px; background: var(--green); }}
  .score-num {{ font-size: 12px; font-weight: 500; min-width: 42px; text-align: right; }}

  .avail-dot {{ display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 5px; }}

  .pagination {{ padding: 12px 20px; border-top: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; font-size: 12px; color: var(--muted); }}
  .page-btns {{ display: flex; gap: 4px; }}
  .page-btn {{ padding: 4px 10px; border-radius: var(--radius); border: 1px solid var(--border); background: transparent; font-size: 12px; cursor: pointer; color: var(--secondary); font-family: inherit; }}
  .page-btn:hover {{ border-color: #b0b0a8; }}
  .page-btn.active {{ background: var(--green); color: #fff; border-color: var(--green); font-weight: 500; }}

  .empty {{ padding: 40px; text-align: center; color: var(--muted); font-size: 14px; }}

  @media (max-width: 700px) {{
    .kpi-row {{ grid-template-columns: 1fr 1fr; }}
    .charts-row {{ grid-template-columns: 1fr; }}
    .search-box {{ width: 140px; }}
  }}
</style>
</head>
<body>

<div class="topbar">
  <div class="logo-row">
    <div class="logo-box">🧠</div>
    <div>
      <div class="brand">Redrob<span> AI</span> — Candidate Intelligence</div>
    </div>
  </div>
  <div class="jd-badge">Senior AI Engineer · Founding Team · Pune / Noida</div>
</div>

<div class="main">

  <div class="kpi-row">
    <div class="kpi">
      <div class="kpi-label">Pool scored</div>
      <div class="kpi-value">100,000</div>
      <div class="kpi-sub">candidates</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Shortlist</div>
      <div class="kpi-value">100</div>
      <div class="kpi-sub">trust-ranked</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Top score</div>
      <div class="kpi-value" id="topScore">—</div>
      <div class="kpi-sub">rank #1</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Runtime</div>
      <div class="kpi-value">59s</div>
      <div class="kpi-sub">CPU-only · no GPU</div>
    </div>
  </div>

  <div class="charts-row">
    <div class="chart-card">
      <div class="chart-title">Score distribution — top 100</div>
      <div style="position:relative;height:160px;"><canvas id="scoreChart"></canvas></div>
    </div>
    <div class="chart-card">
      <div class="chart-title">Score by rank band</div>
      <div style="position:relative;height:160px;"><canvas id="trendChart"></canvas></div>
    </div>
  </div>

  <div class="table-section">
    <div class="table-header">
      <div class="section-title">Ranked shortlist</div>
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
        <input class="search-box" id="searchBox" placeholder="Search candidate ID..." />
        <div class="filters" id="filters">
          <button class="chip active" data-filter="all">All</button>
          <button class="chip" data-filter="top10">Top 10</button>
          <button class="chip" data-filter="top25">Top 25</button>
          <button class="chip" data-filter="top50">Top 50</button>
        </div>
      </div>
    </div>

    <table>
      <thead>
        <tr>
          <th>Rank</th>
          <th>Candidate ID</th>
          <th>Fit score</th>
          <th>Reasoning</th>
        </tr>
      </thead>
      <tbody id="tableBody"></tbody>
    </table>

    <div class="pagination">
      <span id="pageInfo"></span>
      <div class="page-btns" id="pageBtns"></div>
    </div>
  </div>

</div>

<script>
const ALL = {candidates_json};

document.getElementById('topScore').textContent = ALL[0].score.toFixed(4);

let filtered = [...ALL];
let page = 1;
const PER_PAGE = 15;

function applyFilters() {{
  const search = document.getElementById('searchBox').value.trim().toLowerCase();
  const band = document.querySelector('.chip.active').dataset.filter;
  filtered = ALL.filter(c => {{
    const matchSearch = !search || c.id.toLowerCase().includes(search) || c.reasoning.toLowerCase().includes(search);
    const matchBand = band === 'all' || (band === 'top10' && c.rank <= 10) || (band === 'top25' && c.rank <= 25) || (band === 'top50' && c.rank <= 50);
    return matchSearch && matchBand;
  }});
  page = 1;
  render();
}}

function rankClass(r) {{
  if (r === 1) return 'r1';
  if (r === 2) return 'r2';
  if (r === 3) return 'r3';
  return 'rn';
}}

function render() {{
  const total = filtered.length;
  const pages = Math.max(1, Math.ceil(total / PER_PAGE));
  const slice = filtered.slice((page-1)*PER_PAGE, page*PER_PAGE);

  const tbody = document.getElementById('tableBody');
  if (slice.length === 0) {{
    tbody.innerHTML = '<tr><td colspan="4" class="empty">No candidates match your filter.</td></tr>';
  }} else {{
    tbody.innerHTML = slice.map(c => {{
      const barW = Math.round((c.score / 0.60) * 100);
      const dotColor = c.reasoning.includes('high response') ? '#1D9E75' : '#B4B2A9';
      return `<tr>
        <td><span class="rank-badge ${{rankClass(c.rank)}}">${{c.rank}}</span></td>
        <td><div class="cand-id">${{c.id}}</div></td>
        <td><div class="score-wrap"><div class="bar-bg"><div class="bar-fill" style="width:${{barW}}%"></div></div><span class="score-num">${{c.score.toFixed(4)}}</span></div></td>
        <td><div class="reasoning-text">${{c.reasoning}}</div></td>
      </tr>`;
    }}).join('');
  }}

  document.getElementById('pageInfo').textContent = total > 0
    ? `Showing ${{(page-1)*PER_PAGE+1}}–${{Math.min(page*PER_PAGE, total)}} of ${{total}}`
    : 'No results';

  const pb = document.getElementById('pageBtns');
  pb.innerHTML = '';
  for (let i = 1; i <= pages; i++) {{
    const btn = document.createElement('button');
    btn.className = 'page-btn' + (i === page ? ' active' : '');
    btn.textContent = i;
    btn.onclick = () => {{ page = i; render(); }};
    pb.appendChild(btn);
  }}
}}

document.getElementById('filters').addEventListener('click', e => {{
  const chip = e.target.closest('.chip');
  if (!chip) return;
  document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
  chip.classList.add('active');
  applyFilters();
}});
document.getElementById('searchBox').addEventListener('input', applyFilters);

render();

// Charts using real data
const scores = ALL.map(c => c.score);
const buckets = [0,0,0,0,0,0];
scores.forEach(s => {{
  const idx = Math.min(5, Math.floor((s - 0.37) / 0.03));
  if (idx >= 0) buckets[idx]++;
}});

new Chart(document.getElementById('scoreChart'), {{
  type: 'bar',
  data: {{
    labels: ['0.37–0.40','0.40–0.43','0.43–0.46','0.46–0.49','0.49–0.52','0.52+'],
    datasets: [{{ data: buckets, backgroundColor: '#5DCAA5', borderRadius: 4, borderSkipped: false }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ ticks: {{ color: '#888780', font: {{ size: 10 }} }}, grid: {{ color: '#e8e8e4' }} }},
      y: {{ ticks: {{ color: '#888780', font: {{ size: 10 }} }}, grid: {{ color: '#e8e8e4' }} }}
    }}
  }}
}});

const bands = ['1–10','11–20','21–30','31–40','41–50','51–60','61–70','71–80','81–90','91–100'];
const bandAvg = bands.map((_, i) => {{
  const slice = ALL.slice(i*10, (i+1)*10);
  return slice.length ? parseFloat((slice.reduce((s,c)=>s+c.score,0)/slice.length).toFixed(4)) : 0;
}});

new Chart(document.getElementById('trendChart'), {{
  type: 'line',
  data: {{
    labels: bands,
    datasets: [{{ label: 'Avg score', data: bandAvg, borderColor: '#2a78d6', backgroundColor: 'rgba(42,120,214,0.08)', borderWidth: 2, pointRadius: 4, pointBackgroundColor: '#2a78d6', tension: 0.3, fill: true }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ ticks: {{ color: '#888780', font: {{ size: 10 }} }}, grid: {{ color: '#e8e8e4' }} }},
      y: {{ ticks: {{ color: '#888780', font: {{ size: 10 }} }}, grid: {{ color: '#e8e8e4' }} }}
    }}
  }}
}});
</script>
</body>
</html>"""

OUTPUT_HTML.write_text(html, encoding="utf-8")
print(f"[OK] Dashboard written to {OUTPUT_HTML.resolve()}")

# Open in browser automatically
webbrowser.open(OUTPUT_HTML.resolve().as_uri())
print("[OK] Opened in your browser!")
