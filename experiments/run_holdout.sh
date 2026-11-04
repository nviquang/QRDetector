#!/usr/bin/env bash
# Kiểm tra trên dữ liệu chưa dùng để chọn cấu hình (seed 2, 3) và các điều kiện thử độ bền.
PY="${LAB_PY:-python}"
BEST="H4+H6k3+H7k05+H9+SW"
CONFIGS="base,$BEST,H6k3+H7k05+H9+SW,H4+H6k3+H7k05+SW,H6k3+H7k05+SW,H0+H1+H4+H6k3+H7k05+H9+SW,H0+H1v1+H2+H3+H4+H6k3+H7k05+H9+SW"
printf '%s\n' v10_e12.9 v20_e6.45 v30_e4.3 v15_e12.9 v20_e12.9 ctl_bright rob_corr rob_jit | \
  xargs -P 4 -I{} sh -c "'$PY' experiments/run_lab.py run --configs '$CONFIGS' --scenes {} --seeds 2 3 --passes 40 --out experiments/out/holdout_{}.jsonl > experiments/out/logs/holdout_{}.log 2>&1"
echo holdout done
