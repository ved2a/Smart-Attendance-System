"""
Smart Attendance System — Flask Web Dashboard (Fixed: single camera thread)
Run: python app.py
Open: http://localhost:5000
"""

from flask import Flask, Response, render_template, jsonify, request, send_file
import cv2, face_recognition, numpy as np
import sqlite3, pickle, csv, io, threading, time
from datetime import datetime, date, timedelta
from pathlib import Path

app = Flask(__name__)

# ── Config ──────────────────────────────────────────────────
DB_PATH       = "attendance.db"
ENCODINGS_DIR = Path("encodings")
TOLERANCE     = 0.5
COOLDOWN_SEC  = 60

# ── Globals ─────────────────────────────────────────────────
known_names   = []
known_encs    = []
last_logged   = {}

# ── Single shared camera thread ──────────────────────────────
class CameraStream:
    def __init__(self):
        self.cap        = None
        self.frame      = None
        self.lock       = threading.Lock()
        self.running    = False
        self.thread     = None
        self.mode       = "attend"   # "attend" | "register"

    def start(self):
        if self.running:
            return
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            raise RuntimeError("Cannot open camera")
        self.running = True
        self.thread  = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()

    def _read_loop(self):
        while self.running:
            ok, frame = self.cap.read()
            if ok:
                with self.lock:
                    self.frame = frame.copy()
            time.sleep(0.03)

    def get_frame(self):
        with self.lock:
            return None if self.frame is None else self.frame.copy()

    def stop(self):
        self.running = False
        if self.cap:
            self.cap.release()

stream = CameraStream()

# ── DB ──────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS students (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name     TEXT NOT NULL UNIQUE,
            reg_date TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS attendance (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            timestamp  TEXT NOT NULL,
            date       TEXT NOT NULL,
            status     TEXT DEFAULT 'PRESENT',
            FOREIGN KEY (student_id) REFERENCES students(id)
        );
        CREATE INDEX IF NOT EXISTS idx_att_date ON attendance(date);
    """)
    conn.commit(); conn.close()

def get_or_create_student(conn, name):
    row = conn.execute("SELECT id FROM students WHERE name=?", (name,)).fetchone()
    if row: return row["id"]
    conn.execute("INSERT INTO students(name,reg_date) VALUES(?,?)",
                 (name, date.today().isoformat()))
    conn.commit()
    return conn.execute("SELECT id FROM students WHERE name=?", (name,)).fetchone()["id"]

# ── Encodings ────────────────────────────────────────────────
def reload_encodings():
    global known_names, known_encs
    names, encs = [], []
    ENCODINGS_DIR.mkdir(exist_ok=True)
    for f in ENCODINGS_DIR.glob("*.pkl"):
        with open(f, "rb") as fh:
            encs.append(pickle.load(fh))
        names.append(f.stem)
    known_names, known_encs = names, encs

def save_encoding(name, enc):
    ENCODINGS_DIR.mkdir(exist_ok=True)
    with open(ENCODINGS_DIR / f"{name}.pkl", "wb") as f:
        pickle.dump(enc, f)
    reload_encodings()

# ── Frame processor (attend mode) ───────────────────────────
def process_frame_attend(frame):
    small = cv2.resize(frame, (0,0), fx=0.5, fy=0.5)
    rgb   = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
    locs  = face_recognition.face_locations(rgb, model="hog")
    encs  = face_recognition.face_encodings(rgb, locs)

    for enc, (t,r,b,l) in zip(encs, locs):
        t2,r2,b2,l2 = t*2, r*2, b*2, l*2

        if known_encs:
            dists   = face_recognition.face_distance(known_encs, enc)
            best    = int(np.argmin(dists))
            matched = dists[best] < TOLERANCE
            label   = known_names[best] if matched else "Unknown"
            color   = (34,197,94) if matched else (239,68,68)

            if matched:
                conn = get_db()
                sid  = get_or_create_student(conn, label)
                now  = datetime.now()
                last = last_logged.get(sid)
                if not last or (now-last).total_seconds() > COOLDOWN_SEC:
                    conn.execute(
                        "INSERT INTO attendance(student_id,timestamp,date) VALUES(?,?,?)",
                        (sid, now.isoformat(timespec="seconds"), date.today().isoformat())
                    )
                    conn.commit()
                    last_logged[sid] = now
                conn.close()
        else:
            label = "No faces registered"
            color = (99,102,241)

        cv2.rectangle(frame, (l2,t2), (r2,b2), color, 2)
        cv2.rectangle(frame, (l2,b2-28), (r2,b2), color, cv2.FILLED)
        cv2.putText(frame, label, (l2+5, b2-8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1)

    cv2.putText(frame, datetime.now().strftime("%H:%M:%S"),
                (10,25), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200,200,200), 1)
    return frame

def process_frame_register(frame):
    small = cv2.resize(frame, (0,0), fx=0.5, fy=0.5)
    rgb   = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
    locs  = face_recognition.face_locations(rgb, model="hog")

    for (t,r,b,l) in locs:
        t2,r2,b2,l2 = t*2, r*2, b*2, l*2
        cv2.rectangle(frame, (l2,t2), (r2,b2), (99,102,241), 2)
        cv2.rectangle(frame, (l2,b2-28), (r2,b2), (99,102,241), cv2.FILLED)
        cv2.putText(frame, "Position face here", (l2+5, b2-8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255,255,255), 1)

    cv2.putText(frame, "REGISTER MODE", (10,25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (99,102,241), 2)
    return frame

# ── MJPEG generators (both read from same stream) ────────────
def gen_attend():
    while True:
        frame = stream.get_frame()
        if frame is None:
            time.sleep(0.05); continue
        frame = process_frame_attend(frame)
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
               + buf.tobytes() + b"\r\n")
        time.sleep(0.04)

def gen_register():
    while True:
        frame = stream.get_frame()
        if frame is None:
            time.sleep(0.05); continue
        frame = process_frame_register(frame)
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
               + buf.tobytes() + b"\r\n")
        time.sleep(0.04)

# ── Routes ───────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/video_feed")
def video_feed():
    return Response(gen_attend(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/register_feed")
def register_feed():
    return Response(gen_register(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")

# ── Registration ─────────────────────────────────────────────
register_state = {"samples": [], "name": None, "status": "idle"}

@app.route("/api/register/start", methods=["POST"])
def register_start():
    name = request.json.get("name", "").strip()
    if not name:
        return jsonify(ok=False, msg="Name is required")
    register_state["name"]    = name
    register_state["samples"] = []
    register_state["status"]  = "collecting"
    return jsonify(ok=True, msg=f"Capturing samples for {name}…")

@app.route("/api/register/capture", methods=["POST"])
def register_capture():
    if register_state["status"] != "collecting":
        return jsonify(ok=False, msg="Start registration first")

    frame = stream.get_frame()
    if frame is None:
        return jsonify(ok=False, msg="Camera not ready, try again")

    rgb  = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    locs = face_recognition.face_locations(rgb, model="hog")
    encs = face_recognition.face_encodings(rgb, locs)

    if len(encs) == 0:
        return jsonify(ok=False, msg="No face detected — move closer")
    if len(encs) > 1:
        return jsonify(ok=False, msg="Multiple faces detected — only one person please")

    register_state["samples"].append(encs[0])
    count = len(register_state["samples"])

    if count >= 5:
        avg  = np.mean(register_state["samples"], axis=0)
        name = register_state["name"]
        save_encoding(name, avg)
        conn = get_db()
        get_or_create_student(conn, name)
        conn.close()
        register_state["status"] = "idle"
        return jsonify(ok=True, done=True, msg=f"✅ {name} registered!", count=count)

    return jsonify(ok=True, done=False, msg=f"Sample {count}/5 captured — click again", count=count)

# ── Attendance API ────────────────────────────────────────────
@app.route("/api/attendance")
def api_attendance():
    target = request.args.get("date", date.today().isoformat())
    conn   = get_db()
    rows   = conn.execute("""
        SELECT s.name, a.timestamp, a.status
        FROM attendance a JOIN students s ON s.id=a.student_id
        WHERE a.date=? ORDER BY a.timestamp DESC
    """, (target,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/stats")
def api_stats():
    conn    = get_db()
    today   = date.today().isoformat()
    total   = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    present = conn.execute(
        "SELECT COUNT(DISTINCT student_id) FROM attendance WHERE date=?", (today,)
    ).fetchone()[0]
    week_ago = (date.today()-timedelta(days=6)).isoformat()
    daily    = conn.execute("""
        SELECT date, COUNT(DISTINCT student_id) as cnt
        FROM attendance WHERE date>=? GROUP BY date ORDER BY date
    """, (week_ago,)).fetchall()
    conn.close()
    return jsonify(
        total=total, present=present, absent=total-present,
        rate=round(present/total*100) if total else 0,
        daily=[dict(r) for r in daily]
    )

@app.route("/api/students")
def api_students():
    conn = get_db()
    rows = conn.execute("SELECT name, reg_date FROM students ORDER BY name").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

# ── CSV Export ────────────────────────────────────────────────
@app.route("/api/export")
def export_csv():
    days  = int(request.args.get("days", 30))
    since = (date.today()-timedelta(days=days-1)).isoformat()
    conn  = get_db()
    rows  = conn.execute("""
        SELECT s.name, a.date, a.timestamp, a.status
        FROM attendance a JOIN students s ON s.id=a.student_id
        WHERE a.date>=? ORDER BY a.date DESC, s.name
    """, (since,)).fetchall()
    conn.close()

    buf = io.StringIO()
    w   = csv.writer(buf)
    w.writerow(["Name", "Date", "Time", "Status"])
    for r in rows:
        w.writerow([r["name"], r["date"], r["timestamp"][11:19], r["status"]])

    out = io.BytesIO(buf.getvalue().encode())
    out.seek(0)
    return send_file(out, mimetype="text/csv",
                     as_attachment=True,
                     download_name=f"attendance_{date.today()}.csv")

if __name__ == "__main__":
    init_db()
    reload_encodings()
    stream.start()
    print("\n🎓  Smart Attendance System (Fixed)")
    print("   Open http://localhost:5000 in your browser\n")
    app.run(debug=False, host="0.0.0.0", port=5000, threaded=True)
