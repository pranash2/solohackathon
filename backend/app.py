from __future__ import annotations

import base64
import io
import os
import time
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any

import numpy as np
from PIL import Image
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # allow frontend localhost file:// or other origins during hackathon

OUT_DIR = os.path.join(os.path.dirname(__file__), "received")
os.makedirs(OUT_DIR, exist_ok=True)

GridCell = Tuple[int, int]  # (x, y)

@dataclass
class Plan:
  grid_n: int
  grid: List[List[int]]         # 0/1 occupancy
  cells: List[GridCell]         # list of occupied cells
  debug: Dict[str, Any]

def _decode_data_url_png(data_url: str) -> Image.Image:
  """
  data_url: "data:image/png;base64,...."
  """
  if "," not in data_url:
    raise ValueError("Invalid data URL")
  header, b64 = data_url.split(",", 1)
  raw = base64.b64decode(b64)
  return Image.open(io.BytesIO(raw)).convert("L")  # grayscale

def _image_to_grid(img_gray: Image.Image, grid_n: int = 8, threshold: int = 30) -> Plan:
  """
  Convert a grayscale drawing into an 8x8 occupancy grid.
  We consider "ink" as dark pixels (< 255 - threshold).
  """
  w, h = img_gray.size
  arr = np.array(img_gray, dtype=np.uint8)

  # Treat dark pixels as ink
  ink = (arr < (255 - threshold)).astype(np.uint8)

  cell_w = w / grid_n
  cell_h = h / grid_n

  grid_counts = np.zeros((grid_n, grid_n), dtype=np.int32)

  # Sum ink per cell
  for y in range(h):
    gy = int(y / cell_h)
    if gy >= grid_n: 
      gy = grid_n - 1
    for x in range(w):
      gx = int(x / cell_w)
      if gx >= grid_n:
        gx = grid_n - 1
      grid_counts[gy, gx] += int(ink[y, x])

  # occupancy: cell is "on" if ink pixels exceed a fraction of cell area
  cell_area = (w * h) / (grid_n * grid_n)
  occ_thresh = max(10, int(0.02 * cell_area))  # 2% of cell area or >=10 pixels
  occ = (grid_counts >= occ_thresh).astype(np.uint8)

  cells: List[GridCell] = []
  for gy in range(grid_n):
    for gx in range(grid_n):
      if occ[gy, gx] == 1:
        cells.append((gx, gy))

  plan = Plan(
    grid_n=grid_n,
    grid=occ.tolist(),
    cells=cells,
    debug={
      "image_size": [w, h],
      "cell_area": float(cell_area),
      "occ_thresh": int(occ_thresh),
      "total_cells_on": int(len(cells)),
    }
  )
  return plan

def _order_cells(cells: List[GridCell], mode: str = "row_major") -> List[GridCell]:
  if mode == "row_major":
    return sorted(cells, key=lambda c: (c[1], c[0]))  # y then x
  if mode == "col_major":
    return sorted(cells, key=lambda c: (c[0], c[1]))
  return cells

def _send_to_robot_stub(cells: List[GridCell]) -> None:
  """
  TODO: replace this with your actual robot execution.
  For now we just log. Later you’ll call Solo movement primitives
  or your policy executor.
  """
  print(f"[ROBOT] would place blocks at: {cells}")

@app.get("/health")
def health():
  return jsonify({"ok": True})

@app.post("/plan")
def plan():
  payload = request.get_json(force=True)
  image_b64 = payload.get("image_b64")
  grid_n = int(payload.get("grid_n", 8))
  order = payload.get("order", "row_major")

  if not image_b64:
    return jsonify({"error": "missing image_b64"}), 400

  try:
    img = _decode_data_url_png(image_b64)

    # Save raw input for debugging
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(OUT_DIR, f"drawing_{ts}.png")
    img.save(path)

    plan_obj = _image_to_grid(img, grid_n=grid_n)
    ordered = _order_cells(plan_obj.cells, mode=order)

    return jsonify({
      "grid_n": plan_obj.grid_n,
      "grid": plan_obj.grid,
      "cells": ordered,
      "debug": {**plan_obj.debug, "saved_path": path, "order": order},
    })
  except Exception as e:
    return jsonify({"error": str(e)}), 500

@app.post("/execute")
def execute():
  """
  Receives a list of grid cells and (later) drives the robot.
  """
  payload = request.get_json(force=True)
  cells = payload.get("cells", [])

  # Basic validation
  if not isinstance(cells, list):
    return jsonify({"error": "cells must be a list"}), 400

  norm_cells: List[GridCell] = []
  for c in cells:
    if not (isinstance(c, list) or isinstance(c, tuple)) or len(c) != 2:
      continue
    x, y = int(c[0]), int(c[1])
    norm_cells.append((x, y))

  # Robot stub for now
  _send_to_robot_stub(norm_cells)

  return jsonify({"status": "queued", "n": len(norm_cells)})

if __name__ == "__main__":
  # For hackathon simplicity
  app.run(host="0.0.0.0", port=5000, debug=True)
