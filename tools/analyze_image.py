#!/usr/bin/env python
"""One-shot deterministic image-stats analyzer for the Arconium studio QC (P2.4).

Usage:  python analyze_image.py <absolute_image_path>

Computes NON-LLM, bias-free pixel statistics the QC gate folds in alongside the
VLM judge: dimensions, luminance mean/std (blank/degenerate detection), and the
dominant color palette (brand-conformance). Writes ONE JSON line to stdout:
  {"width":1024,"height":1024,"luma_mean":118.3,"luma_std":51.7,
   "palette":[[12,10,30,0.21],[200,180,160,0.14], ...]}

Exit codes:  0 ok | 2 load/IO/decode error.

Uses Pillow + numpy, both already in the ComfyUI .venv. Keeps all library
chatter OFF stdout so the single JSON line parses cleanly on the Node side.
"""
import sys
import os
import json


def _fail(code, msg):
    sys.stderr.write(json.dumps({"error": msg}) + "\n")
    sys.exit(code)


def main():
    if len(sys.argv) < 2:
        _fail(2, "usage: analyze_image.py <image_path>")
    img_path = sys.argv[1]
    if not os.path.isfile(img_path):
        _fail(2, "image not found: " + img_path)

    # Silence library chatter on BOTH levels: reassign the Python sys.stdout
    # object AND redirect OS fd 1 → fd 2, so a C-extension (numpy/Pillow) that
    # writes straight to file descriptor 1 can't corrupt the single JSON line.
    real_stdout = sys.stdout
    saved_fd1 = os.dup(1)
    sys.stdout = sys.stderr
    os.dup2(2, 1)
    try:
        import numpy as np
        from PIL import Image

        with Image.open(img_path) as im:
            im = im.convert("RGB")
            width, height = im.size
            # Downscale for stats — palette + luma are scale-robust and this
            # keeps a 4K still cheap (a few ms instead of decoding every pixel).
            sample = im.copy()
            sample.thumbnail((256, 256))
            arr = np.asarray(sample, dtype=np.float32)  # H x W x 3

        # Rec. 601 luma.
        luma = arr[..., 0] * 0.299 + arr[..., 1] * 0.587 + arr[..., 2] * 0.114
        luma_mean = float(luma.mean())
        luma_std = float(luma.std())

        # Dominant palette: quantize to a 4-bit-per-channel grid (4096 bins),
        # count, take the top buckets, and report each bucket's mean color +
        # fraction of pixels. Cheap, deterministic, no clustering needed.
        flat = arr.reshape(-1, 3)
        total = flat.shape[0]
        quant = (flat / 16.0).astype(np.int32)  # 0..15 per channel
        keys = quant[:, 0] * 256 + quant[:, 1] * 16 + quant[:, 2]
        uniq, counts = np.unique(keys, return_counts=True)
        order = np.argsort(counts)[::-1][:8]
        palette = []
        for idx in order:
            mask = keys == uniq[idx]
            mean_rgb = flat[mask].mean(axis=0)
            frac = float(counts[idx]) / float(total)
            palette.append(
                [
                    int(round(mean_rgb[0])),
                    int(round(mean_rgb[1])),
                    int(round(mean_rgb[2])),
                    round(frac, 4),
                ]
            )
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        _fail(2, "image analysis failed: " + str(e))
    finally:
        sys.stderr.flush()
        sys.stdout = real_stdout
        os.dup2(saved_fd1, 1)
        os.close(saved_fd1)

    out = {
        "width": int(width),
        "height": int(height),
        "luma_mean": round(luma_mean, 2),
        "luma_std": round(luma_std, 2),
        "palette": palette,
    }
    sys.stdout.write(json.dumps(out) + "\n")
    sys.stdout.flush()
    sys.exit(0)


if __name__ == "__main__":
    main()
