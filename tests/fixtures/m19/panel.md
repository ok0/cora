# M19 panel

reports: a=tests/fixtures/m19/reports/a-m1-i01.json a=tests/fixtures/m19/reports/a-m1-i02.json a=tests/fixtures/m19/reports/a-m1-i03.json a=tests/fixtures/m19/reports/a-m1-i04.json a=tests/fixtures/m19/reports/a-m1-i05.json a=tests/fixtures/m19/reports/a-m2-i01.json a=tests/fixtures/m19/reports/a-m2-i02.json a=tests/fixtures/m19/reports/a-m2-i03.json a=tests/fixtures/m19/reports/a-m2-i04.json a=tests/fixtures/m19/reports/a-m2-i05.json e=tests/fixtures/m19/reports/e-i01.json e=tests/fixtures/m19/reports/e-i02.json e=tests/fixtures/m19/reports/e-i03.json e=tests/fixtures/m19/reports/e-i04.json e=tests/fixtures/m19/reports/e-i05.json e=tests/fixtures/m19/reports/e-i06.json e=tests/fixtures/m19/reports/e-i07.json e=tests/fixtures/m19/reports/e-i08.json e=tests/fixtures/m19/reports/e-i09.json e=tests/fixtures/m19/reports/e-i10.json e=tests/fixtures/m19/reports/e-i11.json e=tests/fixtures/m19/reports/e-i12.json e=tests/fixtures/m19/reports/e-i13.json e=tests/fixtures/m19/reports/e-i14.json e=tests/fixtures/m19/reports/e-i15.json e=tests/fixtures/m19/reports/e-i16.json e=tests/fixtures/m19/reports/e-i17.json e=tests/fixtures/m19/reports/e-i18.json e=tests/fixtures/m19/reports/e-i19.json e=tests/fixtures/m19/reports/e-i20.json e=tests/fixtures/m19/reports/e-i21.json e=tests/fixtures/m19/reports/e-i22.json e=tests/fixtures/m19/reports/e-i23.json e=tests/fixtures/m19/reports/e-i24.json c_s=tests/fixtures/m19/reports/c_s-m1-i01.json c_s=tests/fixtures/m19/reports/c_s-m1-i02.json c_s=tests/fixtures/m19/reports/c_s-m1-i03.json c_s=tests/fixtures/m19/reports/c_s-m1-i04.json c_s=tests/fixtures/m19/reports/c_s-m1-i05.json d1=tests/fixtures/m19/reports/d1-m1-i01.json c_s=tests/fixtures/m19/reports/c_s-m2-i01.json c_s=tests/fixtures/m19/reports/c_s-m2-i02.json c_s=tests/fixtures/m19/reports/c_s-m2-i03.json c_s=tests/fixtures/m19/reports/c_s-m2-i04.json c_s=tests/fixtures/m19/reports/c_s-m2-i05.json d1=tests/fixtures/m19/reports/d1-m2-i01.json a=tests/fixtures/m19/reports/a-m3-i01.json a=tests/fixtures/m19/reports/a-m3-i02.json a=tests/fixtures/m19/reports/a-m3-i03.json a=tests/fixtures/m19/reports/a-m3-i04.json a=tests/fixtures/m19/reports/a-m3-i05.json
baseline: claude-code-m19.toml (claude-code, claude-sonnet-5-5)
thresholds: A=0.7 B=0.4 cost=2.0x
error policy: replace
cost basis: billed
extras: tests/fixtures/m19/panel-extras.json

## (a) cells

| arm | model | task | k/n | wilson | cost_usd |
|---|---|---|---|---|---|
| a | google/gemini-2.5-flash-lite | e2e_h01 | 0/3 | [0.000, 0.562] | 0.1038 |
| a | google/gemini-2.5-flash-lite | e2e_h02 | 0/3 | [0.000, 0.562] | 0.0406 |
| a | google/gemini-2.5-flash-lite | e2e_h03 | 0/3 | [0.000, 0.562] | 0.2406 |
| a | google/gemini-2.5-flash-lite | e2e_h04 | 0/3 | [0.000, 0.562] | 0.1015 |
| a | google/gemini-2.5-flash-lite | e2e_h05 | 1/3 | [0.061, 0.792] | 0.0481 |
| a | google/gemini-2.5-flash-lite | e2e_h06 | 0/3 | [0.000, 0.562] | 0.0634 |
| a | google/gemini-2.5-flash-lite | e2e_hx1 | 1/3 | [0.061, 0.792] | 0.0293 |
| a | google/gemini-2.5-flash-lite | e2e_hx2 | 0/3 | [0.000, 0.562] | 0.0207 |
| a | mistralai/mistral-small-3.2-24b-instruct | e2e_h01 | 0/3 | [0.000, 0.562] | 0.0558 |
| a | mistralai/mistral-small-3.2-24b-instruct | e2e_h02 | 1/3 | [0.061, 0.792] | 0.0146 |
| a | mistralai/mistral-small-3.2-24b-instruct | e2e_h03 | 0/3 | [0.000, 0.562] | 0.0817 |
| a | mistralai/mistral-small-3.2-24b-instruct | e2e_h04 | 0/3 | [0.000, 0.562] | 0.0590 |
| a | mistralai/mistral-small-3.2-24b-instruct | e2e_h05 | 0/3 | [0.000, 0.562] | 0.0182 |
| a | mistralai/mistral-small-3.2-24b-instruct | e2e_h06 | 0/3 | [0.000, 0.562] | 0.0229 |
| a | mistralai/mistral-small-3.2-24b-instruct | e2e_hx1 | 1/3 | [0.061, 0.792] | 0.0117 |
| a | mistralai/mistral-small-3.2-24b-instruct | e2e_hx2 | 0/3 | [0.000, 0.562] | 0.0282 |
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_h01 | 0/3 | [0.000, 0.562] | 0.0227 |
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_h02 | 2/3 | [0.208, 0.939] | 0.0470 |
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_h03 | 0/3 | [0.000, 0.562] | 0.0520 |
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_h04 | 0/3 | [0.000, 0.562] | 0.0817 |
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_h05 | 2/3 | [0.208, 0.939] | 0.0314 |
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_h06 | 1/3 | [0.061, 0.792] | 0.0308 |
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_hx1 | 1/3 | [0.061, 0.792] | 0.0120 |
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_hx2 | 0/3 | [0.000, 0.562] | 0.0054 |
| c_s | google/gemini-2.5-flash-lite | e2e_h01 | 1/3 | [0.061, 0.792] | 0.1093 |
| c_s | google/gemini-2.5-flash-lite | e2e_h02 | 0/3 | [0.000, 0.562] | 0.0676 |
| c_s | google/gemini-2.5-flash-lite | e2e_h03 | 0/3 | [0.000, 0.562] | 0.1269 |
| c_s | google/gemini-2.5-flash-lite | e2e_h04 | 1/3 | [0.061, 0.792] | 0.0908 |
| c_s | google/gemini-2.5-flash-lite | e2e_h05 | 0/3 | [0.000, 0.562] | 0.1185 |
| c_s | google/gemini-2.5-flash-lite | e2e_h06 | 3/3 | [0.438, 1.000] | 0.0638 |
| c_s | google/gemini-2.5-flash-lite | e2e_hx2 | 0/3 | [0.000, 0.562] | 0.0435 |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | e2e_h01 | 0/3 | [0.000, 0.562] | 0.1358 |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | e2e_h02 | 1/3 | [0.061, 0.792] | 0.0996 |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | e2e_h03 | 0/3 | [0.000, 0.562] | 0.0772 |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | e2e_h04 | 0/3 | [0.000, 0.562] | 0.1176 |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | e2e_h05 | 1/3 | [0.061, 0.792] | 0.0547 |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | e2e_h06 | 1/3 | [0.061, 0.792] | 0.0729 |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | e2e_hx2 | 0/3 | [0.000, 0.562] | 0.0348 |
| d1 | google/gemini-2.5-flash-lite | e2e_hx1 | 0/3 | [0.000, 0.562] | 0.0283 |
| d1 | google/gemini-2.5-flash-lite | e2e_hx2 | 0/3 | [0.000, 0.562] | 0.0170 |
| d1 | qwen/qwen3-coder-30b-a3b-instruct | e2e_hx1 | 2/3 | [0.208, 0.939] | 0.0382 |
| d1 | qwen/qwen3-coder-30b-a3b-instruct | e2e_hx2 | 0/3 | [0.000, 0.562] | 0.0254 |
| e | deepseek/deepseek-v3.2 | e2e_h01 | 2/3 | [0.208, 0.939] | 0.0982 |
| e | deepseek/deepseek-v3.2 | e2e_h02 | 3/3 | [0.438, 1.000] | 0.0586 |
| e | deepseek/deepseek-v3.2 | e2e_h03 | 1/3 | [0.061, 0.792] | 0.1512 |
| e | deepseek/deepseek-v3.2 | e2e_h04 | 1/3 | [0.061, 0.792] | 0.1373 |
| e | deepseek/deepseek-v3.2 | e2e_h05 | 3/3 | [0.438, 1.000] | 0.0779 |
| e | deepseek/deepseek-v3.2 | e2e_h06 | 3/3 | [0.438, 1.000] | 0.0686 |
| e | deepseek/deepseek-v3.2 | e2e_hx1 | 3/3 | [0.438, 1.000] | 0.0619 |
| e | deepseek/deepseek-v3.2 | e2e_hx2 | 3/3 | [0.438, 1.000] | 0.0918 |

## (a2) incomplete cells (no claim, n < 3 or missing tasks)

(none)

## (b) pooled

| arm | model | tasks | k/n | ratio | wilson | cost_usd | spd |
|---|---|---|---|---|---|---|---|
| a | google/gemini-2.5-flash-lite | 8 | 2/24 | 0.083 | [0.023, 0.258] | 0.6479 | 3.1 |
| a | mistralai/mistral-small-3.2-24b-instruct | 8 | 2/24 | 0.083 | [0.023, 0.258] | 0.2922 | 6.8 |
| a | qwen/qwen3-coder-30b-a3b-instruct | 8 | 6/24 | 0.250 | [0.120, 0.449] | 0.2830 | 21.2 |
| c_s | google/gemini-2.5-flash-lite | 7 | 5/21 | 0.238 | [0.106, 0.451] | 0.6204 | 8.1 |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | 7 | 3/21 | 0.143 | [0.050, 0.346] | 0.5926 | 5.1 |
| d1 | google/gemini-2.5-flash-lite | 2 | 0/6 | 0.000 | [0.000, 0.390] | 0.0453 | 0.0 |
| d1 | qwen/qwen3-coder-30b-a3b-instruct | 2 | 2/6 | 0.333 | [0.097, 0.700] | 0.0637 | 31.4 |
| e | deepseek/deepseek-v3.2 | 8 | 19/24 | 0.792 | [0.595, 0.908] | 0.7454 | 25.5 |

## (c) R38 classes

| role | arm | model | k/n | S | S_cc | S_cc wilson | r | interval | class | spd | base_spd | cost_advantage |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| arm a | a | google/gemini-2.5-flash-lite | 2/24 | 0.083 | 0.875 | [0.690, 0.957] | 0.095 | [0.026, 0.295] | c | 3.1 | 11.1 | no |
| arm a | a | mistralai/mistral-small-3.2-24b-instruct | 2/24 | 0.083 | 0.875 | [0.690, 0.957] | 0.095 | [0.026, 0.295] | c | 6.8 | 11.1 | no |
| arm a | a | qwen/qwen3-coder-30b-a3b-instruct | 6/24 | 0.250 | 0.875 | [0.690, 0.957] | 0.286 | [0.137, 0.513] | indeterminate | 21.2 | 11.1 | no |
| best | d1 | qwen/qwen3-coder-30b-a3b-instruct | 2/6 | 0.333 | 1.000 | [0.610, 1.000] | 0.333 | [0.097, 0.700] | indeterminate | 31.4 | 12.5 | yes |

best configuration: chosen post hoc among a, b, c_s, c_cc, d1, d2 by pooled solved ratio (tie: spd); optimistic at n = 3 (A20); every arm's own ratio is in (b).
indeterminate: the interval crosses a class boundary; the higher class is not claimed.

## (d) complementarity (arm a)

| task | solved by (>=1 of n) | max k/n | oracle cost/run |
|---|---|---|---|
| e2e_h01 | - | 0.000 | 0.0076 |
| e2e_h02 | mistralai/mistral-small-3.2-24b-instruct, qwen/qwen3-coder-30b-a3b-instruct | 0.667 | 0.0157 |
| e2e_h03 | - | 0.000 | 0.0173 |
| e2e_h04 | - | 0.000 | 0.0197 |
| e2e_h05 | google/gemini-2.5-flash-lite, qwen/qwen3-coder-30b-a3b-instruct | 0.667 | 0.0105 |
| e2e_h06 | qwen/qwen3-coder-30b-a3b-instruct | 0.333 | 0.0103 |
| e2e_hx1 | google/gemini-2.5-flash-lite, mistralai/mistral-small-3.2-24b-instruct, qwen/qwen3-coder-30b-a3b-instruct | 0.333 | 0.0039 |
| e2e_hx2 | - | 0.000 | 0.0018 |

union: 4 of 8 tasks
oracle_ratio: 0.250
oracle_cost_usd: 0.0867
oracle_spd: 23.1
best_single: qwen/qwen3-coder-30b-a3b-instruct (4 tasks)

| arm | model | tasks | S | spd | oracle S (same tasks) | oracle spd (same tasks) |
|---|---|---|---|---|---|---|
| c_s | google/gemini-2.5-flash-lite | 7 | 0.238 | 8.1 | 0.238 | 20.1 |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | 7 | 0.143 | 5.1 | 0.238 | 20.1 |

## (e) delegation

| arm | model | runs | attempts | attempts_unparsed | started | solved | cost_usd | wall_s |
|---|---|---|---|---|---|---|---|---|
| d1 | google/gemini-2.5-flash-lite | 6 | 6 | 0 | 5 | 0 | 0.0453 | 316.2 |
| d1 | qwen/qwen3-coder-30b-a3b-instruct | 6 | 0 | 0 | 0 | 2 | 0.0637 | 3784.3 |

## (f) P1

| mechanism | model | tasks | S | spd | best a | best a S | best a spd | decision |
|---|---|---|---|---|---|---|---|---|
| c_s | google/gemini-2.5-flash-lite | 7 | 0.238 | 8.1 | qwen/qwen3-coder-30b-a3b-instruct | 0.238 | 18.5 | OFF |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | 7 | 0.143 | 5.1 | qwen/qwen3-coder-30b-a3b-instruct | 0.238 | 18.5 | OFF |
| d1 | google/gemini-2.5-flash-lite | 2 | 0.000 | 0.0 | qwen/qwen3-coder-30b-a3b-instruct | 0.167 | 57.3 | OFF |
| d1 | qwen/qwen3-coder-30b-a3b-instruct | 2 | 0.333 | 31.4 | qwen/qwen3-coder-30b-a3b-instruct | 0.167 | 57.3 | OFF |
P1 b: not measured
P1 c_s: OFF
P1 c_cc: not measured
P1 d1: OFF

## (g) sensitivity: error runs and billed cost

| arm | model | variant | k/n | ratio | cost_usd | spd | complete |
|---|---|---|---|---|---|---|---|
| a | qwen/qwen3-coder-30b-a3b-instruct | unsolved/report | 4/24 | 0.167 | 0.2394 | 16.7 | yes |
| a | qwen/qwen3-coder-30b-a3b-instruct | unsolved/billed | 4/24 | 0.167 | 0.2729 | 14.7 | yes |
| a | qwen/qwen3-coder-30b-a3b-instruct | exclude/report | 4/21 | 0.190 | 0.2217 | 18.0 | no |
| a | qwen/qwen3-coder-30b-a3b-instruct | exclude/billed | 4/21 | 0.190 | 0.2552 | 15.7 | no |
| a | qwen/qwen3-coder-30b-a3b-instruct | replace/report | 6/24 | 0.250 | 0.2495 | 24.0 | yes |
| a | qwen/qwen3-coder-30b-a3b-instruct | replace/billed | 6/24 | 0.250 | 0.2830 | 21.2 | yes |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | unsolved/report | 2/21 | 0.095 | 0.4414 | 4.5 | yes |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | unsolved/billed | 2/21 | 0.095 | 0.4570 | 4.4 | yes |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | exclude/report | 2/16 | 0.125 | 0.4191 | 4.8 | no |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | exclude/billed | 2/16 | 0.125 | 0.4347 | 4.6 | no |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | replace/report | 3/21 | 0.143 | 0.5770 | 5.2 | yes |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | replace/billed | 3/21 | 0.143 | 0.5926 | 5.1 | yes |
| e | deepseek/deepseek-v3.2 | unsolved/report | 18/24 | 0.750 | 0.6818 | 26.4 | yes |
| e | deepseek/deepseek-v3.2 | unsolved/billed | 18/24 | 0.750 | 0.6994 | 25.7 | yes |
| e | deepseek/deepseek-v3.2 | exclude/report | 18/22 | 0.818 | 0.6687 | 26.9 | no |
| e | deepseek/deepseek-v3.2 | exclude/billed | 18/22 | 0.818 | 0.6725 | 26.8 | no |
| e | deepseek/deepseek-v3.2 | replace/report | 19/24 | 0.792 | 0.7385 | 25.7 | yes |
| e | deepseek/deepseek-v3.2 | replace/billed | 19/24 | 0.792 | 0.7454 | 25.5 | yes |

rerun RR-01 (of M19-08): a qwen/qwen3-coder-30b-a3b-instruct e2e_h04 r0 -> failed
rerun RR-02 (of M19-08): a qwen/qwen3-coder-30b-a3b-instruct e2e_h05 r2 -> solved
rerun RR-03 (of M19-09): a qwen/qwen3-coder-30b-a3b-instruct e2e_h06 r0 -> solved
rerun RR-04 (of M19-21): e deepseek/deepseek-v3.2 e2e_h04 r0 -> failed
rerun RR-05 (of M19-26): e deepseek/deepseek-v3.2 e2e_h06 r0 -> solved
rerun RR-06 (of M19-43): c_s qwen/qwen3-coder-30b-a3b-instruct e2e_h04 r0 -> failed
rerun RR-07 (of M19-43): c_s qwen/qwen3-coder-30b-a3b-instruct e2e_h04 r1 -> failed
rerun RR-08 (of M19-43): c_s qwen/qwen3-coder-30b-a3b-instruct e2e_h04 r2 -> failed
rerun RR-09 (of M19-43): c_s qwen/qwen3-coder-30b-a3b-instruct e2e_h05 r2 -> solved
rerun RR-10 (of M19-44): c_s qwen/qwen3-coder-30b-a3b-instruct e2e_h06 r2 -> failed

| report | report_cost | billed | extra |
|---|---|---|---|
| tests/fixtures/m19/reports/a-m2-i01.json | 0.0688 | 0.0697 | 0.0010 |
| tests/fixtures/m19/reports/a-m2-i02.json | 0.0490 | 0.0520 | 0.0029 |
| tests/fixtures/m19/reports/a-m2-i03.json | 0.0883 | 0.1110 | 0.0227 |
| tests/fixtures/m19/reports/a-m2-i04.json | 0.0295 | 0.0347 | 0.0052 |
| tests/fixtures/m19/reports/a-m2-i05.json | 0.0037 | 0.0054 | 0.0018 |
| tests/fixtures/m19/reports/e-i07.json | 0.0380 | 0.0417 | 0.0037 |
| tests/fixtures/m19/reports/e-i11.json | 0.0123 | 0.0214 | 0.0091 |
| tests/fixtures/m19/reports/e-i16.json | 0.0007 | 0.0055 | 0.0048 |
| tests/fixtures/m19/reports/rerun-05.json | 0.0178 | 0.0210 | 0.0032 |
| tests/fixtures/m19/reports/c_s-m1-i01.json | 0.1703 | 0.1769 | 0.0066 |
| tests/fixtures/m19/reports/c_s-m2-i04.json | 0.0431 | 0.0588 | 0.0156 |
| tests/fixtures/m19/reports/d1-m2-i01.json | 0.0623 | 0.0637 | 0.0014 |
billed extra total: 0.077827

## (g2) error runs and slow calls (> 90 s)

| arm | model | task | runs | error runs | calls > 90 s | max call s |
|---|---|---|---|---|---|---|
| a | google/gemini-2.5-flash-lite | e2e_h01 | 3 | 0 | 0 | 11.0 |
| a | google/gemini-2.5-flash-lite | e2e_h02 | 3 | 0 | 0 | 6.3 |
| a | google/gemini-2.5-flash-lite | e2e_h03 | 3 | 0 | 0 | 10.9 |
| a | google/gemini-2.5-flash-lite | e2e_h04 | 3 | 0 | 0 | 12.8 |
| a | google/gemini-2.5-flash-lite | e2e_h05 | 3 | 0 | 0 | 9.5 |
| a | google/gemini-2.5-flash-lite | e2e_h06 | 3 | 0 | 0 | 11.8 |
| a | google/gemini-2.5-flash-lite | e2e_hx1 | 3 | 0 | 0 | 10.0 |
| a | google/gemini-2.5-flash-lite | e2e_hx2 | 3 | 0 | 0 | 8.3 |
| a | mistralai/mistral-small-3.2-24b-instruct | e2e_h01 | 3 | 0 | 1 | 108.7 |
| a | mistralai/mistral-small-3.2-24b-instruct | e2e_h02 | 3 | 0 | 0 | 20.9 |
| a | mistralai/mistral-small-3.2-24b-instruct | e2e_h03 | 3 | 0 | 0 | 85.7 |
| a | mistralai/mistral-small-3.2-24b-instruct | e2e_h04 | 3 | 0 | 0 | 45.4 |
| a | mistralai/mistral-small-3.2-24b-instruct | e2e_h05 | 3 | 0 | 0 | 14.3 |
| a | mistralai/mistral-small-3.2-24b-instruct | e2e_h06 | 3 | 0 | 0 | 14.3 |
| a | mistralai/mistral-small-3.2-24b-instruct | e2e_hx1 | 3 | 0 | 0 | 8.1 |
| a | mistralai/mistral-small-3.2-24b-instruct | e2e_hx2 | 3 | 0 | 0 | 14.5 |
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_h01 | 3 | 0 | 0 | 89.8 |
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_h02 | 3 | 0 | 1 | 93.8 |
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_h03 | 3 | 0 | 2 | 258.4 |
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_h04 | 3 | 1 | 8 | 273.0 |
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_h05 | 3 | 1 | 3 | 273.0 |
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_h06 | 3 | 1 | 4 | 273.0 |
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_hx1 | 3 | 0 | 1 | 130.2 |
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_hx2 | 3 | 0 | 2 | 109.9 |
| c_s | google/gemini-2.5-flash-lite | e2e_h01 | 3 | 0 | 2 | 344.3 |
| c_s | google/gemini-2.5-flash-lite | e2e_h02 | 3 | 0 | 5 | 147.5 |
| c_s | google/gemini-2.5-flash-lite | e2e_h03 | 3 | 0 | 0 | 51.8 |
| c_s | google/gemini-2.5-flash-lite | e2e_h04 | 3 | 0 | 2 | 167.0 |
| c_s | google/gemini-2.5-flash-lite | e2e_h05 | 3 | 0 | 2 | 156.4 |
| c_s | google/gemini-2.5-flash-lite | e2e_h06 | 3 | 0 | 1 | 139.7 |
| c_s | google/gemini-2.5-flash-lite | e2e_hx2 | 3 | 0 | 0 | 18.2 |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | e2e_h01 | 3 | 0 | 8 | 157.7 |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | e2e_h02 | 3 | 0 | 11 | 184.1 |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | e2e_h03 | 3 | 0 | 3 | 176.0 |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | e2e_h04 | 3 | 3 | 0 | 82.4 |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | e2e_h05 | 3 | 1 | 3 | 111.2 |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | e2e_h06 | 3 | 1 | 4 | 903.0 |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | e2e_hx2 | 3 | 0 | 1 | 138.0 |
| d1 | google/gemini-2.5-flash-lite | e2e_hx1 | 3 | 0 | 0 | 11.0 |
| d1 | google/gemini-2.5-flash-lite | e2e_hx2 | 3 | 0 | 0 | 4.0 |
| d1 | qwen/qwen3-coder-30b-a3b-instruct | e2e_hx1 | 3 | 0 | 12 | 250.3 |
| d1 | qwen/qwen3-coder-30b-a3b-instruct | e2e_hx2 | 3 | 0 | 1 | 355.1 |
| e | deepseek/deepseek-v3.2 | e2e_h01 | 3 | 0 | 0 | 69.3 |
| e | deepseek/deepseek-v3.2 | e2e_h02 | 3 | 0 | 0 | 57.9 |
| e | deepseek/deepseek-v3.2 | e2e_h03 | 3 | 0 | 2 | 97.2 |
| e | deepseek/deepseek-v3.2 | e2e_h04 | 3 | 1 | 2 | 273.0 |
| e | deepseek/deepseek-v3.2 | e2e_h05 | 3 | 0 | 0 | 43.2 |
| e | deepseek/deepseek-v3.2 | e2e_h06 | 3 | 1 | 1 | 273.0 |
| e | deepseek/deepseek-v3.2 | e2e_hx1 | 3 | 0 | 1 | 172.9 |
| e | deepseek/deepseek-v3.2 | e2e_hx2 | 3 | 0 | 0 | 54.6 |
