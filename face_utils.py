import cv2
import dlib
import numpy as np
try:
    from insightface.app import FaceAnalysis
except ImportError:
    FaceAnalysis = None
    print("Warning: insightface not installed. ArcFace features will be disabled.")
import os

# ----------------------------
# Load Models
# ----------------------------
# Initialize these lazily or globally
dlib_detector = None
dlib_shape_predictor = None
dlib_face_rec_model = None
arcface_app = None

def load_models():
    global dlib_detector, dlib_shape_predictor, dlib_face_rec_model, arcface_app
    
    if dlib_detector is None:
        dlib_detector = dlib.get_frontal_face_detector()
        dlib_shape_predictor = dlib.shape_predictor("models/shape_predictor_68_face_landmarks.dat")
        dlib_face_rec_model = dlib.face_recognition_model_v1("models/dlib_face_recognition_resnet_model_v1.dat")

    if arcface_app is None and FaceAnalysis is not None:
        try:
            arcface_app = FaceAnalysis(providers=['CPUExecutionProvider'])
            arcface_app.prepare(ctx_id=0, det_size=(640, 640))
        except Exception as e:
            print(f"Failed to initialize ArcFace: {e}")

def read_image(image_path):
    """Reads image, converts to RGB and grayscale, ensures contiguous memory"""
    img_bgr = cv2.imread(image_path)
    if img_bgr is None:
        raise Exception(f"Image not found or cannot be read: {image_path}")
    
    # RGB uint8
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    img_rgb = np.ascontiguousarray(img_rgb, dtype=np.uint8)

    # Grayscale uint8
    img_gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    img_gray = np.ascontiguousarray(img_gray, dtype=np.uint8)

    return img_rgb, img_gray

def get_embeddings(image_path):
    load_models()
    img_rgb, img_gray = read_image(image_path)
    
    results = {}

    # ----------------------------
    # Dlib Embedding
    # ----------------------------
    faces = dlib_detector(img_gray, 1)
    if len(faces) > 0:
        face_rect = faces[0]
        shape = dlib_shape_predictor(img_gray, face_rect)
        face_chip = dlib.get_face_chip(img_rgb, shape, size=150)
        dlib_embedding = np.array(dlib_face_rec_model.compute_face_descriptor(face_chip))
        results['dlib'] = dlib_embedding.tolist()
    else:
        results['dlib'] = None

    # ----------------------------
    # ArcFace Embedding
    # ----------------------------
    if arcface_app is not None:
        arcface_results = arcface_app.get(img_rgb)
        if len(arcface_results) > 0:
            face = arcface_results[0]
            results['arcface'] = face.embedding.tolist()
            results['age'] = int(face.age)
            results['gender'] = "Male" if face.gender == 1 else "Female"
        else:
            results['arcface'] = None
            results['age'] = None
            results['gender'] = None
    else:
        results['arcface'] = None
        results['age'] = None
        results['gender'] = None

    return results
