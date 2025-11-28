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
# Configuration
# ----------------------------
DLIB_SHAPE_MODEL = "shape_predictor_68_face_landmarks.dat"
DLIB_FACE_MODEL = "dlib_face_recognition_resnet_model_v1.dat"
SCRFD_MODEL = "models/scrfd_10g_bnkps.onnx"

SCALE_FACTOR = 1.0
FRAME_SKIP = 2
DLIB_FACE_CHIP_SIZE = 150
MAX_WORKERS = 2
USE_HIST_EQUALIZATION = False

RECOGNITION_BUFFER_TIME = 7.0
BUFFER_IOU_THRESHOLD = 0.3

DLIB_THRESHOLD = 0.60
SCRFD_SCORE_THRESHOLD = 0.30
SCRFD_NMS_THRESHOLD = 0.45
SCRFD_INPUT_SIZE = (640, 640)
SCRFD_MAX_NUM = 50
CONFIDENCE_MATCH = 0.35

DLIB_WEIGHT = 0.4
ARCFACE_WEIGHT = 0.6

MIN_FACE_PIXELS = 40
MIN_BLUR_VAR = 50.0

CAPTURE_DIR = "captured_faces"
WEBCAM_ID = 0

Rect = Tuple[int, int, int, int]

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("surveillance_system")

class RecognitionBuffer:
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
                iou = self.calculate_iou(box, entry_box)
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

    @staticmethod
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

class VideoCamera(object):
    def __init__(self, mode='both'):
        self.mode = mode
        # Use DirectShow on Windows to avoid MSMF errors
        self.video = cv2.VideoCapture(WEBCAM_ID, cv2.CAP_DSHOW)
        
        # Initialize models
        self.init_models()
        
        # Load embeddings
        self.metadata_db = {}
        self.dlib_db, self.arc_db = self.load_db_embeddings('data/active_surveillance_targets.json', mode)
        
        self.recognition_buffer = RecognitionBuffer(RECOGNITION_BUFFER_TIME, BUFFER_IOU_THRESHOLD)
        self.frame_counter = 0
        
        self.stopped = False
        self.current_frame = None
        self.lock = threading.Lock()
        
        # Start processing thread
        self.thread = threading.Thread(target=self.update, args=())
        self.thread.daemon = True
        self.thread.start()
        
    def __del__(self):
        self.stop()

    def stop(self):
        self.stopped = True
        if self.thread.is_alive():
            self.thread.join(timeout=1.0)
        if self.video.isOpened():
            self.video.release()

    def set_mode(self, mode):
        self.mode = mode
        self.dlib_db, self.arc_db = self.load_db_embeddings('data/active_surveillance_targets.json', mode)
        logger.info(f"Switched mode to {mode}")

    def init_models(self):
        # SCRFD
        try:
            self.scrfd_detector = SCRFD(model_file=SCRFD_MODEL)
            self.scrfd_detector.prepare(ctx_id=-1, input_size=SCRFD_INPUT_SIZE)
            self.scrfd_detector.nms_thresh = SCRFD_NMS_THRESHOLD
            self.scrfd_detector.det_thresh = SCRFD_SCORE_THRESHOLD
            self.scrfd_detector.max_num = SCRFD_MAX_NUM
            self.use_scrfd = True
        except Exception as e:
            logger.warning(f"Could not load SCRFD: {e}")
            self.use_scrfd = False

        # Dlib
        self.dlib_detector = dlib.get_frontal_face_detector()
        self.dlib_shape_predictor = dlib.shape_predictor(DLIB_SHAPE_MODEL)
        self.dlib_face_rec_model = dlib.face_recognition_model_v1(DLIB_FACE_MODEL)

        # ArcFace
        self.arc_app = FaceAnalysis(providers=['CPUExecutionProvider'])
        self.arc_app.prepare(ctx_id=-1, det_size=(320, 320))
        self.arc_app_lock = threading.Lock()

    def load_db_embeddings(self, json_path, mode):
        dlib_db = {}
        arc_db = {}
        
        if not os.path.exists(json_path):
            logger.warning(f"JSON path {json_path} does not exist")
            return dlib_db, arc_db

        try:
            with open(json_path, 'r') as f:
                targets = json.load(f)
            
            for target in targets:
                if mode != 'both' and target['db_type'] != mode:
                    continue
                    
                label = target['name']
                self.metadata_db[label] = target
                
                if target['embeddings'].get('dlib'):
                    dlib_db[label] = np.array(target['embeddings']['dlib'], dtype=np.float32)
                    
                if target['embeddings'].get('arcface'):
                    arr = np.array(target['embeddings']['arcface'], dtype=np.float32)
                    arc_db[label] = l2_normalize(arr)
                    
            logger.info(f"Loaded {len(dlib_db)} targets for mode {mode}")
        except Exception as e:
            logger.error(f"Error loading embeddings: {e}")
            
        return dlib_db, arc_db

    def recognize_against_db(self, dlib_emb, arc_emb):
        best_label = "Unknown"
        best_conf = 0.0
        best_dlib_sim = 0.0
        best_arc_sim = 0.0

        arc_emb_n = arc_emb if arc_emb is not None else None
        labels = sorted(set(list(self.dlib_db.keys()) + list(self.arc_db.keys())))

        for label in labels:
            d_sim = 0.0
            if label in self.dlib_db and dlib_emb is not None:
                dist = euclidean_distance(dlib_emb, self.dlib_db[label])
                d_sim = max(0.0, 1.0 - (dist / DLIB_THRESHOLD))
                d_sim = min(max(d_sim, 0.0), 1.0)

            a_sim = 0.0
            if label in self.arc_db and arc_emb_n is not None:
                a_sim_raw = float(np.dot(arc_emb_n, self.arc_db[label]))
                a_sim = min(max(a_sim_raw, 0.0), 1.0)

            if (label in self.dlib_db) and (label in self.arc_db):
                combined = (DLIB_WEIGHT * d_sim) + (ARCFACE_WEIGHT * a_sim)
            elif (label in self.dlib_db):
                combined = d_sim
            elif (label in self.arc_db):
                combined = a_sim
            else:
                combined = 0.0

            if combined > best_conf:
                best_conf = combined
                best_label = label
                best_dlib_sim = d_sim
                best_arc_sim = a_sim

        return best_label, best_dlib_sim, best_arc_sim, best_conf

    def extract_embeddings_for_box(self, box, rgb_frame_small, gray_frame_small):
        x1, y1, x2, y2 = box
        dlib_embedding = None
        arcface_embedding = None

        try:
            rect = dlib.rectangle(x1, y1, x2, y2)
            shape = self.dlib_shape_predictor(gray_frame_small, rect)
            face_chip = dlib.get_face_chip(rgb_frame_small, shape, size=DLIB_FACE_CHIP_SIZE)

            if face_chip.shape[0] < DLIB_FACE_CHIP_SIZE or face_chip.shape[1] < DLIB_FACE_CHIP_SIZE:
                face_chip = cv2.resize(face_chip, (DLIB_FACE_CHIP_SIZE, DLIB_FACE_CHIP_SIZE), interpolation=cv2.INTER_CUBIC)

            descriptor = self.dlib_face_rec_model.compute_face_descriptor(face_chip)
            dlib_embedding = np.asarray(descriptor, dtype=np.float32)
        except Exception:
            pass

        try:
            crop_rgb = rgb_frame_small[y1:y2, x1:x2]
            if crop_rgb.size > 0:
                with self.arc_app_lock:
                    faces_af = self.arc_app.get(crop_rgb)
                if faces_af:
                    embedding = getattr(faces_af[0], "embedding", None)
                    if embedding is not None:
                        arcface_embedding = l2_normalize(np.asarray(embedding, dtype=np.float32))
        except Exception:
            pass
        return box, dlib_embedding, arcface_embedding

    def save_alert(self, label, conf, frame, box):
        try:
            target = self.metadata_db.get(label)
            if not target:
                return

            person_id = target['id']
            alert_dir = "data/alerts"
            images_dir = os.path.join(alert_dir, "images")
            os.makedirs(images_dir, exist_ok=True)
            
            alert_file = os.path.join(alert_dir, f"{person_id}.json")
            
            current_match_percentage = round(conf * 100, 2)
            timestamp = datetime.utcnow().isoformat() + "Z"
            
            # Crop face for the alert image
            x1, y1, x2, y2 = box
            h, w, _ = frame.shape
            # Add some padding
            pad_x = int((x2 - x1) * 0.2)
            pad_y = int((y2 - y1) * 0.2)
            x1 = max(0, x1 - pad_x)
            y1 = max(0, y1 - pad_y)
            x2 = min(w, x2 + pad_x)
            y2 = min(h, y2 + pad_y)
            
            face_img = frame[y1:y2, x1:x2]
            image_filename = f"{person_id}_{int(time.time())}.jpg"
            image_path = os.path.join(images_dir, image_filename)
            
            new_detection = {
                "timestamp": timestamp,
                "match_percentage": current_match_percentage,
                "capture_frame": image_filename
            }

            alert_data = {}
            if os.path.exists(alert_file):
                with open(alert_file, 'r') as f:
                    alert_data = json.load(f)
            else:
                # Initialize with target data
                alert_data = target.copy()
                alert_data['detections'] = []
                alert_data['best_match_percentage'] = 0.0
                # Remove embeddings to save space if not needed, or keep them
                if 'embeddings' in alert_data:
                    del alert_data['embeddings']

            # Logic: Save new alert only when match percentage is higher than existed
            # But also "make version control... multiple capture frame"
            # So we always add to history if it's a "good" match? 
            # The user said "saved new alert only when the match percentage is higher than existed"
            # This implies we only update the record if we found a BETTER match.
            
            if current_match_percentage > alert_data.get('best_match_percentage', 0):
                # Save the image only if we are going to record it
                cv2.imwrite(image_path, face_img)
                
                alert_data['best_match_percentage'] = current_match_percentage
                alert_data['detections'].append(new_detection)
                # Sort detections by percentage descending
                alert_data['detections'].sort(key=lambda x: x['match_percentage'], reverse=True)
                
                with open(alert_file, 'w') as f:
                    json.dump(alert_data, f, indent=2)
                
                logger.info(f"New high confidence alert saved for {label}: {current_match_percentage}%")

        except Exception as e:
            logger.error(f"Error saving alert: {e}")

    def update(self):
        logger.info("Starting camera update loop...")
        while not self.stopped:
            try:
                if not self.video.isOpened():
                    # Try to reopen
                    logger.info(f"Opening camera {WEBCAM_ID}...")
                    self.video.open(WEBCAM_ID, cv2.CAP_DSHOW)
                    if not self.video.isOpened():
                        logger.error("Failed to open camera.")
                        time.sleep(0.5)
                        continue
                    
                    # Set resolution to ensure compatibility
                    self.video.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    self.video.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    logger.info("Camera opened.")
                    
                success, frame = self.video.read()
                if not success:
                    # If read fails, maybe camera disconnected
                    logger.warning("Failed to read frame from camera.")
                    self.video.release()
                    time.sleep(0.1)
                    continue

                current_time = time.time()
                self.recognition_buffer.clean(current_time)

                if SCALE_FACTOR != 1.0:
                    small_frame = cv2.resize(frame, (0, 0), fx=SCALE_FACTOR, fy=SCALE_FACTOR)
                else:
                    small_frame = frame.copy()
                    
                rgb_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
                gray_small = cv2.cvtColor(rgb_small, cv2.COLOR_RGB2GRAY)
                gray_small_proc = cv2.equalizeHist(gray_small) if USE_HIST_EQUALIZATION else gray_small
                small_height, small_width = gray_small_proc.shape

                detections_small = []
                detection_sources = {}

                if self.frame_counter % FRAME_SKIP == 0:
                    if self.use_scrfd:
                        try:
                            bboxes, _ = self.scrfd_detector.detect(small_frame, input_size=SCRFD_INPUT_SIZE, max_num=SCRFD_MAX_NUM)
                            if bboxes is not None:
                                for bbox in bboxes:
                                    x1, y1, x2, y2, score = bbox[:5]
                                    if score < SCRFD_SCORE_THRESHOLD: continue
                                    
                                    x1 = max(0, min(int(x1), small_width - 1))
                                    y1 = max(0, min(int(y1), small_height - 1))
                                    x2 = max(x1 + 1, min(int(x2), small_width - 1))
                                    y2 = max(y1 + 1, min(int(y2), small_height - 1))
                                    
                                    if (x2 - x1) >= MIN_FACE_PIXELS and (y2 - y1) >= MIN_FACE_PIXELS:
                                        box = (x1, y1, x2, y2)
                                        detections_small.append(box)
                                        detection_sources[box] = "scrfd"
                        except Exception: pass

                    if not detections_small:
                        faces = self.dlib_detector(gray_small_proc, 0)
                        for rect in faces:
                            x1 = max(rect.left(), 0)
                            y1 = max(rect.top(), 0)
                            x2 = min(rect.right(), small_width - 1)
                            y2 = min(rect.bottom(), small_height - 1)
                            if (x2 - x1) >= MIN_FACE_PIXELS and (y2 - y1) >= MIN_FACE_PIXELS:
                                box = (x1, y1, x2, y2)
                                detections_small.append(box)
                                detection_sources[box] = "dlib"

                pending_boxes = []
                buffered_boxes = []

                for box in detections_small:
                    source = detection_sources.get(box, "unknown")
                    label_in_buffer, remaining_time, buffer_source = self.recognition_buffer.check(box, current_time)
                    if label_in_buffer:
                        buffered_boxes.append((box, label_in_buffer, remaining_time, buffer_source or source))
                    else:
                        pending_boxes.append(box)
                        detection_sources[box] = source

                embeddings_map = {}
                if pending_boxes:
                    worker_count = min(MAX_WORKERS, max(1, len(pending_boxes)))
                    with ThreadPoolExecutor(max_workers=worker_count) as executor:
                        future_to_box = {
                            executor.submit(self.extract_embeddings_for_box, box, rgb_small, gray_small_proc): box
                            for box in pending_boxes
                        }
                        for future in as_completed(future_to_box):
                            box = future_to_box[future]
                            try:
                                box_result, d_emb, a_emb = future.result()
                                embeddings_map[tuple(box_result)] = (d_emb, a_emb)
                            except Exception:
                                embeddings_map[tuple(box)] = (None, None)

                recognition_results = []
                for box in pending_boxes:
                    source = detection_sources.get(box, "unknown")
                    d_emb, a_emb = embeddings_map.get(tuple(box), (None, None))
                    label, d_sim, a_sim, conf = self.recognize_against_db(d_emb, a_emb)
                    matched = conf >= CONFIDENCE_MATCH and label != "Unknown"

                    if matched:
                        self.recognition_buffer.add(box, label, current_time, source)
                        # Save capture logic
                        threading.Thread(target=self.save_alert, args=(label, conf, frame.copy(), box)).start()

                    recognition_results.append({
                        "box": box,
                        "label": label,
                        "matched": matched,
                        "source": source
                    })

                # Draw results
                for box, label, remaining, source in buffered_boxes:
                    x1, y1, x2, y2 = box
                    color = (0, 255, 255) if source == "scrfd" else (0, 200, 0)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(frame, f"{label} ({remaining:.1f}s)", (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                for result in recognition_results:
                    x1, y1, x2, y2 = result["box"]
                    matched = result["matched"]
                    color = (0, 200, 0) if matched else (0, 0, 255)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    if matched:
                        cv2.putText(frame, result["label"], (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                self.frame_counter += 1
                
                ret, jpeg = cv2.imencode('.jpg', frame)
                if ret:
                    with self.lock:
                        self.current_frame = jpeg.tobytes()
            
            except Exception as e:
                logger.error(f"Error in surveillance update loop: {e}")
                time.sleep(0.1)

    def get_frame(self):
        with self.lock:
            return self.current_frame
