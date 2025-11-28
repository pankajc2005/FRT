import os
import sys
import time
import cv2
from core.plugin_manager import PluginManager

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def main():
    print("Starting Modular FRT System...")
    
    # 1. Load Config
    config_path = os.path.join("config", "config.yaml")
    if not os.path.exists(config_path):
        print("Config file not found!")
        return

    # 2. Initialize Plugin Manager
    pm = PluginManager()
    import yaml
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # 3. Load Components
    try:
        camera = pm.initialize_camera(config)
        model = pm.initialize_model(config)
    except Exception as e:
        print(f"Initialization Error: {e}")
        return

    print("System Ready. Press 'q' to quit.")

    # 4. Main Loop
    while True:
        ret, frame = camera.get_frame()
        if not ret:
            print("Failed to grab frame")
            break

        # Detect Faces
        faces = model.detect_faces(frame)
        
        # Draw Rectangles
        for face in faces:
            # Check if it's an ArcFace object (has bbox property)
            if hasattr(face, 'bbox'): 
                bbox = face.bbox.astype(int)
                x1, y1, x2, y2 = bbox[0], bbox[1], bbox[2], bbox[3]
                label = f"ArcFace {face.det_score:.2f}"
            # Check if it's a Dlib rect (has left method)
            elif hasattr(face, 'left') and callable(face.left): 
                x1, y1, x2, y2 = face.left(), face.top(), face.right(), face.bottom()
                label = "Dlib"
            else:
                continue

            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, label, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        cv2.imshow("Modular FRT", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # 5. Cleanup
    camera.shutdown()
    model.shutdown()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
