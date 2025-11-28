import numpy as np
import os
from typing import Dict, Any, List, Optional
from insightface.app import FaceAnalysis
from core.interfaces import IFaceModel

class ArcFaceModel(IFaceModel):
    def __init__(self):
        self.app = None
        self.det_size = (640, 640)

    def initialize(self, config: Dict[str, Any]) -> None:
        self.det_size = tuple(config.get('det_size', [640, 640]))
        # 'providers' can be configured, e.g., ['CUDAExecutionProvider'] if GPU available
        providers = config.get('providers', ['CPUExecutionProvider'])
        
        self.app = FaceAnalysis(providers=providers)
        # ctx_id=0 usually means GPU 0, -1 means CPU. 
        # If using CPU provider, ctx_id is ignored or should be -1.
        ctx_id = 0 if 'CUDAExecutionProvider' in providers else -1
        
        self.app.prepare(ctx_id=ctx_id, det_size=self.det_size)
        print(f"ArcFace Plugin Initialized (Providers: {providers})")

    def detect_faces(self, frame: np.ndarray) -> List[Any]:
        if self.app is None:
            return []
        # ArcFace 'get' returns a list of Face objects (with bbox, kps, embedding, etc.)
        # We might want to standardize the return type for the interface, 
        # but for now we return the raw objects or a standardized dict.
        # The interface says "list of bounding boxes or face objects".
        return self.app.get(frame)

    def generate_embedding(self, face_image: np.ndarray) -> Optional[np.ndarray]:
        # ArcFace 'get' runs detection + recognition.
        # If we pass a crop, it might try to detect a face inside the crop.
        # If the crop is tight, detection might fail.
        # InsightFace usually expects a full image.
        
        # However, if we just want the embedding from a crop, we might need a recognizer-only call.
        # The high-level FaceAnalysis app doesn't expose "recognize only" easily without detection.
        # But we can try passing the crop.
        
        results = self.app.get(face_image)
        if results:
            # Return the embedding of the most prominent face
            # (Assuming the crop contains mainly the face)
            # Sort by size or centrality if multiple found
            return results[0].embedding
        return None

    def shutdown(self) -> None:
        self.app = None
