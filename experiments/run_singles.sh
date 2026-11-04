#!/usr/bin/env bash
# Đo từng hướng riêng lẻ trên bộ phát triển (seed 1): mỗi điều kiện một tiến trình, kết quả ghi nối tiếp.
PY="${LAB_PY:-python}"
CONFIGS="base,H0,H1,H1v1,H2,H3,H4,H5,H5cheap,H6k3,H6k5,H7,H7k005,H8,H9"
mkdir -p experiments/out/logs
for scene in v10_e12.9 v20_e6.45 v30_e4.3 v15_e12.9 v20_e12.9; do
  "$PY" experiments/run_lab.py run --configs "$CONFIGS" --scenes "$scene" --seeds 1 --passes 40 \
    --out "experiments/out/singles_$scene.jsonl" > "experiments/out/logs/singles_$scene.log" 2>&1 &
done
wait
echo singles done
