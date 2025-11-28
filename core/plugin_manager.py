import importlib
import logging
import os
import sys
from typing import Dict, Any, Type
from .interfaces import IPlugin, IFaceModel, IVideoSource

# Ensure the root directory is in path to load plugins
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

logger = logging.getLogger("PluginManager")

class PluginManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PluginManager, cls).__new__(cls)
            cls._instance.plugins = {}
            cls._instance.active_model = None
            cls._instance.active_camera = None
        return cls._instance

    def load_plugin(self, module_path: str, class_name: str) -> Type[IPlugin]:
        """Dynamically load a plugin class."""
        try:
            module = importlib.import_module(module_path)
            plugin_class = getattr(module, class_name)
            return plugin_class
        except Exception as e:
            logger.error(f"Failed to load plugin {module_path}.{class_name}: {e}")
            raise

    def initialize_model(self, config: Dict[str, Any]) -> IFaceModel:
        """Initialize the face recognition model defined in config."""
        model_cfg = config.get('active_components', {}).get('face_model')
        if not model_cfg:
            raise ValueError("No face_model defined in active_components")

        plugin_def = config.get('models', {}).get(model_cfg)
        if not plugin_def:
            raise ValueError(f"Model definition for {model_cfg} not found")

        cls = self.load_plugin(plugin_def['module'], plugin_def['class'])
        instance = cls()
        instance.initialize(plugin_def.get('params', {}))
        self.active_model = instance
        logger.info(f"Initialized Face Model: {model_cfg}")
        return instance

    def initialize_camera(self, config: Dict[str, Any]) -> IVideoSource:
        """Initialize the camera source defined in config."""
        cam_cfg = config.get('active_components', {}).get('camera')
        if not cam_cfg:
            raise ValueError("No camera defined in active_components")

        plugin_def = config.get('cameras', {}).get(cam_cfg)
        if not plugin_def:
            raise ValueError(f"Camera definition for {cam_cfg} not found")

        cls = self.load_plugin(plugin_def['module'], plugin_def['class'])
        instance = cls()
        instance.initialize(plugin_def.get('params', {}))
        self.active_camera = instance
        logger.info(f"Initialized Camera: {cam_cfg}")
        return instance
