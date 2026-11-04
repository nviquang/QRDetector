#!/usr/bin/env bash
# Bán thực: ảnh camera không nén + chuyển động/nhiễu mô phỏng.
PY="${LAB_PY:-python}"
BASE="base,H4,H6k3,H7k05,H9,H5e3,H6k3+SW"
COMBO="H6k3+H7k05,H6k3+H7k05+H5e3,H6k3+H7k05+H9,H6k3+H7k05+SW,H6k3+H7k05+H9+SW,H4+H6k3+H7k05+SW,H4+H6k3+H7k05+H9+SW,H4+H6k3+H7k05+H5e3"
printf '%s\n' A_v10_mo1_sang B_v10_mo3_sang C_v10_mo3_vua_nhieu D_v10_mo1_toi E_v20_mo3_toi F_v30_mo3_rat_toi G_v20_mo1_rat_toi H_v20_mo6_sang | \
  xargs -P 4 -I{} sh -c "'$PY' experiments/run_lab.py semi --configs '$BASE,$COMBO' --scenes {} --seeds 1 --repeats 3 --out experiments/out/semi_{}.jsonl > experiments/out/logs/semi_{}.log 2>&1"
echo semi done
