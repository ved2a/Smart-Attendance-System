"""
pip install -r requirements.txt   # dlib + opencv + face_recognition

python attendance_system.py --register --name "Your Name"
python attendance_system.py --run         # press Q to quit
python attendance_system.py --report

python dashboard.py               # → report.html

Smart Attendance System — Face Recognition + SQLite
Author: Vedant

Requirements:
    pip install opencv-python face_recognition numpy pillow

Usage:
    python attendance_system.py --register --name "Alice"   # register a new face
    python attendance_system.py --run                       # run live attendance
    python attendance_system.py --report                    # print today's report
"""

import cv2
import face_recognition
import numpy as np
import sqlite3
import os
import sys
import argparse
import pickle
from datetime import datetime, date
from pathlib import Path

# ─────────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────────
DB_PATH       = "attendance.db"
ENCODINGS_DIR = Path("encodings")
PHOTOS_DIR    = Path("photos")
TOLERANCE     = 0.5       # lower = stricter match
FRAME_SCALE   = 0.5       # downscale for speed (0.25 – 1.0)
COOLDOWN_SEC  = 60        # seconds between two logs for same person


# ─────────────────────────────────────────────────────────────
#  DATABASE
# ─────────────────────────────────────────────────────────────
def init_db(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS students (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT NOT NULL UNIQUE,
            reg_date  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS attendance (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            timestamp  TEXT NOT NULL,
            date       TEXT NOT NULL,
            status     TEXT DEFAULT 'PRESENT',
            FOREIGN KEY (student_id) REFERENCES students(id)
        );

        CREATE INDEX IF NOT EXISTS idx_attendance_date
            ON attendance(date);
    """)
    conn.commit()


def get_or_create_student(conn: sqlite3.Connection, name: str) -> int:
    row = conn.execute("SELECT id FROM students WHERE name=?", (name,)).fetchone()
    if row:
        return row[0]
    conn.execute("INSERT INTO students(name, reg_date) VALUES(?,?)",
                 (name, date.today().isoformat()))
    conn.commit()
    return conn.execute("SELECT id FROM students WHERE name=?", (name,)).fetchone()[0]


def log_attendance(conn: sqlite3.Connection, student_id: int,
                   last_logged: dict, name: str) -> bool:
    """Returns True if a new record was inserted (respects cooldown)."""
    now = datetime.now()
    last = last_logged.get(student_id)
    if last and (now - last).total_seconds() < COOLDOWN_SEC:
        return False
    conn.execute(
        "INSERT INTO attendance(student_id, timestamp, date) VALUES(?,?,?)",
        (student_id, now.isoformat(timespec="seconds"), date.today().isoformat())
    )
    conn.commit()
    last_logged[student_id] = now
    print(f"[{now.strftime('%H:%M:%S')}] ✅  Marked PRESENT: {name}")
    return True


# ─────────────────────────────────────────────────────────────
#  ENCODING STORE
# ─────────────────────────────────────────────────────────────
def save_encoding(name: str, encoding: np.ndarray):
    ENCODINGS_DIR.mkdir(exist_ok=True)
    path = ENCODINGS_DIR / f"{name}.pkl"
    with open(path, "wb") as f:
        pickle.dump(encoding, f)
    print(f"Encoding saved → {path}")


def load_all_encodings() -> tuple[list, list]:
    """Returns (names, encodings)."""
    names, encodings = [], []
    if not ENCODINGS_DIR.exists():
        return names, encodings
    for pkl in ENCODINGS_DIR.glob("*.pkl"):
        with open(pkl, "rb") as f:
            enc = pickle.load(f)
        names.append(pkl.stem)
        encodings.append(enc)
    return names, encodings


# ─────────────────────────────────────────────────────────────
#  REGISTRATION
# ─────────────────────────────────────────────────────────────
def register_face(name: str, conn: sqlite3.Connection):
    """Capture 5 frames and save the average encoding."""
    PHOTOS_DIR.mkdir(exist_ok=True)
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        sys.exit("❌  Could not open camera.")

    print(f"\nRegistering '{name}'. Look at the camera. Collecting samples…")
    samples, count = [], 0

    while count < 5:
        ret, frame = cap.read()
        if not ret:
            continue

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        locs = face_recognition.face_locations(rgb, model="hog")
        encs = face_recognition.face_encodings(rgb, locs)

        if len(encs) == 1:
            samples.append(encs[0])
            count += 1
            cv2.putText(frame, f"Sample {count}/5", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 200, 0), 2)
            print(f"  Sample {count}/5 captured")

        # draw box around detected face
        for top, right, bottom, left in locs:
            cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)

        cv2.imshow(f"Register — {name}  (press Q to abort)", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()

    if len(samples) < 3:
        print("❌  Not enough samples. Try again in better lighting.")
        return

    avg_encoding = np.mean(samples, axis=0)
    save_encoding(name, avg_encoding)
    get_or_create_student(conn, name)
    print(f"✅  '{name}' registered successfully!\n")


# ─────────────────────────────────────────────────────────────
#  LIVE ATTENDANCE
# ─────────────────────────────────────────────────────────────
def draw_label(frame, name: str, top: int, right: int, bottom: int, left: int,
               matched: bool):
    color = (0, 220, 0) if matched else (0, 0, 220)
    cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
    cv2.rectangle(frame, (left, bottom - 30), (right, bottom), color, cv2.FILLED)
    cv2.putText(frame, name, (left + 6, bottom - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 1)


def run_attendance(conn: sqlite3.Connection):
    names, known_encodings = load_all_encodings()
    if not names:
        sys.exit("❌  No registered faces found. Run --register first.")

    print(f"\n🎓  Loaded {len(names)} registered face(s): {', '.join(names)}")
    print("   Press  Q  to quit.\n")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        sys.exit("❌  Could not open camera.")

    last_logged: dict[int, datetime] = {}
    process_this_frame = True

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Process every other frame for speed
        if process_this_frame:
            small = cv2.resize(frame, (0, 0), fx=FRAME_SCALE, fy=FRAME_SCALE)
            rgb_small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

            locs   = face_recognition.face_locations(rgb_small, model="hog")
            encs   = face_recognition.face_encodings(rgb_small, locs)

            results = []
            for enc in encs:
                distances = face_recognition.face_distance(known_encodings, enc)
                best_idx  = int(np.argmin(distances))
                matched   = distances[best_idx] < TOLERANCE
                label     = names[best_idx] if matched else "Unknown"
                results.append((label, matched))

                if matched:
                    sid = get_or_create_student(conn, label)
                    log_attendance(conn, sid, last_logged, label)

        process_this_frame = not process_this_frame

        # Scale locations back to full frame
        scale = 1 / FRAME_SCALE
        for (top, right, bottom, left), (label, matched) in zip(locs, results):
            t, r, b, l = (int(v * scale) for v in (top, right, bottom, left))
            draw_label(frame, label, t, r, b, l, matched)

        # HUD
        ts = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        cv2.putText(frame, ts, (10, 25), cv2.FONT_HERSHEY_SIMPLEX,
                    0.6, (200, 200, 200), 1)
        cv2.putText(frame, "Smart Attendance System", (10, frame.shape[0] - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)

        cv2.imshow("Smart Attendance  |  Q = quit", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("\nSession ended.")


# ─────────────────────────────────────────────────────────────
#  REPORT
# ─────────────────────────────────────────────────────────────
def print_report(conn: sqlite3.Connection, target_date: str | None = None):
    d = target_date or date.today().isoformat()
    rows = conn.execute("""
        SELECT s.name, a.timestamp, a.status
        FROM attendance a
        JOIN students s ON s.id = a.student_id
        WHERE a.date = ?
        ORDER BY a.timestamp
    """, (d,)).fetchall()

    print(f"\n{'='*48}")
    print(f"  Attendance Report — {d}")
    print(f"{'='*48}")
    if not rows:
        print("  No attendance records for this date.")
    else:
        for name, ts, status in rows:
            print(f"  {status:<10} {name:<20} {ts}")
    print(f"{'='*48}\n")


# ─────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Smart Attendance System")
    group  = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--register", action="store_true",
                       help="Register a new face")
    group.add_argument("--run",      action="store_true",
                       help="Run live attendance tracking")
    group.add_argument("--report",   action="store_true",
                       help="Print attendance report")
    parser.add_argument("--name",    help="Name for --register")
    parser.add_argument("--date",    help="YYYY-MM-DD for --report (default: today)")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    if args.register:
        if not args.name:
            sys.exit("❌  Provide --name when using --register")
        register_face(args.name, conn)
    elif args.run:
        run_attendance(conn)
    elif args.report:
        print_report(conn, args.date)

    conn.close()


if __name__ == "__main__":
    main()
