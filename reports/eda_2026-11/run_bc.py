"""PassReader(multi_frame) trên dữ liệu xưởng, thu crop các lượt PassDecoder không đọc được, rồi chạy ComboBC
với nhiều giả định độ dài vệt mờ (exposure thật không biết)."""
import os, sys, re, glob, time, pickle, dataclasses, json
ROOT = r"C:\Users\nviquang\Documents\AISTDR\QRDetector"
sys.path.insert(0, ROOT); os.chdir(ROOT)
sys.stdout.reconfigure(encoding="utf-8")
import torch  # noqa
import cv2, numpy as np, logging
logging.basicConfig(level=logging.WARNING)
from qr.improved_pipeline import ImprovePipeline
from qr.pass_reader import PassReader
OUT = os.path.dirname(os.path.abspath(__file__))
SESS = [("cheo", "20261113_111206382", 0, 55), ("xuong1", "20261113_133123291", 1400, 1601),
        ("xuong2", "20261113_133521948", 0, 200), ("xuong2", "20261113_133546659", 0, 80),
        ("xuong2", "20261113_133735410", 0, 200)]

class Recorder:
    revision = 0
    def __init__(self): self.jobs = []; self._p = set()
    pending = property(lambda s: 0)
    def stage(self, key): return None
    def submit(self, obs, ctx):
        self.jobs.append((obs, ctx)); return len(self.jobs) - 1
    def poll(self): return []
    def wait(self, timeout): return []
    def discard(self): pass

stage = sys.argv[1] if len(sys.argv) > 1 else "all"
pk = os.path.join(OUT, "bc_jobs.pkl")
if stage in ("all", "collect"):
    pipe = ImprovePipeline(multi_frame=True); pipe.warmup((2848, 2856))
    alljobs, summary = [], []
    for d, s, a, b in SESS:
        rec = Recorder(); now = [0.0]
        reader = PassReader(pipe, clock=lambda: now[0], fallback=rec)
        files = sorted(glob.glob(f"data/field/raw/{s}_*/frame_*.tiff"))  # thư mục pylon gốc đã chuyển vào raw/
        t00 = os.stat(files[0]).st_mtime_ns
        finished, reads = [], []
        t0 = time.time()
        for f in files:
            i = int(re.search(r"_(\d+)\.tiff$", f).group(1))
            if not a <= i <= b: continue
            now[0] = (os.stat(f).st_mtime_ns - t00) / 1e9
            im = cv2.imread(f, 0)
            r = reader.process(np.ascontiguousarray(cv2.cvtColor(im, cv2.COLOR_GRAY2BGR)), i)
            finished += r.finished; reads += [t.text for t in r.first_reads]
        finished += reader.flush()
        real = [t for t in finished if t.text or t.observations >= 2]
        info = dict(sess=f"{d}/{s}", frames=f"{a}-{b}", passes=len(real), passdecoder_read=sum(bool(t.text) for t in real),
                    texts=sorted({t.text for t in real if t.text}), sent_to_fallback=len(rec.jobs),
                    obs_per_pass=[t.observations for t in real], sec=round(time.time() - t0))
        print(json.dumps(info, ensure_ascii=False), flush=True); summary.append(info)
        alljobs += [(f"{d}/{s}", o, c) for o, c in rec.jobs]
    pickle.dump((alljobs, summary), open(pk, "wb"))
if stage in ("all", "solve"):
    alljobs, summary = pickle.load(open(pk, "rb"))
    from qr.pass_fallback import _load_solver
    os.environ["QR_MAIN"] = ROOT
    solver = _load_solver("combo_bc.py:ComboBC")
    res = []
    for j, (sess, obs, ctx) in enumerate(alljobs):
        sp = float(np.hypot(*ctx.velocity))
        for blur in (0.0, 6.0, 10.0, 14.0, 18.0):
            c = dataclasses.replace(ctx, blur_px=blur)
            stages = []
            t = time.perf_counter()
            try:
                text = solver.read_pass(obs, c, progress=stages.append); err = None
            except Exception as e:
                text, err = None, repr(e)
            ms = (time.perf_counter() - t) * 1000
            row = dict(job=j, sess=sess, n_obs=len(obs), speed=round(sp, 1), vel=[round(v, 1) for v in ctx.velocity],
                       side=round(float(np.median([o.bbox[2] - o.bbox[0] for o in obs])), 1),
                       blur=blur, text=text, stage=stages[-1] if stages else None, ms=round(ms), err=err)
            print(json.dumps(row, ensure_ascii=False), flush=True); res.append(row)
            if text: break
    json.dump(res, open(os.path.join(OUT, "bc_results.json"), "w"), ensure_ascii=False, indent=1)
    print("done")
