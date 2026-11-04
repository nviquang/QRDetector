#!/usr/bin/env bash
# Đo tốc độ tuần tự: mỗi lúc một tiến trình, không tranh CPU/GPU với tiến trình khác.
PY="${LAB_PY:-python}"
export LAB_CV_THREADS="${LAB_CV_THREADS:-$(nproc)}"
CONFIGS="base,H0+H1v1+H2+H3+H4+H6k3+H7k05+SW,H4+H6k3+H7k05+SW"
for s in B_v10_mo3_sang E_v20_mo3_toi; do
  "$PY" experiments/run_lab.py semi --configs "$CONFIGS" --scenes "$s" --seeds 2 --repeats 3 \
    --out "experiments/out/timing_$s.jsonl" > "experiments/out/logs/timing_$s.log" 2>&1
done
echo "threads=$LAB_CV_THREADS timing done"
