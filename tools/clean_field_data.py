"""Làm sạch dữ liệu hiện trường 06/11 và 13/11/2026 theo `reports/EDA dữ liệu hiện trường 11-2026.md`.

python tools/clean_field_data.py [--out data/field] [--manifest reports/eda_2026-11/frames_manifest.csv]

``raw/`` LÀ BẢN DỮ LIỆU DUY NHẤT: 5 thư mục pylon gốc (cheo/gan/xa/xuong1/xuong2) đã bị xóa ngày 14/11/2026 sau
khi chuyển vào đây; tên file gốc còn trong cột ``orig_dir``/``orig_name`` của manifest và ``frames.csv``. Script không
bao giờ xóa hay ghi đè ``raw/``: chạy lại chỉ dựng lại ``curated/`` (hard link tới ``raw/``), ảnh cắt, các file CSV,
và giữ nguyên các cột điền tay của ``labels/passes.csv``. Đường dẫn ``path`` trong manifest tính từ gốc repo.
Đầu ra:
  raw/<rec_id>/frame_NNNN.tiff + meta.json   mỗi lần ghi một thư mục, giữ số thứ tự gốc
  frames.csv                                 nhãn từng frame (đoạn, có kính, phát hiện)
  segments.csv                               các đoạn liên tục cùng nhãn
  curated/<rec_id>/frame_NNNN.tiff           bộ đã lọc (hard link), danh sách ở curated.csv
  labels/passes.csv + labels/crops/*.png     mẫu nhãn ground truth theo lượt (điền cột text bằng tay)
Manifest sinh bởi bước EDA (độ sáng, % cháy sáng, chênh lệch frame kề, phát hiện YOLO của ImprovePipeline).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

import cv2
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Thông tin từng lần ghi, rút từ EDA. scene: lab_* = phòng thí nghiệm 06/11 (ROI 1792×992, 25 fps),
# xuong_* = xưởng 13/11 (toàn khung 2856×2848, ~16 fps ghi). pose: tư thế camera ở xưởng.
RECORDINGS = {
    "20261106_172246399": dict(scene="lab_xa", pose="lab", note="Băng đen dọc, camera xa; tem thử mã giả"),
    "20261106_172658547": dict(scene="lab_gan", pose="lab", note="Băng đen dọc, camera gần; tem thử mã giả"),
    "20261106_173102461": dict(scene="lab_cheo", pose="lab", note="Băng đen chéo; tem thử mã giả"),
    "20261113_111206382": dict(scene="xuong_tinh", pose="A", note="Đứng yên, 2 tem thật, 56 frame gần như giống hệt"),
    "20261113_132745078": dict(scene="xuong_khong_tem", pose="A",
                               note="Không có tem; vệt phản xạ kính phần lớn video; exposure/gain đổi ở frame 259 và 324 (3 mức sáng)"),
    "20261113_132944090": dict(scene="xuong_khong_tem", pose="A", note="Không có tem; có vệt phản xạ kính suốt video"),
    "20261113_133123291": dict(scene="xuong_chay", pose="A", note="Kính từ ~frame 1080, tem ở 1447–1551"),
    "20261113_133521948": dict(scene="xuong_chay", pose="A", note="Bắt đầu giữa lượt có tem"),
    "20261113_133546659": dict(scene="xuong_chay", pose="A", note="Bắt đầu giữa lượt có tem"),
    "20261113_133640302": dict(scene="xuong_chay", pose="A", note="Con lăn trống suốt video"),
    "20261113_133735410": dict(scene="xuong_chay", pose="A", note="Một lượt có tem"),
    "20261113_133806945": dict(scene="xuong_chay", pose="A", note="Có kính, không phát hiện QR"),
    "20261113_134415246": dict(scene="xuong_chay", pose="B",
                               note="Camera ở tư thế khác (quay sau 6 phút); kính có tem trắng chạy nhanh ở "
                                    "~frame 520–590 nhưng không phát hiện QR"),
}
CAMERA = "Basler a2A2840-48umBAS, serial 42023350"

PASS_GAP = 10         # frame hở tối đa trong một lượt (tính theo frame đã quét)
PASS_MIN = 3          # lượt phải có ít nhất chừng này frame
PASS_PAD = 10         # frame đệm mỗi đầu lượt khi đưa vào curated
GLASS_SAT_PCT = 0.1   # % pixel ≥250: vệt phản xạ đèn trên kính
CHANGE_DIFF = 10.0    # chênh lệch thumbnail giữa hai frame kề (mức xám) coi là đổi cấu hình
CHANGE_STEP = 3.0     # và độ sáng TB phải đổi hẳn ít nhất chừng này
KEEP_BACKGROUND = 100  # số frame empty / glass_no_det giữ lại mỗi lần ghi
KEEP_STATIC = 3


def rec_id(sess: str) -> str:
    return f"{sess}_{RECORDINGS[sess]['scene']}"


def runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Các đoạn liên tục True: [(start, end)] theo chỉ số mảng, end bao gồm."""
    out, start = [], None
    for i, v in enumerate(mask):
        if v and start is None:
            start = i
        elif not v and start is not None:
            out.append((start, i - 1)); start = None
    if start is not None:
        out.append((start, len(mask) - 1))
    return out


def change_points(g: pd.DataFrame) -> list[int]:
    """Vị trí (chỉ số mảng) đổi exposure/gain: frame kề khác hẳn và độ sáng không quay lại."""
    mean, diff = g["mean"].to_numpy(), g["diff_prev"].to_numpy()
    pts = []
    for i in np.where(diff > CHANGE_DIFF)[0]:
        before, after = mean[max(0, i - 5):i], mean[i:i + 5]
        if len(before) and abs(np.median(after) - np.median(before)) > CHANGE_STEP:
            pts.append(int(i))
    return pts


def label_recording(g: pd.DataFrame) -> pd.DataFrame:
    g = g.sort_values("idx").reset_index(drop=True)
    sess = g["sess"].iat[0]
    scene = RECORDINGS[sess]["scene"]
    n = len(g)
    step = int(np.median(np.diff(g.loc[g["scanned"], "idx"]))) if g["scanned"].sum() > 1 else 1

    # Có phát hiện QR: frame đã quét có ndet>0; frame chưa quét (06/11 quét 1/3) lấy theo frame quét gần nhất trong lượt
    det = (g["ndet"].fillna(0) > 0).to_numpy()
    scanned_idx = np.where(g["scanned"].to_numpy())[0]
    in_pass = np.zeros(n, bool)
    hits = scanned_idx[det[scanned_idx]]
    if len(hits):
        start = prev = hits[0]
        for h in list(hits[1:]) + [None]:
            if h is None or h - prev > PASS_GAP * step:
                if prev - start + 1 >= PASS_MIN * step:
                    in_pass[start:prev + 1] = True
                if h is not None:
                    start = h
            if h is not None:
                prev = h

    glass = (g["sat"].to_numpy() >= GLASS_SAT_PCT) & scene.startswith("xuong")
    label = np.where(in_pass, "pass", np.where(glass, "glass_no_det", "empty")).astype(object)
    if scene == "xuong_tinh":
        label[:] = "static"

    # Đổi cấu hình: mỗi mức sáng là một "chế độ" (cột exposure_mode). Chế độ kẹp giữa hai lần đổi là đoạn chỉnh tạm
    # thời → config_change; chế độ đầu/cuối vẫn là cảnh bình thường, chỉ khác exposure_mode.
    cps = change_points(g)
    mode = np.zeros(n, int)
    for k, cp in enumerate(cps, 1):
        mode[cp:] = k
    for k in range(1, len(cps)):
        label[(mode == k) & (label != "pass")] = "config_change"
    g["exposure_mode"] = mode
    g["label"] = label
    g["glass"] = glass
    g["rec_id"] = rec_id(sess)
    return g


def segments(g: pd.DataFrame) -> list[dict]:
    out, lab, idx = [], g["label"].to_numpy(), g["idx"].to_numpy()
    start = 0
    for i in range(1, len(g) + 1):
        if i == len(g) or lab[i] != lab[start]:
            part = g.iloc[start:i]
            seg = dict(rec_id=g["rec_id"].iat[0], seg_no=len(out), label=lab[start],
                       start_idx=int(idx[start]), end_idx=int(idx[i - 1]), n_frames=i - start,
                       det_frames=int((part["ndet"].fillna(0) > 0).sum()),
                       t_start_s=float(part["t_s"].iat[0]), t_end_s=float(part["t_s"].iat[-1]),
                       mean_brightness=round(float(part["mean"].mean()), 2),
                       cut_at_start=lab[start] == "pass" and start == 0,
                       cut_at_end=lab[start] == "pass" and i == len(g),
                       texts="|".join(sorted({t for s in part["texts"].dropna() for t in str(s).split("|") if t})))
            seg["speed_px_per_frame"] = pass_speed(part) if lab[start] == "pass" else None
            out.append(seg)
            start = i
    return out


def centers(row) -> list[tuple[float, float, float]]:
    boxes = json.loads(row["det_bboxes"]) if isinstance(row["det_bboxes"], str) and row["det_bboxes"] else []
    return [((b[0] + b[2]) / 2, (b[1] + b[3]) / 2, max(b[2] - b[0], b[3] - b[1])) for b in boxes]


def pass_speed(part: pd.DataFrame) -> float | None:
    """Vận tốc trung vị (px / số thứ tự frame) của QR, ghép láng giềng gần nhất giữa hai frame quét liên tiếp."""
    rows = [(int(r["idx"]), centers(r)) for _, r in part.iterrows() if r["scanned"]]
    v = []
    for (i0, c0), (i1, c1) in zip(rows, rows[1:]):
        for x0, y0, _ in c0:
            best = min(((np.hypot(x1 - x0, y1 - y0), x1, y1) for x1, y1, _ in c1), default=None)
            if best and best[0] < 400:
                v.append(best[0] / (i1 - i0))
    return round(float(np.median(v)), 1) if v else None


def link(src: str, dst: str):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst):
        if os.path.samefile(src, dst):
            return
        raise FileExistsError(dst)
    os.link(src, dst)


def even_sample(df: pd.DataFrame, k: int) -> pd.DataFrame:
    if len(df) <= k:
        return df
    return df.iloc[np.linspace(0, len(df) - 1, k).round().astype(int)]


def curate(g: pd.DataFrame) -> pd.DataFrame:
    keep = np.zeros(len(g), bool)
    reason = np.array([""] * len(g), dtype=object)
    lab = g["label"].to_numpy()
    for a, b in runs(lab == "pass"):
        lo, hi = max(0, a - PASS_PAD), min(len(g) - 1, b + PASS_PAD)
        sel = np.arange(lo, hi + 1)
        reason[sel[~keep[sel]]] = "pass"
        keep[sel] = True
    for name, k in (("static", KEEP_STATIC), ("empty", KEEP_BACKGROUND), ("glass_no_det", KEEP_BACKGROUND),
                    ("config_change", KEEP_BACKGROUND)):
        cand = g[(lab == name) & ~keep]
        pick = even_sample(cand, k).index
        keep[pick] = True
        reason[pick] = name
    out = g[keep].copy()
    out["keep_reason"] = reason[keep]
    return out


def save_pass_crops(g: pd.DataFrame, segs: list[dict], out_dir: str) -> list[dict]:
    """Mỗi lượt: frame giữa đoạn có phát hiện, cắt quanh QR lớn nhất để gán nhãn tay."""
    rows = []
    crops = os.path.join(out_dir, "labels", "crops")
    os.makedirs(crops, exist_ok=True)
    for seg in segs:
        if seg["label"] not in ("pass", "static"):
            continue
        part = g[(g["idx"] >= seg["start_idx"]) & (g["idx"] <= seg["end_idx"]) & (g["ndet"].fillna(0) > 0)]
        if part.empty:
            continue
        r = part.iloc[len(part) // 2]
        name = f"{seg['rec_id']}_seg{seg['seg_no']:02d}_f{int(r['idx']):04d}"
        im = cv2.imread(r["path"], cv2.IMREAD_GRAYSCALE)
        tiles = []
        for x, y, s in centers(r):
            m = int(max(80, 1.5 * s))
            c = im[max(0, int(y) - m):int(y) + m, max(0, int(x) - m):int(x) + m]
            tiles.append(cv2.resize(cv2.normalize(c, None, 0, 255, cv2.NORM_MINMAX), (320, 320),
                                    interpolation=cv2.INTER_CUBIC))
        cv2.imwrite(os.path.join(crops, name + ".png"), np.hstack(tiles))
        rows.append(dict(rec_id=seg["rec_id"], seg_no=seg["seg_no"], label=seg["label"],
                         start_idx=seg["start_idx"], end_idx=seg["end_idx"], best_frame=int(r["idx"]),
                         crop=f"crops/{name}.png", auto_texts=seg["texts"],
                         cut_at_start=seg["cut_at_start"], cut_at_end=seg["cut_at_end"],
                         speed_px_per_frame=seg["speed_px_per_frame"],
                         text="", n_labels_visible="", note=""))
    return rows


def meta_for(g: pd.DataFrame) -> dict:
    sess = g["sess"].iat[0]
    t = g["t_s"].to_numpy()
    dt = np.diff(t) * 1000
    med = float(np.median(dt)) if len(dt) else 0.0
    info = RECORDINGS[sess]
    return dict(rec_id=rec_id(sess), source_dir=g["orig_dir"].iat[0], source_prefix=sess, camera=CAMERA,
                scene=info["scene"], camera_pose=info["pose"], note=info["note"],
                width=int(g["w"].iat[0]), height=int(g["h"].iat[0]), frames=len(g),
                first_idx=int(g["idx"].min()), last_idx=int(g["idx"].max()),
                duration_s=round(float(t[-1] - t[0]), 2), write_fps=round(1000 / med, 2) if med else None,
                write_gaps_ms=[dict(after_idx=int(g["idx"].iat[i]), ms=round(float(x)))
                               for i, x in enumerate(dt) if med and x > 5 * med],
                timing_note="t_s là mtime lúc ghi file, không phải lúc chụp; khoảng giữa frame không đều",
                exposure_ms=None, gain_db=None, lens_mm=None, distance_m=None,
                exposure_change_at_idx=[int(g["idx"].iat[i]) for i in change_points(g)],
                labels={k: int(v) for k, v in g["label"].value_counts().items()})


MANUAL_COLS = ["text", "n_labels_visible", "note"]
META_MANUAL = ["exposure_ms", "gain_db", "lens_mm", "distance_m"]


def reset_derived(out_dir: str):
    """Xóa ``curated/`` và ảnh cắt để dựng lại. Mỗi ảnh trong curated phải còn ít nhất một tên khác (bản ở raw/),
    nếu không thì dừng hẳn: xóa nó sẽ mất dữ liệu."""
    curated = os.path.join(out_dir, "curated")
    if os.path.isdir(curated):
        for dirpath, _, names in os.walk(curated):
            for name in names:
                p = os.path.join(dirpath, name)
                if name.endswith(".tiff") and os.stat(p).st_nlink < 2:
                    sys.exit(f"Dừng: {p} không còn bản nào khác ngoài curated/ — không xóa")
        shutil.rmtree(curated)
    crops = os.path.join(out_dir, "labels", "crops")
    if os.path.isdir(crops):
        shutil.rmtree(crops)


def merge_manual(new: pd.DataFrame, path: str) -> pd.DataFrame:
    """Giữ các cột điền tay của passes.csv cũ, ghép theo (rec_id, start_idx, end_idx). Dòng cũ không còn khớp được
    giữ lại ở cuối với label='orphan' để không mất nhãn tay."""
    if new.empty or not os.path.exists(path):
        return new
    old = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    key = ["rec_id", "start_idx", "end_idx"]
    new[key[1:]] = new[key[1:]].astype(str)
    filled = old[(old[MANUAL_COLS] != "").any(axis=1)]
    merged = new.drop(columns=MANUAL_COLS).merge(filled[key + MANUAL_COLS], on=key, how="left")
    merged[MANUAL_COLS] = merged[MANUAL_COLS].fillna("")
    orphan = filled.merge(new[key], on=key, how="left", indicator=True)
    orphan = orphan[orphan["_merge"] == "left_only"].drop(columns="_merge").assign(label="orphan")
    return pd.concat([merged, orphan], ignore_index=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "field"))
    ap.add_argument("--manifest", default=os.path.join(ROOT, "reports", "eda_2026-11", "frames_manifest.csv"))
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    m = pd.read_csv(args.manifest, dtype={"sess": str})
    unknown = set(m["sess"]) - set(RECORDINGS)
    if unknown:
        sys.exit(f"Lần ghi chưa có trong RECORDINGS: {sorted(unknown)}")
    m["path"] = [p if os.path.isabs(p) else os.path.join(ROOT, p) for p in m["path"]]
    missing = [p for p in m["path"] if not os.path.isfile(p)]
    if missing:
        sys.exit(f"Thiếu {len(missing)} ảnh trong manifest, ví dụ {missing[0]} — không ghi gì")
    reset_derived(args.out)

    labelled, segs, curated, passes = [], [], [], []
    for sess, g in m.groupby("sess"):
        g = label_recording(g)
        rid = g["rec_id"].iat[0]
        raw_dir = os.path.join(args.out, "raw", rid)
        g["raw_path"] = [os.path.join("raw", rid, f"frame_{i:04d}.tiff") for i in g["idx"]]
        for src, rel in zip(g["path"], g["raw_path"]):
            link(src, os.path.join(args.out, rel))
        meta_path = os.path.join(raw_dir, "meta.json")
        meta = meta_for(g)
        if os.path.exists(meta_path):   # giữ các trường điền tay (exposure, gain, ống kính, khoảng cách)
            old = json.load(open(meta_path, encoding="utf-8"))
            meta.update({k: old[k] for k in META_MANUAL if old.get(k) is not None})
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, ensure_ascii=False, indent=1)
        s = segments(g)
        c = curate(g)
        c["curated_path"] = [os.path.join("curated", rid, f"frame_{i:04d}.tiff") for i in c["idx"]]
        for src, rel in zip(c["path"], c["curated_path"]):
            link(src, os.path.join(args.out, rel))
        passes += save_pass_crops(g, s, args.out)
        labelled.append(g); segs += s; curated.append(c)
        print(f"{rid}: {len(g)} frame, nhãn {dict(g['label'].value_counts())}, giữ {len(c)}")

    cols = ["rec_id", "idx", "raw_path", "orig_dir", "orig_name", "t_s", "label", "glass", "exposure_mode", "mean",
            "sat", "lapvar", "fg_pct", "diff_prev", "scanned", "ndet", "nread", "texts", "det_bboxes"]
    pd.concat(labelled)[cols].to_csv(os.path.join(args.out, "frames.csv"), index=False)
    pd.DataFrame(segs).to_csv(os.path.join(args.out, "segments.csv"), index=False)
    pd.concat(curated)[["rec_id", "idx", "curated_path", "raw_path", "label", "keep_reason", "ndet", "texts"]].to_csv(
        os.path.join(args.out, "curated.csv"), index=False)
    passes_path = os.path.join(args.out, "labels", "passes.csv")
    merge_manual(pd.DataFrame(passes), passes_path).to_csv(passes_path, index=False, encoding="utf-8-sig")
    print("xong:", args.out)


if __name__ == "__main__":
    main()
