"""Xem ROI QR trong video thật và thử đọc không giới hạn thời gian (giới hạn trên của mỗi video)."""
import glob
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [_ROOT, os.path.dirname(os.path.abspath(__file__))]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import torch  # noqa: F401,E402
import cv2  # noqa: E402
import numpy as np  # noqa: E402

from lab_reader import _w, _z, stack_rois, wiener_motion  # noqa: E402
from qr.preprocessor import clahe, stretch_contrast, upscale_gray  # noqa: E402
from scenes import VideoScene  # noqa: E402

RESEARCH = "C:/Users/nviquang/Documents/AISTDR/QRDetector-research/data"


class NoDetector:
    def detect(self, frame):
        raise RuntimeError("cache miss")


paths = sorted(glob.glob(RESEARCH + "/video/*.mp4") + glob.glob(RESEARCH + "/videos/*.avi"))
tiles = []
for path in paths:
    sc = VideoScene(path, NoDetector())
    sc.build_oracle()
    size_mb = os.path.getsize(path) / 1e6
    frame_read = attempts = 0
    pass_read = stack_read = 0
    speeds, sharp, ctr, sizes = [], [], [], []
    first_tile = None
    for p in sc.passes:
        rois = []
        got = False
        for row in p.x:
            idx, cx, cy = int(row[0]), float(row[1]), float(row[2])
            dets = sc.detect(idx)
            if not dets:
                continue
            det = min(dets, key=lambda d: abs((d.bbox_xyxy[0] + d.bbox_xyxy[2]) / 2 - cx) + abs((d.bbox_xyxy[1] + d.bbox_xyxy[3]) / 2 - cy))
            x1, y1, x2, y2 = det.bbox_xyxy
            s = max(x2 - x1, y2 - y1)
            sizes.append(s)
            side = int(s * 1.8)
            ax, ay = int(cx - side / 2), int(cy - side / 2)
            frame = sc.frame(idx)
            if ax < 0 or ay < 0 or ax + side > frame.shape[1] or ay + side > frame.shape[0]:
                continue
            g = cv2.cvtColor(frame[ay:ay + side, ax:ax + side], cv2.COLOR_BGR2GRAY)
            rois.append(g)
            attempts += 1
            sharp.append(cv2.Laplacian(g, cv2.CV_32F).var())
            ctr.append(float(np.percentile(g, 95) - np.percentile(g, 5)))
            if first_tile is None and len(rois) == 3:
                first_tile = cv2.resize(g, (300, 300), interpolation=cv2.INTER_NEAREST)
            if attempts % 2 == 0:
                continue
            hit = _z(upscale_gray(g, 4)) or _w(upscale_gray(clahe(g), 4), False) or _w(upscale_gray(stretch_contrast(g), 4), True)
            if hit:
                frame_read += 1
                got = True
        path_xy = p.x
        if len(path_xy) >= 2:
            dt = np.diff(path_xy[:, 0])
            speeds.append(float(np.median(np.hypot(np.diff(path_xy[:, 1]), np.diff(path_xy[:, 2])) / np.maximum(dt, 1))))
        pass_read += got
        shapes = [r for r in rois if r.shape == rois[0].shape] if rois else []
        if len(shapes) >= 3:
            st = stack_rois(shapes[:8])
            hit = _z(st) or _w(st, True)
            if not hit and speeds and speeds[-1] > 0.5:
                for L in (2, 4, 7, 10, 15):
                    if _z(wiener_motion(st, L * 4, 0.0, 0.02)):
                        hit = True
                        break
            stack_read += bool(hit)
    name = os.path.basename(path)[-22:]
    print(f"{name:24} {size_mb:5.1f}MB {size_mb * 1e3 / max(sc.n_frames, 1):6.1f}KB/fr fps={sc.fps:4.1f} passes={len(sc.passes):2} "
          f"đọc_từng_frame={pass_read:2} xếp_chồng={stack_read:2} ROI_đã_thử={attempts:4} frame_đọc_được={frame_read:3} "
          f"QR={np.median(sizes) if sizes else 0:4.0f}px v={np.median(speeds) if speeds else 0:5.1f}px/fr "
          f"nét={np.median(sharp) if sharp else 0:6.0f} tương_phản={np.median(ctr) if ctr else 0:4.0f}", flush=True)
    if first_tile is not None:
        tiles.append(first_tile)
if tiles:
    while len(tiles) % 5:
        tiles.append(np.zeros((300, 300), np.uint8))
    cv2.imwrite("experiments/out/real_rois.png",
                np.vstack([np.hstack(tiles[i:i + 5]) for i in range(0, len(tiles), 5)]))
