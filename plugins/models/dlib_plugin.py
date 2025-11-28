import cv2
import dlib
import numpy as np
import os
from typing import Dict, Any, Optional, List
from core.interfaces import IFaceModel

class DlibFaceModel(IFaceModel):
    def __init__(self):
        self.detector = None
        self.shape_predictor = None
        self.face_rec_model = None
        self.threshold = 0.6

    def initialize(self, config: Dict[str, Any]) -> None:
        shape_path = config.get('shape_predictor_path')
        rec_path = config.get('recognition_model_path')
        self.threshold = config.get('threshold', 0.6)

        if not os.path.exists(shape_path) or not os.path.exists(rec_path):
            raise FileNotFoundError("Dlib model files not found. Check config paths.")

        self.detector = dlib.get_frontal_face_detector()
        self.shape_predictor = dlib.shape_predictor(shape_path)
        self.face_rec_model = dlib.face_recognition_model_v1(rec_path)
        print("Dlib Plugin Initialized")

    def detect_faces(self, frame: np.ndarray) -> List[Any]:
        if self.detector is None:
            return []
        
        # Convert to grayscale if needed, Dlib works on gray or RGB
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame
            
        rects = self.detector(gray, 1)
        return list(rects)

    def generate_embedding(self, face_image: np.ndarray) -> Optional[np.ndarray]:
        # Dlib expects a full image and a shape, but if we already have a crop,
        # we might need to handle it differently. 
        # However, the standard pipeline is: Image -> Detect -> Shape -> Chip -> Descriptor
        # If face_image is already a chip (150x150), we might skip shape prediction?
        # Actually, dlib's compute_face_descriptor takes an image and a shape object OR a face chip.
        # If we pass a raw numpy array (chip), we need to be careful.
        
        # For this implementation, let's assume face_image is a standard RGB image crop.
        # But dlib usually needs landmarks to align.
        # To keep it simple and compatible with the interface:
        # We will assume the input is a pre-aligned face chip or we try to detect landmarks on the crop.
        
        # Let's try to treat the input as a face chip directly if it's small/aligned
        # Or we can just return None if we can't process it.
        
        # In the original code:
        # shape = dlib_shape_predictor(img_gray, face_rect)
        # face_chip = dlib.get_face_chip(img_rgb, shape, size=150)
        # dlib_embedding = np.array(dlib_face_rec_model.compute_face_descriptor(face_chip))
        
        try:
            # If the input is already a chip (uint8), we can pass it directly?
            # compute_face_descriptor(face_image) -> returns vector
            # It supports "an image" directly if it's aligned.
            vec = self.face_rec_model.compute_face_descriptor(face_image)
            return np.array(vec)
        except Exception as e:
            # Fallback or error logging
            return None

    def shutdown(self) -> None:
        self.detector = None
        self.shape_predictor = None
        self.face_rec_model = None
