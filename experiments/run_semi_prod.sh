#!/usr/bin/env bash
# Kiểm tra code sản phẩm (qr.PassReader) trên đúng các điều kiện của run_semi_holdout.sh.
PY="${LAB_PY:-python}"
printf '%s\n' A_v10_mo1_sang B_v10_mo3_sang C_v10_mo3_vua_nhieu D_v10_mo1_toi E_v20_mo3_toi F_v30_mo3_rat_toi G_v20_mo1_rat_toi H_v20_mo6_sang | \
  xargs -P 4 -I{} sh -c "'$PY' experiments/run_lab.py semi --configs PROD1,PROD2 --scenes {} --seeds 1 2 --repeats 3 --out experiments/out/semi4_{}.jsonl > experiments/out/logs/semi4_{}.log 2>&1"
echo semi4 done
