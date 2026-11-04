#!/usr/bin/env bash
# Kiểm tra lại trên hạt giống mới (nhiễu, thứ tự, lệch subpixel khác) các cấu hình đứng đầu lượt bán thực.
PY="${LAB_PY:-python}"
CONFIGS="base,H4+H6k3+H7k05+SW,H0+H1v1+H2+H3+H4+H6k3+H7k05+SW,H4+H6k3+H7k05+H9+SW,H6k3+H7k05+SW"
printf '%s\n' A_v10_mo1_sang B_v10_mo3_sang C_v10_mo3_vua_nhieu D_v10_mo1_toi E_v20_mo3_toi F_v30_mo3_rat_toi G_v20_mo1_rat_toi H_v20_mo6_sang | \
  xargs -P 4 -I{} sh -c "'$PY' experiments/run_lab.py semi --configs '$CONFIGS' --scenes {} --seeds 2 --repeats 3 --out experiments/out/semi2_{}.jsonl > experiments/out/logs/semi2_{}.log 2>&1"
echo semi2 done
