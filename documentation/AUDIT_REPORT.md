# Comprehensive Security & Code Audit Report
**Project:** FRT (Face Recognition System)  
**Auditor:** Senior Full-Stack Security Architect  
**Date:** November 28, 2025  
**Target:** Production Deployment (Indian Police Department)

---

## 1. Executive Summary
This audit identifies critical security vulnerabilities, performance bottlenecks, and code quality issues in the FRT system. The most severe finding is a **Path Traversal vulnerability** in multiple endpoints, allowing potential unauthorized file access. The system also suffers from **race conditions** in model loading and **inefficient file-based database** operations that will not scale in a production environment.

**Compliance Status:**
- **Numpy Version:** Enforced `numpy==1.26.4` in `requirements.txt`.
- **Hardware Constraints:** Current implementation is heavy on CPU/RAM due to redundant model loading. Optimizations are required for low-end hardware.

---

## 2. Critical Security Vulnerabilities (High Priority)

### 2.1. Path Traversal (Critical)
**Location:** `app.py` (Routes: `/person/<person_id>`, `/update_person/<person_id>`, `/delete_person/<person_id>`, `/surveillance/start/...`, `/surveillance/stop/...`, `/alerts/view/...`)
**Issue:** The `person_id` parameter is taken directly from the URL and used in `os.path.join` without sanitization.
**Risk:** An attacker can manipulate `person_id` (e.g., `../../etc/passwd%00`) to access arbitrary files on the server, although the current code appends `.json`, limiting the scope to JSON files. However, accessing other internal JSON configuration files is possible.
**Fix:**
```python
from werkzeug.utils import secure_filename

# In all routes using person_id:
person_id = secure_filename(person_id)
json_path = os.path.join(app.config['PERSONS_FOLDER'], f"{person_id}.json")
```

### 2.2. Hardcoded Secrets (High)
**Location:** `app.py` (Line 14)
**Issue:** `app.secret_key = 'supersecretkey'` is hardcoded.
**Risk:** Session hijacking if the key is compromised.
**Fix:** Use environment variables.
```python
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))
```

### 2.3. Missing CSRF Protection (High)
**Location:** All `POST` forms (`add_person`, `update_person`, etc.)
**Issue:** No CSRF tokens are implemented.
**Risk:** Attackers can trick logged-in officers into performing actions (adding/deleting suspects) without their consent.
**Fix:** Integrate `Flask-WTF` and add `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>` to all forms.

### 2.4. Insecure Direct Object References (IDOR) / Data Integrity
**Location:** `surveillance_system.py` -> `save_alert`
**Issue:** The system writes alert files based on `person_id` derived from the in-memory metadata. While less risky than user input, ensuring `person_id` is safe for filesystem usage is crucial.
**Fix:** Apply `secure_filename` before file operations in `save_alert`.

---

## 3. Bug Detection & Logic Errors

### 3.1. Race Condition in Model Loading
**Location:** `face_utils.py` and `surveillance_system.py`
**Issue:** Models are loaded using global variables or instance-specific re-initialization without proper locking in `face_utils.py`. In `surveillance_system.py`, `VideoCamera` re-initializes models, leading to double memory usage.
**Fix:** Implement a Singleton pattern for model loading in a separate module (`model_loader.py`) and share the instance.

### 3.2. Alert Logic Flaw
**Location:** `surveillance_system.py` (Line 280-290)
**Issue:** `if current_match_percentage > alert_data.get('best_match_percentage', 0):`
This logic prevents saving a new detection if it has a lower confidence score than the historical best. A suspect might be detected with 90% confidence today, but if they were detected with 95% last year, today's detection is ignored.
**Fix:** Remove the condition or change it to a threshold check (e.g., `> 0.6`). Always append to history if it matches the identity.

### 3.3. JSON Database Scalability
**Location:** Entire Backend
**Issue:** Using flat JSON files for storage (`data/persons/*.json`) is acceptable for a prototype but will fail under load (file locks, read/write latency).
**Fix:** For production, migrate to SQLite or PostgreSQL. If JSON must be used, implement a file-locking mechanism (e.g., `filelock` library).

---

## 4. Duplicate & Dead Code

### 4.1. Redundant Model Initialization
**Files:** `face_utils.py`, `surveillance_system.py`, `convert.py`
**Issue:** All three files contain identical or similar code to load Dlib and ArcFace models.
**Fix:** Centralize model loading in `face_utils.py` or a new `models.py`.

### 4.2. Duplicate Image Reading Logic
**Files:** `face_utils.py`, `convert.py`
**Issue:** `read_image` function is duplicated.
**Fix:** Import `read_image` from `face_utils.py` in `convert.py`.

### 4.3. Unused/Test Code
**Files:** `convert.py`
**Issue:** This appears to be a development script.
**Recommendation:** Move to a `scripts/` or `tools/` directory and exclude from production deployment.

---

## 5. Performance Optimization

### 5.1. Model Lazy Loading
**Current:** Models load on import or first use, blocking the main thread.
**Optimization:** Load models in a background thread upon server start, or keep them loaded in memory (Singleton) to avoid reloading per request (if using CGI/worker pattern).

### 5.2. Image Processing
**Current:** `surveillance_system.py` resizes frames for processing.
**Optimization:** Ensure `SCALE_FACTOR` is tuned for low-end hardware. Use `cv2.INTER_NEAREST` for faster resizing if high precision isn't needed for the downscale.

### 5.3. Frontend Assets
**Current:** Images are served directly via Flask (`send_from_directory`).
**Optimization:** In production, use Nginx/Apache to serve `static/` and `data/images/` folders directly. Flask is slow for static file serving.

---

## 6. Production Readiness Checklist

- [x] **Dependency Locking:** `requirements.txt` created with `numpy==1.26.4`.
- [ ] **Logging:** Replace `print()` statements in `app.py` with `logging` module.
- [ ] **Error Boundaries:** Wrap `app.run()` in a try-except block to log crashes.
- [ ] **Offline Support:** The system relies on local models, which is good. Ensure no external CDNs are used for CSS/JS (FontAwesome is currently loaded from CDN in `layout.html`). **Fix:** Download FontAwesome assets locally.
- [ ] **Accessibility:** Add `alt` tags to all images in templates.

---

## 7. Recommended Project Structure

```
FRT/
├── app.py                  # Main Flask App
├── config.py               # Configuration (Secret keys, paths)
├── requirements.txt        # Dependencies
├── wsgi.py                 # Entry point for Gunicorn
├── core/
│   ├── __init__.py
│   ├── models.py           # Singleton Model Loader
│   ├── face_utils.py       # Face processing logic
│   └── surveillance.py     # Background thread logic
├── data/                   # Storage (GitIgnore this in prod)
├── static/                 # CSS, JS, Images
├── templates/              # HTML
└── documentation/          # Audit reports & guides
```

## 8. Deployment Instructions

1.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
2.  **Environment Setup:**
    Set `FLASK_APP=app.py`
    Set `FLASK_ENV=production`
    Set `SECRET_KEY=<random_string>`
3.  **Run with Gunicorn (Linux):**
    ```bash
    gunicorn -w 1 -b 0.0.0.0:5000 app:app
    ```
    *Note: Use 1 worker because of the global `camera_instance` and model memory usage.*

---

**Signed,**
**GitHub Copilot**
**Senior Full-Stack Security Architect**
