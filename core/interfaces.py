from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple
import numpy as np

class IPlugin(ABC):
    """Base interface for all plugins."""
    @abstractmethod
    def initialize(self, config: Dict[str, Any]) -> None:
        """Initialize the plugin with configuration."""
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """Cleanup resources."""
        pass

class IVideoSource(IPlugin):
    """Interface for video input sources (Webcam, IP Cam, File)."""
    @abstractmethod
    def get_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Read a frame from the source.
        Returns: (success, frame)
        """
        pass

class IFaceModel(IPlugin):
    """Interface for face detection and recognition models."""
    @abstractmethod
    def detect_faces(self, frame: np.ndarray) -> list:
        """
        Detect faces in the frame.
        Returns list of bounding boxes or face objects.
        """
        pass

    @abstractmethod
    def generate_embedding(self, face_image: np.ndarray) -> Optional[np.ndarray]:
        """
        Generate a vector embedding for a face crop.
        """
        pass
