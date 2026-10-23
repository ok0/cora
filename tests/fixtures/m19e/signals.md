# M19e1 signals

## Dataset and labels

| task | set | cheap cell | strong cell | member | k/n | cheap_ok |
|---|---|---|---|---|---|---|
| query_client_timeout | multi | M15 A cheap | M15 C strong | google/gemini-2.5-flash-lite | 3/3 (strong 3/3) | True |
| query_total_backoff | multi | M15 A cheap | M15 C strong | google/gemini-2.5-flash-lite | 3/3 (strong 2/3) | True |
| query_env_override | multi | M15 A cheap | M15 C strong | google/gemini-2.5-flash-lite | 3/3 (strong 2/3) | True |
| multi_edit_delay_cap | multi | M15 A cheap | M15 C strong | google/gemini-2.5-flash-lite | 1/3 (strong 2/3) | False |
| multi_edit_rename_cents | multi | M15 A cheap | M15 C strong | google/gemini-2.5-flash-lite | 2/3 (strong 1/3) | True |
| multi_edit_region | multi | M15 A cheap | M15 C strong | google/gemini-2.5-flash-lite | 3/3 (strong 0/3) | True |
| e2e_todo_cli | e2e | M16d A'' | M15 C strong | google/gemini-2.5-flash-lite | 8/8 (strong 0/3) | True |
| e2e_text_stats | e2e | M16d A'' | M15 C strong | google/gemini-2.5-flash-lite | 4/8 (strong 3/3) | False |
| e2e_rest_notes | e2e | M16d A'' | M15 C strong | google/gemini-2.5-flash-lite | 6/8 (strong 3/3) | True |
| e2e_md_to_html | e2e | M17 OFF | M15 C strong | google/gemini-2.5-flash-lite | 0/5 (strong 0/3) | False |
| e2e_refactor_inventory | e2e | M15b retest-cheap | M15 C strong | google/gemini-2.5-flash-lite | 0/2 (strong 1/3) | False |
| e2e_h01 | hard | M19 arm a | M19 arm e | qwen/qwen3-coder-30b-a3b-instruct | 0/3 (strong 2/3) | False |
| e2e_h02 | hard | M19 arm a | M19 arm e | qwen/qwen3-coder-30b-a3b-instruct | 2/3 (strong 3/3) | True |
| e2e_h03 | hard | M19 arm a | M19 arm e | qwen/qwen3-coder-30b-a3b-instruct | 0/3 (strong 1/3) | False |
| e2e_h04 | hard | M19 arm a | M19 arm e | qwen/qwen3-coder-30b-a3b-instruct | 0/3 (strong 1/3) | False |
| e2e_h05 | hard | M19 arm a | M19 arm e | qwen/qwen3-coder-30b-a3b-instruct | 1/3 (strong 3/3) | False |
| e2e_h06 | hard | M19 arm a | M19 arm e | qwen/qwen3-coder-30b-a3b-instruct | 0/3 (strong 2/3) | False |
| e2e_hx1 | hard | M19 arm a | M19 arm e | qwen/qwen3-coder-30b-a3b-instruct | 1/3 (strong 3/3) | False |
| e2e_hx2 | hard | M19 arm a | M19 arm e | qwen/qwen3-coder-30b-a3b-instruct | 0/3 (strong 3/3) | False |

## Per-task decisions

- query_client_timeout: S1a=5 (θ=14, cheap); S1b=2 (θ=10, cheap); S2=0 (θ=7, cheap); S3=0.3333 (θ=1, cheap); baseline=0.2
- query_total_backoff: S1a=11 (θ=11, strong); S1b=2 (θ=10, cheap); S2=0 (θ=6, cheap); S3=0 (θ=0.6667, cheap); baseline=0.2
- query_env_override: S1a=10 (θ=11, cheap); S1b=7 (θ=10, cheap); S2=0 (θ=6, cheap); S3=0 (θ=0.6667, cheap); baseline=0.2
- multi_edit_delay_cap: S1a=12 (θ=14, cheap); S1b=7 (θ=10, cheap); S2=1 (θ=7, cheap); S3=0 (θ=1, cheap); baseline=0
- multi_edit_rename_cents: S1a=8 (θ=11, cheap); S1b=3 (θ=10, cheap); S2=0 (θ=6, cheap); S3=0.3333 (θ=0.3333, strong); baseline=0.2
- multi_edit_region: S1a=12 (θ=11, strong); S1b=7 (θ=10, cheap); S2=2 (θ=6, cheap); S3=1 (θ=0.6667, strong); baseline=0.2
- e2e_todo_cli: S1a=7 (θ=7, strong); S1b=5 (θ=10, cheap); S2=1 (θ=6, cheap); S3=0.6667 (θ=0.6667, strong); baseline=0.75
- e2e_text_stats: S1a=7 (θ=19, cheap); S1b=7 (θ=10, cheap); S2=2 (θ=12, cheap); S3=0.3333 (θ=1, cheap); baseline=0.5
- e2e_rest_notes: S1a=9 (θ=14, cheap); S1b=7 (θ=10, cheap); S2=1 (θ=7, cheap); S3=0.3333 (θ=0.3333, strong); baseline=0.75
- e2e_md_to_html: S1a=8 (θ=14, cheap); S1b=12 (θ=10, strong); S2=1 (θ=7, cheap); S3=0 (θ=1, cheap); baseline=0.5
- e2e_refactor_inventory: S1a=10 (θ=14, cheap); S1b=7 (θ=10, cheap); S2=5 (θ=7, cheap); S3=0.6667 (θ=0.6667, strong); baseline=0.5
- e2e_h01: S1a=12 (θ=19, cheap); S1b=12 (θ=10, strong); S2=6 (θ=12, cheap); S3=0.6667 (θ=1, cheap); baseline=0.857
- e2e_h02: S1a=11 (θ=19, cheap); S1b=10 (θ=12, cheap); S2=6 (θ=12, cheap); S3=1 (θ=1, strong); baseline=1
- e2e_h03: S1a=12 (θ=14, cheap); S1b=12 (θ=10, strong); S2=5 (θ=7, cheap); S3=1 (θ=0.6667, strong); baseline=0.857
- e2e_h04: S1a=12 (θ=14, cheap); S1b=15 (θ=10, strong); S2=6 (θ=7, cheap); S3=0.6667 (θ=1, cheap); baseline=0.857
- e2e_h05: S1a=14 (θ=19, cheap); S1b=12 (θ=10, strong); S2=7 (θ=12, cheap); S3=1 (θ=1, strong); baseline=0.857
- e2e_h06: S1a=11 (θ=19, cheap); S1b=12 (θ=10, strong); S2=5 (θ=12, cheap); S3=0.6667 (θ=1, cheap); baseline=0.857
- e2e_hx1: S1a=9 (θ=19, cheap); S1b=4 (θ=10, cheap); S2=6 (θ=12, cheap); S3=0.6667 (θ=1, cheap); baseline=0.857
- e2e_hx2: S1a=19 (θ=14, strong); S1b=7 (θ=15, cheap); S2=12 (θ=7, strong); S3=1 (θ=1, strong); baseline=0.857

Decisions differ across tasks (S1a): yes
Decisions differ across tasks (S1b): yes
Decisions differ across tasks (S2): yes
Decisions differ across tasks (S3): yes

## Metrics

| signal | n | n_pos | AUROC | p | method | AUROC hard-only | > baseline | policy ratio | Wilson | spd | (i) | (ii) | (iii) | (iv) | pass |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S1a | 19 | 11 | 0.727 | 0.053 | exact | 0.786 | False | 0.412 | [0.303, 0.530] | 30.56 | False | False | False | False | False |
| S1b | 19 | 11 | 0.830 | 0.006 | exact | 0.714 | True | 0.634 | [0.518, 0.736] | 46.83 | True | True | True | True | True |
| S2 | 19 | 11 | 0.864 | 0.003 | exact | 0.500 | True | 0.548 | [0.434, 0.657] | 52.31 | True | True | True | False | False |
| S3 | 19 | 11 | 0.614 | 0.222 | exact | 0.214 | False | 0.469 | [0.352, 0.589] | 28.53 | False | False | False | False | False |
| S4 | 121 | 80 | 0.754 | 0.000 | monte_carlo | 0.701 | n/a | 0.554 | [0.465, 0.639] (approx) | 25.68 | True | True | n/a | False | False |
| baseline | 19 | 11 | 0.727 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | | | | | |

## Policy table

| policy | k | n | cost | ratio | Wilson | spd |
|---|---|---|---|---|---|---|
| always-best-cheap | 37.00 | 73 | 0.6765 | 0.507 | [0.395, 0.618] | 54.69 |
| always-strong | 35.00 | 57 | 1.2000 | 0.614 | [0.484, 0.729] | 29.17 |
| routed-S1a | 28.00 | 68 | 0.9161 | 0.412 | [0.303, 0.530] | 30.56 |
| routed-S1b | 45.00 | 71 | 0.9610 | 0.634 | [0.518, 0.736] | 46.83 |
| routed-S2 | 40.00 | 73 | 0.7646 | 0.548 | [0.434, 0.657] | 52.31 |
| routed-S3 | 30.00 | 64 | 1.0516 | 0.469 | [0.352, 0.589] | 28.53 |
| routed-S4 | 67.00 | 121 | 2.6086 | 0.554 | [0.465, 0.639] (approx) | 25.68 |
| oracle | 49.00 | 64 | 1.0517 | 0.766 | [0.649, 0.853] | 46.59 |

## S4 (run level)

- units (cheap runs with s4 status ok): 121; excluded cheap runs (not ok): 0
- prefix AUROC: 0.754; p: 0.000 (monte_carlo); hard-only AUROC: 0.701
- routed θ per task: e2e_h01=1, e2e_h02=1, e2e_h03=1, e2e_h04=1, e2e_h05=1, e2e_h06=1, e2e_hx1=1, e2e_hx2=1, e2e_md_to_html=1, e2e_refactor_inventory=1, e2e_rest_notes=1, e2e_text_stats=1, e2e_todo_cli=0, multi_edit_delay_cap=1, multi_edit_region=0, multi_edit_rename_cents=1, query_client_timeout=1, query_env_override=1, query_total_backoff=1

## Blocked

none

## Decision

Pass rule: PASS iff at least one signal meets all of: (i) AUROC ≥ 0.75; (ii) permutation p ≤ 0.025 (0.10 Bonferroni over 4 signals); (iii) S1–S3: AUROC > the set-identity baseline's; (iv) its simulated policy has solved-per-dollar > always-strong's AND solved ratio ≥ always-strong's − 0.05.

PASS — M19e2 proceeds.

cost: $0; openrouter_calls: 0
