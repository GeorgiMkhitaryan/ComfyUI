import sys
import os
import json
import cv2
import numpy as np

def main():
    if len(sys.argv) < 2:
        sys.exit(2)

    img_path = sys.argv[1]
    if not os.path.exists(img_path):
        sys.exit(2)

    try:
        import insightface
        from insightface.app import FaceAnalysis
    except Exception as e:
        sys.stderr.write(f"Import error: {e}\n")
        sys.exit(2)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, "..", "models", "insightface"),
        "D:/Project/ComfyUI/models/insightface",
        os.path.expanduser("~/.insightface/models"),
    ]
    root_dir = next((c for c in candidates if os.path.exists(c)), None)

    try:
        img = cv2.imread(img_path)
        if img is None:
            sys.exit(2)

        model_name = "antelopev2"
        if root_dir and not os.path.exists(os.path.join(root_dir, "models", "antelopev2")):
            if os.path.exists(os.path.join(root_dir, "models", "buffalo_l")):
                model_name = "buffalo_l"

        app = FaceAnalysis(name=model_name, root=root_dir, providers=['CPUExecutionProvider'])
        app.prepare(ctx_id=0, det_size=(640, 640))
        faces = app.get(img)

        if not faces:
            sys.exit(3)

        faces.sort(key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]), reverse=True)
        largest_face = faces[0]

        embedding = largest_face.embedding.tolist()
        print(json.dumps({"embedding": embedding}))
        sys.exit(0)
    except Exception as e:
        sys.stderr.write(f"Inference error: {e}\n")
        sys.exit(2)

if __name__ == "__main__":
    main()
