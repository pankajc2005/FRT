import cv2
import dlib
import numpy as np
from insightface.app import FaceAnalysis
import os

# ----------------------------
# Load Models
# ----------------------------
dlib_detector = dlib.get_frontal_face_detector()
dlib_shape_predictor = dlib.shape_predictor("models/shape_predictor_68_face_landmarks.dat")
dlib_face_rec_model = dlib.face_recognition_model_v1("models/dlib_face_recognition_resnet_model_v1.dat")

arcface_app = FaceAnalysis(providers=['CPUExecutionProvider'])
arcface_app.prepare(ctx_id=0, det_size=(640, 640))

# ----------------------------
# Helper Functions
# ----------------------------
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

def save_embedding(embedding, folder, photo_id):
    """Save embedding as .npy file"""
    os.makedirs(folder, exist_ok=True)
    file_path = os.path.join(folder, f"{photo_id}.npy")
    np.save(file_path, embedding)
    print(f"Saved embedding: {file_path}")

# ----------------------------
# Main Execution
# ----------------------------
image_path = input("Enter image path: ")
img_rgb, img_gray = read_image(image_path)

# Use filename without extension as ID
photo_id = os.path.splitext(os.path.basename(image_path))[0]

# ----------------------------
# Dlib Embedding
# ----------------------------
faces = dlib_detector(img_gray, 1)
if len(faces) == 0:
    raise Exception("No face detected for dlib embedding.")
face_rect = faces[0]
shape = dlib_shape_predictor(img_gray, face_rect)
face_chip = dlib.get_face_chip(img_rgb, shape, size=150)
dlib_embedding = np.array(dlib_face_rec_model.compute_face_descriptor(face_chip))

# Save dlib embedding
save_embedding(dlib_embedding, "embeddings/dlib", photo_id)

# ----------------------------
# ArcFace Embedding
# ----------------------------
arcface_results = arcface_app.get(img_rgb)
if len(arcface_results) == 0:
    raise Exception("No face detected for ArcFace embedding.")

arcface_embedding = arcface_results[0].embedding
# Save ArcFace embedding
save_embedding(arcface_embedding, "embeddings/arface", photo_id)

# Optional: save age and gender
age = arcface_results[0].age
gender = arcface_results[0].gender
print(f"Predicted Age: {age}, Gender: {gender}")
