# 🎓 Smart Attendance System — Face Recognition

An automated attendance system using **Python**, **OpenCV**, **Flask**, and **SQLite**.  
Detects and recognizes faces in real time via webcam and logs attendance into a database.  
Includes a full **web dashboard** accessible from any browser on the same network.

---

## 📸 Features

-  Real-time face detection and recognition via webcam
-  Web-based dashboard (Flask) — no CMD needed after setup
-  Register new faces directly from the browser
-  Attendance auto-logged to SQLite with timestamp
-  Cooldown system — prevents duplicate entries
-  View attendance by date with filters
-  Export attendance records as CSV
-  Live camera feed with bounding boxes in browser
-  Weekly attendance bar chart on dashboard

---

## 🛠️ Tech Stack

| Layer       | Technology                        |
|-------------|-----------------------------------|
| Language    | Python 3.10+                      |
| Face AI     | face_recognition, dlib            |
| Computer Vision | OpenCV                        |
| Web Server  | Flask                             |
| Database    | SQLite3                           |
| Frontend    | HTML, CSS, JavaScript             |

---

## 📁 Project Structure

```
Smart-Attendance-System/
├── app.py                  ← Flask web server (main entry point)
├── attendance_system.py    ← CLI-based core (register / run / report)
├── dashboard.py            ← Static HTML report generator
├── requirements.txt        ← Python dependencies
├── templates/
│   └── index.html          ← Web dashboard UI
├── encodings/              ← Auto-created: stores face encodings (.pkl)
├── photos/                 ← Auto-created: reserved for captures
└── attendance.db           ← Auto-created: SQLite database
```

---

## ⚙️ Installation

### 1. Clone the repository
```bash
git clone https://github.com/ved2a/Smart-Attendance-System.git
cd Smart-Attendance-System
```

### 2. Install dependencies

**On Windows (recommended):**
```bash
pip install dlib-bin
pip install face_recognition --no-deps
pip install face-recognition-models click colorama
pip install opencv-python flask numpy pillow
```

**On Linux/macOS:**
```bash
pip install -r requirements.txt
```

> **Note:** On Windows, always install `dlib-bin` first before `face_recognition` to avoid build errors.

---

## 🚀 Usage

### Option A — Web Dashboard (Recommended)

```bash
python app.py
```
Then open **http://localhost:5000** in your browser.

| Page | What you can do |
|------|----------------|
| Dashboard | View live camera feed + today's log + weekly chart |
| Register Face | Add new students via webcam |
| Attendance | Filter records by date |
| Students | View all registered students |
| Export CSV | Download last 30 days attendance |

---

### Option B — Command Line

**Register a new face:**
```bash
python attendance_system.py --register --name "Vedant"
```

**Start live attendance:**
```bash
python attendance_system.py --run
# Press Q to quit
```

**View today's report:**
```bash
python attendance_system.py --report
```

**View report for specific date:**
```bash
python attendance_system.py --report --date 2026-06-20
```

**Generate HTML report:**
```bash
python dashboard.py
python dashboard.py --export    # also exports CSV
```

---

## 🗄️ Database Schema

```sql
-- Students table
CREATE TABLE students (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT NOT NULL UNIQUE,
    reg_date TEXT NOT NULL
);

-- Attendance table
CREATE TABLE attendance (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    timestamp  TEXT NOT NULL,
    date       TEXT NOT NULL,
    status     TEXT DEFAULT 'PRESENT',
    FOREIGN KEY (student_id) REFERENCES students(id)
);
```

---

## 🧠 How It Works

```
Webcam Frame
     │
     ▼
Resize to 50% (for speed)
     │
     ▼
face_recognition.face_locations()   ← finds face positions
     │
     ▼
face_recognition.face_encodings()   ← generates 128-D vector
     │
     ▼
Compare with stored encodings (Euclidean / L2 distance)
     │
     ├── distance < 0.5  →  MATCH  →  Log to SQLite  →  Green box
     │
     └── distance ≥ 0.5  →  UNKNOWN  →  Red box
```

---

## 🔧 Configuration

Edit these constants at the top of `app.py` or `attendance_system.py`:

| Variable | Default | Description |
|----------|---------|-------------|
| `TOLERANCE` | `0.5` | Match threshold — lower is stricter |
| `FRAME_SCALE` | `0.5` | Frame resize factor for speed |
| `COOLDOWN_SEC` | `60` | Seconds before same person is re-logged |

---

## 💡 Tips

- Register faces in the **same lighting** as the attendance environment
- Keep camera at **eye level** for best detection accuracy
- Use `TOLERANCE = 0.4` for stricter matching (fewer false positives)
- Access dashboard from **any device on the same WiFi** via `http://192.168.x.x:5000`

---

## 👤 Author

**Vedant Akare**  
B.Tech CSE-IoT | YCCE Nagpur  
GitHub: [@ved2a](https://github.com/ved2a)

---

## 📄 License

This project is licensed under the MIT License.
