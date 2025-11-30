import numpy as np
import cv2
from typing import Dict, Any, List, Optional, Tuple
import logging

logger = logging.getLogger("YOLOWeaponPlugin")

class YOLOWeaponDetector:
    """YOLOv8 Weapon Detection Plugin"""
    
    def __init__(self):
        self.model = None
        self.confidence_threshold = 0.70  # Default threshold
        self.model_path = 'models/best.pt'
        self.classes = []  # Will be populated from model
        
    def initialize(self, config: Dict[str, Any]) -> None:
        """Initialize the YOLOv8 weapon detection model"""
        self.model_path = config.get('model_path', 'models/best.pt')
        self.confidence_threshold = config.get('confidence_threshold', 0.65)
        
        try:
            from ultralytics import YOLO
            self.model = YOLO(self.model_path)
            self.classes = self.model.names if hasattr(self.model, 'names') else {}
            logger.info(f"YOLOv8 Weapon Detection Plugin Initialized")
            logger.info(f"  Model: {self.model_path}")
            logger.info(f"  Confidence Threshold: {self.confidence_threshold}")
            logger.info(f"  Classes: {list(self.classes.values()) if self.classes else 'Unknown'}")
        except ImportError:
            logger.error("ultralytics package not installed. Run: pip install ultralytics")
            raise
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
            raise
    
    def detect(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """
        Detect weapons in a frame
        
        Args:
            frame: BGR image as numpy array
            
        Returns:
            List of detections, each containing:
                - bbox: (x1, y1, x2, y2)
                - confidence: float
                - class_id: int
                - class_name: str
        """
        if self.model is None:
            return []
        
        detections = []
        
        try:
            results = self.model(frame, verbose=False, conf=self.confidence_threshold)
            
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                    conf = float(box.conf[0].cpu().numpy())
                    cls = int(box.cls[0].cpu().numpy())
                    class_name = result.names.get(cls, f"Class_{cls}")
                    
                    detections.append({
                        'bbox': (x1, y1, x2, y2),
                        'confidence': conf,
                        'class_id': cls,
                        'class_name': class_name
                    })
                    
        except Exception as e:
            logger.error(f"Detection error: {e}")
        
        return detections
    
    def detect_and_draw(self, frame: np.ndarray) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
        """
        Detect weapons and draw bounding boxes on frame
        
        Args:
            frame: BGR image as numpy array
            
        Returns:
            Tuple of (annotated_frame, detections)
        """
        detections = self.detect(frame)
        annotated_frame = frame.copy()
        
        for det in detections:
            x1, y1, x2, y2 = det['bbox']
            conf = det['confidence']
            class_name = det['class_name']
            
            # Draw red bounding box
            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
            
            # Draw label background
            label = f"{class_name} {conf:.0%}"
            (label_w, label_h), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
            cv2.rectangle(annotated_frame, (x1, y1 - label_h - 10), (x1 + label_w + 10, y1), (0, 0, 255), -1)
            
            # Draw label text
            cv2.putText(annotated_frame, label, (x1 + 5, y1 - 5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # Add threat warning if detections found
        if detections:
            cv2.putText(annotated_frame, "! THREAT DETECTED !", (10, 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
            cv2.putText(annotated_frame, "! THREAT DETECTED !", (10, 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 1)
        
        return annotated_frame, detections
    
    def set_confidence_threshold(self, threshold: float) -> None:
        """Update the confidence threshold"""
        self.confidence_threshold = max(0.1, min(1.0, threshold))
        logger.info(f"Confidence threshold updated to: {self.confidence_threshold}")
    
    def get_confidence_threshold(self) -> float:
        """Get current confidence threshold"""
        return self.confidence_threshold
    
    def shutdown(self) -> None:
        """Cleanup resources"""
        self.model = None
        logger.info("YOLOv8 Weapon Detection Plugin shutdown")
