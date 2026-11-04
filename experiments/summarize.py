"""In bảng tổng hợp: python experiments/summarize.py 'experiments/out/singles_*.jsonl'"""
import collections
import glob
import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
rows = []
for pattern in sys.argv[1:]:
    for path in glob.glob(pattern):
        with open(path, encoding="utf-8") as f:
            rows += [json.loads(line) for line in f]
groups = sorted({r["group"] for r in rows})
by = collections.defaultdict(dict)
for r in rows:
    by[r["config"]].setdefault(r["group"], []).append(r)
print(f"{'cấu hình':26}" + "".join(f"{g[:10]:>11}" for g in groups) + f"{'tổng':>9}{'%':>6}{'sai':>4}{'tách':>5}{'ms/job':>7}{'lần/lượt':>9}{'trễ s':>6}")
order = sorted(by, key=lambda c: -sum(r["read"] for g in by[c].values() for r in g))
for c in order:
    all_rows = [r for g in by[c].values() for r in g]
    read, n = sum(r["read"] for r in all_rows), sum(r["passes"] for r in all_rows)
    wrong = sum(r["wrong"] for r in all_rows)
    extra = sum(max(0, r["emitted"] - r["read"] - r["wrong"]) for r in all_rows)
    ms = sum(r["ms_per_job"] for r in all_rows) / len(all_rows)
    att = sum(r["attempts_per_pass"] for r in all_rows) / len(all_rows)
    lags = [r["lag_s"] for r in all_rows if r["lag_s"] is not None]
    cells = "".join(f"{sum(r['read'] for r in by[c].get(g, [])):>7}/{sum(r['passes'] for r in by[c].get(g, [])):<3}" for g in groups)
    print(f"{c:26}{cells}{read:>5}/{n:<3}{100 * read / max(n, 1):>6.1f}{wrong:>4}{extra:>5}{ms:>7.0f}{att:>9.1f}"
          f"{(sum(lags) / len(lags)) if lags else 0:>6.2f}")
