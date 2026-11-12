"""Mốc: PassDecoder (mode='pass', như sản phẩm) hoặc cascade từng frame (mode='cascade'), chốt khi 2 frame đọc giống nhau."""
import collections
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

import cv2  # noqa: E402
from qr.detector import Detection  # noqa: E402
from qr.improved_pipeline import ImprovePipeline  # noqa: E402
from qr.multiframe import PassDecoder  # noqa: E402
from qr.tracker import Track  # noqa: E402


class Baseline:
    def __init__(self, mode="pass", need=2):
        self.mode, self.need = mode, need
        self.pipe = ImprovePipeline(detector=object(), multi_frame=False)

    def read_pass(self, obs, ctx):
        need = min(self.need, len(obs))
        votes = collections.Counter()
        dec = PassDecoder(None)
        track = Track(track_id=1, first_frame=0, last_frame=0, center=(0.0, 0.0), size=1.0, velocity=ctx.velocity)
        blur = [ctx.blur_px] if ctx.blur_px >= 1.0 else []
        for o in obs:
            img = cv2.cvtColor(o.gray, cv2.COLOR_GRAY2BGR)
            det = Detection(bbox_xyxy=o.bbox, quad_xy=o.quad, confidence=o.conf, polygon_xy=o.polygon)
            hit = dec.read(img, o.bbox, det, track, blur) if self.mode == "pass" else self.pipe.decode_detection(img, det)
            if hit:
                votes[hit.text] += 1
                if votes[hit.text] >= need:
                    return hit.text
        return None
