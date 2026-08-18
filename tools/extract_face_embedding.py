#!/usr/bin/env python
"""One-shot face-embedding extractor for the Arconium studio Asset Memory Bank.

Usage:  python extract_face_embedding.py <absolute_image_path>

Loads insightface (antelopev2) on CPU, detects faces, picks the LARGEST-bbox
face (the primary subject), and writes ONE JSON line to stdout:
  {"embedding": [...512 floats...], "dim": 512, "det_score": 0.87, "bbox": [...]}

Exit codes:  0 ok | 2 load/IO/decode error | 3 no face detected.

All library chatter (insightface bare print(), onnxruntime warnings) is kept
OFF stdout so the single JSON line parses cleanly on the Node bridge side.
Runs inside the ComfyUI .venv where insightface 1.0.1 + antelopev2 live.
"""
import sys
import os
import json


def _fail(code, msg):
    sys.stderr.write(json.dumps({"error": msg}) + "\n")
    sys.exit(code)


def main():
    if len(sys.argv) < 2:
        _fail(2, "usage: extract_face_embedding.py <image_path>")
    img_path = sys.argv[1]
    if not os.path.isfile(img_path):
        _fail(2, "image not found: " + img_path)

    # Suppress startup chatter: route stdout to stderr DURING import + model
    # load (insightface/onnxruntime print to stdout), restore only to emit JSON.
    real_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        import onnxruntime as ort

        ort.set_default_logger_severity(3)
        import cv2
        from insightface.app import FaceAnalysis

        # antelopev2 lives under ComfyUI/models/insightface; resolve the root
        # from this script's location (ComfyUI/tools/..) with an env override.
        comfy_home = os.environ.get(
            "COMFYUI_HOME",
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        root = os.path.join(comfy_home, "models", "insightface")

        app = FaceAnalysis(
            name="antelopev2", root=root, providers=["CPUExecutionProvider"]
        )
        app.prepare(ctx_id=-1, det_size=(640, 640))

        img = cv2.imread(img_path)
        if img is None:
            _fail(2, "could not decode image: " + img_path)
        faces = app.get(img)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        _fail(2, "insightface load/inference failed: " + str(e))
    finally:
        sys.stdout = real_stdout

    if not faces:
        _fail(3, "no face detected")

    def _area(f):
        x1, y1, x2, y2 = f.bbox
        return (x2 - x1) * (y2 - y1)

    face = max(faces, key=_area)
    emb = face.normed_embedding  # 512-D, unit-norm by construction
    out = {
        "embedding": [float(x) for x in emb.tolist()],
        "dim": int(emb.shape[0]),
        "det_score": float(getattr(face, "det_score", 0.0)),
        "bbox": [float(x) for x in face.bbox.tolist()],
    }
    sys.stdout.write(json.dumps(out) + "\n")
    sys.stdout.flush()
    sys.exit(0)


if __name__ == "__main__":
    main()
