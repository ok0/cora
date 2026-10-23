# M19 panel

reports: a=tests/fixtures/m19/reports/a-m1-i01.json a=tests/fixtures/m19/reports/a-m1-i02.json a=tests/fixtures/m19/reports/a-m1-i03.json a=tests/fixtures/m19/reports/a-m1-i04.json a=tests/fixtures/m19/reports/a-m1-i05.json a=tests/fixtures/m19/reports/a-m2-i01.json a=tests/fixtures/m19/reports/a-m2-i02.json a=tests/fixtures/m19/reports/a-m2-i03.json a=tests/fixtures/m19/reports/a-m2-i04.json a=tests/fixtures/m19/reports/a-m2-i05.json e=tests/fixtures/m19/reports/e-i01.json e=tests/fixtures/m19/reports/e-i02.json e=tests/fixtures/m19/reports/e-i03.json e=tests/fixtures/m19/reports/e-i04.json e=tests/fixtures/m19/reports/e-i05.json e=tests/fixtures/m19/reports/e-i06.json e=tests/fixtures/m19/reports/e-i07.json e=tests/fixtures/m19/reports/e-i08.json e=tests/fixtures/m19/reports/e-i09.json e=tests/fixtures/m19/reports/e-i10.json e=tests/fixtures/m19/reports/e-i11.json e=tests/fixtures/m19/reports/e-i12.json e=tests/fixtures/m19/reports/e-i13.json e=tests/fixtures/m19/reports/e-i14.json e=tests/fixtures/m19/reports/e-i15.json e=tests/fixtures/m19/reports/e-i16.json e=tests/fixtures/m19/reports/e-i17.json e=tests/fixtures/m19/reports/e-i18.json
baseline: none (blocked: no Claude Code baseline, arm f)
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
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_h01 | 0/3 | [0.000, 0.562] | 0.0224 |
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_h02 | 2/3 | [0.208, 0.939] | 0.0464 |
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_h03 | 0/3 | [0.000, 0.562] | 0.0490 |
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_h04 | 0/3 | [0.000, 0.562] | 0.0676 |
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_h05 | 1/3 | [0.061, 0.792] | 0.0207 |
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_h06 | 0/3 | [0.000, 0.562] | 0.0193 |
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_hx1 | 1/3 | [0.061, 0.792] | 0.0102 |
| a | qwen/qwen3-coder-30b-a3b-instruct | e2e_hx2 | 0/3 | [0.000, 0.562] | 0.0037 |
| e | deepseek/deepseek-v3.2 | e2e_h01 | 2/3 | [0.208, 0.939] | 0.0982 |
| e | deepseek/deepseek-v3.2 | e2e_h02 | 3/3 | [0.438, 1.000] | 0.0586 |
| e | deepseek/deepseek-v3.2 | e2e_h03 | 1/3 | [0.061, 0.792] | 0.1475 |
| e | deepseek/deepseek-v3.2 | e2e_h04 | 1/3 | [0.061, 0.792] | 0.0976 |
| e | deepseek/deepseek-v3.2 | e2e_h05 | 3/3 | [0.438, 1.000] | 0.0779 |
| e | deepseek/deepseek-v3.2 | e2e_h06 | 2/3 | [0.208, 0.939] | 0.0484 |

## (a2) incomplete cells (no claim, n < 3 or missing tasks)

| arm | model | missing | short |
|---|---|---|---|
| e | deepseek/deepseek-v3.2 | e2e_hx1, e2e_hx2 | - |

## (b) pooled

| arm | model | tasks | k/n | ratio | wilson | cost_usd | spd |
|---|---|---|---|---|---|---|---|
| a | google/gemini-2.5-flash-lite | 8 | 2/24 | 0.083 | [0.023, 0.258] | 0.6479 | 3.1 |
| a | qwen/qwen3-coder-30b-a3b-instruct | 8 | 4/24 | 0.167 | [0.067, 0.359] | 0.2394 | 16.7 |

## (c) R38 classes

blocked: no Claude Code baseline (arm f); classes and cost advantage not computed

## (d) complementarity (arm a)

| task | solved by (>=1 of n) | max k/n | oracle cost/run |
|---|---|---|---|
| e2e_h01 | - | 0.000 | 0.0075 |
| e2e_h02 | qwen/qwen3-coder-30b-a3b-instruct | 0.667 | 0.0155 |
| e2e_h03 | - | 0.000 | 0.0163 |
| e2e_h04 | - | 0.000 | 0.0225 |
| e2e_h05 | google/gemini-2.5-flash-lite, qwen/qwen3-coder-30b-a3b-instruct | 0.333 | 0.0069 |
| e2e_h06 | - | 0.000 | 0.0064 |
| e2e_hx1 | google/gemini-2.5-flash-lite, qwen/qwen3-coder-30b-a3b-instruct | 0.333 | 0.0034 |
| e2e_hx2 | - | 0.000 | 0.0012 |

union: 3 of 8 tasks
oracle_ratio: 0.167
oracle_cost_usd: 0.0798
oracle_spd: 16.7
best_single: qwen/qwen3-coder-30b-a3b-instruct (3 tasks)

(no b/c_s/c_cc cell)

## (e) delegation

(none)

## (f) P1

(none)
P1 b: not measured
P1 c_s: not measured
P1 c_cc: not measured
P1 d1: not measured
