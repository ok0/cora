# M19d perfect pre-router upper bound (offline, $0)

inputs:
- tests/fixtures/m19/panel-args.txt
- tests/fixtures/m19/panel-extras.json
- tests/fixtures/m19/claude-code-m19.toml

## Caveats

- This is an upper bound, not a router.
- It uses post-hoc knowledge of the same trials it is scored on (selection bias); the numbers are optimistic.
- n is small: 8 tasks, n=3 per cell; intervals are wide.
- No claim is made that any router can reach this bound. Nothing is adopted; routing defaults are unchanged.

## Oracle rule

- Oracle rule (fixed before computing): for each task, choose the arm group (cheap-only or strong) with the higher observed solve rate k/n on that task.
- Ties (equal k/n) go to the cheaper group: lower mean cost per trial (cost/n) on that task; if mean cost is also equal, cheap-only.
- Cheap-only group on a task = the best-observed arm `a` model on that task: highest k/n, then lowest mean cost per trial, then model name ascending.
- Strong group = arm `e` (single model). Arms c_s and d1 mix cheap and strong models and are excluded.
- If only one group has data for a task, that group is chosen (reason `only data`). If neither has data, the task is named as missing and left out of every denominator; nothing is imputed.
- Oracle totals = sum of the chosen group's k, n and cost over tasks.

## View: billed
error policy: replace
cost basis: billed
extras: tests/fixtures/m19/panel-extras.json

### Groups

- cheap-only (arm a): google/gemini-2.5-flash-lite, mistralai/mistral-small-3.2-24b-instruct, qwen/qwen3-coder-30b-a3b-instruct
- strong (arm e): deepseek/deepseek-v3.2
- excluded arms: c_s, d1

### Per-task

| task | cheap best config | cheap k/n | cheap cost_usd | strong k/n | strong cost_usd | oracle choice | reason |
|---|---|---|---|---|---|---|---|
| e2e_h01 | qwen/qwen3-coder-30b-a3b-instruct | 0/3 | 0.0227 | 2/3 | 0.0982 | strong | higher rate |
| e2e_h02 | qwen/qwen3-coder-30b-a3b-instruct | 2/3 | 0.0470 | 3/3 | 0.0586 | strong | higher rate |
| e2e_h03 | qwen/qwen3-coder-30b-a3b-instruct | 0/3 | 0.0520 | 1/3 | 0.1512 | strong | higher rate |
| e2e_h04 | mistralai/mistral-small-3.2-24b-instruct | 0/3 | 0.0590 | 1/3 | 0.1373 | strong | higher rate |
| e2e_h05 | qwen/qwen3-coder-30b-a3b-instruct | 2/3 | 0.0314 | 3/3 | 0.0779 | strong | higher rate |
| e2e_h06 | qwen/qwen3-coder-30b-a3b-instruct | 1/3 | 0.0308 | 3/3 | 0.0686 | strong | higher rate |
| e2e_hx1 | mistralai/mistral-small-3.2-24b-instruct | 1/3 | 0.0117 | 3/3 | 0.0619 | strong | higher rate |
| e2e_hx2 | qwen/qwen3-coder-30b-a3b-instruct | 0/3 | 0.0054 | 3/3 | 0.0918 | strong | higher rate |

### Comparison

| row | config | tasks | solved/total | ratio | wilson95 | cost_usd | solved/$ | missing |
|---|---|---|---|---|---|---|---|---|
| oracle | per-task choice | 8/8 | 19/24 | 0.792 | [0.595, 0.908] | 0.7454 | 25.5 | none |
| best single cheap | qwen/qwen3-coder-30b-a3b-instruct | 8/8 | 6/24 | 0.250 | [0.120, 0.449] | 0.2830 | 21.2 | none |
| strong | deepseek/deepseek-v3.2 | 8/8 | 19/24 | 0.792 | [0.595, 0.908] | 0.7454 | 25.5 | none |
| Claude Code | claude-code-m19.toml (toml cost, no ledger) | 8/8 | 21/24 | 0.875 | [0.690, 0.957] | 1.8933 | 11.1 | none |

Missing oracle tasks: none

## View: registered
error policy: unsolved
cost basis: report
extras: none

### Groups

- cheap-only (arm a): google/gemini-2.5-flash-lite, mistralai/mistral-small-3.2-24b-instruct, qwen/qwen3-coder-30b-a3b-instruct
- strong (arm e): deepseek/deepseek-v3.2
- excluded arms: c_s, d1

### Per-task

| task | cheap best config | cheap k/n | cheap cost_usd | strong k/n | strong cost_usd | oracle choice | reason |
|---|---|---|---|---|---|---|---|
| e2e_h01 | qwen/qwen3-coder-30b-a3b-instruct | 0/3 | 0.0224 | 2/3 | 0.0982 | strong | higher rate |
| e2e_h02 | qwen/qwen3-coder-30b-a3b-instruct | 2/3 | 0.0464 | 3/3 | 0.0586 | strong | higher rate |
| e2e_h03 | qwen/qwen3-coder-30b-a3b-instruct | 0/3 | 0.0490 | 1/3 | 0.1475 | strong | higher rate |
| e2e_h04 | mistralai/mistral-small-3.2-24b-instruct | 0/3 | 0.0590 | 1/3 | 0.0976 | strong | higher rate |
| e2e_h05 | qwen/qwen3-coder-30b-a3b-instruct | 1/3 | 0.0207 | 3/3 | 0.0779 | strong | higher rate |
| e2e_h06 | qwen/qwen3-coder-30b-a3b-instruct | 0/3 | 0.0193 | 2/3 | 0.0484 | strong | higher rate |
| e2e_hx1 | qwen/qwen3-coder-30b-a3b-instruct | 1/3 | 0.0102 | 3/3 | 0.0619 | strong | higher rate |
| e2e_hx2 | qwen/qwen3-coder-30b-a3b-instruct | 0/3 | 0.0037 | 3/3 | 0.0918 | strong | higher rate |

### Comparison

| row | config | tasks | solved/total | ratio | wilson95 | cost_usd | solved/$ | missing |
|---|---|---|---|---|---|---|---|---|
| oracle | per-task choice | 8/8 | 18/24 | 0.750 | [0.551, 0.880] | 0.6818 | 26.4 | none |
| best single cheap | qwen/qwen3-coder-30b-a3b-instruct | 8/8 | 4/24 | 0.167 | [0.067, 0.359] | 0.2394 | 16.7 | none |
| strong | deepseek/deepseek-v3.2 | 8/8 | 18/24 | 0.750 | [0.551, 0.880] | 0.6818 | 26.4 | none |
| Claude Code | claude-code-m19.toml (toml cost, no ledger) | 8/8 | 21/24 | 0.875 | [0.690, 0.957] | 1.8933 | 11.1 | none |

Missing oracle tasks: none
