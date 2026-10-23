# M19c spec-aware routing probe

- date: 2026-10-22
- model: gemini-3.5-flash-lite
- provider: gemini
- input_cap: 6000
- timeout_s: 60.0
- temperature: 0
- decider: llm (src/cora/core/deciders/llm.py, unchanged)
- openrouter_calls: 0 (GeminiOnlyPool)

## Pre-registered labels

- e2e_h01: strong
- e2e_h02: cheap
- e2e_h03: strong
- e2e_h04: strong
- e2e_h05: cheap
- e2e_h06: cheap
- e2e_hx1: cheap
- e2e_hx2: strong

## Protocol

- P-1: task.toml difficulty is medium for e2e_h02 and e2e_h06 and hard for the other six; the set is the 8 M19 panel tasks and the difficulty column shows task.toml as-is.
- P-2: the model is gemini-3.5-flash-lite (provider gemini, free_tier true), the first flash-lite free-tier gemini entry in cora.toml order.
- P-3: the decider input is built by the probe as agent prompt plus full REQUIREMENTS.md; spec+summary appends a template and required-file count line; production routing is unchanged.
- P-4: the LLMDecider input cap is patched to 6000 chars inside the probe only (src default 2000 unchanged); any input over the cap raises.
- P-5: the probe decider timeout is 60 s; a timeout is recorded as blocked (timeout).
- P-6: any decider fallback is recorded as blocked with its reason; blocked rows are never hits; no script-level retries; one pass per variant.
- P-7: k = hits out of 8 (blocked rows are not hits); k >= 6 not adopted; 3 to 5 near chance; k <= 2 below chance; any blocked row appends an incomplete note.
- P-8: no ProviderPool is built; only the gemini provider is reachable through GeminiOnlyPool; cost is recorded per task by CostMeter.

## Results: spec

| task | difficulty | label | pick | conf | hit | status | heur_wrapper | heur_input | spec_chars | input_chars | required_files | template_files | cost_usd | cost_source |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| e2e_h01 | hard | strong | strong | 0.90 | hit | ok | 2 | 3 | 2811 | 3122 | 3 | 6 | 0.000000 | free_tier |
| e2e_h02 | medium | cheap | strong | 0.90 | miss | ok | 2 | 3 | 2364 | 2692 | 4 | 6 | 0.000000 | free_tier |
| e2e_h03 | hard | strong | strong | 0.90 | hit | ok | 2 | 3 | 3191 | 3521 | 4 | 6 | 0.000000 | free_tier |
| e2e_h04 | hard | strong | strong | 0.95 | hit | ok | 2 | 3 | 2640 | 2943 | 3 | 6 | 0.000000 | free_tier |
| e2e_h05 | hard | cheap | strong | 0.95 | miss | ok | 2 | 4 | 2335 | 2685 | 5 | 8 | 0.000000 | free_tier |
| e2e_h06 | medium | cheap | strong | 0.95 | miss | ok | 2 | 3 | 2581 | 2895 | 3 | 5 | 0.000000 | free_tier |
| e2e_hx1 | hard | cheap | strong | 0.85 | miss | ok | 2 | 4 | 1055 | 1321 | 1 | 33 | 0.000000 | free_tier |
| e2e_hx2 | hard | strong | strong | 0.85 | hit | ok | 2 | 3 | 643 | 910 | 1 | 33 | 0.000000 | free_tier |

Summary: 4/8 hits
Misses: e2e_h02, e2e_h05, e2e_h06, e2e_hx1
Blocked: none
Outcome: near chance: no discrimination from input improvement alone

## Results: spec+summary

| task | difficulty | label | pick | conf | hit | status | heur_wrapper | heur_input | spec_chars | input_chars | required_files | template_files | cost_usd | cost_source |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| e2e_h01 | hard | strong | strong | 0.90 | hit | ok | 2 | 3 | 2811 | 3182 | 3 | 6 | 0.000000 | free_tier |
| e2e_h02 | medium | cheap | strong | 0.90 | miss | ok | 2 | 3 | 2364 | 2752 | 4 | 6 | 0.000000 | free_tier |
| e2e_h03 | hard | strong | strong | 0.90 | hit | ok | 2 | 3 | 3191 | 3581 | 4 | 6 | 0.000000 | free_tier |
| e2e_h04 | hard | strong | strong | 0.95 | hit | ok | 2 | 3 | 2640 | 3003 | 3 | 6 | 0.000000 | free_tier |
| e2e_h05 | hard | cheap | strong | 0.95 | miss | ok | 2 | 4 | 2335 | 2745 | 5 | 8 | 0.000000 | free_tier |
| e2e_h06 | medium | cheap | strong | 0.95 | miss | ok | 2 | 3 | 2581 | 2955 | 3 | 5 | 0.000000 | free_tier |
| e2e_hx1 | hard | cheap | cheap | 0.90 | hit | ok | 2 | 4 | 1055 | 1382 | 1 | 33 | 0.000000 | free_tier |
| e2e_hx2 | hard | strong | strong | 0.85 | hit | ok | 2 | 3 | 643 | 971 | 1 | 33 | 0.000000 | free_tier |

Summary: 5/8 hits
Misses: e2e_h02, e2e_h05, e2e_h06
Blocked: none
Outcome: near chance: no discrimination from input improvement alone

## Raw answers

```jsonl
{"variant": "spec", "task": "e2e_h01", "raw": "{\"answer\": \"strong\", \"confidence\": 0.9}", "reason": ""}
{"variant": "spec", "task": "e2e_h02", "raw": "{\"answer\": \"strong\", \"confidence\": 0.9}", "reason": ""}
{"variant": "spec", "task": "e2e_h03", "raw": "{\"answer\": \"strong\", \"confidence\": 0.9}", "reason": ""}
{"variant": "spec", "task": "e2e_h04", "raw": "{\"answer\": \"strong\", \"confidence\": 0.95}", "reason": ""}
{"variant": "spec", "task": "e2e_h05", "raw": "{\"answer\": \"strong\", \"confidence\": 0.95}", "reason": ""}
{"variant": "spec", "task": "e2e_h06", "raw": "{\"answer\": \"strong\", \"confidence\": 0.95}", "reason": ""}
{"variant": "spec", "task": "e2e_hx1", "raw": "{\"answer\": \"strong\", \"confidence\": 0.85}", "reason": ""}
{"variant": "spec", "task": "e2e_hx2", "raw": "{\"answer\": \"strong\", \"confidence\": 0.85}", "reason": ""}
{"variant": "spec+summary", "task": "e2e_h01", "raw": "{\"answer\": \"strong\", \"confidence\": 0.9}", "reason": ""}
{"variant": "spec+summary", "task": "e2e_h02", "raw": "{\"answer\": \"strong\", \"confidence\": 0.9}", "reason": ""}
{"variant": "spec+summary", "task": "e2e_h03", "raw": "{\"answer\": \"strong\", \"confidence\": 0.9}", "reason": ""}
{"variant": "spec+summary", "task": "e2e_h04", "raw": "{\n  \"answer\": \"strong\",\n  \"confidence\": 0.95\n}", "reason": ""}
{"variant": "spec+summary", "task": "e2e_h05", "raw": "{\"answer\": \"strong\", \"confidence\": 0.95}", "reason": ""}
{"variant": "spec+summary", "task": "e2e_h06", "raw": "{\"answer\": \"strong\", \"confidence\": 0.95}", "reason": ""}
{"variant": "spec+summary", "task": "e2e_hx1", "raw": "{\"answer\": \"cheap\", \"confidence\": 0.9}", "reason": ""}
{"variant": "spec+summary", "task": "e2e_hx2", "raw": "{\n  \"answer\": \"strong\",\n  \"confidence\": 0.85\n}", "reason": ""}
```

## Cost

- cost_usd total: 0.000000
- cost_source: free_tier
