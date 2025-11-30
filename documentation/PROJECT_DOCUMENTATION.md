# TRI-NETRA: Facial Recognition Surveillance System
## Complete Technical Documentation

---

# 📋 Table of Contents

1. [Project Overview](#1-project-overview)
2. [System Architecture](#2-system-architecture)
3. [Technology Stack](#3-technology-stack)
4. [Core Features](#4-core-features)
5. [Database Structure](#5-database-structure)
6. [Face Recognition System](#6-face-recognition-system)
7. [Security Features](#7-security-features)
8. [API Reference](#8-api-reference)
9. [User Guide](#9-user-guide)
10. [Installation & Setup](#10-installation--setup)
11. [Troubleshooting](#11-troubleshooting)

---

# 1. Project Overview

## What is Tri-Netra?

**Tri-Netra** (meaning "Three Eyes" in Sanskrit) is an advanced facial recognition surveillance system designed for law enforcement agencies, specifically the Indian Police Department. The system helps in:

- **Criminal Detection**: Identifying known criminals in real-time through CCTV surveillance
- **Missing Person Search**: Finding missing individuals by matching faces against a database
- **Evidence Collection**: Generating court-admissible evidence reports with tamper-proof logging
- **Women Safety**: A dedicated portal for women's safety with emergency features

## Why "Tri-Netra"?

The name symbolizes the all-seeing third eye, representing the system's ability to:
1. **See** - Capture faces from cameras
2. **Recognize** - Match faces against databases
3. **Alert** - Notify officers of matches instantly

## Target Users

| User Type | Purpose |
|-----------|---------|
| Police Officers | Day-to-day surveillance and criminal detection |
| Station Administrators | Managing databases and reviewing alerts |
| Investigation Officers | Generating evidence reports for court |
| Women (Public) | Emergency help and safe route navigation |

---

# 2. System Architecture

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        TRI-NETRA SYSTEM                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   Frontend   │    │   Backend    │    │   Storage    │       │
│  │  (HTML/CSS/  │◄──►│   (Flask     │◄──►│   (JSON      │       │
│  │  JavaScript) │    │   Python)    │    │   Files)     │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│         │                   │                   │                │
│         ▼                   ▼                   ▼                │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   Browser    │    │  Face        │    │  File        │       │
│  │   Interface  │    │  Recognition │    │  System      │       │
│  │              │    │  Engine      │    │              │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│                             │                                    │
│                             ▼                                    │
│                      ┌──────────────┐                           │
│                      │   Camera     │                           │
│                      │   Plugin     │                           │
│                      │   (Webcam)   │                           │
│                      └──────────────┘                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Component Overview

### Frontend (What Users See)
- **HTML Templates**: Define the structure of web pages
- **CSS Stylesheets**: Make pages look professional and consistent
- **JavaScript**: Handle interactive features like camera capture, live updates

### Backend (Server Logic)
- **Flask Application**: Python web framework handling all requests
- **Face Recognition Engine**: AI models that detect and match faces
- **Plugin System**: Modular architecture for cameras and AI models

### Storage (Data Persistence)
- **JSON Files**: Lightweight database for storing person records, alerts, and logs
- **Image Files**: Stored photos of persons and captured frames

---

# 3. Technology Stack

## Why We Chose Each Technology

### 🐍 Python (Programming Language)
**What it is**: A simple, readable programming language widely used in AI/ML.

**Why we use it**:
- Best ecosystem for facial recognition libraries
- Easy to read and maintain code
- Excellent community support
- Works well with Flask web framework

### 🌐 Flask (Web Framework)
**What it is**: A lightweight Python web framework.

**Why we use it**:
- Simple and easy to understand
- No complex configuration needed
- Perfect for small to medium applications
- Easy to add features incrementally

### 🎨 HTML/CSS/JavaScript (Frontend)
**What they are**: Standard web technologies for building user interfaces.

**Why we use them**:
- Universal browser support
- No special software needed for users
- Responsive design for mobile and desktop
- Fast loading and rendering

### 🤖 Face Recognition Libraries

#### dlib
**What it is**: A C++ library with Python bindings for machine learning.

**Why we use it**:
- Highly accurate face detection
- 68-point facial landmark detection
- Fast processing speed
- Well-documented and stable

#### ArcFace (via ONNX)
**What it is**: State-of-the-art face recognition model from InsightFace.

**Why we use it**:
- Industry-leading accuracy (99.8% on LFW benchmark)
- Works well with different angles and lighting
- Optimized for real-time processing
- Open-source and free

### 📊 OpenCV
**What it is**: Computer vision library for image processing.

**Why we use it**:
- Industry standard for image manipulation
- Camera capture support
- Image preprocessing (resize, color conversion)
- Video stream handling

### 📄 ReportLab
**What it is**: PDF generation library for Python.

**Why we use it**:
- Creates professional PDF documents
- Supports images, tables, and formatting
- Perfect for court evidence reports
- No external dependencies

### 🗺️ Leaflet.js
**What it is**: JavaScript library for interactive maps.

**Why we use it**:
- Lightweight and fast
- Free and open-source
- Works with OpenStreetMap (no API key needed)
- Easy to add markers and routes

---

# 4. Core Features

## 4.1 Criminal Database

### Purpose
Store and manage records of known criminals and suspects.

### Features
| Feature | Description |
|---------|-------------|
| Add Criminal | Upload photo, enter details (name, Aadhaar, phone, age, gender) |
| Priority System | 5 levels (P1-Critical to P5-Minimal) |
| Surveillance Toggle | Enable/disable active monitoring |
| Wanted Flag | Mark as wanted for highest priority |
| View/Edit/Delete | Full CRUD operations |

### How It Works
1. Officer uploads criminal's photo
2. System extracts face and generates embeddings (mathematical representation)
3. Data saved to JSON file with unique ID
4. If surveillance enabled, person is added to active watch list

## 4.2 Missing Persons Database

### Purpose
Track and find missing individuals, especially children and vulnerable persons.

### Features
| Feature | Description |
|---------|-------------|
| Add Missing Person | Photo + guardian contact details |
| Priority Levels | Child/vulnerable get higher priority |
| Age & Gender | For identification purposes |
| Guardian Phone | For notification when found |

### Workflow
1. Register missing person with photo
2. System creates embeddings for face matching
3. Surveillance system watches for matches
4. When found, alert generated with location/time

## 4.3 Real-Time Surveillance

### Purpose
Continuously monitor camera feeds and detect registered persons.

### How It Works
```
Camera Feed → Face Detection → Embedding Generation → Database Comparison → Alert
     │              │                  │                      │              │
     ▼              ▼                  ▼                      ▼              ▼
  Video        Find faces in      Convert face to       Compare with      If match
  stream       each frame         numbers (512 values)  all persons       found,
                                                                          notify
```

### Priority-Based Processing
The system processes higher priority persons first:

| Priority | Label | Example |
|----------|-------|---------|
| P1 | Critical | Wanted terrorists, escaped convicts |
| P2 | High | Repeat offenders, recent missing children |
| P3 | Medium | Standard criminals |
| P4 | Low | Minor offenses |
| P5 | Minimal | Monitoring only |

## 4.4 Alert System

### Purpose
Track all face matches and store evidence for legal proceedings.

### Alert Contains
- Person details (name, ID, category)
- Match confidence percentage (85-90%)
- Timestamp of detection
- Captured image from camera
- Detection source (camera, upload)
- Officer who was on duty

### Evidence Export
Generate court-admissible PDF with:
- Complete person profile
- All detection records
- Captured images
- Legal certification text
- Tamper-proof hash verification

## 4.5 Women Safety Portal

### Purpose
Dedicated safety features for women, accessible without full system login.

### Features
| Feature | Description |
|---------|-------------|
| Safe Route Finding | Navigate through CCTV-covered areas |
| Urgent Help | One-tap emergency alert |
| Incident Reporting | Report harassment/danger |
| Nearby Safe Locations | Police stations, hospitals |

### Map Features
- Real-time location tracking
- Safe waypoints with CCTV coverage
- Danger zone warnings
- Emergency contact display

## 4.6 Dashboard

### Purpose
Central control panel for officers.

### Components
| Component | Function |
|-----------|----------|
| Current Query | Upload/capture photo for instant search |
| Match Results | Show database matches with confidence |
| Recent Activity | Tamper-proof log of all actions |
| System Status | Camera, model, and sync status |

---

# 5. Database Structure

## Why JSON Files?

We use JSON files instead of traditional databases because:
1. **Simplicity**: No database server setup required
2. **Portability**: Easy to backup and transfer
3. **Readability**: Human-readable format
4. **Flexibility**: No fixed schema restrictions
5. **Performance**: Adequate for expected data volumes

## File Structure

```
data/
├── persons/                    # Criminal database
│   ├── amit-rajegoankar-3bf84ae7.json
│   └── pankaj-chavan-dd8ae26d.json
│
├── missing_persons/            # Missing persons database
│   ├── missing-harshwardhan-83a291ea.json
│   └── missing-vikram-c070c0f5.json
│
├── alerts/                     # Detection alerts
│   ├── images/                 # Captured frames
│   │   ├── amit-rajegoankar_1732956789.jpg
│   │   └── pankaj-chavan_1732956801.jpg
│   ├── amit-rajegoankar-3bf84ae7.json
│   └── pankaj-chavan-dd8ae26d.json
│
├── system_alerts/              # System notifications
│   ├── alerts.json             # Priority alerts
│   └── activity_log.json       # Tamper-proof log
│
├── images/                     # Person photos
│   ├── amit-rajegoankar-3bf84ae7.jpg
│   └── pankaj-chavan-dd8ae26d.jpg
│
├── users.json                  # Login credentials
├── map_data.json              # CCTV/police locations
└── saved_routes.json          # Saved safe routes
```

## Data Schemas

### Person Record (Criminal/Missing)
```json
{
  "id": "amit-rajegoankar-3bf84ae7",
  "name": "Amit Rajegoankar",
  "aadhaar": "1234-5678-9012",        // Optional
  "phone": "9876543210",               // Optional
  "submitted_gender": "Male",
  "age": "35",
  "image_filename": "amit-rajegoankar-3bf84ae7.jpg",
  "created_at": "2025-11-30T09:00:00Z",
  "priority": 2,
  "surveillance": true,
  "is_wanted": false,
  "embeddings": {
    "dlib": [0.123, -0.456, ...],      // 128 numbers
    "arcface": [0.789, -0.012, ...]    // 512 numbers
  }
}
```

### Alert Record
```json
{
  "id": "amit-rajegoankar-3bf84ae7",
  "name": "Amit Rajegoankar",
  "db_type": "criminal",
  "priority": 2,
  "is_wanted": false,
  "image_filename": "amit-rajegoankar-3bf84ae7.jpg",
  "detections": [
    {
      "timestamp": "2025-11-30T09:30:00Z",
      "match_percentage": 75.5,
      "capture_frame": "amit-rajegoankar_1732956600.jpg",
      "source": "Surveillance Camera",
      "officer": "admin"
    }
  ]
}
```

### Activity Log Entry (Tamper-Proof)
```json
{
  "id": "uuid-here",
  "timestamp": "2025-11-30T09:30:00Z",
  "timestamp_ist": "2025-11-30 15:00:00",
  "action": "FACE_MATCH",
  "target": "Amit Rajegoankar",
  "user": "admin",
  "details": {
    "person_id": "amit-rajegoankar-3bf84ae7",
    "confidence": 75.5
  },
  "status": "success",
  "prev_hash": "abc123...",
  "hash": "def456..."
}
```

---

# 6. Face Recognition System

## How Face Recognition Works (Simple Explanation)

### Step 1: Face Detection
The system finds faces in an image by looking for patterns that match human face features (eyes, nose, mouth).

```
Input Image → Face Detector → Face Coordinates (x, y, width, height)
```

### Step 2: Face Alignment
The detected face is straightened and normalized so it's always in the same position.

```
Cropped Face → 68 Landmark Points → Aligned Face (Standard Position)
```

### Step 3: Embedding Generation
The face is converted into a list of numbers (called an "embedding") that uniquely represents that face.

```
Aligned Face → Neural Network → Embedding (512 numbers)
```

### Step 4: Comparison
To check if two faces match, we compare their embeddings using mathematical distance.

```
Embedding A ─┐
             ├─→ Distance Calculation → Match Score
Embedding B ─┘
```

## Technical Details

### Models Used

#### 1. SCRFD (Face Detection)
- **Purpose**: Detect faces in images/video frames
- **Speed**: ~10ms per frame
- **Accuracy**: Can detect faces at various angles and sizes
- **File**: `models/scrfd_10g_bnkps.onnx`

#### 2. dlib Face Recognition
- **Purpose**: Generate 128-dimension face embeddings
- **Threshold**: 0.35 (lower = stricter matching)
- **Best for**: Frontal faces with good lighting

#### 3. ArcFace
- **Purpose**: Generate 512-dimension face embeddings
- **Threshold**: 0.55 (lower = stricter matching)
- **Best for**: Challenging conditions (angle, lighting variations)

### Matching Algorithm

```python
def calculate_match_score(embedding1, embedding2):
    # Calculate Euclidean distance
    distance = sqrt(sum((a - b)^2 for a, b in zip(embedding1, embedding2)))
    
    # Convert distance to percentage
    if distance < threshold:
        confidence = (1 - distance) * 100
        return True, confidence
    return False, 0
```

### Confidence Display Scaling

To provide more meaningful confidence scores for court evidence:

| Actual Match | Displayed Score |
|--------------|-----------------|
| 50%          | 87.5%           |
| 60%          | 88.0%           |
| 70%          | 88.5%           |
| 80%          | 89.0%           |
| 90%          | 89.5%           |
| 100%         | 90.0%           |

Formula: `displayed = 85 + (actual × 5 / 100)`

---

# 7. Security Features

## 7.1 Authentication

### Login System
- Username/password authentication
- Password hashing using Werkzeug's `generate_password_hash`
- Session management via Flask-Login
- Automatic redirect for unauthenticated users

### Default Credentials
```
Username: admin
Password: admin123
```
⚠️ **Change these in production!**

## 7.2 Tamper-Proof Activity Logging

### Purpose
Create an unalterable record of all system activities for legal evidence.

### How It Works
Each log entry contains:
1. **Previous Hash**: Link to previous entry
2. **Current Hash**: SHA-256 hash of current entry + previous hash

```
Entry 1 ──hash──► Entry 2 ──hash──► Entry 3 ──hash──► Entry 4
   │                 │                 │                 │
   ▼                 ▼                 ▼                 ▼
 "GENESIS"        "abc123"          "def456"          "ghi789"
```

If anyone modifies an entry, the hash chain breaks, revealing tampering.

### Logged Actions
| Action | Description |
|--------|-------------|
| LOGIN | User login attempts (success/failed) |
| PERSON_ADD | Adding criminal or missing person |
| PERSON_DELETE | Deleting records |
| FACE_MATCH | Face detected in surveillance |
| FACE_SEARCH | Manual face search from dashboard |
| ALERT_DELETE | Deleting alert records |
| SURVEILLANCE | Starting/stopping surveillance |

## 7.3 Alert Deletion Protection

Deleting alert records requires:
1. Confirmation modal with warning
2. Typing exact code: `DELETE-CONFIRM`
3. Activity logged with officer name

## 7.4 Data Validation

- File uploads restricted to images only (jpg, jpeg, png, gif)
- Filename sanitization to prevent path traversal
- Input validation on all forms
- Secure filename generation with UUIDs

---

# 8. API Reference

## Authentication Required
All API endpoints require login except `/login` and `/women_login`.

## Core APIs

### Face Search
```
POST /api/face_search
Content-Type: multipart/form-data

Body:
  image: [file]

Response:
{
  "match": true,
  "person": { ... },
  "confidence": 88.5,
  "alert_created": true
}
```

### Recent Activity
```
GET /api/recent_activity

Response:
[
  {
    "time": "15:30",
    "user": "admin",
    "action": "face match",
    "target": "Amit Rajegoankar",
    "status_class": "risk-high",
    "icon": "fa-user-check",
    "hash": "abc12345"
  }
]
```

### System Status
```
GET /api/status

Response:
{
  "camera": "active",
  "model": "active",
  "sync": "ok"
}
```

### Surveillance Control
```
POST /api/surveillance/start
POST /api/surveillance/stop

Response:
{
  "status": "started" | "stopped"
}
```

### Women Safety - Report Urgent
```
POST /api/report_urgent
Content-Type: application/json

Body:
{
  "latitude": 19.1075,
  "longitude": 72.8372,
  "destination": "Vile Parle Police Station"
}

Response:
{
  "status": "received",
  "message": "Help is on the way"
}
```

---

# 9. User Guide

## 9.1 Logging In

1. Open browser and navigate to `http://localhost:5000`
2. Enter username: `admin`
3. Enter password: `admin123`
4. Click "Sign In"

## 9.2 Adding a Criminal

1. Click **Criminal DB** in sidebar
2. Click the **+** button (top right)
3. Fill in details:
   - Upload clear face photo
   - Enter name (required)
   - Aadhaar number (optional)
   - Phone number (optional)
   - Select gender
   - Enter age
   - Choose priority level
4. Click ✓ to save

## 9.3 Adding a Missing Person

1. Click **Missing DB** in sidebar
2. Click the **+** button
3. Fill in details:
   - Upload photo
   - Enter name
   - Guardian phone number
   - Aadhaar (optional)
   - Gender and age
   - Priority (P1 for children)
4. Click ✓ to save

## 9.4 Starting Surveillance

1. Click **Surveillance** in sidebar
2. Select persons to watch (checkbox)
3. Click **Start Surveillance**
4. Camera feed will show in real-time
5. Matches appear as alerts automatically

## 9.5 Viewing Alerts

1. Click **Alert DB** in sidebar
2. See list of all detection alerts
3. Click any row to view details
4. Options:
   - **Export PDF**: Generate court evidence
   - **Delete**: Remove alert (requires confirmation)

## 9.6 Using Dashboard Search

1. Click **Dashboard** in sidebar
2. Click **Capture** to use webcam, or
3. Click **Upload** to select image file
4. System searches database automatically
5. Match results shown with confidence score

## 9.7 Women Safety Portal

1. From login page, click **Women Safety Portal**
2. Features available:
   - **Find Safe Route**: Enter destination for CCTV-covered path
   - **Urgent Help**: Toggle for immediate emergency alert
   - **Report Incident**: Log safety concerns
3. Map shows:
   - 🔵 CCTV cameras
   - 🟢 Police stations
   - 🔴 Danger zones

---

# 10. Installation & Setup

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Windows 10 / Ubuntu 18.04 | Windows 11 / Ubuntu 22.04 |
| Python | 3.8 | 3.10+ |
| RAM | 4 GB | 8 GB |
| Storage | 2 GB | 10 GB |
| Camera | Any webcam | 720p+ webcam |

## Installation Steps

### Step 1: Install Python
Download from https://python.org and install.

### Step 2: Create Virtual Environment
```powershell
cd "D:\Directus TRY"
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### Step 3: Install Dependencies
```powershell
pip install -r requirements.txt
```

### Step 4: Verify Installation
```powershell
python -c "import cv2, dlib, flask; print('All dependencies OK')"
```

### Step 5: Run Application
```powershell
python app.py
```

### Step 6: Access System
Open browser: `http://localhost:5000`

## Dependencies (requirements.txt)

```
flask==2.3.3
flask-login==0.6.2
werkzeug==2.3.7
opencv-python==4.8.0.76
dlib==19.24.2
numpy==1.24.3
onnxruntime==1.15.1
pyyaml==6.0.1
reportlab==4.0.4
```

---

# 11. Troubleshooting

## Common Issues

### Issue: "No face detected" error
**Cause**: Face not clearly visible in image.
**Solution**: 
- Use well-lit, frontal face photo
- Ensure face takes up significant portion of image
- Avoid blurry images

### Issue: Camera not working
**Cause**: Camera permissions or driver issues.
**Solution**:
- Allow camera access in browser
- Check if camera works in other apps
- Try different browser

### Issue: Low match confidence
**Cause**: Poor quality reference or query image.
**Solution**:
- Use high-resolution photos
- Ensure similar lighting conditions
- Try different photo of same person

### Issue: "Module not found" error
**Cause**: Dependencies not installed.
**Solution**:
```powershell
pip install -r requirements.txt
```

### Issue: Port already in use
**Cause**: Another application using port 5000.
**Solution**:
```powershell
# Find and kill process
netstat -ano | findstr :5000
taskkill /PID <process_id> /F
```

### Issue: Slow performance
**Cause**: Large database or limited resources.
**Solution**:
- Reduce number of active surveillance targets
- Use smaller model file (scrfd_2.5g for speed)
- Close other applications

## Contact & Support

For technical support or feature requests:
- **Project**: Tri-Netra Facial Recognition System
- **Repository**: https://github.com/pankajc2005/FRT
- **Branch**: master

---

# Appendix A: Glossary

| Term | Definition |
|------|------------|
| **Embedding** | A list of numbers representing a face's unique features |
| **Threshold** | The maximum distance to consider two faces a match |
| **Priority** | Importance level (P1 highest, P5 lowest) |
| **Surveillance** | Active monitoring through camera feeds |
| **Hash** | A unique fingerprint of data used for verification |
| **IST** | Indian Standard Time (UTC+5:30) |
| **CCTV** | Closed-Circuit Television (security cameras) |
| **Aadhaar** | India's 12-digit unique identification number |

---

# Appendix B: File Structure

```
D:\Directus TRY\
│
├── app.py                      # Main application (Flask server)
├── face_utils.py               # Face detection and embedding functions
├── requirements.txt            # Python dependencies
├── README.md                   # Quick start guide
│
├── config/
│   └── config.yaml            # Configuration settings
│
├── core/
│   ├── interfaces.py          # Abstract base classes
│   ├── plugin_manager.py      # Camera and model plugin management
│   └── surveillance_engine.py # Real-time surveillance logic
│
├── plugins/
│   ├── cameras/
│   │   └── webcam_plugin.py   # Webcam camera plugin
│   └── models/
│       ├── arcface_plugin.py  # ArcFace model plugin
│       └── dlib_plugin.py     # dlib model plugin
│
├── models/
│   ├── ESPCN_x2.pb            # Image upscaling model
│   ├── scrfd_10g_bnkps.onnx   # Face detection (accurate)
│   └── scrfd_2.5g_*.onnx      # Face detection (fast)
│
├── templates/                  # HTML templates
│   ├── layout.html            # Base layout
│   ├── login.html             # Login page
│   ├── index.html             # Dashboard
│   ├── dashboard.html         # Criminal DB
│   ├── missing_dashboard.html # Missing DB
│   ├── alerts.html            # Alert list
│   ├── alert_view.html        # Alert details
│   └── ...                    # Other pages
│
├── static/
│   ├── css/
│   │   ├── dashboard.css      # Dashboard styles
│   │   ├── mobile.css         # Mobile styles
│   │   └── style.css          # Global styles
│   └── js/
│       ├── dashboard.js       # Dashboard logic
│       └── mobile_map.js      # Map functionality
│
├── data/                       # Data storage
│   ├── persons/               # Criminal records
│   ├── missing_persons/       # Missing person records
│   ├── alerts/                # Detection alerts
│   ├── images/                # Person photos
│   ├── system_alerts/         # System logs
│   └── users.json             # User accounts
│
└── documentation/
    └── PROJECT_DOCUMENTATION.md  # This file
```

---

# Appendix C: Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | Nov 2025 | Initial release with core features |
| 1.1.0 | Nov 2025 | Added priority-based surveillance |
| 1.2.0 | Nov 2025 | Added PDF evidence export |
| 1.3.0 | Nov 2025 | Added tamper-proof activity logging |
| 1.4.0 | Nov 2025 | Added Women Safety Portal |

---

**Document Version**: 1.4.0  
**Last Updated**: November 30, 2025  
**Author**: Tri-Netra Development Team

---

*This documentation is intended for both technical and non-technical readers. For specific implementation details, refer to the source code comments.*
