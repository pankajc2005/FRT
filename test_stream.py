import os
import cv2
import dlib
import json
import time
import logging
import threading
import numpy as np
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Tuple, List, Optional

from insightface.app import FaceAnalysis
from insightface.model_zoo import SCRFD

# ----------------------------
# Configuration (tune these)
# ----------------------------
# Models
DLIB_SHAPE_MODEL = "shape_predictor_68_face_landmarks.dat"
DLIB_FACE_MODEL = "dlib_face_recognition_resnet_model_v1.dat"
SCRFD_MODEL = "models/scrfd_10g_bnkps.onnx"  # SCRFD face detection model (update path if needed)

# Performance
SCALE_FACTOR = 1.0           # keep full resolution for better long-distance detection
FRAME_SKIP = 2               # process every N frames (reduce for smoother performance)
DLIB_FACE_CHIP_SIZE = 150    # must be 150 for dlib model
MAX_WORKERS = 2              # thread pool size for embedding extraction
USE_HIST_EQUALIZATION = False  # enable only if lighting is inconsistent

# Recognition buffer (cooldown)
RECOGNITION_BUFFER_TIME = 7.0  # seconds - adjustable cooldown period
BUFFER_IOU_THRESHOLD = 0.3     # IoU threshold to consider same face in buffer

# Thresholds (tune on your validation set)
DLIB_THRESHOLD = 0.60          # Euclidean distance threshold (lower = more similar)
SCRFD_SCORE_THRESHOLD = 0.30   # detection score threshold
SCRFD_NMS_THRESHOLD = 0.45     # non-max suppression threshold
SCRFD_INPUT_SIZE = (640, 640)  # detector input size (width, height)
SCRFD_MAX_NUM = 50             # max faces per frame
CONFIDENCE_MATCH = 0.35        # Combined confidence threshold for a positive match

# Super resolution (applied before detection)
USE_SUPER_RESOLUTION = True
SUPER_RES_MODEL_PATH = "models/ESPCN_x2.pb"         # path to OpenCV super-resolution model (.pb)
SUPER_RES_MODEL_NAME = "espcn"                      # model name (edsr, espcn, fsrcnn, lapsrn)
SUPER_RES_MODEL_SCALE = 2                           # scale factor encoded by the model (e.g. 2, 3, 4)

# Weights for combined confidence
DLIB_WEIGHT = 0.4
ARCFACE_WEIGHT = 0.6

# Face quality
MIN_FACE_PIXELS = 40
MIN_BLUR_VAR = 50.0

# Embedding folders
DLIB_EMB_DIR = "embeddings/dlib"
ARCFACE_EMB_DIR = "embeddings/arcface"

# Capture settings
CAPTURE_DIR = "captured_faces"  # Folder to save detected faces
WEBCAM_ID = 0  # Webcam number
WEBCAM_LOCATION = "India Bulls"  # Location of the webcam

# Diagnostics / logging
FPS_UPDATE_INTERVAL = 1.0  # seconds
LOG_LEVEL = logging.INFO

# Configure logging early
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("face_recognition")

Rect = Tuple[int, int, int, int]


class RecognitionBuffer:
    """Stores recent recognition results to avoid duplicate processing."""

    def __init__(self, cooldown: float, iou_threshold: float) -> None:
        self.cooldown = cooldown
        self.iou_threshold = iou_threshold
        self._entries: List[Tuple[Rect, str, float, str]] = []
        self._lock = threading.Lock()

    def clean(self, now: float) -> None:
        with self._lock:
            self._entries = [entry for entry in self._entries if now - entry[2] < self.cooldown]

    def check(self, box: Rect, now: float) -> Tuple[Optional[str], float, Optional[str]]:
        with self._lock:
            for entry_box, label, ts, source in self._entries:
                iou = calculate_iou(box, entry_box)
                if iou >= self.iou_threshold:
                    remaining = max(0.0, self.cooldown - (now - ts))
                    if remaining > 0:
                        return label, remaining, source
        return None, 0.0, None

    def add(self, box: Rect, label: str, now: float, source: str) -> None:
        with self._lock:
            self._entries.append((box, label, now, source))

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


# ----------------------------
# Utilities
# ----------------------------
def calculate_iou(box_a: Rect, box_b: Rect) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
        return 0.0

    inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union_area = area_a + area_b - inter_area

    if union_area <= 0:
        return 0.0
    return inter_area / union_area


def scale_box_to_original(box: Rect, scale_factor: float, frame_shape: Tuple[int, int]) -> Rect:
    x1, y1, x2, y2 = box
    width, height = frame_shape[1], frame_shape[0]

    x1 = min(max(int(x1 / scale_factor), 0), width - 1)
    y1 = min(max(int(y1 / scale_factor), 0), height - 1)
    x2 = min(max(int(x2 / scale_factor), x1 + 1), width - 1)
    y2 = min(max(int(y2 / scale_factor), y1 + 1), height - 1)
    return x1, y1, x2, y2


def clamp_box_to_bounds(box: Rect, width: int, height: int) -> Rect:
    x1, y1, x2, y2 = box
    x1 = max(0, min(x1, width - 1))
    y1 = max(0, min(y1, height - 1))
    x2 = max(x1 + 1, min(x2, width - 1))
    y2 = max(y1 + 1, min(y2, height - 1))
    return x1, y1, x2, y2

def l2_normalize(v: np.ndarray, eps: float = 1e-10) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32)
    n = np.linalg.norm(v)
    if n < eps:
        return v
    return v / (n + eps)

def euclidean_distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(a - b))

def is_blurry(gray: np.ndarray, var_thresh: float = MIN_BLUR_VAR) -> bool:
    if gray.size == 0:
        return True
    return cv2.Laplacian(gray, cv2.CV_64F).var() < var_thresh

# ----------------------------
# Load embeddings DB
# ----------------------------
def load_db_embeddings(dlib_dir: str, arc_dir: str) -> Tuple[Dict[str, np.ndarray], Dict[str, np.ndarray]]:
    dlib_db = {}
    arc_db = {}
    # Dlib folder - expected raw 128-D vectors (not normalized)
    if os.path.isdir(dlib_dir):
        for f in os.listdir(dlib_dir):
            if not f.endswith(".npy"):
                continue
            label = os.path.splitext(f)[0]
            try:
                arr = np.load(os.path.join(dlib_dir, f)).astype(np.float32)
                # If array is 2D (multiple embeddings), average them
                if arr.ndim == 2:
                    arr = np.mean(arr, axis=0)
                dlib_db[label] = arr
            except Exception as e:
                logger.warning("Could not load dlib embedding %s: %s", f, e)
    else:
        logger.warning("dlib embeddings folder not found: %s", dlib_dir)

    # ArcFace folder - expected L2-normalized 512-D vectors
    if os.path.isdir(arc_dir):
        for f in os.listdir(arc_dir):
            if not f.endswith(".npy"):
                continue
            label = os.path.splitext(f)[0]
            try:
                arr = np.load(os.path.join(arc_dir, f)).astype(np.float32)
                if arr.ndim == 2:
                    arr = np.mean(arr, axis=0)
                arr = l2_normalize(arr)
                arc_db[label] = arr
            except Exception as e:
                logger.warning("Could not load arcface embedding %s: %s", f, e)
    else:
        logger.warning("arcface embeddings folder not found: %s", arc_dir)

    # Keep only labels present in both DBs (optional). We'll allow comparisons even if one missing.
    labels = sorted(set(list(dlib_db.keys()) + list(arc_db.keys())))
    return dlib_db, arc_db

# ----------------------------
# Initialize models & DBs
# ----------------------------
logger.info("Loading SCRFD face detector...")
try:
    scrfd_detector = SCRFD(model_file=SCRFD_MODEL)
    scrfd_detector.prepare(ctx_id=-1, input_size=SCRFD_INPUT_SIZE)
    scrfd_detector.nms_thresh = SCRFD_NMS_THRESHOLD
    scrfd_detector.det_thresh = SCRFD_SCORE_THRESHOLD
    scrfd_detector.max_num = SCRFD_MAX_NUM
    USE_SCRFD = True
    logger.info("SCRFD detector loaded successfully")
except Exception as e:
    logger.warning("Could not load SCRFD model (%s). Falling back to dlib detector.", e)
    scrfd_detector = None
    USE_SCRFD = False

logger.info("Loading dlib models...")
dlib_detector = dlib.get_frontal_face_detector()
dlib_shape_predictor = dlib.shape_predictor(DLIB_SHAPE_MODEL)
dlib_face_rec_model = dlib.face_recognition_model_v1(DLIB_FACE_MODEL)

logger.info("Preparing InsightFace (ArcFace)...")
arc_app = FaceAnalysis(providers=['CPUExecutionProvider'])
arc_app.prepare(ctx_id=-1, det_size=(320, 320))  # CPU execution
arc_app_lock = threading.Lock()

logger.info("Initializing super resolution (optional)...")
super_res_engine = None
super_res_scale_hint = 1.0
if USE_SUPER_RESOLUTION:
    if hasattr(cv2, "dnn_superres"):
        try:
            if os.path.isfile(SUPER_RES_MODEL_PATH):
                super_res_engine = cv2.dnn_superres.DnnSuperResImpl_create()
                super_res_engine.readModel(SUPER_RES_MODEL_PATH)
                super_res_engine.setModel(SUPER_RES_MODEL_NAME, SUPER_RES_MODEL_SCALE)
                super_res_scale_hint = float(SUPER_RES_MODEL_SCALE)
                logger.info(
                    "Super resolution model loaded (%s x%d)",
                    SUPER_RES_MODEL_NAME.upper(),
                    SUPER_RES_MODEL_SCALE,
                )
            else:
                logger.warning(
                    "Super resolution model not found: %s. Super resolution disabled.",
                    SUPER_RES_MODEL_PATH,
                )
        except Exception as error:
            logger.warning("Could not initialize super resolution (%s). Super resolution disabled.", error)
            super_res_engine = None
    else:
        logger.warning("OpenCV build does not include dnn_superres; super resolution disabled.")
else:
    logger.info("Super resolution disabled via configuration.")

logger.info("Loading embeddings DBs...")
dlib_db, arc_db = load_db_embeddings(DLIB_EMB_DIR, ARCFACE_EMB_DIR)
logger.info("Loaded DB counts: dlib=%d arcface=%d", len(dlib_db), len(arc_db))

# Recognition buffer to prevent repeated recognition
recognition_buffer = RecognitionBuffer(RECOGNITION_BUFFER_TIME, BUFFER_IOU_THRESHOLD)

# ----------------------------
# Recognition helpers
# ----------------------------
def recognize_against_db(dlib_emb: np.ndarray, arc_emb: np.ndarray, dlib_db: dict, arc_db: dict) -> Tuple[str, float, float, float]:
    """
    Returns (best_label, dlib_sim, arc_sim, combined_confidence)
    - dlib_emb: raw 128-D vector (from dlib model)
    - arc_emb: raw 512-D vector (from arcface model) -> should be normalized before comparing
    """
    best_label = "Unknown"
    best_conf = 0.0
    best_dlib_sim = 0.0
    best_arc_sim = 0.0

    # ArcFace embeddings are already normalized during extraction
    arc_emb_n = arc_emb if arc_emb is not None else None

    # iterate labels union
    labels = sorted(set(list(dlib_db.keys()) + list(arc_db.keys())))
    if len(labels) == 0:
        return best_label, 0.0, 0.0, 0.0

    for label in labels:
        # dlib similarity: convert euclidean distance -> similarity [0,1] using DLIB_THRESHOLD
        d_sim = 0.0
        if label in dlib_db and dlib_emb is not None:
            dist = euclidean_distance(dlib_emb, dlib_db[label])
            # map to similarity only when dist <= 2*threshold, else zero
            # similarity = max(0, 1 - dist / (2*DLIB_THRESHOLD))
            # Better: similarity = 1 - (dist / DLIB_THRESHOLD), clamp 0..1 for dist<=threshold
            d_sim = max(0.0, 1.0 - (dist / DLIB_THRESHOLD))
            # clamp
            d_sim = min(max(d_sim, 0.0), 1.0)

        # arc similarity: cosine in [ -1, 1 ], but we clamp to [0,1]
        a_sim = 0.0
        if label in arc_db and arc_emb_n is not None:
            a_sim_raw = float(np.dot(arc_emb_n, arc_db[label]))
            a_sim = min(max(a_sim_raw, 0.0), 1.0)

        # if both present, compute weighted average; if only one -> use that one
        if (label in dlib_db) and (label in arc_db):
            combined = (DLIB_WEIGHT * d_sim) + (ARCFACE_WEIGHT * a_sim)
        elif (label in dlib_db):
            combined = d_sim
        elif (label in arc_db):
            combined = a_sim
        else:
            combined = 0.0

        if combined > best_conf:
            best_conf = combined
            best_label = label
            best_dlib_sim = d_sim
            best_arc_sim = a_sim

    return best_label, best_dlib_sim, best_arc_sim, best_conf

def save_captured_face(frame: np.ndarray, x1: int, y1: int, x2: int, y2: int, 
                       label: str, dlib_sim: float, arc_sim: float, conf: float):
    """Save the detected face with metadata to JSON file"""
    # Create capture directory if it doesn't exist
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    
    # Generate timestamp
    now = datetime.now()
    timestamp_str = now.strftime("%Y%m%d_%H%M%S_%f")
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    
    # Create filename
    image_filename = f"{label}_{timestamp_str}.jpg"
    json_filename = f"{label}_{timestamp_str}.json"
    
    image_path = os.path.join(CAPTURE_DIR, image_filename)
    json_path = os.path.join(CAPTURE_DIR, json_filename)
    
    # Ensure crop is within frame bounds and non-empty
    height, width = frame.shape[:2]
    x1 = max(0, min(x1, width - 1))
    y1 = max(0, min(y1, height - 1))
    x2 = max(x1 + 1, min(x2 + 1, width))
    y2 = max(y1 + 1, min(y2 + 1, height))

    # Crop and save face image
    face_crop = frame[y1:y2, x1:x2]
    if face_crop.size == 0:
        logger.warning("Skipped saving capture for %s due to empty crop", label)
        return None, None
    cv2.imwrite(image_path, face_crop)
    
    # Create metadata JSON
    metadata = {
        "name": label,
        "confidence": round(conf, 4),
        "models": {
            "dlib": {
                "similarity": round(dlib_sim, 4)
            },
            "arcface": {
                "similarity": round(arc_sim, 4)
            }
        },
        "detection": {
            "bounding_box": {
                "x1": int(x1),
                "y1": int(y1),
                "x2": int(x2),
                "y2": int(y2)
            }
        },
        "timestamp": {
            "date": date_str,
            "time": time_str,
            "unix": now.timestamp()
        },
        "webcam": {
            "id": WEBCAM_ID,
            "location": WEBCAM_LOCATION
        },
        "image_file": image_filename
    }
    
    # Save JSON metadata
    with open(json_path, 'w') as f:
        json.dump(metadata, f, indent=4)
    
    logger.info("Saved capture %s (confidence=%.3f)", image_filename, conf)
    return image_path, json_path


def extract_embeddings_for_box(
    box: Rect,
    rgb_frame_small: np.ndarray,
    gray_frame_small: np.ndarray,
    shape_predictor: dlib.shape_predictor,
    face_rec_model: dlib.face_recognition_model_v1,
    arcface_app: FaceAnalysis,
    arcface_lock: threading.Lock,
) -> Tuple[Rect, Optional[np.ndarray], Optional[np.ndarray]]:
    """Extract embeddings for a detected face bounding box."""

    x1, y1, x2, y2 = box
    dlib_embedding: Optional[np.ndarray] = None
    arcface_embedding: Optional[np.ndarray] = None

    try:
        rect = dlib.rectangle(x1, y1, x2, y2)
        shape = shape_predictor(gray_frame_small, rect)
        face_chip = dlib.get_face_chip(rgb_frame_small, shape, size=DLIB_FACE_CHIP_SIZE)

        if face_chip.shape[0] < DLIB_FACE_CHIP_SIZE or face_chip.shape[1] < DLIB_FACE_CHIP_SIZE:
            face_chip = cv2.resize(face_chip, (DLIB_FACE_CHIP_SIZE, DLIB_FACE_CHIP_SIZE), interpolation=cv2.INTER_CUBIC)

        descriptor = face_rec_model.compute_face_descriptor(face_chip)
        dlib_embedding = np.asarray(descriptor, dtype=np.float32)
    except Exception as error:
        logger.debug("Dlib embedding failed for box %s: %s", box, error)

    try:
        crop_rgb = rgb_frame_small[y1:y2, x1:x2]
        if crop_rgb.size > 0:
            with arcface_lock:
                faces_af = arcface_app.get(crop_rgb)
            if faces_af:
                embedding = getattr(faces_af[0], "embedding", None)
                if embedding is not None:
                    arcface_embedding = l2_normalize(np.asarray(embedding, dtype=np.float32))
    except Exception as error:
        logger.debug("ArcFace embedding failed for box %s: %s", box, error)

    return box, dlib_embedding, arcface_embedding

# ----------------------------
# Live webcam loop
# ----------------------------
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    raise Exception("Webcam not accessible")

frame_counter = 0
fps_counter = 0
fps_display = 0.0
fps_last_update = time.time()

logger.info("Starting webcam. Press 'q' to quit.")

while True:
    ret, frame = cap.read()
    if not ret:
        break

    current_time = time.time()
    recognition_buffer.clean(current_time)

    # FPS tracking
    fps_counter += 1
    elapsed_since_update = current_time - fps_last_update
    if elapsed_since_update >= FPS_UPDATE_INTERVAL:
        fps_display = fps_counter / max(elapsed_since_update, 1e-6)
        fps_counter = 0
        fps_last_update = current_time

    # Prepare working frame (optionally downscale if explicitly configured)
    if SCALE_FACTOR != 1.0:
        small_frame = cv2.resize(frame, (0, 0), fx=SCALE_FACTOR, fy=SCALE_FACTOR)
    else:
        small_frame = frame.copy()
    rgb_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
    gray_small = cv2.cvtColor(rgb_small, cv2.COLOR_RGB2GRAY)
    gray_small_proc = cv2.equalizeHist(gray_small) if USE_HIST_EQUALIZATION else gray_small
    small_height, small_width = gray_small_proc.shape

    sr_scale_x = 1.0
    sr_scale_y = 1.0

    detections_small: List[Rect] = []
    detection_sources: Dict[Tuple[int, int, int, int], str] = {}

    if frame_counter % FRAME_SKIP == 0:
        # Primary detection with SCRFD (if available)
        if USE_SCRFD:
            try:
                detection_frame = small_frame
                det_height, det_width = detection_frame.shape[:2]
                if super_res_engine is not None:
                    try:
                        detection_frame = super_res_engine.upsample(small_frame)
                        det_height, det_width = detection_frame.shape[:2]
                        sr_scale_x = det_width / float(max(1, small_width))
                        sr_scale_y = det_height / float(max(1, small_height))
                        super_res_scale_hint = max(sr_scale_x, sr_scale_y)
                    except Exception as sr_error:
                        logger.error("Super resolution inference failed (%s). Disabling super resolution.", sr_error)
                        super_res_engine = None
                        super_res_scale_hint = 1.0
                        detection_frame = small_frame
                        det_height, det_width = detection_frame.shape[:2]

                bboxes, _ = scrfd_detector.detect(
                    detection_frame,
                    input_size=SCRFD_INPUT_SIZE,
                    max_num=SCRFD_MAX_NUM,
                )
                if bboxes is not None:
                    for bbox in bboxes:
                        x1_det, y1_det, x2_det, y2_det, score = bbox[:5]
                        if score < SCRFD_SCORE_THRESHOLD:
                            continue

                        x1_det = max(0.0, min(float(x1_det), det_width - 1))
                        y1_det = max(0.0, min(float(y1_det), det_height - 1))
                        x2_det = max(0.0, min(float(x2_det), det_width - 1))
                        y2_det = max(0.0, min(float(y2_det), det_height - 1))
                        x2_det = max(x1_det + 1.0, x2_det)
                        y2_det = max(y1_det + 1.0, y2_det)

                        if sr_scale_x != 1.0:
                            x1 = int(round(x1_det / sr_scale_x))
                            x2 = int(round(x2_det / sr_scale_x))
                        else:
                            x1 = int(round(x1_det))
                            x2 = int(round(x2_det))

                        if sr_scale_y != 1.0:
                            y1 = int(round(y1_det / sr_scale_y))
                            y2 = int(round(y2_det / sr_scale_y))
                        else:
                            y1 = int(round(y1_det))
                            y2 = int(round(y2_det))

                        x1 = max(0, min(x1, small_width - 1))
                        y1 = max(0, min(y1, small_height - 1))
                        x2 = max(x1 + 1, min(x2, small_width - 1))
                        y2 = max(y1 + 1, min(y2, small_height - 1))
                        if (x2 - x1) >= MIN_FACE_PIXELS and (y2 - y1) >= MIN_FACE_PIXELS:
                            box = (x1, y1, x2, y2)
                            detections_small.append(box)
                            detection_sources[box] = "scrfd"
            except Exception as error:
                logger.error("SCRFD detection failed: %s", error)

        # Fallback to dlib detector if needed
        if not detections_small:
            faces = dlib_detector(gray_small_proc, 0)
            for rect in faces:
                x1 = max(rect.left(), 0)
                y1 = max(rect.top(), 0)
                x2 = min(rect.right(), small_width - 1)
                y2 = min(rect.bottom(), small_height - 1)
                if (x2 - x1) >= MIN_FACE_PIXELS and (y2 - y1) >= MIN_FACE_PIXELS:
                    box = (x1, y1, x2, y2)
                    detections_small.append(box)
                    detection_sources[box] = "dlib"

    pending_boxes: List[Rect] = []
    buffered_boxes: List[Tuple[Rect, str, float, str]] = []

    for box in detections_small:
        source = detection_sources.get(box, "unknown")
        x1, y1, x2, y2 = box
        roi_gray = gray_small_proc[y1:y2, x1:x2]
        if roi_gray.size == 0 or is_blurry(roi_gray):
            continue

        label_in_buffer, remaining_time, buffer_source = recognition_buffer.check(box, current_time)
        if label_in_buffer:
            buffered_boxes.append((box, label_in_buffer, remaining_time, buffer_source or source))
        else:
            pending_boxes.append(box)
            detection_sources[box] = source

    embeddings_map: Dict[Tuple[int, int, int, int], Tuple[Optional[np.ndarray], Optional[np.ndarray]]] = {}

    if pending_boxes:
        worker_count = min(MAX_WORKERS, max(1, len(pending_boxes)))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_to_box = {
                executor.submit(
                    extract_embeddings_for_box,
                    box,
                    rgb_small,
                    gray_small_proc,
                    dlib_shape_predictor,
                    dlib_face_rec_model,
                    arc_app,
                    arc_app_lock,
                ): box
                for box in pending_boxes
            }

            for future in as_completed(future_to_box):
                box = future_to_box[future]
                try:
                    box_result, d_emb, a_emb = future.result()
                    embeddings_map[tuple(box_result)] = (d_emb, a_emb)
                except Exception as error:
                    logger.error("Embedding extraction task failed for box %s: %s", box, error)
                    embeddings_map[tuple(box)] = (None, None)

    recognition_results: List[Dict[str, object]] = []

    for box in pending_boxes:
        source = detection_sources.get(box, "unknown")
        d_emb, a_emb = embeddings_map.get(tuple(box), (None, None))
        label, d_sim, a_sim, conf = recognize_against_db(d_emb, a_emb, dlib_db, arc_db)
        matched = conf >= CONFIDENCE_MATCH and label != "Unknown"

        full_box = scale_box_to_original(box, SCALE_FACTOR, frame.shape[:2])
        full_box = clamp_box_to_bounds(full_box, frame.shape[1], frame.shape[0])

        if matched:
            recognition_buffer.add(box, label, current_time, source)
            save_captured_face(frame, *full_box, label, d_sim, a_sim, conf)

        recognition_results.append(
            {
                "box_small": box,
                "box_full": full_box,
                "label": label,
                "d_sim": d_sim,
                "a_sim": a_sim,
                "conf": conf,
                "matched": matched,
                "source": source,
            }
        )

    # ----------------------------
    # Draw boxes & diagnostics on original (full-size) frame
    # ----------------------------
    frame_height, frame_width = frame.shape[:2]

    for box, label, remaining, source in buffered_boxes:
        full_box = scale_box_to_original(box, SCALE_FACTOR, frame.shape[:2])
        x1, y1, x2, y2 = clamp_box_to_bounds(full_box, frame_width, frame_height)
        color = (0, 255, 255) if source == "scrfd" else (0, 200, 0)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        title = f"MATCHED: {label}"
        cooldown_line = f"Cooldown: {remaining:.1f}s"

        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.6
        thickness = 1
        pad = 6

        w1, h1 = cv2.getTextSize(title, font, scale, thickness)[0]
        w2, h2 = cv2.getTextSize(cooldown_line, font, scale, thickness)[0]
        box_w = max(w1, w2) + pad * 2
        box_h = h1 + h2 + pad * 3

        bx1 = x1
        by1 = y2 + 10
        bx2 = min(bx1 + box_w, frame_width - 1)
        by2 = min(by1 + box_h, frame_height - 1)
        bx1 = max(0, bx2 - box_w)
        by1 = max(0, by2 - box_h)

        cv2.rectangle(frame, (bx1, by1), (bx2, by2), (10, 10, 10), cv2.FILLED)
        cv2.rectangle(frame, (bx1, by1), (bx2, by2), color, 1)

        ty = by1 + pad + h1
        cv2.putText(frame, title, (bx1 + pad, ty), font, scale, (255, 255, 255), thickness, cv2.LINE_AA)
        ty += h1 + pad // 2
        cv2.putText(frame, cooldown_line, (bx1 + pad, ty), font, scale, (100, 255, 100), thickness, cv2.LINE_AA)

    for result in recognition_results:
        full_box = result["box_full"]
        x1, y1, x2, y2 = clamp_box_to_bounds(full_box, frame_width, frame_height)
        matched = bool(result["matched"])
        source = result.get("source", "unknown")

        if source == "scrfd":
            color = (0, 255, 255)
        else:
            color = (0, 200, 0) if matched else (0, 120, 255)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        label = result["label"] if matched else "UNKNOWN"
        d_sim = result["d_sim"]
        a_sim = result["a_sim"]
        conf = result["conf"]

        line1 = f"MATCHED: {label}" if matched else "UNKNOWN"
        line2 = f"Dlib similarity: {d_sim:.2f}"
        line3 = f"ArcFace similarity: {a_sim:.2f}"
        line4 = f"Confidence: {conf:.2f}"

        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.6
        thickness = 1
        pad = 6

        w1, h1 = cv2.getTextSize(line1, font, scale, thickness)[0]
        w2, h2 = cv2.getTextSize(line2, font, scale, thickness)[0]
        w3, h3 = cv2.getTextSize(line3, font, scale, thickness)[0]
        w4, h4 = cv2.getTextSize(line4, font, scale, thickness)[0]
        box_w = max(w1, w2, w3, w4) + pad * 2
        box_h = h1 + h2 + h3 + h4 + pad * 5

        bx1 = x1
        by1 = y2 + 10
        bx2 = min(bx1 + box_w, frame_width - 1)
        by2 = min(by1 + box_h, frame_height - 1)
        bx1 = max(0, bx2 - box_w)
        by1 = max(0, by2 - box_h)

        cv2.rectangle(frame, (bx1, by1), (bx2, by2), (10, 10, 10), cv2.FILLED)
        cv2.rectangle(frame, (bx1, by1), (bx2, by2), color, 1)

        ty = by1 + pad + h1
        cv2.putText(frame, line1, (bx1 + pad, ty), font, scale, (255, 255, 255), thickness, cv2.LINE_AA)
        ty += h1 + pad // 2
        cv2.putText(frame, line2, (bx1 + pad, ty), font, scale, (230, 230, 230), thickness, cv2.LINE_AA)
        ty += h2 + pad // 2
        cv2.putText(frame, line3, (bx1 + pad, ty), font, scale, (230, 230, 230), thickness, cv2.LINE_AA)
        ty += h3 + pad // 2
        cv2.putText(frame, line4, (bx1 + pad, ty), font, scale, (230, 230, 230), thickness, cv2.LINE_AA)

    # show DB summary on top-left
    detector_type = "SCRFD" if USE_SCRFD else "dlib"
    if super_res_engine is not None:
        if abs(super_res_scale_hint - round(super_res_scale_hint)) < 1e-3:
            sr_scale_label = int(round(super_res_scale_hint))
        else:
            sr_scale_label = round(super_res_scale_hint, 2)
        detector_type += f"+SRx{sr_scale_label}"
    cv2.putText(frame, f"Detector: {detector_type} | DB: dlib={len(dlib_db)} arcface={len(arc_db)}", (10,20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200,200,200), 1)
    cv2.putText(frame, f"Buffer: {len(recognition_buffer)} faces | Cooldown: {RECOGNITION_BUFFER_TIME}s", (10,45), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200,200,200), 1)
    cv2.putText(frame, f"FPS: {fps_display:.1f}", (10,70), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200,200,200), 1)

    cv2.imshow("Face Recognition (dlib + ArcFace) - Diagnostics", frame)

    frame_counter += 1
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
