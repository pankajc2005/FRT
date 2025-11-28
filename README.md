# Face Recognition Dashboard

This application integrates dlib and ArcFace for face recognition and embedding generation, providing a web interface to manage persons.

## Setup

1.  **Install Dependencies:**
    Ensure you have the required packages installed.
    ```bash
    pip install flask insightface opencv-python dlib
    ```
    *Note: `dlib` and `insightface` (and its dependencies like `onnxruntime`) must be properly installed.*

2.  **Models:**
    Ensure the following files are in the root directory:
    - `shape_predictor_68_face_landmarks.dat`
    - `dlib_face_recognition_resnet_model_v1.dat`

## Running the Application

Run the Flask app:
```bash
python app.py
```

Access the dashboard at `http://127.0.0.1:5000`.

## Features

-   **Dashboard:** View all registered persons with their details.
-   **Add Person:** Upload an image and enter details (Name, Gender).
-   **Automatic Processing:**
    -   Detects face.
    -   Generates dlib embeddings.
    -   Generates ArcFace embeddings.
    -   Predicts Age and Gender (using ArcFace).
    -   Saves everything into a single JSON file per person in `data/persons/`.
