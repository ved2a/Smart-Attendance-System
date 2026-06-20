"""
Attendance Admin Dashboard
Generates an HTML report + CSV export from the SQLite database.

Usage:
    python dashboard.py                    # full report
    python dashboard.py --date 2025-06-19  # specific date
    python dashboard.py --export           # also export CSV
"""

import sqlite3
import csv
import argparse
from datetime import date, timedelta
from pathlib import Path

DB_PATH = "attendance.db"


# ─────────────────────────────────────────────────────────────
#  DATA LAYER
# ─────────────────────────────────────────────────────────────
def get_summary(conn, days: int = 7):
    since = (date.today() - timedelta(days=days - 1)).isoformat()
    return conn.execute("""
        SELECT s.name,
               a.date,
               COUNT(*) AS entries,
               MIN(a.timestamp) AS first_in
        FROM attendance a
        JOIN students s ON s.id = a.student_id
        WHERE a.date >= ?
        GROUP BY s.id, a.date
        ORDER BY a.date DESC, s.name
    """, (since,)).fetchall()


def get_students(conn):
    return conn.execute("SELECT name, reg_date FROM students ORDER BY name").fetchall()


def get_daily(conn, target_date: str):
    return conn.execute("""
        SELECT s.name, a.timestamp, a.status
        FROM attendance a
        JOIN students s ON s.id = a.student_id
        WHERE a.date = ?
        ORDER BY a.timestamp
    """, (target_date,)).fetchall()


# ─────────────────────────────────────────────────────────────
#  CSV EXPORT
# ─────────────────────────────────────────────────────────────
def export_csv(conn, days: int = 30):
    rows = get_summary(conn, days)
    out  = Path("attendance_export.csv")
    with open(out, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "Date", "Entries", "First Check-In"])
        writer.writerows(rows)
    print(f"CSV exported → {out}")


# ─────────────────────────────────────────────────────────────
#  HTML REPORT
# ─────────────────────────────────────────────────────────────
def build_html(conn, target_date: str) -> str:
    daily    = get_daily(conn, target_date)
    students = get_students(conn)
    summary  = get_summary(conn, days=7)

    present_today = {r[0] for r in daily}
    all_names     = {r[0] for r in students}
    absent_today  = all_names - present_today

    # Build summary table rows
    summary_rows = ""
    for name, d, entries, first_in in summary:
        first_in_fmt = first_in[11:19] if first_in else "—"
        summary_rows += f"""
        <tr>
          <td>{name}</td>
          <td>{d}</td>
          <td><span class="badge present">PRESENT</span></td>
          <td>{first_in_fmt}</td>
          <td>{entries}</td>
        </tr>"""

    # Today's detail rows
    detail_rows = ""
    for name, ts, status in daily:
        detail_rows += f"""
        <tr>
          <td>{name}</td>
          <td>{ts[11:19]}</td>
          <td><span class="badge present">{status}</span></td>
        </tr>"""

    absent_rows = "".join(
        f'<tr><td>{n}</td><td>—</td><td><span class="badge absent">ABSENT</span></td></tr>'
        for n in sorted(absent_today)
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Attendance Dashboard</title>
<style>
  :root {{
    --bg:    #0f1117;
    --card:  #1a1d27;
    --line:  #252836;
    --green: #22c55e;
    --red:   #ef4444;
    --blue:  #3b82f6;
    --text:  #e2e8f0;
    --muted: #64748b;
    --accent:#6366f1;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Segoe UI', system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    padding: 24px;
    line-height: 1.6;
  }}
  header {{
    display: flex;
    align-items: center;
    gap: 14px;
    margin-bottom: 32px;
    padding-bottom: 20px;
    border-bottom: 1px solid var(--line);
  }}
  header .icon {{
    font-size: 2rem;
    background: var(--accent);
    border-radius: 12px;
    width: 52px; height: 52px;
    display: grid; place-items: center;
  }}
  header h1 {{ font-size: 1.4rem; font-weight: 700; }}
  header p  {{ color: var(--muted); font-size: 0.85rem; }}

  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 14px;
    margin-bottom: 32px;
  }}
  .stat-card {{
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 18px 20px;
  }}
  .stat-card .value {{ font-size: 2rem; font-weight: 800; }}
  .stat-card .label {{ color: var(--muted); font-size: 0.78rem; text-transform: uppercase; letter-spacing: .06em; }}
  .green {{ color: var(--green); }}
  .red   {{ color: var(--red);   }}
  .blue  {{ color: var(--blue);  }}

  section {{
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 12px;
    margin-bottom: 24px;
    overflow: hidden;
  }}
  section h2 {{
    padding: 16px 20px;
    font-size: 0.95rem;
    font-weight: 600;
    border-bottom: 1px solid var(--line);
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: .08em;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.88rem;
  }}
  th, td {{
    padding: 11px 20px;
    text-align: left;
    border-bottom: 1px solid var(--line);
  }}
  th {{ color: var(--muted); font-weight: 500; font-size: 0.78rem; text-transform: uppercase; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: rgba(255,255,255,.03); }}

  .badge {{
    display: inline-block;
    padding: 2px 10px;
    border-radius: 99px;
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: .05em;
  }}
  .badge.present {{ background: rgba(34,197,94,.15); color: var(--green); }}
  .badge.absent  {{ background: rgba(239,68,68,.15);  color: var(--red);   }}

  .empty {{ padding: 24px 20px; color: var(--muted); font-size: 0.88rem; }}
</style>
</head>
<body>

<header>
  <div class="icon">🎓</div>
  <div>
    <h1>Smart Attendance Dashboard</h1>
    <p>Face Recognition System  ·  Report Date: {target_date}</p>
  </div>
</header>

<div class="grid">
  <div class="stat-card">
    <div class="value green">{len(present_today)}</div>
    <div class="label">Present Today</div>
  </div>
  <div class="stat-card">
    <div class="value red">{len(absent_today)}</div>
    <div class="label">Absent Today</div>
  </div>
  <div class="stat-card">
    <div class="value blue">{len(all_names)}</div>
    <div class="label">Registered</div>
  </div>
  <div class="stat-card">
    <div class="value" style="color:var(--accent)">
      {round(len(present_today)/len(all_names)*100) if all_names else 0}%
    </div>
    <div class="label">Attendance Rate</div>
  </div>
</div>

<section>
  <h2>Today's Attendance — {target_date}</h2>
  {"<table><thead><tr><th>Name</th><th>Check-In Time</th><th>Status</th></tr></thead><tbody>" + detail_rows + absent_rows + "</tbody></table>"
   if (detail_rows or absent_rows)
   else '<p class="empty">No records yet for today.</p>'}
</section>

<section>
  <h2>Last 7 Days — Presence Log</h2>
  {"<table><thead><tr><th>Name</th><th>Date</th><th>Status</th><th>First In</th><th>Entries</th></tr></thead><tbody>" + summary_rows + "</tbody></table>"
   if summary_rows
   else '<p class="empty">No attendance data found.</p>'}
</section>

<section>
  <h2>Registered Students</h2>
  <table>
    <thead><tr><th>#</th><th>Name</th><th>Registered On</th></tr></thead>
    <tbody>
      {"".join(f"<tr><td>{i+1}</td><td>{n}</td><td>{d}</td></tr>" for i,(n,d) in enumerate(students))
       or '<tr><td colspan="3" style="color:var(--muted)">No students registered.</td></tr>'}
    </tbody>
  </table>
</section>

</body>
</html>"""


# ─────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Attendance Dashboard")
    parser.add_argument("--date",   default=date.today().isoformat(),
                        help="YYYY-MM-DD (default: today)")
    parser.add_argument("--export", action="store_true",
                        help="Also export CSV")
    args = parser.parse_args()

    if not Path(DB_PATH).exists():
        import sys; sys.exit(f"❌  Database not found: {DB_PATH}\n   Run attendance_system.py first.")

    conn = sqlite3.connect(DB_PATH)
    html = build_html(conn, args.date)

    out = Path("report.html")
    out.write_text(html, encoding="utf-8")
    print(f"✅  Report saved → {out.resolve()}")

    if args.export:
        export_csv(conn)

    conn.close()


if __name__ == "__main__":
    main()
