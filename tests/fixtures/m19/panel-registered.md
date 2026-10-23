# M19 panel

reports: a=tests/fixtures/m19/reports/a-m1-i01.json a=tests/fixtures/m19/reports/a-m1-i02.json a=tests/fixtures/m19/reports/a-m1-i03.json a=tests/fixtures/m19/reports/a-m1-i04.json a=tests/fixtures/m19/reports/a-m1-i05.json a=tests/fixtures/m19/reports/a-m2-i01.json a=tests/fixtures/m19/reports/a-m2-i02.json a=tests/fixtures/m19/reports/a-m2-i03.json a=tests/fixtures/m19/reports/a-m2-i04.json a=tests/fixtures/m19/reports/a-m2-i05.json e=tests/fixtures/m19/reports/e-i01.json e=tests/fixtures/m19/reports/e-i02.json e=tests/fixtures/m19/reports/e-i03.json e=tests/fixtures/m19/reports/e-i04.json e=tests/fixtures/m19/reports/e-i05.json e=tests/fixtures/m19/reports/e-i06.json e=tests/fixtures/m19/reports/e-i07.json e=tests/fixtures/m19/reports/e-i08.json e=tests/fixtures/m19/reports/e-i09.json e=tests/fixtures/m19/reports/e-i10.json e=tests/fixtures/m19/reports/e-i11.json e=tests/fixtures/m19/reports/e-i12.json e=tests/fixtures/m19/reports/e-i13.json e=tests/fixtures/m19/reports/e-i14.json e=tests/fixtures/m19/reports/e-i15.json e=tests/fixtures/m19/reports/e-i16.json e=tests/fixtures/m19/reports/e-i17.json e=tests/fixtures/m19/reports/e-i18.json e=tests/fixtures/m19/reports/e-i19.json e=tests/fixtures/m19/reports/e-i20.json e=tests/fixtures/m19/reports/e-i21.json e=tests/fixtures/m19/reports/e-i22.json e=tests/fixtures/m19/reports/e-i23.json e=tests/fixtures/m19/reports/e-i24.json c_s=tests/fixtures/m19/reports/c_s-m1-i01.json c_s=tests/fixtures/m19/reports/c_s-m1-i02.json c_s=tests/fixtures/m19/reports/c_s-m1-i03.json c_s=tests/fixtures/m19/reports/c_s-m1-i04.json c_s=tests/fixtures/m19/reports/c_s-m1-i05.json d1=tests/fixtures/m19/reports/d1-m1-i01.json c_s=tests/fixtures/m19/reports/c_s-m2-i01.json c_s=tests/fixtures/m19/reports/c_s-m2-i02.json c_s=tests/fixtures/m19/reports/c_s-m2-i03.json c_s=tests/fixtures/m19/reports/c_s-m2-i04.json c_s=tests/fixtures/m19/reports/c_s-m2-i05.json d1=tests/fixtures/m19/reports/d1-m2-i01.json a=tests/fixtures/m19/reports/a-m3-i01.json a=tests/fixtures/m19/reports/a-m3-i02.json a=tests/fixtures/m19/reports/a-m3-i03.json a=tests/fixtures/m19/reports/a-m3-i04.json a=tests/fixtures/m19/reports/a-m3-i05.json
baseline: claude-code-m19.toml (claude-code, claude-sonnet-5-5)
thresholds: A=0.7 B=0.4 cost=2.0x

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
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_h01 | 0/3 | [0.000, 0.562] | 0.0224 |
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_h02 | 2/3 | [0.208, 0.939] | 0.0464 |
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_h03 | 0/3 | [0.000, 0.562] | 0.0490 |
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_h04 | 0/3 | [0.000, 0.562] | 0.0676 |
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_h05 | 1/3 | [0.061, 0.792] | 0.0207 |
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_h06 | 0/3 | [0.000, 0.562] | 0.0193 |
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_hx1 | 1/3 | [0.061, 0.792] | 0.0102 |
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_hx2 | 0/3 | [0.000, 0.562] | 0.0037 |
| c_s | google/gemini-2.5-flash-lite | e2e_h01 | 1/3 | [0.061, 0.792] | 0.1052 |
| c_s | google/gemini-2.5-flash-lite | e2e_h02 | 0/3 | [0.000, 0.562] | 0.0651 |
| c_s | google/gemini-2.5-flash-lite | e2e_h03 | 0/3 | [0.000, 0.562] | 0.1269 |
| c_s | google/gemini-2.5-flash-lite | e2e_h04 | 1/3 | [0.061, 0.792] | 0.0908 |
| c_s | google/gemini-2.5-flash-lite | e2e_h05 | 0/3 | [0.000, 0.562] | 0.1185 |
| c_s | google/gemini-2.5-flash-lite | e2e_h06 | 3/3 | [0.438, 1.000] | 0.0638 |
| c_s | google/gemini-2.5-flash-lite | e2e_hx2 | 0/3 | [0.000, 0.562] | 0.0435 |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | e2e_h01 | 0/3 | [0.000, 0.562] | 0.1358 |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | e2e_h02 | 1/3 | [0.061, 0.792] | 0.0996 |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | e2e_h03 | 0/3 | [0.000, 0.562] | 0.0772 |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | e2e_h04 | 0/3 | [0.000, 0.562] | 0.0054 |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | e2e_h05 | 0/3 | [0.000, 0.562] | 0.0454 |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | e2e_h06 | 1/3 | [0.061, 0.792] | 0.0431 |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | e2e_hx2 | 0/3 | [0.000, 0.562] | 0.0348 |
| d1 | google/gemini-2.5-flash-lite | e2e_hx1 | 0/3 | [0.000, 0.562] | 0.0283 |
| d1 | google/gemini-2.5-flash-lite | e2e_hx2 | 0/3 | [0.000, 0.562] | 0.0170 |
| d1 | qwen/qwen3-coder-30b-a3b-instruct | e2e_hx1 | 2/3 | [0.208, 0.939] | 0.0374 |
| d1 | qwen/qwen3-coder-30b-a3b-instruct | e2e_hx2 | 0/3 | [0.000, 0.562] | 0.0249 |
| e | deepseek/deepseek-v3.2 | e2e_h01 | 2/3 | [0.208, 0.939] | 0.0982 |
| e | deepseek/deepseek-v3.2 | e2e_h02 | 3/3 | [0.438, 1.000] | 0.0586 |
| e | deepseek/deepseek-v3.2 | e2e_h03 | 1/3 | [0.061, 0.792] | 0.1475 |
| e | deepseek/deepseek-v3.2 | e2e_h04 | 1/3 | [0.061, 0.792] | 0.0976 |
| e | deepseek/deepseek-v3.2 | e2e_h05 | 3/3 | [0.438, 1.000] | 0.0779 |
| e | deepseek/deepseek-v3.2 | e2e_h06 | 2/3 | [0.208, 0.939] | 0.0484 |
| e | deepseek/deepseek-v3.2 | e2e_hx1 | 3/3 | [0.438, 1.000] | 0.0619 |
| e | deepseek/deepseek-v3.2 | e2e_hx2 | 3/3 | [0.438, 1.000] | 0.0918 |

## (a2) incomplete cells (no claim, n < 3 or missing tasks)

(none)

## (b) pooled

| arm | model | tasks | k/n | ratio | wilson | cost_usd | spd |
|---|---|---|---|---|---|---|---|
| a | google/gemini-2.5-flash-lite | 8 | 2/24 | 0.083 | [0.023, 0.258] | 0.6479 | 3.1 |
| a | mistralai/mistral-small-3.2-24b-instruct | 8 | 2/24 | 0.083 | [0.023, 0.258] | 0.2922 | 6.8 |
| a | qwen/qwen3-coder-30b-a3b-instruct | 8 | 4/24 | 0.167 | [0.067, 0.359] | 0.2394 | 16.7 |
| c_s | google/gemini-2.5-flash-lite | 7 | 5/21 | 0.238 | [0.106, 0.451] | 0.6139 | 8.1 |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | 7 | 2/21 | 0.095 | [0.027, 0.289] | 0.4414 | 4.5 |
| d1 | google/gemini-2.5-flash-lite | 2 | 0/6 | 0.000 | [0.000, 0.390] | 0.0453 | 0.0 |
| d1 | qwen/qwen3-coder-30b-a3b-instruct | 2 | 2/6 | 0.333 | [0.097, 0.700] | 0.0623 | 32.1 |
| e | deepseek/deepseek-v3.2 | 8 | 18/24 | 0.750 | [0.551, 0.880] | 0.6818 | 26.4 |

## (c) R38 classes

| role | arm | model | k/n | S | S_cc | S_cc wilson | r | interval | class | spd | base_spd | cost_advantage |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| arm a | a | google/gemini-2.5-flash-lite | 2/24 | 0.083 | 0.875 | [0.690, 0.957] | 0.095 | [0.026, 0.295] | c | 3.1 | 11.1 | no |
| arm a | a | mistralai/mistral-small-3.2-24b-instruct | 2/24 | 0.083 | 0.875 | [0.690, 0.957] | 0.095 | [0.026, 0.295] | c | 6.8 | 11.1 | no |
| arm a | a | qwen/qwen3-coder-30b-a3b-instruct | 4/24 | 0.167 | 0.875 | [0.690, 0.957] | 0.190 | [0.076, 0.410] | indeterminate | 16.7 | 11.1 | no |
| best | d1 | qwen/qwen3-coder-30b-a3b-instruct | 2/6 | 0.333 | 1.000 | [0.610, 1.000] | 0.333 | [0.097, 0.700] | indeterminate | 32.1 | 12.5 | yes |

best configuration: chosen post hoc among a, b, c_s, c_cc, d1, d2 by pooled solved ratio (tie: spd); optimistic at n = 3 (A20); every arm's own ratio is in (b).
indeterminate: the interval crosses a class boundary; the higher class is not claimed.

## (d) complementarity (arm a)

| task | solved by (>=1 of n) | max k/n | oracle cost/run |
|---|---|---|---|
| e2e_h01 | - | 0.000 | 0.0075 |
| e2e_h02 | mistralai/mistral-small-3.2-24b-instruct, qwen/qwen3-coder-30b-a3b-instruct | 0.667 | 0.0155 |
| e2e_h03 | - | 0.000 | 0.0163 |
| e2e_h04 | - | 0.000 | 0.0197 |
| e2e_h05 | google/gemini-2.5-flash-lite, qwen/qwen3-coder-30b-a3b-instruct | 0.333 | 0.0069 |
| e2e_h06 | - | 0.000 | 0.0064 |
| e2e_hx1 | google/gemini-2.5-flash-lite, mistralai/mistral-small-3.2-24b-instruct, qwen/qwen3-coder-30b-a3b-instruct | 0.333 | 0.0034 |
| e2e_hx2 | - | 0.000 | 0.0012 |

union: 3 of 8 tasks
oracle_ratio: 0.167
oracle_cost_usd: 0.0769
oracle_spd: 17.3
best_single: qwen/qwen3-coder-30b-a3b-instruct (3 tasks)

| arm | model | tasks | S | spd | oracle S (same tasks) | oracle spd (same tasks) |
|---|---|---|---|---|---|---|
| c_s | google/gemini-2.5-flash-lite | 7 | 0.238 | 8.1 | 0.143 | 13.6 |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | 7 | 0.095 | 4.5 | 0.143 | 13.6 |

## (e) delegation

| arm | model | runs | attempts | attempts_unparsed | started | solved | cost_usd | wall_s |
|---|---|---|---|---|---|---|---|---|
| d1 | google/gemini-2.5-flash-lite | 6 | 6 | 0 | 5 | 0 | 0.0453 | 316.2 |
| d1 | qwen/qwen3-coder-30b-a3b-instruct | 6 | 0 | 0 | 0 | 2 | 0.0623 | 3784.3 |

## (f) P1

| mechanism | model | tasks | S | spd | best a | best a S | best a spd | decision |
|---|---|---|---|---|---|---|---|---|
| c_s | google/gemini-2.5-flash-lite | 7 | 0.238 | 8.1 | qwen/qwen3-coder-30b-a3b-instruct | 0.143 | 13.1 | OFF |
| c_s | qwen/qwen3-coder-30b-a3b-instruct | 7 | 0.095 | 4.5 | qwen/qwen3-coder-30b-a3b-instruct | 0.143 | 13.1 | OFF |
| d1 | google/gemini-2.5-flash-lite | 2 | 0.000 | 0.0 | qwen/qwen3-coder-30b-a3b-instruct | 0.167 | 72.0 | OFF |
| d1 | qwen/qwen3-coder-30b-a3b-instruct | 2 | 0.333 | 32.1 | qwen/qwen3-coder-30b-a3b-instruct | 0.167 | 72.0 | OFF |
P1 b: not measured
P1 c_s: OFF
P1 c_cc: not measured
P1 d1: OFF
