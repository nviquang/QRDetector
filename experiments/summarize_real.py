"""In kết quả trên video thật: python experiments/summarize_real.py"""
import collections
import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
rows = [json.loads(line) for line in open("experiments/out/real.jsonl", encoding="utf-8")]
scenes = sorted({r["scene"] for r in rows})
configs = list(dict.fromkeys(r["config"] for r in rows))
print(f"{'video':32}" + "".join(f"{c[:22]:>24}" for c in configs))
for s in scenes:
    cells = []
    for c in configs:
        r = next(x for x in rows if x["scene"] == s and x["config"] == c)
        cells.append(f"{r['read']}/{r['passes']} s{r['wrong']} e{r['emitted']} {r['ms_per_job']:.0f}ms")
    print(f"{s[-30:]:32}" + "".join(f"{x:>24}" for x in cells))
for c in configs:
    rs = [r for r in rows if r["config"] == c]
    print(c, "đọc", sum(r["read"] for r in rs), "/", sum(r["passes"] for r in rs), "sai", sum(r["wrong"] for r in rs),
          "phát", sum(r["emitted"] for r in rs), "ms/job", round(sum(r["ms_per_job"] for r in rs) / len(rs)))
texts = collections.Counter(t for r in rows for t in r.get("emitted_texts", []))
print(texts.most_common(20))
for r in rows:
    if r["wrong"]:
        print("sai:", r["scene"][-20:], r["config"], r["wrong_texts"])
