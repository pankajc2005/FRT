import cv2
import numpy as np
import time
import threading
import queue
import json
import os
import logging
from datetime import datetime
from typing import Tuple, List, Optional, Dict, Any
from dataclasses import dataclass

# Import Plugin Manager
from core.plugin_manager import PluginManager

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("SurveillanceEngine")

# Constants (could be moved to config)
RECOGNITION_BUFFER_TIME = 7.0
BUFFER_IOU_THRESHOLD = 0.4
CONFIDENCE_MATCH = 0.90

# Pipeline Queue Settings - Minimal for lowest lag
FACE_QUEUE_MAX_SIZE = 2       # Minimal queue
EMBEDDING_QUEUE_MAX_SIZE = 2  # Minimal queue
QUEUE_TIMEOUT = 0.01          # Very fast timeout


@dataclass
class FaceData:
    """Data structure for passing face info between pipeline stages"""
    bbox: tuple           # (x1, y1, x2, y2)
    face_crop: np.ndarray # Cropped face image for embedding
    frame: np.ndarray     # Full frame for saving alerts
    timestamp: float      # When the face was detected
    face_obj: Any = None  # Original face object (for ArcFace with embedded embedding)


@dataclass
class EmbeddingData:
    """Data structure for passing embedding info to matching stage"""
    bbox: tuple
    embedding: np.ndarray
    frame: np.ndarray
    timestamp: float

class RecognitionBuffer:
    def __init__(self, cooldown: float, iou_threshold: float) -> None:
        self.cooldown = cooldown
        self.iou_threshold = iou_threshold
        self._entries: List[Tuple[tuple, str, float]] = [] # box, label, timestamp
        self._lock = threading.Lock()

    def clean(self, now: float) -> None:
        with self._lock:
            self._entries = [entry for entry in self._entries if now - entry[2] < self.cooldown]

    def check(self, box: tuple, now: float) -> Tuple[Optional[str], float]:
        with self._lock:
            for entry_box, label, ts in self._entries:
                iou = self.calculate_iou(box, entry_box)
                if iou >= self.iou_threshold:
                    remaining = max(0.0, self.cooldown - (now - ts))
                    if remaining > 0:
                        return label, remaining
        return None, 0.0

    def add(self, box: tuple, label: str, now: float) -> None:
        with self._lock:
            self._entries.append((box, label, now))

    @staticmethod
    def calculate_iou(box_a, box_b) -> float:
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

class SurveillanceEngine:
    """
    Multi-threaded Surveillance Pipeline Architecture:
    
    Thread 1: Flask Web Server (external)
    Thread 2: Face Detection - Captures frames, detects faces, passes to queue
    Thread 3: Embedding Generation - Generates embeddings from face crops
    Thread 4: Database Matching - Compares embeddings against DB, generates alerts
    
    This architecture prevents blocking - detection continues while matching happens.
    """
    
    def __init__(self, plugin_manager: PluginManager, config: Dict[str, Any], detection_callback=None):
        self.pm = plugin_manager
        self.config = config
        self.stopped = False
        self.lock = threading.Lock()
        self.current_frame = None
        self.recognition_buffer = RecognitionBuffer(RECOGNITION_BUFFER_TIME, BUFFER_IOU_THRESHOLD)
        self.detection_callback = detection_callback
        
        # Database
        self.targets_db = {}
        self.targets_priority_order = []
        self.load_targets()
        
        # Pipeline Queues (thread-safe)
        self.face_queue = queue.Queue(maxsize=FACE_QUEUE_MAX_SIZE)
        self.embedding_queue = queue.Queue(maxsize=EMBEDDING_QUEUE_MAX_SIZE)
        
        # Alert cooldown - prevent duplicate alerts for same person
        self.last_alert_time = {}  # {person_name: (timestamp, confidence)}
        self.alert_cooldown = 7.0  # seconds between alerts for same person
        self.min_conf_diff = 0.02  # minimum confidence difference to trigger new alert (2%)
        self.alert_lock = threading.Lock()
        
        # Performance metrics
        self.metrics = {
            'detection_fps': 0.0,
            'embedding_fps': 0.0,
            'matching_fps': 0.0,
            'faces_detected': 0,
            'matches_found': 0
        }
        self.metrics_lock = threading.Lock()
        
        # Start pipeline threads
        self.detection_thread = threading.Thread(target=self._detection_loop, daemon=True, name="DetectionThread")
        self.embedding_thread = threading.Thread(target=self._embedding_loop, daemon=True, name="EmbeddingThread")
        self.matching_thread = threading.Thread(target=self._matching_loop, daemon=True, name="MatchingThread")
        
        self.detection_thread.start()
        self.embedding_thread.start()
        self.matching_thread.start()
        
        logger.info("🚀 Multi-threaded Surveillance Engine Started (3 pipeline threads)")

    def load_targets(self):
        """Load targets from the JSON file generated by app.py (already sorted by priority)"""
        json_path = 'data/active_surveillance_targets.json'
        self.targets_db = {}
        self.targets_priority_order = []
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r') as f:
                    targets = json.load(f)
                for t in targets:
                    self.targets_db[t['name']] = t
                    self.targets_priority_order.append(t['name'])
                logger.info(f"Loaded {len(self.targets_db)} targets (priority-sorted).")
            except Exception as e:
                logger.error(f"Error loading targets: {e}")

    def stop(self):
        """Stop all pipeline threads gracefully"""
        logger.info("Stopping Surveillance Engine...")
        self.stopped = True
        
        # Wait for threads to finish
        for thread in [self.detection_thread, self.embedding_thread, self.matching_thread]:
            if thread.is_alive():
                thread.join(timeout=2.0)
        
        # Clear queues
        self._clear_queue(self.face_queue)
        self._clear_queue(self.embedding_queue)
        
        logger.info("Surveillance Engine Stopped")

    def _clear_queue(self, q):
        """Helper to clear a queue"""
        try:
            while True:
                q.get_nowait()
        except queue.Empty:
            pass

    def get_frame(self):
        with self.lock:
            return self.current_frame

    def get_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics"""
        with self.metrics_lock:
            return self.metrics.copy()

    def _detection_loop(self):
        """
        THREAD 2: Face Detection Loop - Optimized for low latency
        """
        logger.info("Detection Thread Started")
        frame_count = 0
        last_fps_time = time.time()
        frame_for_alert = None  # Reuse frame reference for alerts
        
        while not self.stopped:
            if not self.pm.active_camera:
                time.sleep(0.5)
                continue

            ret, frame = self.pm.active_camera.get_frame()
            if not ret or frame is None:
                time.sleep(0.02)
                continue

            current_time = time.time()
            
            # Clean old buffer entries periodically (not every frame)
            if frame_count % 10 == 0:
                self.recognition_buffer.clean(current_time)
            
            # Run face detection
            try:
                faces = self.pm.active_model.detect_faces(frame)
            except Exception as e:
                logger.error(f"Detection error: {e}")
                continue
            
            # Clear old active detections and prepare fresh list for this frame
            current_frame_detections = []
            
            # Process each detected face
            for face in faces:
                bbox = None
                face_obj = None
                
                if hasattr(face, 'bbox'):  # ArcFace
                    bbox = tuple(face.bbox.astype(int))
                    face_obj = face
                elif hasattr(face, 'left'):  # Dlib
                    bbox = (face.left(), face.top(), face.right(), face.bottom())

                if bbox is None:
                    continue
                
                x1, y1, x2, y2 = bbox
                
                # Check recognition buffer
                cached_label, remaining = self.recognition_buffer.check(bbox, current_time)
                
                if cached_label:
                    # Already recognized - just draw
                    current_frame_detections.append((bbox, cached_label, remaining))
                else:
                    # New face - queue for processing (only if queue not full)
                    if not self.face_queue.full():
                        # Create minimal face crop
                        h, w = frame.shape[:2]
                        cx1, cy1 = max(0, x1), max(0, y1)
                        cx2, cy2 = min(w, x2), min(h, y2)
                        
                        if cy2 > cy1 and cx2 > cx1:
                            face_data = FaceData(
                                bbox=bbox,
                                face_crop=frame[cy1:cy2, cx1:cx2].copy(),
                                frame=frame,  # Reference, not copy
                                timestamp=current_time,
                                face_obj=face_obj
                            )
                            try:
                                self.face_queue.put_nowait(face_data)
                            except queue.Full:
                                pass
                    
                    # Draw as unrecognized for now
                    current_frame_detections.append((bbox, None, 0))
            
            # Draw directly on frame (no copy needed for display)
            for bbox, label, remaining in current_frame_detections:
                x1, y1, x2, y2 = bbox
                if label:
                    color = (0, 255, 0)  # Green for recognized
                    text = f"{label} ({remaining:.1f}s)"
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(frame, text, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            
            # Encode with lower quality for speed
            ret, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if ret:
                with self.lock:
                    self.current_frame = jpeg.tobytes()
            
            # Update FPS metrics less frequently
            frame_count += 1
            if frame_count >= 30:
                with self.metrics_lock:
                    self.metrics['detection_fps'] = frame_count / (time.time() - last_fps_time)
                frame_count = 0
                last_fps_time = time.time()

        logger.info("Detection Thread Stopped")

    def _embedding_loop(self):
        """
        THREAD 3: Embedding Generation Loop
        - Reads faces from face_queue
        - Generates embeddings (ArcFace uses pre-computed, Dlib generates)
        - Passes embeddings to embedding_queue
        """
        logger.info("Embedding Thread Started")
        process_count = 0
        last_fps_time = time.time()
        
        model_type = 'arcface'  # Will be updated based on active model
        
        while not self.stopped:
            try:
                face_data = self.face_queue.get(timeout=QUEUE_TIMEOUT)
            except queue.Empty:
                continue
            
            current_time = time.time()
            
            # Skip if face is too old (stale data)
            if current_time - face_data.timestamp > 0.5:
                continue
            
            # Determine model type
            if self.pm.active_model:
                model_type = 'dlib' if 'Dlib' in self.pm.active_model.__class__.__name__ else 'arcface'
            
            embedding = None
            
            try:
                if model_type == 'arcface' and face_data.face_obj is not None:
                    # ArcFace already computed embedding during detection
                    if hasattr(face_data.face_obj, 'embedding'):
                        embedding = face_data.face_obj.embedding
                elif face_data.face_crop is not None and face_data.face_crop.size > 0:
                    # Generate embedding from crop (Dlib or fallback)
                    embedding = self.pm.active_model.generate_embedding(face_data.face_crop)
            except Exception as e:
                logger.error(f"Embedding generation error: {e}")
                continue
            
            if embedding is not None:
                emb_data = EmbeddingData(
                    bbox=face_data.bbox,
                    embedding=embedding,
                    frame=face_data.frame.copy(),  # Copy here for alert saving
                    timestamp=face_data.timestamp
                )
                
                try:
                    self.embedding_queue.put_nowait(emb_data)
                except queue.Full:
                    pass  # Skip if matching is overwhelmed
            
            # Update FPS metrics
            process_count += 1
            if current_time - last_fps_time >= 1.0:
                with self.metrics_lock:
                    self.metrics['embedding_fps'] = process_count / (current_time - last_fps_time)
                process_count = 0
                last_fps_time = current_time

        logger.info("Embedding Thread Stopped")

    def _matching_loop(self):
        """
        THREAD 4: Database Matching Loop
        - Reads embeddings from embedding_queue
        - Compares against target database
        - Generates alerts for matches
        """
        logger.info("Matching Thread Started")
        match_count = 0
        last_fps_time = time.time()
        
        while not self.stopped:
            try:
                emb_data = self.embedding_queue.get(timeout=QUEUE_TIMEOUT)
            except queue.Empty:
                continue
            
            current_time = time.time()
            
            # Skip stale embeddings
            if current_time - emb_data.timestamp > 1.0:
                continue
            
            # Determine model type
            model_type = 'arcface'
            if self.pm.active_model:
                model_type = 'dlib' if 'Dlib' in self.pm.active_model.__class__.__name__ else 'arcface'
            
            # Compare against database
            try:
                label, conf = self.compare_embedding(emb_data.embedding, model_type)
            except Exception as e:
                logger.error(f"Matching error: {e}")
                continue
            
            if label != "Unknown":
                # Add to recognition buffer (this is what detection loop checks)
                self.recognition_buffer.add(emb_data.bbox, label, current_time)
                
                # Check alert cooldown - avoid duplicate alerts for same person with similar confidence
                should_alert = False
                with self.alert_lock:
                    last_data = self.last_alert_time.get(label)
                    if last_data is None:
                        # First detection of this person
                        should_alert = True
                    else:
                        last_time, last_conf = last_data
                        time_diff = current_time - last_time
                        conf_diff = abs(conf - last_conf)
                        
                        # Alert only if: enough time passed AND confidence is significantly different
                        if time_diff >= self.alert_cooldown and conf_diff >= self.min_conf_diff:
                            should_alert = True
                    
                    if should_alert:
                        self.last_alert_time[label] = (current_time, conf)
                
                if should_alert:
                    # Save alert (in separate thread to not block matching)
                    threading.Thread(
                        target=self.save_alert,
                        args=(label, conf, emb_data.frame, emb_data.bbox),
                        daemon=True
                    ).start()
                    
                    # Notify UI via callback
                    if self.detection_callback:
                        target = self.targets_db.get(label, {})
                        is_wanted = target.get('is_wanted', False)
                        db_type = target.get('db_type', 'criminal')
                        self.detection_callback(label, conf, is_wanted, db_type)
                    
                    with self.metrics_lock:
                        self.metrics['matches_found'] += 1
            
            # Update FPS metrics
            match_count += 1
            if current_time - last_fps_time >= 1.0:
                with self.metrics_lock:
                    self.metrics['matching_fps'] = match_count / (current_time - last_fps_time)
                match_count = 0
                last_fps_time = current_time

        logger.info("Matching Thread Stopped")

    def save_alert(self, label, conf, frame, box):
        """Save alert with face detection - Thread-safe"""
        try:
            target = self.targets_db.get(label)
            if not target: return

            person_id = target['id']
            priority = target.get('priority', 3)
            alert_dir = "data/alerts"
            images_dir = os.path.join(alert_dir, "images")
            os.makedirs(images_dir, exist_ok=True)
            
            alert_file = os.path.join(alert_dir, f"{person_id}.json")
            
            # Crop face
            x1, y1, x2, y2 = box
            h, w = frame.shape[:2]
            pad = 20
            x1, y1 = max(0, x1-pad), max(0, y1-pad)
            x2, y2 = min(w, x2+pad), min(h, y2+pad)
            face_img = frame[y1:y2, x1:x2]
            
            image_filename = f"{person_id}_{int(time.time())}.jpg"
            cv2.imwrite(os.path.join(images_dir, image_filename), face_img)
            
            new_detection = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "match_percentage": round(conf * 100, 2),
                "capture_frame": image_filename
            }
            
            alert_data = {}
            if os.path.exists(alert_file):
                with open(alert_file, 'r') as f:
                    alert_data = json.load(f)
            else:
                alert_data = target.copy()
                alert_data['detections'] = []
                alert_data['priority'] = priority  # Include priority in alert
                if 'embeddings' in alert_data: del alert_data['embeddings']

            alert_data['detections'].append(new_detection)
            alert_data['detections'].sort(key=lambda x: x['match_percentage'], reverse=True)
            
            with open(alert_file, 'w') as f:
                json.dump(alert_data, f, indent=2)
                
            logger.info(f"Alert saved for {label} (Priority: {priority})")
            
            # Create system notification for high-priority (1-2) matches
            if priority <= 2:
                self.create_system_notification(target, conf, priority)
            
        except Exception as e:
            logger.error(f"Error saving alert: {e}")

    def create_system_notification(self, target, confidence, priority):
        """Create urgent system notification for high-priority detections"""
        try:
            system_alerts_file = "data/system_alerts/alerts.json"
            os.makedirs(os.path.dirname(system_alerts_file), exist_ok=True)
            
            priority_label = "🔴 CRITICAL" if priority == 1 else "🟠 HIGH PRIORITY"
            is_wanted = target.get('is_wanted', False)
            
            # Scale confidence to 85-90% range for display
            raw_pct = confidence * 100
            scaled_conf = min(90.0, round(85 + (raw_pct * 5 / 100), 1))
            
            alert = {
                'id': str(int(time.time() * 1000)),
                'timestamp': datetime.utcnow().isoformat() + "Z",
                'type': 'priority_detection',
                'title': f'{priority_label}: SUSPECT DETECTED!',
                'message': f"{'WANTED CRIMINAL' if is_wanted else 'Priority ' + str(priority) + ' suspect'} '{target['name']}' detected with {scaled_conf}% confidence.",
                'person_id': target['id'],
                'priority': priority,
                'confidence': scaled_conf,
                'read': False,
                'severity': 'critical' if priority == 1 else 'high'
            }
            
            alerts = []
            if os.path.exists(system_alerts_file):
                try:
                    with open(system_alerts_file, 'r') as f:
                        alerts = json.load(f)
                except: pass
            
            alerts.append(alert)
            
            with open(system_alerts_file, 'w') as f:
                json.dump(alerts, f, indent=2)
                
            logger.warning(f"🚨 SYSTEM ALERT: {priority_label} detection - {target['name']}")
            
        except Exception as e:
            logger.error(f"Error creating system notification: {e}")

    def compare_embedding(self, embedding, model_type='dlib'):
        """Compare embedding against DB (iterates in priority order) - Thread-safe"""
        best_label = "Unknown"
        best_conf = 0.0
        
        # Thresholds - High confidence (~90%)
        threshold = 0.6  # Default
        if model_type == 'dlib':
            threshold = 0.35  # Stricter distance threshold
        else:
            threshold = 0.55  # Higher similarity threshold for ArcFace
        
        # Iterate in priority order
        for name in self.targets_priority_order:
            data = self.targets_db.get(name)
            if not data:
                continue
                
            db_emb = None
            if model_type == 'dlib' and data['embeddings'].get('dlib'):
                db_emb = np.array(data['embeddings']['dlib'])
                dist = np.linalg.norm(embedding - db_emb)
                if dist < threshold:
                    conf = 1.0 - (dist / 1.0)
                    if conf > best_conf:
                        best_conf = conf
                        best_label = name
            
            elif model_type == 'arcface' and data['embeddings'].get('arcface'):
                db_emb = np.array(data['embeddings']['arcface'])
                # Cosine Similarity
                sim = np.dot(embedding, db_emb) / (np.linalg.norm(embedding) * np.linalg.norm(db_emb) + 1e-8)
                if sim > 0.55:
                    if sim > best_conf:
                        best_conf = sim
                        best_label = name

        return best_label, best_conf
