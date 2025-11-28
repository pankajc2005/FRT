# Police Face Recognition System (FRT)

Welcome! This is a project designed for Police departments to identify criminals and missing persons using live cameras. It uses Artificial Intelligence (AI) to detect and recognize faces in real-time.

This project is built for students and beginners. You don't need to be an expert in AI to run this!

## 💻 System Requirements

Before you start, make sure you have:
*   **OS:** Windows 10 or 11.
*   **Python:** Version 3.10 to 3.12.10(Used in project) is recommended.
*   **Code Editor:** VS Code (Visual Studio Code).

## 🚀 Step-by-Step Installation Guide

Follow these steps exactly to get the project running in 30 minutes.

### Step 1: Download the Code
1.  Download this project as a ZIP file and extract it, or use Git:
    ```bash
    git clone https://github.com/pankajc2005/FRT.git
    ```
2.  Open the folder in VS Code.

### Step 2: Create a Virtual Environment
This keeps your project clean and separate from other projects.
1.  Open the Terminal in VS Code (Ctrl + `).
2.  Run this command:
    ```bash
    python -m venv venv
    ```
3.  Activate the environment:
    ```bash
    .\venv\Scripts\activate
    ```
    *(You should see `(venv)` appear at the start of your terminal line).*

### Step 3: Install Libraries
Now we install the tools the project needs.
```bash
pip install -r requirements.txt
```
*Note: This might take a few minutes. If you get an error about "CMake", see the Common Errors section below.*

### Step 4: The Important Numpy Fix ⚠️
Sometimes the latest version of numpy causes errors. Run this command to fix it:
```bash
pip install numpy==1.26.4
```

### Step 5: Download Model Files
The AI needs "brain" files to work. You need to download these two files and put them inside the **`models/`** folder:
1.  `shape_predictor_68_face_landmarks.dat`
2.  `dlib_face_recognition_resnet_model_v1.dat`

*(You can find these online or from the original dlib repository).*

## ▶️ How to Run

1.  Make sure your virtual environment is active `(venv)`.
2.  Run the app:
    ```bash
    python app.py
    ```
3.  You will see a message saying "Running on http://127.0.0.1:5000".
4.  Open your web browser (Chrome/Edge) and go to: **http://127.0.0.1:5000**

## 🛠️ How to Use

1.  **Add a Criminal:** Go to the "Criminals" page and click "Add Person". Upload a photo and give it a name.
2.  **Start Surveillance:** Go to the "Surveillance" page.
3.  **Start Camera:** Click "Start Background Surveillance" or "Start Live Stream".
4.  **Test:** Show the photo of the person to your webcam. The system should recognize them!

## ❓ Common Errors & Solutions

**Error 1: "CMake must be installed to build dlib"**
*   **Fix:** You need to install "CMake" on your computer. Download it from the official website. Also, install "Visual Studio Community" with "Desktop development with C++".

**Error 2: "RuntimeError: module compiled against API version 0x..."**
*   **Fix:** This is a numpy version issue. Run: `pip install numpy==1.26.4`

**Error 3: "File not found... .dat"**
*   **Fix:** You forgot to put the model files in the `models/` folder. Check Step 5 again.


