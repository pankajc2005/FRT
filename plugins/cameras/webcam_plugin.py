import cv2
import numpy as np
from typing import Dict, Any, Tuple, Optional
from core.interfaces import IVideoSource

class WebcamSource(IVideoSource):
    def __init__(self):
        self.cap = None
        self.device_id = 0

    def initialize(self, config: Dict[str, Any]) -> None:
        self.device_id = config.get('device_id', 0)
        # Use CAP_DSHOW on Windows for faster startup
        self.cap = cv2.VideoCapture(self.device_id, cv2.CAP_DSHOW)
        
        width = config.get('width', 640)
        height = config.get('height', 480)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        
        if not self.cap.isOpened():
            raise RuntimeError(f"Failed to open webcam {self.device_id}")
        print(f"Webcam Plugin Initialized: Device {self.device_id}")

    def get_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            return ret, frame
        return False, None

    def shutdown(self) -> None:
        if self.cap and self.cap.isOpened():
            self.cap.release()
