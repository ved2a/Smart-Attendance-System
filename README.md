# Smart Attendance System — Face Recognition + SQLite

A complete attendance system using OpenCV, `face_recognition`, and SQLite.
No cloud, no subscription — runs entirely on your local machine.

---

## Project Structure

```
attendance_system/
├── attendance_system.py   ← core: register / live recognition / report
├── dashboard.py           ← HTML dashboard + CSV export
├── requirements.txt
├── attendance.db          ← auto-created SQLite database
├── encodings/             ← auto-created, stores .pkl face encodings
└── photos/                ← auto-created, reserved for raw captures
```

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

> **Note on `dlib` (required by `face_recognition`):**
> On Windows, install the prebuilt wheel:
> ```
> pip install dlib-bin
> ```
> On Linux/macOS `dlib` builds from source — requires `cmake` and a C++ compiler.

---

## Usage

### Register a new person
Opens your webcam, captures 5 face samples, then saves the encoding.

```bash
python attendance_system.py --register --name "Alice"
python attendance_system.py --register --name "Bob"
```

### Run live attendance
Opens webcam, continuously recognizes faces, logs to SQLite.
Same person is NOT re-logged within 60 seconds (configurable via `COOLDOWN_SEC`).

```bash
python attendance_system.py --run
# Press Q to quit
```

### Print terminal report (today)
```bash
python attendance_system.py --report
```

### Print terminal report (specific date)
```bash
python attendance_system.py --report --date 2025-06-19
```

---

## Dashboard

Generates a dark-themed HTML dashboard + optional CSV:

```bash
python dashboard.py                     # today's report → report.html
python dashboard.py --date 2025-06-19  # specific date
python dashboard.py --export            # also writes attendance_export.csv
```

Open `report.html` in any browser.

---

## Database Schema

```sql
-- students table
id        INTEGER PRIMARY KEY
name      TEXT UNIQUE NOT NULL
reg_date  TEXT

-- attendance table
id          INTEGER PRIMARY KEY
student_id  INTEGER → students.id
timestamp   TEXT (ISO 8601, seconds)
date        TEXT (YYYY-MM-DD)
status      TEXT DEFAULT 'PRESENT'
```

---

## Configuration (attendance_system.py top)

| Variable       | Default | Description                              |
|----------------|---------|------------------------------------------|
| `TOLERANCE`    | `0.5`   | Face match threshold (lower = stricter)  |
| `FRAME_SCALE`  | `0.5`   | Downscale factor for speed               |
| `COOLDOWN_SEC` | `60`    | Seconds before same person re-logged     |

---

## How It Works

```
Camera frame
    │
    ▼
Resize (FRAME_SCALE) ──▶ face_recognition.face_locations()
                                    │
                                    ▼
                         face_recognition.face_encodings()
                                    │
                                    ▼
                     Compare vs. stored encodings (L2 distance)
                                    │
                         ┌──────────┴──────────┐
                    distance < 0.5          distance ≥ 0.5
                    (MATCHED)               (UNKNOWN)
                         │
                         ▼
                 Log to SQLite (with cooldown)
                 Draw green box + name
```

---

## Tips

- Register in the same lighting you'll use for attendance.
- For groups, position the camera at eye level.
- `TOLERANCE = 0.4` gives fewer false positives (stricter).
- Use `model="cnn"` in `face_locations()` for GPU-accelerated accuracy.
