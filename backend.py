"""
Robot Grid Backend
------------------
Endpoints:
  GET  /health          – liveness check
  POST /plan            – receives a base64 PNG + grid_rows/grid_cols,
                          thresholds it into binary cells, returns cell list
  POST /execute         – receives a list of {row, col} cells and
                          prints/logs them (swap this out for real robot comms)
"""

import base64
import io
import json
import logging
from typing import Any

from flask import Flask, jsonify, request
from PIL import Image
import numpy as np

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
from flask_cors import CORS
CORS(app)
# Threshold: pixels darker than this (0–255) count as "filled"
PIXEL_THRESHOLD = 128


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def decode_image(b64: str) -> Image.Image:
    """Decode a data-URI or raw base64 string into a PIL Image."""
    # Strip the data-URI prefix if present (e.g. "data:image/png;base64,...")
    if "," in b64:
        b64 = b64.split(",", 1)[1]
    raw = base64.b64decode(b64)
    return Image.open(io.BytesIO(raw)).convert("L")  # grayscale


def image_to_cells(img: Image.Image, rows: int, cols: int) -> list[dict[str, int]]:
    """
    Resize the image to (cols × rows), threshold each pixel,
    and return a list of filled cell coordinates.
    """
    # Resize to exactly (cols wide, rows tall)
    img_resized = img.resize((cols, rows), Image.LANCZOS)
    arr = np.array(img_resized)  # shape (rows, cols), values 0-255

    cells: list[dict[str, int]] = []
    for r in range(rows):
        for c in range(cols):
            if arr[r, c] < PIXEL_THRESHOLD:
                cells.append({"row": r, "col": c})
    return cells


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/plan", methods=["POST"])
def plan():
    """
    Body (JSON):
      {
        "image_b64": "<base64 PNG>",
        "grid_rows": <int>,   // number of rows  (defaults to 8)
        "grid_cols": <int>    // number of columns (defaults to 8)
      }

    Returns:
      { "cells": [{"row": r, "col": c}, ...], "grid_rows": r, "grid_cols": c }
    """
    body: dict[str, Any] = request.get_json(force=True)

    image_b64 = body.get("image_b64", "")
    rows = int(body.get("grid_rows", 8))
    cols = int(body.get("grid_cols", 8))

    if not image_b64:
        return jsonify({"error": "image_b64 is required"}), 400
    if rows < 1 or cols < 1:
        return jsonify({"error": "grid_rows and grid_cols must be >= 1"}), 400

    try:
        img = decode_image(image_b64)
        cells = image_to_cells(img, rows, cols)
    except Exception as exc:
        logger.exception("Failed to process image")
        return jsonify({"error": str(exc)}), 500

    logger.info("plan: %d×%d grid → %d filled cells", rows, cols, len(cells))
    return jsonify({"cells": cells, "grid_rows": rows, "grid_cols": cols})


@app.route("/execute", methods=["POST"])
def execute():
    """
    Body (JSON):
      {
        "cells": [{"row": r, "col": c}, ...],
        "grid_rows": <int>,   // optional metadata
        "grid_cols": <int>    // optional metadata
      }

    In production, replace the logging block below with actual robot commands
    (e.g. serial write, motor driver calls, CNC G-code, etc.).

    Returns:
      { "status": "executed", "cells_received": <int> }
    """
    body: dict[str, Any] = request.get_json(force=True)
    cells: list[dict[str, int]] = body.get("cells", [])
    rows = body.get("grid_rows")
    cols = body.get("grid_cols")

    if not isinstance(cells, list):
        return jsonify({"error": "cells must be a list"}), 400

    # ---------------------------------------------------------------------------
    # 🤖  ROBOT INTEGRATION POINT – replace this block with real hardware calls
    # ---------------------------------------------------------------------------
    logger.info(
        "execute: received %d cells (grid %s×%s)",
        len(cells),
        rows or "?",
        cols or "?",
    )

    # Pretty-print a grid to the console for debugging
    if rows and cols:
        grid = [["·" for _ in range(cols)] for _ in range(rows)]
        for cell in cells:
            r, c = cell["row"], cell["col"]
            if 0 <= r < rows and 0 <= c < cols:
                grid[r][c] = "■"
        print("\nRobot target grid:")
        for row in grid:
            print("  " + " ".join(row))
        print()
    else:
        print("\nRobot target cells:", json.dumps(cells, indent=2))
    # ---------------------------------------------------------------------------

    return jsonify({"status": "executed", "cells_received": len(cells)})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)