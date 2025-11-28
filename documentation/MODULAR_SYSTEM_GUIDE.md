# Modular Architecture & Extensibility Guide

This document explains the modular architecture of the Face Recognition System (FRT) and provides step-by-step instructions on how to extend, configure, and customize the system without needing to understand the entire codebase.

## 1. System Overview

The system is built on a **Plugin-based Architecture**. This means the core logic (the engine) is separated from the specific implementations of cameras and AI models.

### Key Folders
*   **`core/`**: Contains the system interfaces and the main surveillance engine. **Do not modify** these files unless you are changing the core logic.
*   **`plugins/`**: This is where you work.
    *   `plugins/models/`: Contains AI model implementations (e.g., Dlib, ArcFace).
    *   `plugins/cameras/`: Contains camera source implementations (e.g., Webcam).
*   **`config/`**: Contains `config.yaml`, which controls which plugins are active.

---

## 2. Configuration

You can switch between different models and cameras by editing `config/config.yaml`. You do not need to write code to switch components.

**Example `config.yaml`:**
```yaml
active_components:
  face_model: "dlib_standard"  # Change this to "arcface_standard" to switch models
  camera: "local_webcam"       # Change this to switch camera sources

models:
  dlib_standard:
    module: "plugins.models.dlib_plugin"
    class: "DlibFaceModel"
    params:
      threshold: 0.45

  arcface_standard:
    module: "plugins.models.arcface_plugin"
    class: "ArcFaceModel"
    params:
      det_size: [640, 640]

cameras:
  local_webcam:
    module: "plugins.cameras.webcam_plugin"
    class: "WebcamSource"
    params:
      device_id: 0
```

### How to Switch Components
1.  Open `config/config.yaml`.
2.  Change the value under `active_components`.
    *   To use ArcFace: Set `face_model: "arcface_standard"`.
    *   To use Dlib: Set `face_model: "dlib_standard"`.
3.  Restart the application (`python app.py`).

---

## 3. How to Add a New Face Model

If you want to integrate a new face recognition library (e.g., MediaPipe, DeepFace), follow these steps:

### Step 1: Create the Plugin File
Create a new Python file in `plugins/models/`, for example `plugins/models/mediapipe_plugin.py`.

### Step 2: Implement the Interface
Your class must inherit from `IFaceModel` and implement three methods: `initialize`, `detect_faces`, and `generate_embedding`.

```python
# plugins/models/mediapipe_plugin.py
import numpy as np
from typing import List, Any, Dict
from core.interfaces import IFaceModel

class MediaPipeModel(IFaceModel):
    def initialize(self, config: Dict[str, Any]) -> None:
        # Load your model here
        print("MediaPipe Model Initialized")

    def detect_faces(self, frame: np.ndarray) -> List[Any]:
        # Return a list of detected face objects or bounding boxes
        # For compatibility, ensure objects have a .bbox attribute or similar
        return []

    def generate_embedding(self, face_image: np.ndarray) -> np.ndarray:
        # Return a 1D numpy array representing the face embedding
        return np.zeros(128)
```

### Step 3: Register in Config
Add your new model to `config/config.yaml`:

```yaml
models:
  # ... existing models ...
  mediapipe_new:
    module: "plugins.models.mediapipe_plugin"
    class: "MediaPipeModel"
    params:
      min_detection_confidence: 0.5
```

### Step 4: Activate
Set `face_model: "mediapipe_new"` in `active_components` and restart.

---

## 4. How to Add a New Camera Source

If you want to add support for an IP Camera (RTSP stream) or a video file, follow these steps:

### Step 1: Create the Plugin File
Create a new file in `plugins/cameras/`, for example `plugins/cameras/ip_cam_plugin.py`.

### Step 2: Implement the Interface
Your class must inherit from `IVideoSource` and implement `initialize`, `get_frame`, and `shutdown`.

```python
# plugins/cameras/ip_cam_plugin.py
import cv2
import numpy as np
from typing import Tuple, Optional, Dict, Any
from core.interfaces import IVideoSource

class IPCameraSource(IVideoSource):
    def __init__(self):
        self.cap = None

    def initialize(self, config: Dict[str, Any]) -> None:
        rtsp_url = config.get('rtsp_url')
        self.cap = cv2.VideoCapture(rtsp_url)

    def get_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        if self.cap and self.cap.isOpened():
            return self.cap.read()
        return False, None

    def shutdown(self) -> None:
        if self.cap:
            self.cap.release()
```

### Step 3: Register in Config
Add your new camera to `config/config.yaml`:

```yaml
cameras:
  # ... existing cameras ...
  office_ip_cam:
    module: "plugins.cameras.ip_cam_plugin"
    class: "IPCameraSource"
    params:
      rtsp_url: "rtsp://admin:password@192.168.1.100:554/stream"
```

### Step 4: Activate
Set `camera: "office_ip_cam"` in `active_components` and restart.

---

## 5. Troubleshooting

*   **ImportError / Module Not Found**: Ensure your plugin file is in the correct folder and the `module` path in `config.yaml` uses dots (e.g., `plugins.models.my_plugin`).
*   **AttributeError**: Ensure your plugin class implements ALL methods defined in the interface (`core/interfaces.py`).
*   **Camera Light Won't Turn Off**: Ensure your `shutdown()` method properly releases resources (e.g., `cv2.VideoCapture.release()`).
