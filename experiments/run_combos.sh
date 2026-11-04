#!/usr/bin/env bash
# Tổ hợp trên bộ phát triển (seed 1).
PY="${LAB_PY:-python}"
CONFIGS="base,H5,H5e3,H6k3+H9,H1+H6k3+H9,H6k3+H5e3,H6k3+H9+H5e3,H6k3+SW,H6k3+NoW,H6k3+H9+SW,H6k3+H9+NoW,H4+H6k3+NoW,H4+H6k3+SW,H4+H6k3+H9+NoW,H4+H6k3+H9+SW,H4+H6k3+H9+H5e3,H4+H6k3+H9,H6k3+H7+H9,H4+H6k3+H7k05+H9+SW,H4+H6k3+H9+SW+M16,H0+H1v1+H2+H3,H0+H1v1+H2+H3+H4+H6k3+H9+SW"
for scene in v10_e12.9 v20_e6.45 v30_e4.3 v15_e12.9 v20_e12.9; do
  "$PY" experiments/run_lab.py run --configs "$CONFIGS" --scenes "$scene" --seeds 1 --passes 40 \
    --out "experiments/out/combos_$scene.jsonl" > "experiments/out/logs/combos_$scene.log" 2>&1 &
done
wait
echo combos done
