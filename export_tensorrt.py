"""One-click PyTorch -> TensorRT engine converter.

Converts the YOLO pose model into a high-performance TensorRT engine:
    python export_tensorrt.py
Requires the `tensorrt` Python package and a CUDA GPU. Falls back to FP32
if half-precision export fails on the local TensorRT version.
"""

import os
import sys

from ultralytics import YOLO

import config


def main() -> int:
    src = config.MODEL_PATH
    dst = config.MODEL_ENGINE

    if not os.path.exists(src):
        print(f"ERROR: source model not found: {src}")
        return 1

    try:
        import tensorrt  # noqa: F401
    except ImportError:
        print(
            "TensorRT Python package is not installed.\n"
            "Install it first (see README) or the app will fall back to the .pt model."
        )
        return 1

    try:
        import torch

        if not torch.cuda.is_available():
            print("ERROR: no CUDA GPU detected. TensorRT requires a CUDA device.")
            return 1
    except ImportError:
        print("ERROR: PyTorch not available.")
        return 1

    print(f"Converting {src} -> {dst} (imgsz={config.MODEL_IMGSZ}, half=True)...")
    try:
        # Explicit device ensures the engine is built for the local GPU.
        model = YOLO(src)
        model.to("0")
        model.export(
            format="engine",
            imgsz=config.MODEL_IMGSZ,
            half=True,
            device="0",
            workspace=8,
        )
    except Exception:
        print("FP16 export failed - retrying with half=False (FP32)...")
        model = YOLO(src)
        model.export(
            format="engine",
            imgsz=config.MODEL_IMGSZ,
            half=False,
            device="0",
            workspace=8,
        )

    if os.path.exists(dst):
        print(f"SUCCESS: {dst} created ({os.path.getsize(dst) / 1e6:.1f} MB).")
        return 0
    print("Export finished but output file not found; check the logs above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())