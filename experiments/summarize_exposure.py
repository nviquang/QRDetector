"""In bảng kết quả analyze_exposure: python experiments/summarize_exposure.py f4"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
RUN = sys.argv[1] if len(sys.argv) > 1 else "f4"
path = os.path.join("experiments", "out", "exposure_" + RUN, "results.jsonl")
rows = [json.loads(line) for line in open(path, encoding="utf-8")]
names = list(rows[0]["tems"][0]["methods"])
print("số tem", len(rows[0]["tems"]))
print("mã đọc được:", [sorted({t for r in rows for t in r["tems"][i]["texts"]}) for i in range(len(rows[0]["tems"]))])
print("thời gian ms/lần:", {n: round(sum(c["ms"].get(n, 0) for r in rows for c in r["tems"]) / (len(rows) * len(rows[0]["tems"])), 1) for n in names})
print()
print("gain exp sángTB fps saiYOLO | mỗi tem: YOLO đen/trắng cháy% nhiễu z4/16 cascadeTốt/16 chồng/2")
for r in rows:
    cells = []
    for c in r["tems"]:
        m = c["methods"]
        single = max(m[k] for k in ("z4", "z4_hist", "z4_fixed", "warp", "w_clahe", "w_cnn_stretch", "w_cnn3"))
        stack = max(m[k] for k in m if k.startswith("st_"))
        cells.append(f"{c['detected']} {c['black']:>3.0f}/{c['white']:>3.0f} {c['sat']:>4.1f} {c['noise']:>4.1f} z{m['z4']:>2} s{single:>2} c{stack}")
    print(f"{r['gain']:>3} {r['ms']:>3} {r['mean']:>6} {r['fps']:>5} {r['false_pos']} | " + " | ".join(cells))
print()
print("tổng theo phương pháp (mỗi tem cộng các mức sáng): frame đơn /16, chồng /2")
for n in names:
    print(f"{n:15}", [sum(r["tems"][i]["methods"].get(n, 0) for r in rows) for i in range(len(rows[0]["tems"]))])
