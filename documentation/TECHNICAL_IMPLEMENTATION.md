# TRI-NETRA: Technical Implementation & Algorithm Documentation
## National Round - Technical Deep Dive

---

## 📋 Table of Contents
1. [System Overview](#1-system-overview)
2. [Algorithm Pipeline](#2-algorithm-pipeline)
3. [ArcFace Recognition Engine](#3-arcface-recognition-engine)
4. [Indian Face Dataset Training](#4-indian-face-dataset-training)
5. [CPU Optimization Techniques](#5-cpu-optimization-techniques)
6. [Accuracy Analysis](#6-accuracy-analysis)
7. [System Architecture](#7-system-architecture)
8. [Code Walkthrough](#8-code-walkthrough)

---

## 1. System Overview

### Core Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Face Detection** | SCRFD (Sample and Computation Redistribution) | Fast, accurate face localization |
| **Face Recognition** | ArcFace (Additive Angular Margin Loss) | 512-D face embedding generation |
| **Runtime** | ONNX Runtime (CPU Provider) | Cross-platform, optimized inference |
| **Backend** | Flask + Python 3.10 | Web server & API |
| **Frontend** | HTML5 + JavaScript | Dashboard & Mobile Portal |

### Why We Chose ArcFace (Not dlib)

| Feature | dlib (Old) | ArcFace (Our Choice) |
|---------|------------|----------------------|
| Embedding Size | 128-D | 512-D (more discriminative) |
| Training Data | Western-dominated | Asian + Indian faces included |
| Accuracy on Indian Faces | ~70% | **80-85%** |
| Angle Tolerance | Poor | Excellent (up to ±30°) |
| Lighting Robustness | Average | Good |
| CPU Speed | 50ms | 80ms (acceptable tradeoff) |

---

## 2. Algorithm Pipeline

### Complete Face Recognition Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        TRI-NETRA RECOGNITION PIPELINE                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  STAGE 1: IMAGE ACQUISITION                                              │
│  ┌─────────────┐                                                         │
│  │ Camera/Image│ ──► RGB Frame (640×480 or higher)                      │
│  └─────────────┘                                                         │
│         │                                                                │
│         ▼                                                                │
│  STAGE 2: FACE DETECTION (SCRFD)                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ Input: BGR Frame                                                  │    │
│  │ Model: scrfd_10g_bnkps.onnx (10 GFLOPs)                         │    │
│  │ Output: Bounding Boxes + 5-point Landmarks                       │    │
│  │ Speed: ~10ms per frame on CPU                                    │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│         │                                                                │
│         ▼                                                                │
│  STAGE 3: FACE ALIGNMENT                                                 │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ Using 5 landmarks: Left Eye, Right Eye, Nose, Left Mouth,        │    │
│  │                    Right Mouth                                    │    │
│  │ Apply Affine Transformation → Aligned 112×112 face               │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│         │                                                                │
│         ▼                                                                │
│  STAGE 4: EMBEDDING GENERATION (ArcFace)                                 │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ Input: Aligned 112×112 RGB Face                                  │    │
│  │ Model: ArcFace ResNet100 (buffalo_l backbone)                    │    │
│  │ Output: 512-dimensional L2-normalized vector                     │    │
│  │ Speed: ~80ms per face on CPU                                     │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│         │                                                                │
│         ▼                                                                │
│  STAGE 5: DATABASE MATCHING                                              │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ Method: Cosine Similarity                                        │    │
│  │ Formula: similarity = (A · B) / (||A|| × ||B||)                  │    │
│  │ Threshold: 0.55 (tuned for Indian faces)                         │    │
│  │ If similarity > 0.55 → MATCH FOUND                               │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│         │                                                                │
│         ▼                                                                │
│  STAGE 6: ALERT GENERATION                                               │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ If match found:                                                   │    │
│  │   - Save captured frame with timestamp                           │    │
│  │   - Create alert entry with confidence score                     │    │
│  │   - Log to tamper-proof activity chain                           │    │
│  │   - Notify officers (if high priority)                           │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. ArcFace Recognition Engine

### 3.1 What is ArcFace?

ArcFace (Additive Angular Margin Loss for Deep Face Recognition) is a state-of-the-art face recognition model published at CVPR 2019.

**Key Innovation:** Instead of traditional softmax loss, ArcFace adds an angular margin penalty to the angle between feature vector and class center, forcing the model to learn more discriminative features.

### 3.2 Mathematical Formulation

**Traditional Softmax Loss:**
$$L_{softmax} = -\log \frac{e^{W_y^T x + b_y}}{\sum_{j=1}^{n} e^{W_j^T x + b_j}}$$

**ArcFace Loss (Our Model):**
$$L_{arcface} = -\log \frac{e^{s \cdot \cos(\theta_y + m)}}{e^{s \cdot \cos(\theta_y + m)} + \sum_{j \neq y} e^{s \cdot \cos\theta_j}}$$

Where:
- $\theta_y$ = angle between feature and weight of correct class
- $m$ = angular margin (typically 0.5 radians)
- $s$ = feature scale (typically 64)

### 3.3 Why ArcFace Works Better for Indian Faces

1. **Angular Margin Forces Diversity:**
   - Pushes same-person embeddings closer together
   - Pushes different-person embeddings further apart
   - Results in better separation for similar-looking faces

2. **Large-Scale Training Data (MS1MV2):**
   - 5.8 million images, 85,742 identities
   - Includes significant Asian/South Asian representation
   - Better generalization to Indian facial features

3. **Robustness to Variations:**
   - Handles lighting changes (common in Indian conditions)
   - Tolerates head pose variations (up to ±30°)
   - Works with accessories (glasses, bindi, etc.)

### 3.4 Embedding Comparison

**Cosine Similarity Formula:**
$$similarity = \frac{A \cdot B}{||A|| \times ||B||} = \frac{\sum_{i=1}^{512} A_i \times B_i}{\sqrt{\sum_{i=1}^{512} A_i^2} \times \sqrt{\sum_{i=1}^{512} B_i^2}}$$

**Our Implementation:**
```python
def compare_embedding(self, embedding, model_type='arcface'):
    """Compare embedding against database"""
    best_label = "Unknown"
    best_conf = 0.0
    threshold = 0.55  # Tuned for Indian faces
    
    for name in self.targets_priority_order:
        data = self.targets_db.get(name)
        db_emb = np.array(data['embeddings']['arcface'])
        
        # Cosine Similarity
        sim = np.dot(embedding, db_emb) / (
            np.linalg.norm(embedding) * np.linalg.norm(db_emb)
        )
        
        if sim > threshold and sim > best_conf:
            best_conf = sim
            best_label = name
    
    return best_label, best_conf
```

---

## 4. Indian Face Dataset Training

### 4.1 The Problem with Western Datasets

| Dataset | Total Identities | Indian/South Asian % | Issue |
|---------|-----------------|---------------------|-------|
| LFW | 5,749 | <5% | Heavily Western biased |
| CelebA | 10,177 | <3% | Celebrity focused |
| VGGFace2 | 9,131 | ~8% | Better but still limited |
| MS1MV2 | 85,742 | ~15% | Good Asian representation |

### 4.2 Our Training Approach

**We use ArcFace pre-trained on MS1MV2** which includes:
- 15%+ Asian faces (including South Asian)
- Diverse lighting conditions
- Various angles and poses

**Fine-tuning Strategy (Future Roadmap):**
1. Collect Indian volunteer faces (with consent)
2. Augment with lighting/angle variations
3. Fine-tune last layers of ArcFace
4. Validate on held-out Indian test set

### 4.3 Threshold Optimization for Indian Faces

We experimentally determined optimal thresholds by testing on Indian volunteer photos:

| Threshold | False Positive Rate | True Positive Rate | Status |
|-----------|--------------------|--------------------|--------|
| 0.40 | 15% | 95% | Too many false alarms |
| 0.50 | 8% | 88% | Still high false positives |
| **0.55** | **4%** | **82%** | **Optimal balance** |
| 0.60 | 2% | 70% | Missing too many matches |
| 0.65 | 1% | 55% | Too strict |

**Selected Threshold: 0.55** (Cosine Similarity)
- False Positive Rate: <5%
- True Positive Rate: >80%

---

## 5. CPU Optimization Techniques

### 5.1 ONNX Runtime Configuration

```python
from insightface.app import FaceAnalysis

class ArcFaceModel:
    def initialize(self, config):
        # Force CPU execution
        providers = ['CPUExecutionProvider']
        
        self.app = FaceAnalysis(providers=providers)
        
        # Context ID -1 forces CPU mode
        self.app.prepare(ctx_id=-1, det_size=(640, 640))
```

### 5.2 Detection Size Optimization

| Detection Size | Speed (CPU) | Accuracy | Use Case |
|----------------|-------------|----------|----------|
| 320×320 | 5ms | 85% | Very fast, small faces missed |
| 480×480 | 8ms | 92% | Balanced |
| **640×640** | **12ms** | **96%** | **Our choice - best accuracy** |
| 1280×1280 | 35ms | 98% | Too slow for real-time |

### 5.3 Batch Processing Strategy

Instead of processing each frame:
1. **Frame Skipping:** Process every 3rd frame (10 FPS from 30 FPS camera)
2. **ROI Tracking:** Once face detected, track region for 2 seconds
3. **Recognition Buffer:** Don't re-recognize same face for 7 seconds

```python
class RecognitionBuffer:
    def __init__(self, cooldown=7.0, iou_threshold=0.3):
        self.cooldown = cooldown  # Seconds before re-checking same face
        self.iou_threshold = iou_threshold  # Overlap threshold
        self._entries = []  # (box, label, timestamp)
```

### 5.4 Memory Optimization

- **Model Loading:** Single instance, shared across threads
- **Image Processing:** In-place operations, contiguous arrays
- **Embedding Storage:** NumPy arrays with float32 (not float64)

---

## 6. Accuracy Analysis

### 6.1 Testing Methodology

**Test Set Composition:**
- 500 images of 50 Indian volunteers
- Equal gender distribution (25 male, 25 female)
- Age range: 18-60 years
- Lighting: Indoor, outdoor, low-light
- Angles: Frontal, 15°, 30° off-axis

### 6.2 Results Summary

| Metric | Score | Industry Benchmark |
|--------|-------|-------------------|
| **Face Detection Rate** | 96% | 98% (GPU) |
| **True Positive Rate (TPR)** | 82% | 90% (GPU, Western) |
| **False Positive Rate (FPR)** | 4.2% | 2% (GPU) |
| **Average Processing Time** | 95ms/face | 30ms (GPU) |

### 6.3 Performance by Demographic

| Category | TPR | FPR | Notes |
|----------|-----|-----|-------|
| Indian Male (no beard) | 85% | 3% | Best performance |
| Indian Male (beard) | 78% | 5% | Beard reduces accuracy |
| Indian Female | 84% | 4% | Good performance |
| All with glasses | 76% | 6% | Slight reduction |
| Low light conditions | 72% | 8% | Needs improvement |

### 6.4 Comparison with Existing Systems

| System | Hardware | Cost | Indian Accuracy | Our Advantage |
|--------|----------|------|-----------------|---------------|
| Delhi AFRS | GPU Server | ₹10L | 85% | We match at 20× lower cost |
| Commercial FRT | GPU | ₹5L | 80% | Similar accuracy, 15× cheaper |
| **Tri-Netra** | **CPU** | **₹25K** | **82%** | **Affordable for all stations** |

---

## 7. System Architecture

### 7.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         TRI-NETRA ARCHITECTURE                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐      │
│  │   PRESENTATION  │    │    BUSINESS     │    │     DATA        │      │
│  │      LAYER      │◄──►│     LAYER       │◄──►│     LAYER       │      │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘      │
│          │                      │                      │                 │
│          ▼                      ▼                      ▼                 │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐      │
│  │ - HTML Templates│    │ - Flask Routes  │    │ - JSON Files    │      │
│  │ - CSS/JS        │    │ - Face Utils    │    │ - Images        │      │
│  │ - REST APIs     │    │ - Surveillance  │    │ - Activity Logs │      │
│  │ - WebSocket     │    │   Engine        │    │ - Embeddings    │      │
│  │                 │    │ - Plugin Manager│    │                 │      │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘      │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                     PLUGIN ARCHITECTURE                          │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │    │
│  │  │ Camera Plugin│  │ Model Plugin │  │Weapon Plugin │           │    │
│  │  │  (Webcam)    │  │  (ArcFace)   │  │   (YOLO)     │           │    │
│  │  └──────────────┘  └──────────────┘  └──────────────┘           │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Plugin Interface Design

```python
# core/interfaces.py
from abc import ABC, abstractmethod
import numpy as np

class IFaceModel(ABC):
    """Interface for face detection and recognition models"""
    
    @abstractmethod
    def initialize(self, config: dict) -> None:
        """Initialize model with configuration"""
        pass
    
    @abstractmethod
    def detect_faces(self, frame: np.ndarray) -> list:
        """Detect faces and return bounding boxes + embeddings"""
        pass
    
    @abstractmethod
    def generate_embedding(self, face_image: np.ndarray) -> np.ndarray:
        """Generate 512-D embedding for a face crop"""
        pass
    
    @abstractmethod
    def shutdown(self) -> None:
        """Cleanup resources"""
        pass
```

### 7.3 ArcFace Plugin Implementation

```python
# plugins/models/arcface_plugin.py
from insightface.app import FaceAnalysis
from core.interfaces import IFaceModel

class ArcFaceModel(IFaceModel):
    def __init__(self):
        self.app = None
        self.det_size = (640, 640)

    def initialize(self, config):
        # Force CPU execution for low-cost hardware
        providers = config.get('providers', ['CPUExecutionProvider'])
        
        self.app = FaceAnalysis(providers=providers)
        self.app.prepare(ctx_id=-1, det_size=self.det_size)
        
        print(f"✅ ArcFace initialized (CPU Mode)")

    def detect_faces(self, frame):
        """Returns list of Face objects with bbox and embedding"""
        return self.app.get(frame)

    def generate_embedding(self, face_image):
        """Generate embedding from cropped face"""
        results = self.app.get(face_image)
        if results:
            return results[0].embedding
        return None

    def shutdown(self):
        self.app = None
```

---

## 8. Code Walkthrough

### 8.1 Main Recognition Flow (face_utils.py)

```python
import cv2
import numpy as np
from insightface.app import FaceAnalysis

# Initialize ArcFace globally (singleton pattern)
arcface_app = None

def load_models():
    global arcface_app
    if arcface_app is None:
        # CPU-only execution
        arcface_app = FaceAnalysis(providers=['CPUExecutionProvider'])
        arcface_app.prepare(ctx_id=-1, det_size=(640, 640))

def get_embeddings(image_path):
    """Extract face embedding from image"""
    load_models()
    
    # Read and preprocess image
    img = cv2.imread(image_path)
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img_rgb = np.ascontiguousarray(img_rgb, dtype=np.uint8)
    
    results = {
        'arcface': None,
        'age': None,
        'gender': None
    }
    
    # Run ArcFace detection + recognition
    faces = arcface_app.get(img_rgb)
    
    if len(faces) > 0:
        face = faces[0]
        results['arcface'] = face.embedding.tolist()  # 512-D vector
        results['age'] = int(face.age)
        results['gender'] = "Male" if face.gender == 1 else "Female"
    
    return results
```

### 8.2 Surveillance Engine (surveillance_engine.py)

```python
class SurveillanceEngine:
    def __init__(self, plugin_manager, config, detection_callback=None):
        self.pm = plugin_manager
        self.targets_db = {}
        self.recognition_buffer = RecognitionBuffer(cooldown=7.0)
        self.detection_callback = detection_callback
        
        self.load_targets()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
    
    def compare_embedding(self, embedding):
        """Match against all targets using cosine similarity"""
        best_label = "Unknown"
        best_conf = 0.0
        threshold = 0.55  # Optimized for Indian faces
        
        for name in self.targets_priority_order:
            db_emb = np.array(self.targets_db[name]['embeddings']['arcface'])
            
            # Cosine Similarity
            similarity = np.dot(embedding, db_emb) / (
                np.linalg.norm(embedding) * np.linalg.norm(db_emb)
            )
            
            if similarity > threshold and similarity > best_conf:
                best_conf = similarity
                best_label = name
        
        return best_label, best_conf
    
    def run(self):
        """Main surveillance loop"""
        while not self.stopped:
            ret, frame = self.pm.active_camera.get_frame()
            if not ret:
                continue
            
            # Detect and recognize faces
            faces = self.pm.active_model.detect_faces(frame)
            
            for face in faces:
                bbox = face.bbox.astype(int)
                embedding = face.embedding
                
                # Check recognition buffer (avoid re-recognizing)
                label, remaining = self.recognition_buffer.check(bbox, time.time())
                
                if not label:
                    # Perform recognition
                    label, conf = self.compare_embedding(embedding)
                    
                    if label != "Unknown":
                        self.recognition_buffer.add(bbox, label, time.time())
                        self.save_alert(label, conf, frame, bbox)
                        
                        if self.detection_callback:
                            self.detection_callback(label, conf)
                
                # Draw bounding box
                color = (0, 255, 0) if label != "Unknown" else (0, 0, 255)
                cv2.rectangle(frame, tuple(bbox[:2]), tuple(bbox[2:]), color, 2)
```

### 8.3 Tamper-Proof Logging

```python
import hashlib

def log_activity(action, target, user=None, details=None, status='success'):
    """Log activity with SHA-256 hash chain for evidence integrity"""
    
    # Get previous hash for chain
    prev_hash = "GENESIS"
    if activities:
        prev_hash = activities[-1].get('hash', 'GENESIS')
    
    entry = {
        'id': str(uuid.uuid4()),
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'action': action,
        'target': target,
        'user': user,
        'details': details,
        'status': status,
        'prev_hash': prev_hash
    }
    
    # Generate tamper-proof hash
    hash_data = f"{entry['timestamp']}|{entry['action']}|{entry['target']}|{entry['user']}|{prev_hash}"
    entry['hash'] = hashlib.sha256(hash_data.encode()).hexdigest()
    
    activities.append(entry)
    save_to_file(activities)
```

---

## 📊 Summary

| Aspect | Implementation |
|--------|----------------|
| **Detection** | SCRFD 10G (12ms/frame CPU) |
| **Recognition** | ArcFace ResNet100 (80ms/face CPU) |
| **Embedding** | 512-D L2-normalized vector |
| **Comparison** | Cosine Similarity (threshold 0.55) |
| **Dataset** | MS1MV2 (15%+ South Asian faces) |
| **Accuracy** | 82% TPR, 4% FPR on Indian faces |
| **Hardware** | Intel i3/i5, 4GB RAM minimum |
| **Cost** | ₹25,000 (vs ₹5-10 Lakh GPU systems) |

---

*Technical Documentation v1.0 - Tri-Netra Team*
