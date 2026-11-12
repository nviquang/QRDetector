"""Tạo trước kịch bản đặt tem cho một đoạn quay: thứ tự mã, làn trên băng, góc xoay.

python experiments/make_sequence.py <tên đoạn> --codes experiments/codes.txt --belt-x <mm> [--passes 30]
       [--mode luoi|ngau_nhien] [--seed N] [--note "..."]

Ghi experiments/out/runs/<tên>/labels.json (đáp án cho bộ chấm điểm) và in bảng để in ra giấy, người đặt tem
làm theo đúng thứ tự. Khi quay có lượt nào khác kịch bản (rơi tem, bỏ lượt, hai tem dính nhau) thì sửa
labels.json: đổi "status" của lượt đó thành "bo" (không tính) hoặc ghi vào "deviations".

--mode luoi: xoay vòng đều làn × góc (mỗi tổ hợp xuất hiện như nhau); ngau_nhien: bốc ngẫu nhiên có seed.
--belt-x: vị trí tâm băng so với trục camera theo chiều 1,6 m (mm, trái âm, phải dương).
"""
import argparse
import itertools
import json
import os
import random
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

LANES = ["T", "G", "P"]          # trái / giữa / phải trên mặt băng (nhìn theo chiều băng chạy)
ROTS = [0, 45, 90]

parser = argparse.ArgumentParser()
parser.add_argument("name")
parser.add_argument("--codes", required=True, help="file text, mỗi dòng một mã tem đang có")
parser.add_argument("--belt-x", type=float, required=True)
parser.add_argument("--passes", type=int, default=30)
parser.add_argument("--mode", choices=["luoi", "ngau_nhien"], default="ngau_nhien")
parser.add_argument("--seed", type=int, default=None)
parser.add_argument("--note", default="")
args = parser.parse_args()

codes = [line.strip() for line in open(args.codes, encoding="utf-8") if line.strip() and not line.startswith("#")]
if len(set(codes)) != len(codes):
    sys.exit("file mã có dòng trùng")
if len(codes) < 2:
    sys.exit("cần ít nhất 2 mã khác nhau")
seed = args.seed if args.seed is not None else random.SystemRandom().randrange(10 ** 6)
rng = random.Random(seed)

combos = list(itertools.product(LANES, ROTS))
passes = []
prev = None
for i in range(args.passes):
    if args.mode == "luoi":
        lane, rot = combos[(i + i // len(combos)) % len(combos)]
    else:
        lane, rot = rng.choice(combos)
    # mã liền nhau khác nhau để bộ theo dõi không nối nhầm hai lượt cùng mã
    code = rng.choice([c for c in codes if c != prev])
    prev = code
    passes.append({"i": i + 1, "code": code, "lane": lane, "rot": rot, "status": "ok"})

out = os.path.join(_ROOT, "experiments", "out", "runs", args.name)
path = os.path.join(out, "labels.json")
if os.path.exists(path):
    sys.exit(f"đã có {path}, chọn tên khác hoặc xóa file cũ")
os.makedirs(out, exist_ok=True)
labels = dict(clip=args.name, belt_x_mm=args.belt_x, mode=args.mode, seed=seed, codes=sorted(set(codes)),
              note=args.note, deviations="", passes=passes)
with open(path, "w", encoding="utf-8") as f:
    json.dump(labels, f, ensure_ascii=False, indent=1)

print(f"Đoạn {args.name}   băng tại x = {args.belt_x:+.0f} mm   {args.mode}, seed {seed}")
print("Làn: T = trái, G = giữa, P = phải mặt băng (nhìn theo chiều chạy). Góc: xoay tem theo chiều kim đồng hồ.")
print(f"{'#':>3}  {'mã':<16} {'làn':^4} {'góc':>4}   đã đặt")
for p in passes:
    print(f"{p['i']:>3}  {p['code']:<16} {p['lane']:^4} {p['rot']:>3}°   [ ]")
print(f"\nĐã ghi {path}")
