# M19 사전 등록 — git 추적 기록

`.docs/`는 .gitignore 대상이므로 이 파일이 M19 사전 등록의 git 추적 기록입니다. 각 `##` 절은 `.docs/bench-results.md`의 같은 절과 바이트 단위로 같습니다. 절은 덧붙이기만 하고 기존 절은 고치지 않습니다.

## M19 사전 등록 (2026-10-18T06:16:09Z)
이 절은 M19 실행 전에 기록하는 판정 규칙, 분류 규칙, 팔 레시피입니다. 1부는 실행 전에 고정하고, 2부(모델 가격, 팔 설정 차이, 호출 목록, 사용자 확인)는 별도 절에 기록합니다. 이 절은 수정하지 않습니다. 변경은 `## M19 사전 등록 수정 (<UTC>)` 새 절로 남깁니다.

### 판정 기준

- 임계값: 0.70 / 0.40 / 2.0x (A16, 사용자 확인 2026-10-18).
- N = 3: 셀(팔, 모델, 과제)마다 3회 실행합니다 (A17).
- 해결 비율 S = 해결된 실행 수 / 완료된 전체 실행 수. 과제 집합 전체(`e2e_h01`–`e2e_h06`, `e2e_hx1`, `e2e_hx2`)에서 풀링합니다. 팔 레시피 6에서 과제 부분집합을 지정한 경우에는 그 부분집합을 씁니다.
- S_cc = 같은 과제에서 Claude Code가 풀링한 해결 비율. 값은 `.docs/baselines/claude-code-m19.toml`에서 읽습니다. 이 파일은 `.docs/baseline-protocol.md`에 따라 M19에서 팔 f가 만듭니다. `claude-code-m15.toml`에는 hard set 과제가 없으므로 쓰지 않습니다.
- 분석 명령: `uv run python tests/m19_panel.py <label>=<report.json>... --baseline .docs/baselines/claude-code-m19.toml --thresholds 0.70,0.40,2.0`

### 분류와 indeterminate 규칙

- 청사진 2.30 "Classification"의 내용을 그대로 따릅니다.
- r = S / S_cc.
- 구간: [W_lo(S) / S_cc, W_hi(S) / S_cc], Wilson 95%. S_cc의 구간도 옆에 함께 표시합니다.
- 점추정 기준 분류: (a) r ≥ 0.70, (b) 0.40 ≤ r < 0.70, (c) r < 0.40.
- 구간이 점추정 분류 위 또는 아래의 분류 경계를 가로지르면 결과는 "indeterminate at this n"입니다. 이때 더 높은 분류를 주장하지 않습니다.
- 주의: n = 3에서 구간의 반폭은 약 ±0.2입니다. 분류 결과는 이 폭을 감안해 읽습니다.

### 비용 우위 규칙

- 비용 우위는 solved-per-dollar ≥ 2.0 × Claude Code의 solved-per-dollar일 때만 주장합니다.
- 비용은 R29 가격 규칙으로 계산하며, Claude Code 값은 기준 파일의 `cost_usd`를 씁니다.

### 최선 구성 (best configuration)

- 후보: 저가 단독 팔(a, b, d1, d2, 모델별)과 캐스케이드(c_s, c_cc). 캐스케이드는 강한 모델과 두 번째 모델의 토큰을 포함한 실제 비용으로 셉니다.
- 선택 기준: 풀링한 해결 비율이 가장 높은 구성을 고릅니다. 동률이면 solved-per-dollar가 높은 구성을 고릅니다.
- 이 선택은 사후(post hoc)에 합니다. n = 3에서는 낙관적인 값임을 명시합니다 (A20).
- 최선 구성 옆에 모든 팔의 개별 비율을 함께 보고합니다.

### 상보성 (oracle / union)

- 청사진 2.30 "Complementarity"의 내용을 그대로 따릅니다.
- 대상: 팔 a의 셀만 씁니다.
- Union: 어떤 저가 멤버라도 3회 중 1회 이상(≥ 1/3) 푼 과제 집합.
- Oracle 비율 = 과제별 max_m (k / n)의 평균. 여기서 k는 해결 수, n은 실행 수, m은 멤버입니다.
- Oracle 과제당 비용 = max에 도달한 멤버들 중 가장 싼 멤버의 실행당 평균 비용. max = 0이면 가장 싼 멤버의 평균 비용입니다.
- Oracle solved-per-dollar는 위 두 값에서 계산합니다. b, c_cc, c_s 옆에 표시합니다.

### 팔 레시피

모든 팔은 출시 기본값으로 실행합니다. 도구 그룹은 `core`, 루프는 react입니다. 팔 설정 파일은 `cora.toml`의 전체 복사본이며 나열된 키만 바꿉니다. `diff`는 2부에 인용합니다.

- `a(m)` = `--live --suite e2e --models <m> --protocols react`, 고정(pinned), 과제 8개 전체.
- `b(m)` = a + `--verify-attempts 3`, F 과제 + `e2e_hx2`.
- `c_s(m)` = `-c .cora/bench/m19/cascade-strong.toml --ab auto-routed --sensor --sensor-source auto --models <m>`, F 과제 + `e2e_hx2`. 설정: `[router] mode = "cheap_first"`, `[escalation] enabled = true, on_budget_fraction = 0.5, on_stuck_iterations = 4, on_tripwire = true, strong_model = "deepseek/deepseek-v3.2"`, `[agent] ladder = true`.
- `c_cc(m1→m2)` = 같은 레시피에 `-c .cora/bench/m19/cascade-m1-m2.toml`을 쓰고 `strong_model = <m2 id>`, `--models <m1>`.
- `d1(m)` = `-c .cora/bench/m19/deleg-nudge.toml --ab deleg-on-par-on --models <m>` (`[delegation] nudge = true`), 과제 `e2e_hx1,e2e_hx2`.
- `d2(m)` = 팔 a의 X 과제 셀을 재사용합니다. 단, 보고서 `settings`가 팔 외에는 같을 때만 씁니다. 아니면 X 과제에서 `--ab deleg-off`로 실행합니다.
- `e` = `--models deepseek/deepseek-v3.2 --e2e-task-cost <strong cap>`, 과제 8개 전체. 강한 한도(strong cap) = 최대 과제별 보정 강한 모델 추정치 × 3. 추정치는 M18 보정 토큰 × 갱신된 deepseek 가격으로 구하고, 센트 단위로 올림합니다. 값은 2부에서 고정합니다.
- `f` = Claude Code, `.docs/baseline-protocol.md` 기준, 가능한 경우 n = 3 (할당량이 부족하면 실제 n을 적습니다). 구독 사용이며 유료 지출은 없습니다.
- `g` (선택, 우선순위 최하, ADR-32) = `a(m2)` + `-c .cora/bench/m19/keys-on.toml` (`raw_file_body`, `repeat_breaker`, `located_errors` = true), F 과제.

### 팔 b 한도 의미 (ADR-33)

- `max_iterations`는 시도(attempt)마다 셉니다.
- 최종 답변 게이트는 실행당 최대 한 번만 발동합니다.
- 과제별 비용 한도와 `wall_s`는 모든 시도를 합산합니다.
- 팔 b의 설정은 `[agent] ladder = false`를 유지합니다.
- 고정된 실행은 재시도해도 같은 모델을 씁니다.

### 같은 한도 해석

- "같은 한도"(R37)는 역할별로 패널 멤버 사이에서 한도가 같다는 뜻입니다.
- 반복 한도와 `wall_s`는 모든 팔과 모델에서 task.toml 값을 씁니다.
- 과제별 비용 한도는 모든 저가 시작 팔(a, b, c_s, c_cc, d1, d2, g)과 모든 저가 멤버에서 task.toml의 `cost_usd`입니다.
- 팔 e는 강한 한도 하나를 씁니다.
- 이 해석은 제안된 읽기 방식이며 사용자 확인을 기다립니다. 읽기 방식 자체는 이 절에서 고정하고, 확인만 2부에서 받습니다.

### P1 결정 규칙

- 메커니즘(b, c_s, c_cc, d1)마다 판정합니다.
- 기본값 ON 조건: solved-per-dollar가 최선의 단독 저가 팔 a보다 크고, 풀링한 해결 비율이 팔 a 이상입니다. 두 조건은 같은 과제에서 비교합니다.
- 그렇지 않으면 OFF로 두고 결과를 기록합니다.
- d1은 `deleg_attempts`와 시작된 하위 에이전트 수를 함께 보고합니다.

### 하네스 (ADR-32)

- 출시 기본값을 씁니다.
- M16c/M16d의 여섯 키는 ON입니다.
- M17b의 키(`raw_file_body`, `repeat_breaker`, `located_errors`)는 `false`입니다.
- `ledger = false`입니다.
- 이 값들을 바꾸는 것은 셀 g뿐입니다.

### 절단 순서와 실행 규칙

- 셀은 사용자가 확인하고 2부에 기록한 순서로 실행합니다. 절단은 아래에서부터 합니다.
- 셀은 남은 M19 배정액 ≥ 1.5 × 그 셀의 예상 비용일 때만 시작합니다.
- 각 호출은 `bench plan` 상한 ≤ min($10 − 유료 누적 합계, 남은 키 잔액)일 때만 실행합니다.
- n은 셀마다 3을 밑돌지 않습니다. 과제 하나라도 n < 3이면 그 셀은 주장을 하지 않습니다.
- 측정하지 못한 셀은 "not measured (budget)"으로 보고합니다. 추정으로 채우지 않습니다.

### 중단 규칙

- (i) 402 또는 제공자 오류가 나면 호출을 멈추고, 다른 어떤 것을 실행하기 전에 원인을 찾습니다.
- (ii) 최선 구성이 class (c)이면 M19는 사용자 질문(G1 재정의)으로 끝납니다. 추가 튜닝은 하지 않습니다.
- (iii) class (b)이면 남은 예산과 비용을 함께 적어 집중 재측정 선택지를 나열합니다. 사용자가 재측정과 M20 중 하나를 고릅니다.
- (iv) 팔 a와 e 뒤(체크포인트 2)에도 m1 단독이 indeterminate이면 계속하기 전에 사용자에게 묻습니다 (R40).

### 수정 규칙

- 등록된 항목을 나중에 바꾸면 `## M19 사전 등록 수정 (<UTC>)`라는 새 날짜 절을 씁니다.
- 이 절은 제자리에서 고치지 않습니다.
- 2부는 별도의 `## M19 사전 등록 2부 (<UTC>)` 절입니다.
- 1부, 2부, 수정 절은 git 추적 사본 `tests/fixtures/m19/preregistration.md`에 같은 내용으로 함께 기록합니다(`.docs/`는 git에서 제외됨). 등록 증거는 그 파일의 커밋입니다.

## M19 사전 등록 2부 (2026-10-18T08:03:40Z)

이 절은 1부의 규칙을 바꾸지 않습니다. 1부가 정한 규칙을 적용할 숫자(강한 상한, 팔 설정 차이, 호출 목록, 예상 비용과 절단선)와 2026-10-18 사용자 결정을 고정합니다. 1부 절은 그대로 남습니다. 숫자의 원자료는 `.docs/bench-results.md`의 `## M19a 비용 계획`, `## M19a 탐침 (probe)`, `## M19a Q7 모델 목록 확인` 절입니다. 이 절은 `tests/fixtures/m19/preregistration.md`에 같은 내용으로 기록됩니다.

### 패널
| 역할 | id | 제공자 | 입력 $/1M | 출력 $/1M | 출처 (목록 · 확인 시각) |
|---|---|---|---|---|---|
| m1 | google/gemini-2.5-flash-lite | OpenRouter (엔드포인트 5) | 0.10 | 0.40 | https://openrouter.ai/api/v1/models · 2026-10-18T06:28:21Z |
| m2 | qwen/qwen3-coder-30b-a3b-instruct | OpenRouter (엔드포인트 2) | 0.07 | 0.28 | https://openrouter.ai/api/v1/models · 2026-10-18T06:28:21Z |
| m3 | mistralai/mistral-small-3.2-24b-instruct | OpenRouter (엔드포인트 4) | 0.09375 | 0.25 | https://openrouter.ai/api/v1/models · 2026-10-18T06:28:21Z |
| strong | deepseek/deepseek-v3.2 | OpenRouter (엔드포인트 12) | 0.28 | 0.42 | https://openrouter.ai/api/v1/models · 2026-10-18T06:28:21Z |

- 확정: m1 gemini-2.5-flash-lite, m2 qwen3-coder-30b (탐침 1 수용), m3 mistral-small-3.2 (탐침 2 수용, 사용자 요청으로 실행), 강한 모델 deepseek-v3.2. 탐침 기록은 `## M19a 탐침 (probe)`입니다. 캐시 읽기 가격은 deepseek 0.028입니다.
- 패널 id는 사용자 결정 7(2026-10-18)로 확정되었습니다. m3 셀(a(m3))은 실행 집합에 포함, 나머지 선택 셀(g)은 열린 질문입니다.

### 팔 설정 차이
- 모든 팔은 기본값(cora.toml shipped defaults, 도구 그룹 core, react)에서 시작합니다. 아래 diff에 없는 키는 cora.toml과 같습니다.
- 팔 a(m1, m2, m3)와 e는 설정 파일이 없습니다(a는 기본값, e는 `--models deepseek/deepseek-v3.2 --e2e-task-cost 0.30`). 팔 b는 `--verify-attempts 3` 플래그만 씁니다(`[agent] ladder = false` 유지, 1부 7항). 팔 d1은 `deleg-nudge`, 팔 c_s는 `cascade-strong`, 팔 c_cc는 `cascade-m1-m2`, 팔 g는 `keys-on`(g는 이번 실행 집합에 없음, 기록만).
- 각 설정은 `diff -u cora.toml <파일>` 출력입니다(파일 생성 때 캡처, `.cora/bench/m19/arm-diffs.txt`).

#### 설정 cascade-strong

```diff
--- cora.toml	2026-10-18 15:28:59
+++ .cora/bench/m19/cascade-strong.toml	2026-10-18 16:36:23
@@ -106,7 +106,7 @@
 threshold = 3            # heuristic score >= threshold -> complex
 medium_threshold = 1     # score >= medium_threshold -> medium, else simple
 escalate_on_retry = true
-mode = "heuristic"       # heuristic | cheap_first (start every run on cheap; strong only via [escalation])
+mode = "cheap_first"       # heuristic | cheap_first (start every run on cheap; strong only via [escalation])
 default = "cheap"        # fallback when classification fails (tier name or model id)
 
 [router.grades]          # grade -> tier name or a [[models]] id
@@ -133,7 +133,7 @@
 auto_check = false         # no --check given: use the workspace's own test command (pytest/npm/cargo/go/make)
 tamper_guard = false       # with a check: fail the gate (tests_modified) when pre-existing test files are edited or deleted
 selftest = false           # Python workspace, no check: model writes tests under .cora/selftest/; run as soft feedback only
-ladder = false             # with a check: sensor retries, then one reflection + one more check, then ladder_exhausted
+ladder = true              # with a check: sensor retries, then one reflection + one more check, then ladder_exhausted
 call_timeout_s = 300       # max wait per model call in seconds (10-3600), incl. stalled streams; one retry, then stop provider_timeout
 verify_before_final = true  # refuse the first Final Answer once when no check/run command succeeded after the last edit
 compile_check = true      # report Python syntax errors (file:line) after edits; refuse a Final Answer once while they remain
@@ -146,11 +146,11 @@
 located_errors = false    # Action Input JSON errors show decoder message, offset, excerpt; edit_file 'old' not found shows nearest line and column
 
 [escalation]             # failure-driven cheap->strong switch, at most once per run; OFF pending the M16 A/B
-enabled = false
+enabled = true
 on_stuck_iterations = 4  # consecutive iterations with no workspace write and no first-time file read (0 = off)
 on_tripwire = true       # the same-error tripwire escalates instead of stopping
-on_budget_fraction = 0   # escalate when this fraction of the run's cost cap is spent with no passing check (0 = off)
-strong_model = ""        # empty = the router's strong tier; else a [[models]] id
+on_budget_fraction = 0.5 # escalate when this fraction of the run's cost cap is spent with no passing check (0 = off)
+strong_model = "deepseek/deepseek-v3.2" # empty = the router's strong tier; else a [[models]] id
 
 [headless]              # cora run / cora -p --headless (unattended); cost and iterations follow [agent]
 max_wall_s = 900
```

#### 설정 cascade-m1-m2

```diff
--- cora.toml	2026-10-18 15:28:59
+++ .cora/bench/m19/cascade-m1-m2.toml	2026-10-18 16:36:23
@@ -106,7 +106,7 @@
 threshold = 3            # heuristic score >= threshold -> complex
 medium_threshold = 1     # score >= medium_threshold -> medium, else simple
 escalate_on_retry = true
-mode = "heuristic"       # heuristic | cheap_first (start every run on cheap; strong only via [escalation])
+mode = "cheap_first"       # heuristic | cheap_first (start every run on cheap; strong only via [escalation])
 default = "cheap"        # fallback when classification fails (tier name or model id)
 
 [router.grades]          # grade -> tier name or a [[models]] id
@@ -133,7 +133,7 @@
 auto_check = false         # no --check given: use the workspace's own test command (pytest/npm/cargo/go/make)
 tamper_guard = false       # with a check: fail the gate (tests_modified) when pre-existing test files are edited or deleted
 selftest = false           # Python workspace, no check: model writes tests under .cora/selftest/; run as soft feedback only
-ladder = false             # with a check: sensor retries, then one reflection + one more check, then ladder_exhausted
+ladder = true              # with a check: sensor retries, then one reflection + one more check, then ladder_exhausted
 call_timeout_s = 300       # max wait per model call in seconds (10-3600), incl. stalled streams; one retry, then stop provider_timeout
 verify_before_final = true  # refuse the first Final Answer once when no check/run command succeeded after the last edit
 compile_check = true      # report Python syntax errors (file:line) after edits; refuse a Final Answer once while they remain
@@ -146,11 +146,11 @@
 located_errors = false    # Action Input JSON errors show decoder message, offset, excerpt; edit_file 'old' not found shows nearest line and column
 
 [escalation]             # failure-driven cheap->strong switch, at most once per run; OFF pending the M16 A/B
-enabled = false
+enabled = true
 on_stuck_iterations = 4  # consecutive iterations with no workspace write and no first-time file read (0 = off)
 on_tripwire = true       # the same-error tripwire escalates instead of stopping
-on_budget_fraction = 0   # escalate when this fraction of the run's cost cap is spent with no passing check (0 = off)
-strong_model = ""        # empty = the router's strong tier; else a [[models]] id
+on_budget_fraction = 0.5 # escalate when this fraction of the run's cost cap is spent with no passing check (0 = off)
+strong_model = "qwen/qwen3-coder-30b-a3b-instruct" # empty = the router's strong tier; else a [[models]] id
 
 [headless]              # cora run / cora -p --headless (unattended); cost and iterations follow [agent]
 max_wall_s = 900
```

#### 설정 deleg-nudge

```diff
--- cora.toml	2026-10-18 15:28:59
+++ .cora/bench/m19/deleg-nudge.toml	2026-10-18 16:36:23
@@ -208,7 +208,7 @@
 max_total_tokens = 120000  # all sub-agents of a session (in+out); later delegate calls are refused
 max_total_cost_usd = 0.05  # all sub-agents of a session; later delegate calls are refused
 summary_max_chars = 1200   # cap on the summary a sub-agent returns
-nudge = false              # M19 re-test setting: true appends one sentence recommending delegate(mode="explore") to the main prompt when delegate is visible
+nudge = true               # M19 re-test setting: true appends one sentence recommending delegate(mode="explore") to the main prompt when delegate is visible
 
 [tools]                  # caps for @file mentions, git_* and web_fetch tools
 mention_max_file_chars = 8000    # per @file attachment (chars)
```

#### 설정 keys-on

```diff
--- cora.toml	2026-10-18 15:28:59
+++ .cora/bench/m19/keys-on.toml	2026-10-18 16:36:23
@@ -141,9 +141,9 @@
 stub_check = true         # refuse a Final Answer once while stub bodies or definitions removed by edits remain (file:line)
 json_string_repair = true # lenient parse: escape raw control characters and invalid backslashes inside Action Input JSON strings (parse_repaired json_strings)
 overwrite_guard = true    # refuse once per run a write_file that would replace an unread pre-existing Python file with non-stub code (overwrite_refused)
-raw_file_body = false     # write_file/edit_file also accept verbatim raw blocks (<<<CONTENT/<<<OLD/<<<NEW, no JSON escaping); hint shown only when true
-repeat_breaker = false    # same reply or same failure twice in a row: one feedback note; 3rd+ in a row: next call only at temperature 0.7 (repeat_detected)
-located_errors = false    # Action Input JSON errors show decoder message, offset, excerpt; edit_file 'old' not found shows nearest line and column
+raw_file_body = true      # write_file/edit_file also accept verbatim raw blocks (<<<CONTENT/<<<OLD/<<<NEW, no JSON escaping); hint shown only when true
+repeat_breaker = true     # same reply or same failure twice in a row: one feedback note; 3rd+ in a row: next call only at temperature 0.7 (repeat_detected)
+located_errors = true     # Action Input JSON errors show decoder message, offset, excerpt; edit_file 'old' not found shows nearest line and column
 
 [escalation]             # failure-driven cheap->strong switch, at most once per run; OFF pending the M16 A/B
 enabled = false
```

### 호출 목록
이 절은 확정 순서(member-first)의 실행 집합 51호출입니다. `bench plan` 명령과 plan TOTAL은 `## M19a 비용 계획` 4절의 같은 번호 호출에 있습니다. 모든 `--max-cost`는 기록 상한이며 $0.50 이하입니다. 호출은 번호 순서로 하나씩 실행하고, 호출 전에 `/credits`를 기록합니다. 건너뛴 셀(b(m1), c_cc(m1→m2), b(m2), g(m2))은 이 목록에 없습니다. 측정하지 못한 셀은 1부 11항에 따라 "not measured (budget)"로 보고하며, 추정값으로 채우지 않습니다.

| 호출 | 셀 | 과제 | repeats | --max-cost (기록 상한) | plan TOTAL | 라이브 명령 |
|---|---|---|---|---|---|---|
| M19-01 | a(m1) | e2e_h01,e2e_h02 | 3 | 0.42 | 0.330864 | `uv run cora bench --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --tasks e2e_h01,e2e_h02 --repeats 3 --max-cost 0.42 --out .cora/bench/m19/runs/a-m1-i01` |
| M19-02 | a(m1) | e2e_h03 | 3 | 0.36 | 0.180864 | `uv run cora bench --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --tasks e2e_h03 --repeats 3 --max-cost 0.36 --out .cora/bench/m19/runs/a-m1-i02` |
| M19-03 | a(m1) | e2e_h04,e2e_h05 | 3 | 0.45 | 0.330864 | `uv run cora bench --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --tasks e2e_h04,e2e_h05 --repeats 3 --max-cost 0.45 --out .cora/bench/m19/runs/a-m1-i03` |
| M19-04 | a(m1) | e2e_h06,e2e_hx1 | 3 | 0.42 | 0.300720 | `uv run cora bench --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --tasks e2e_h06,e2e_hx1 --repeats 3 --max-cost 0.42 --out .cora/bench/m19/runs/a-m1-i04` |
| M19-05 | a(m1) | e2e_hx2 | 3 | 0.24 | 0.180864 | `uv run cora bench --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --tasks e2e_hx2 --repeats 3 --max-cost 0.24 --out .cora/bench/m19/runs/a-m1-i05` |
| M19-06 | a(m2) | e2e_h01,e2e_h02 | 3 | 0.42 | 0.232109 | `uv run cora bench --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_h01,e2e_h02 --repeats 3 --max-cost 0.42 --out .cora/bench/m19/runs/a-m2-i01` |
| M19-07 | a(m2) | e2e_h03 | 3 | 0.36 | 0.126605 | `uv run cora bench --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_h03 --repeats 3 --max-cost 0.36 --out .cora/bench/m19/runs/a-m2-i02` |
| M19-08 | a(m2) | e2e_h04,e2e_h05 | 3 | 0.45 | 0.253210 | `uv run cora bench --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_h04,e2e_h05 --repeats 3 --max-cost 0.45 --out .cora/bench/m19/runs/a-m2-i03` |
| M19-09 | a(m2) | e2e_h06,e2e_hx1 | 3 | 0.42 | 0.232109 | `uv run cora bench --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_h06,e2e_hx1 --repeats 3 --max-cost 0.42 --out .cora/bench/m19/runs/a-m2-i04` |
| M19-10 | a(m2) | e2e_hx2 | 3 | 0.24 | 0.126605 | `uv run cora bench --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_hx2 --repeats 3 --max-cost 0.24 --out .cora/bench/m19/runs/a-m2-i05` |
| M19-11 | e | e2e_h01 | 1 | 0.30 | 0.147302 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h01 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i01` |
| M19-12 | e | e2e_h01 | 1 | 0.30 | 0.147302 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h01 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i02` |
| M19-13 | e | e2e_h01 | 1 | 0.30 | 0.147302 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h01 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i03` |
| M19-14 | e | e2e_h02 | 1 | 0.30 | 0.122752 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h02 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i04` |
| M19-15 | e | e2e_h02 | 1 | 0.30 | 0.122752 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h02 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i05` |
| M19-16 | e | e2e_h02 | 1 | 0.30 | 0.122752 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h02 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i06` |
| M19-17 | e | e2e_h03 | 1 | 0.30 | 0.147302 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h03 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i07` |
| M19-18 | e | e2e_h03 | 1 | 0.30 | 0.147302 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h03 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i08` |
| M19-19 | e | e2e_h03 | 1 | 0.30 | 0.147302 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h03 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i09` |
| M19-20 | e | e2e_h04 | 1 | 0.30 | 0.147302 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h04 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i10` |
| M19-21 | e | e2e_h04 | 1 | 0.30 | 0.147302 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h04 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i11` |
| M19-22 | e | e2e_h04 | 1 | 0.30 | 0.147302 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h04 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i12` |
| M19-23 | e | e2e_h05 | 1 | 0.30 | 0.147302 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h05 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i13` |
| M19-24 | e | e2e_h05 | 1 | 0.30 | 0.147302 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h05 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i14` |
| M19-25 | e | e2e_h05 | 1 | 0.30 | 0.147302 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h05 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i15` |
| M19-26 | e | e2e_h06 | 1 | 0.30 | 0.122752 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h06 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i16` |
| M19-27 | e | e2e_h06 | 1 | 0.30 | 0.122752 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h06 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i17` |
| M19-28 | e | e2e_h06 | 1 | 0.30 | 0.122752 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h06 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i18` |
| M19-29 | e | e2e_hx1 | 1 | 0.30 | 0.147302 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_hx1 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i19` |
| M19-30 | e | e2e_hx1 | 1 | 0.30 | 0.147302 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_hx1 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i20` |
| M19-31 | e | e2e_hx1 | 1 | 0.30 | 0.147302 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_hx1 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i21` |
| M19-32 | e | e2e_hx2 | 1 | 0.30 | 0.147302 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_hx2 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i22` |
| M19-33 | e | e2e_hx2 | 1 | 0.30 | 0.147302 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_hx2 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i23` |
| M19-34 | e | e2e_hx2 | 1 | 0.30 | 0.147302 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_hx2 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i24` |
| M19-35 | c_s(m1) | e2e_h01,e2e_h02 | 3 | 0.42 | 0.420000 | `uv run cora bench -c .cora/bench/m19/cascade-strong.toml --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h01,e2e_h02 --repeats 3 --max-cost 0.42 --out .cora/bench/m19/runs/c_s-m1-i01` |
| M19-36 | c_s(m1) | e2e_h03 | 3 | 0.36 | 0.360000 | `uv run cora bench -c .cora/bench/m19/cascade-strong.toml --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h03 --repeats 3 --max-cost 0.36 --out .cora/bench/m19/runs/c_s-m1-i02` |
| M19-37 | c_s(m1) | e2e_h04,e2e_h05 | 3 | 0.45 | 0.450000 | `uv run cora bench -c .cora/bench/m19/cascade-strong.toml --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h04,e2e_h05 --repeats 3 --max-cost 0.45 --out .cora/bench/m19/runs/c_s-m1-i03` |
| M19-38 | c_s(m1) | e2e_h06 | 3 | 0.27 | 0.270000 | `uv run cora bench -c .cora/bench/m19/cascade-strong.toml --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h06 --repeats 3 --max-cost 0.27 --out .cora/bench/m19/runs/c_s-m1-i04` |
| M19-39 | c_s(m1) | e2e_hx2 | 3 | 0.24 | 0.240000 | `uv run cora bench -c .cora/bench/m19/cascade-strong.toml --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_hx2 --repeats 3 --max-cost 0.24 --out .cora/bench/m19/runs/c_s-m1-i05` |
| M19-40 | d1(m1) | e2e_hx1,e2e_hx2 | 3 | 0.39 | 0.390000 | `uv run cora bench -c .cora/bench/m19/deleg-nudge.toml --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab deleg-on-par-on --tasks e2e_hx1,e2e_hx2 --repeats 3 --max-cost 0.39 --out .cora/bench/m19/runs/d1-m1-i01` |
| M19-41 | c_s(m2) | e2e_h01,e2e_h02 | 3 | 0.42 | 0.420000 | `uv run cora bench -c .cora/bench/m19/cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h01,e2e_h02 --repeats 3 --max-cost 0.42 --out .cora/bench/m19/runs/c_s-m2-i01` |
| M19-42 | c_s(m2) | e2e_h03 | 3 | 0.36 | 0.360000 | `uv run cora bench -c .cora/bench/m19/cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h03 --repeats 3 --max-cost 0.36 --out .cora/bench/m19/runs/c_s-m2-i02` |
| M19-43 | c_s(m2) | e2e_h04,e2e_h05 | 3 | 0.45 | 0.450000 | `uv run cora bench -c .cora/bench/m19/cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h04,e2e_h05 --repeats 3 --max-cost 0.45 --out .cora/bench/m19/runs/c_s-m2-i03` |
| M19-44 | c_s(m2) | e2e_h06 | 3 | 0.27 | 0.270000 | `uv run cora bench -c .cora/bench/m19/cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h06 --repeats 3 --max-cost 0.27 --out .cora/bench/m19/runs/c_s-m2-i04` |
| M19-45 | c_s(m2) | e2e_hx2 | 3 | 0.24 | 0.240000 | `uv run cora bench -c .cora/bench/m19/cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_hx2 --repeats 3 --max-cost 0.24 --out .cora/bench/m19/runs/c_s-m2-i05` |
| M19-46 | d1(m2) | e2e_hx1,e2e_hx2 | 3 | 0.39 | 0.390000 | `uv run cora bench -c .cora/bench/m19/deleg-nudge.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab deleg-on-par-on --tasks e2e_hx1,e2e_hx2 --repeats 3 --max-cost 0.39 --out .cora/bench/m19/runs/d1-m2-i01` |
| M19-47 | a(m3) | e2e_h01,e2e_h02 | 3 | 0.42 | 0.289740 | `uv run cora bench --live --suite e2e --models mistralai/mistral-small-3.2-24b-instruct --protocols react --tasks e2e_h01,e2e_h02 --repeats 3 --max-cost 0.42 --out .cora/bench/m19/runs/a-m3-i01` |
| M19-48 | a(m3) | e2e_h03 | 3 | 0.36 | 0.158040 | `uv run cora bench --live --suite e2e --models mistralai/mistral-small-3.2-24b-instruct --protocols react --tasks e2e_h03 --repeats 3 --max-cost 0.36 --out .cora/bench/m19/runs/a-m3-i02` |
| M19-49 | a(m3) | e2e_h04,e2e_h05 | 3 | 0.45 | 0.308040 | `uv run cora bench --live --suite e2e --models mistralai/mistral-small-3.2-24b-instruct --protocols react --tasks e2e_h04,e2e_h05 --repeats 3 --max-cost 0.45 --out .cora/bench/m19/runs/a-m3-i03` |
| M19-50 | a(m3) | e2e_h06,e2e_hx1 | 3 | 0.42 | 0.281700 | `uv run cora bench --live --suite e2e --models mistralai/mistral-small-3.2-24b-instruct --protocols react --tasks e2e_h06,e2e_hx1 --repeats 3 --max-cost 0.42 --out .cora/bench/m19/runs/a-m3-i04` |
| M19-51 | a(m3) | e2e_hx2 | 3 | 0.24 | 0.158040 | `uv run cora bench --live --suite e2e --models mistralai/mistral-small-3.2-24b-instruct --protocols react --tasks e2e_hx2 --repeats 3 --max-cost 0.24 --out .cora/bench/m19/runs/a-m3-i05` |

### 예상 비용과 절단선
- 강한 상한 S = **$0.30**(ceil_cent(3 × 0.0973175)). 팔 e 예상 비용 = 보정 × 1.5 = **$2.16**(2.1551). 두 값은 이 절에서 고정됩니다.
- 확정 순서(member-first)의 표:

| 순서 | 셀 | runs | 예상 $ | 누적 $ | 예상 $ (e = 상한) | 누적 $ (e = 상한) | 1.5× 판정 (예상 열 / 상한 열) |
|---|---|---|---|---|---|---|---|
| 1 | a(m1) | 24 | 0.8506 | 0.8506 | 0.8506 | 0.8506 | 실행 / 실행 |
| 2 | a(m2) | 24 | 0.4424 | 1.2930 | 0.4424 | 1.2930 | 실행 / 실행 |
| 3 | e | 24 | 2.1551 | 3.4481 | 7.2000 | 8.4930 | 실행 / 건너뜀 |
| 4 | c_s(m1) | 21 | 1.1974 | 4.6455 | 1.1974 | 9.6904 | 실행 / 실행 |
| 5 | b(m1) | 21 | 1.1974 | 5.8429 | 1.1974 | 10.8878 | 건너뜀 / 실행 |
| 6 | d1(m1) | 6 | 0.2365 | 6.0794 | 0.2365 | 11.1243 | 실행 / 실행 |
| 7 | c_cc(m1→m2) | 21 | 1.1974 | 7.2768 | 1.1974 | 12.3217 | 건너뜀 / 실행 |
| 8 | c_s(m2) | 21 | 0.6228 | 7.8996 | 0.6228 | 12.9445 | 실행 / 건너뜀 |
| 9 | b(m2) | 21 | 0.6228 | 8.5224 | 0.6228 | 13.5673 | 건너뜀 / 건너뜀 |
| 10 | d1(m2) | 6 | 0.1230 | 8.6454 | 0.1230 | 13.6903 | 실행 / 실행 |
| 11 | a(m3) | 24 | 0.1021 | 8.7475 | 0.1021 | 13.7924 | 실행 / 실행 |
| 12 | g(m2) | 18 | 0.3604 | 9.1079 | 0.3604 | 14.1528 | 건너뜀 / 실행 |

- 확정 순서의 누적 절단선(예상 열): d1(m1) 행(누적 6.0794 > $6.00). 1.5× 셀 규칙 결과 실행 집합 = a(m1), a(m2), e, c_s(m1), d1(m1), c_s(m2), d1(m2), a(m3); 건너뜀 = b(m1), c_cc(m1→m2), b(m2), g(m2). 실행 집합의 예상 합 5.7299, 남는 액 0.2701.
- 상한 열(e = 24 × S = 7.20)은 채택하지 않습니다(결정 3). 이 열로 보면 e가 건너뛰어집니다.
- 강한 상한 S = $0.30(고정). 팔 e의 예상 비용 = $2.16(보정 × 1.5, 고정).
- 자세한 계산과 호출 목록은 `## M19a 비용 계획 (2026-10-18T07:40:31Z)` 절에 있습니다.
- 계산 근거와 상한 열, 벽시계 일정은 `## M19a 비용 계획` 절에 있습니다.

### Claude Code 일정
- R17 일정: 사용자 답 없음. 열린 질문: 실행 횟수(n, 최대 3), 날짜, 실행자(사용자 또는 집행자), 구독 한도에 맞춘 시각. 비용은 $0입니다(구독).
- 기준선 파일 `.docs/baselines/claude-code-m19.toml`은 아직 없습니다. 팔 f 실행 뒤에 `.docs/baseline-protocol.md`에 따라 만듭니다. M19의 S_cc와 비용 우위 판정은 이 파일이 있어야 계산할 수 있습니다.
- 상태: 차단됨(사용자 일정 답 없음).

### 사용자 확인 기록
| 항목 (R18) | 날짜 | 답 | 상태 |
|---|---|---|---|
| 패널 id (m1, m2, m3, 강한 모델) | 2026-10-18 | m1 gemini-2.5-flash-lite, m2 qwen3-coder-30b, m3 mistral-small-3.2, 강한 모델 deepseek-v3.2 (결정 7) | 확정 |
| 계속 또는 중단 | 2026-10-18 | 계속 (O4 결정 기록으로 진행) | 확정 |
| 셀 순서 | 2026-10-18 | member-first (결정 2) | 확정 |
| 같은 한도 해석 (Q-O4-3, R37) | 2026-10-18 | 계획 제안 적용: 역할별 상한 (사용자 명시 답 없음) | 기본값 |
| `--max-cost` > 0.30 | 2026-10-18 | 허용, 최대 $0.50 (결정 4) | 확정 |
| 부족분 처리 | 2026-10-18 | M19 $6.00 (결정 1), M20 나중에 재결정. 예비 $0.76 부족 1.63 (키 기준) | 열린 질문 (예비) |
| 선택 셀 a(m3) | 2026-10-18 | 포함 (결정 7) | 확정 |
| 선택 셀 g(m2) | — | 답 없음 | 열린 질문 |
| 팔 e 예상 열 | 2026-10-18 | 보정 × 1.5 = $2.16, 누적 e 지출 점검, $2.16 초과 시 e 중단 (결정 3; 이 문구의 해석) | 확정 (해석 확인 요청) |
| 벽시계 만료 플래그 | 2026-10-18 | 만료 셀은 그 시점에 재결정 (결정 6) | 확정 (재결정 시점) |
| Claude Code 일정 | — | 답 없음 | 열린 질문 |
| R16 일괄 확인 목록 | — | 답 없음 (이 절이 확인 대상 목록) | 열린 질문 |
| d2 재사용 (Q-O4-8) | 2026-10-18 | 계획 제안 (재사용 설정 일치 확인 뒤, 아니면 deleg-off); 실행 집합 밖 | 기본값 |
| "$1.00 project-wide" 문구 (Q-O4-9) | — | 마일스톤 종료 때 사용자와 확인 | 열린 질문 |
| `/credits` O4 재판독, 키 한도 0.80 차이 | — | 기록 없음 | 열린 질문 |
| `.ensemble/roadmap.md` M19 행 $5.00 | — | 이 절은 고치지 않음 (사용자 결정 1로 $6.00) | 열린 질문 |

- 열린 질문(답이 없어 가정하지 않은 항목): Claude Code 일정, R16 일괄 확인, 선택 셀 g(m2), 예비 $0.76 부족분, 키 한도와 `/credits` 차이, `/credits` O4 재판독, 로드맵 M19 $5.00 문구, Q-O4-9 "$1.00 project-wide" 문구.

### M19 유료 호출 목록 (R19 일괄 확인용)
- 대상: 실행 집합 51호출(위 호출 목록과 같은 번호). 총 상한 = M19 배정 **$6.00**. 기대 지출 5.7299. 호출별 상한과 누적 기록 상한(최악값) 표:

| 호출 | 셀 | 과제 | repeats | 호출 상한 (--max-cost) | 누적 기록 상한 |
|---|---|---|---|---|---|
| M19-01 | a(m1) | e2e_h01,e2e_h02 | 3 | 0.42 | 0.42 |
| M19-02 | a(m1) | e2e_h03 | 3 | 0.36 | 0.78 |
| M19-03 | a(m1) | e2e_h04,e2e_h05 | 3 | 0.45 | 1.23 |
| M19-04 | a(m1) | e2e_h06,e2e_hx1 | 3 | 0.42 | 1.65 |
| M19-05 | a(m1) | e2e_hx2 | 3 | 0.24 | 1.89 |
| M19-06 | a(m2) | e2e_h01,e2e_h02 | 3 | 0.42 | 2.31 |
| M19-07 | a(m2) | e2e_h03 | 3 | 0.36 | 2.67 |
| M19-08 | a(m2) | e2e_h04,e2e_h05 | 3 | 0.45 | 3.12 |
| M19-09 | a(m2) | e2e_h06,e2e_hx1 | 3 | 0.42 | 3.54 |
| M19-10 | a(m2) | e2e_hx2 | 3 | 0.24 | 3.78 |
| M19-11 | e | e2e_h01 | 1 | 0.30 | 4.08 |
| M19-12 | e | e2e_h01 | 1 | 0.30 | 4.38 |
| M19-13 | e | e2e_h01 | 1 | 0.30 | 4.68 |
| M19-14 | e | e2e_h02 | 1 | 0.30 | 4.98 |
| M19-15 | e | e2e_h02 | 1 | 0.30 | 5.28 |
| M19-16 | e | e2e_h02 | 1 | 0.30 | 5.58 |
| M19-17 | e | e2e_h03 | 1 | 0.30 | 5.88 |
| M19-18 | e | e2e_h03 | 1 | 0.30 | 6.18 |
| M19-19 | e | e2e_h03 | 1 | 0.30 | 6.48 |
| M19-20 | e | e2e_h04 | 1 | 0.30 | 6.78 |
| M19-21 | e | e2e_h04 | 1 | 0.30 | 7.08 |
| M19-22 | e | e2e_h04 | 1 | 0.30 | 7.38 |
| M19-23 | e | e2e_h05 | 1 | 0.30 | 7.68 |
| M19-24 | e | e2e_h05 | 1 | 0.30 | 7.98 |
| M19-25 | e | e2e_h05 | 1 | 0.30 | 8.28 |
| M19-26 | e | e2e_h06 | 1 | 0.30 | 8.58 |
| M19-27 | e | e2e_h06 | 1 | 0.30 | 8.88 |
| M19-28 | e | e2e_h06 | 1 | 0.30 | 9.18 |
| M19-29 | e | e2e_hx1 | 1 | 0.30 | 9.48 |
| M19-30 | e | e2e_hx1 | 1 | 0.30 | 9.78 |
| M19-31 | e | e2e_hx1 | 1 | 0.30 | 10.08 |
| M19-32 | e | e2e_hx2 | 1 | 0.30 | 10.38 |
| M19-33 | e | e2e_hx2 | 1 | 0.30 | 10.68 |
| M19-34 | e | e2e_hx2 | 1 | 0.30 | 10.98 |
| M19-35 | c_s(m1) | e2e_h01,e2e_h02 | 3 | 0.42 | 11.40 |
| M19-36 | c_s(m1) | e2e_h03 | 3 | 0.36 | 11.76 |
| M19-37 | c_s(m1) | e2e_h04,e2e_h05 | 3 | 0.45 | 12.21 |
| M19-38 | c_s(m1) | e2e_h06 | 3 | 0.27 | 12.48 |
| M19-39 | c_s(m1) | e2e_hx2 | 3 | 0.24 | 12.72 |
| M19-40 | d1(m1) | e2e_hx1,e2e_hx2 | 3 | 0.39 | 13.11 |
| M19-41 | c_s(m2) | e2e_h01,e2e_h02 | 3 | 0.42 | 13.53 |
| M19-42 | c_s(m2) | e2e_h03 | 3 | 0.36 | 13.89 |
| M19-43 | c_s(m2) | e2e_h04,e2e_h05 | 3 | 0.45 | 14.34 |
| M19-44 | c_s(m2) | e2e_h06 | 3 | 0.27 | 14.61 |
| M19-45 | c_s(m2) | e2e_hx2 | 3 | 0.24 | 14.85 |
| M19-46 | d1(m2) | e2e_hx1,e2e_hx2 | 3 | 0.39 | 15.24 |
| M19-47 | a(m3) | e2e_h01,e2e_h02 | 3 | 0.42 | 15.66 |
| M19-48 | a(m3) | e2e_h03 | 3 | 0.36 | 16.02 |
| M19-49 | a(m3) | e2e_h04,e2e_h05 | 3 | 0.45 | 16.47 |
| M19-50 | a(m3) | e2e_h06,e2e_hx1 | 3 | 0.42 | 16.89 |
| M19-51 | a(m3) | e2e_hx2 | 3 | 0.24 | 17.13 |

- 일괄 확인 대상: 이 51호출과 위 상한. 확인 전에는 유료 호출을 하지 않습니다(R16). 확인 답은 열린 질문입니다.
- 402 또는 공급자 오류: 그 호출을 멈추고 원인을 먼저 찾습니다. 맹목적 재시도를 하지 않습니다. 402는 키 한도 소진 가능성으로 보고 `/auth/key`와 `/credits`를 다시 읽습니다.
- 지출 감시: 호출 전후 `/credits`를 기록합니다. 실측 M19 누적 지출과 $6.00 배정, 그리고 $10 − 유료 누적(약 6.94)을 비교합니다. 호출 전 점검은 기록 상한 ≤ min($10 − 유료 누적, 키 한도 잔액 6.1457)이고, 실측 M19 누적 지출이 $6.00 미만이어야 합니다.
- 팔 e: 누적 실측 e 지출이 $2.16을 넘으면 e의 남은 호출을 멈추고 "측정 안 함(예산)"으로 보고합니다(결정 3 문구의 해석, 확인 요청).
- 체크포인트 1: M19a에서 완료(`## M19a 탐침 (probe)`, 사용자 결정 1–7).
- 체크포인트 2: 셀 a(m1), a(m2), e가 끝난 직후(호출 M19-01 … M19-34 뒤). m1만으로 판정이 indeterminate면 사용자에게 묻고 진행합니다(1부 12항 iv).
- 즉시 보고: 402, 공급자 오류, 편향 신호, 예산 초과 위험은 그 자리에서 보고합니다(결정 5).

### M19a 종료 기준
| 종료 기준 (roadmap M19a, 1)–(5) | 상태 | 근거 |
|---|---|---|
| (1) 1부 사전 등록 커밋 (FIRST, $0) | done | `## M19 사전 등록 (2026-10-18T06:16:09Z)`, 커밋 68afa71 (`docs: M19 pre-registration part 1 (M19a)`) |
| (2) Q7 확인과 가격 갱신, 두 toml 동일 | done | `## M19a Q7 모델 목록 확인 (2026-10-18T06:28:21Z)`, 커밋 ba70e38 (`chore(config): refresh panel prices from OpenRouter listing (M19a)`) |
| (3) 유료 탐침 (상한 $0.20 이하), 패널 확인 | done | `## M19a 탐침 (probe) (2026-10-18T06:47:49Z)`: qwen 수용, mistral 수용, 누적 약 $0.016 (≤ $0.20), 패널 확정 (결정 7) |
| (4) 비용 계획, 절단선 (배정 $6.00 기준), 2부 커밋 (첫 M19 유료 호출 전) | done | `## M19a 비용 계획 (2026-10-18T07:40:31Z)`(갱신), `## M19 사전 등록 2부 ({TS})`. 2부 커밋 해시는 O-E 단계에서 기록 |
| (5) Claude Code 기준선 일정, 사용자 합의 | blocked | 누락 자원: 사용자 일정 답 (n, 날짜, 실행자)과 `.docs/baselines/claude-code-m19.toml`(팔 f 실행 뒤 생성) |

## M19 사전 등록 수정 (2026-10-18T08:22:23Z)

이 절은 2부(`## M19 사전 등록 2부 (2026-10-18T08:03:40Z)`)의 기록을 바로잡습니다. 1부와 2부 본문은 바꾸지 않습니다(덧붙이기 전용). 2부 커밋은 `55496cf`(`docs: M19 pre-registration part 2 and cost plan (M19a)`)입니다. 이 절의 사용자 답은 `.ensemble/milestones/M19a/iterations.md`의 결정과 같습니다.

### 정정 1: Claude Code 일정 (2부 `### Claude Code 일정`)
- 2부의 "사용자 답 없음 ... 상태: 차단됨"은 틀렸습니다. 사용자 결정 R17 (2026-10-18): Claude Code 기준선은 n = 3, hard set (e2e_h01–h06, e2e_hx1, e2e_hx2)에서 실행합니다.
- 실행자: 오케스트레이터가 M19 중에 실행합니다.
- 격리: 과제 템플릿의 새 작업 복사본과 REQUIREMENTS.md만 씁니다. 별도 프로세스에서 실행하며, `.ensemble/`, `.docs/`, 참조 해답, 채점기, 숨은 검사, 보정 결과, 이전 결과에 접근하지 않습니다.
- 비용: $0 (구독 한도 사용). 구독 한도가 요구할 때만 n을 줄이고, 줄인 n과 이유를 기록합니다.
- 기준선 파일 `.docs/baselines/claude-code-m19.toml`은 팔 f를 실행한 뒤 `.docs/baseline-protocol.md`에 따라 만듭니다.
- 아직 정하지 않은 것: 달력 시각. 구독 한도에 따라 팔 f 실행 때 정하고 기록합니다(열린 항목).

### 정정 2: 사용자 확인 기록 (2부 `### 사용자 확인 기록`을 갱신)

| 항목 | 날짜 | 답 | 상태 |
|---|---|---|---|
| 패널 id (m1, m2, m3, 강한 모델) | 2026-10-18 | m1 gemini-2.5-flash-lite, m2 qwen3-coder-30b, m3 mistral-small-3.2, 강한 모델 deepseek-v3.2 (결정 7) | 확정 |
| 탐침 1 승인 (qwen, 1회, --max-cost 0.10) | 2026-10-18 | 질문 "유료 프로브 1회를 실행해도 될까요? 모델 qwen/qwen3-coder-30b-a3b-instruct, 과제 e2e_h05, 1회, --max-cost 0.10. bench plan 상한은 $0.042입니다..."에 대한 답 "실행 (Recommended)" | 확정 |
| 탐침 2 (mistral, m3) | 2026-10-18 | "m3 넣으세요" (m3 = mistral-small-3.2, 세 번째 저가 멤버, 탐침 약 $0.01–0.05, 누적 $0.20 한도 안, 설명 뒤 답) | 확정 |
| Claude Code 일정 (R17) | 2026-10-18 | n = 3, 오케스트레이터 실행, 격리 (정정 1) | 확정 (달력 시각은 열린 항목) |
| 계속 또는 중단 | 2026-10-18 | 계속 (O4 결정 기록으로 진행) | 확정 |
| 셀 순서 | 2026-10-18 | member-first (결정 2) | 확정 |
| M19 배정 | 2026-10-18 | $6.00 (결정 1) | 확정 |
| `--max-cost` 상한 | 2026-10-18 | 허용, 최대 $0.50 (결정 4) | 확정 |
| 부족분 처리 | 2026-10-18 | M19 $6.00. M20은 잔액이 부족할 때 나중에 다시 정함 (결정 1). 예비 $0.76 미확보는 열린 질문 | 확정 (예비는 열린 질문) |
| 셀 건너뛰기 규칙 | 2026-10-18 | 셀 단위, 1.5× 시작 규칙 (결정 5) | 확정 |
| 선택 셀 a(m3) | 2026-10-18 | 포함 (결정 7) | 확정 |
| 팔 e 예상 열 | 2026-10-18 | 보정 × 1.5 = $2.16, 누적 e 지출 점검, $2.16 초과 시 e 중단 (결정 3) | 확정 (중단 문구의 해석 확인 필요) |
| 벽시계 만료 플래그 | 2026-10-18 | 만료 셀은 그 시점에 다시 결정 (결정 6) | 확정 (재결정 시점) |
| 같은 한도 해석 (Q-O4-3, R37) | — | 계획 제안(역할별 상한)을 적용했으나 사용자 명시 답은 없음 | 열린 질문 |
| 선택 셀 g(m2) | — | 답 없음, 실행 집합 밖 | 열린 질문 |
| 예비 $0.76 부족분 | — | 답 없음 | 열린 질문 |
| R16 일괄 확인 (M19 유료 호출 목록) | — | 답 없음. 확인 전에는 유료 호출을 하지 않음 | 열린 질문 |
| `/credits` O4 재판독, 키 한도와 계정 잔액의 0.80 차이 | — | 이 수정 시점에는 키를 읽는 GET을 하지 않았음. 마지막 판독은 `## M19a 비용 계획` 1절 | 열린 질문 |
| 로드맵 M19 $5.00 문구 | — | `.ensemble/roadmap.md` M19 행은 이미 $6.00 ("Change 2026-10-18b") | 해결 |
| Q-O4-9 "$1.00 project-wide" 문구 | — | 문구 제거는 `b76503e` (`fix(bench): drop the stale $1.00 budget text from bench plan (M19a)`)에서 완료. 마일스톤 종료 때 사용자 확인 | 열린 질문 (확인만 남음) |

### 정정 3: M19a 종료 기준 (2부 `### M19a 종료 기준`을 갱신)

| 종료 기준 (roadmap M19a) | 상태 | 근거 |
|---|---|---|
| (1) 1부 사전 등록 커밋 | done | `## M19 사전 등록 (2026-10-18T06:16:09Z)`, 커밋 68afa71 |
| (2) Q7 확인과 가격 갱신, 두 toml 동일 | done | `## M19a Q7 모델 목록 확인 (2026-10-18T06:28:21Z)`, 커밋 ba70e38 |
| (3) 유료 탐침 (상한 $0.20 이하), 패널 확인 | done | `## M19a 탐침 (probe) (2026-10-18T06:47:49Z)`, 누적 $0.015718 (/credits 차이, 보고서 cost 합과 일치), 패널 확정 (정정 2) |
| (4) 비용 계획, 절단선 (배정 $6.00), 2부 커밋 (첫 M19 유료 호출 전) | done | `## M19a 비용 계획 (2026-10-18T07:40:31Z)` (3a member-first 표, 3b arm-first 절단 목록), `## M19 사전 등록 2부 (2026-10-18T08:03:40Z)`, 커밋 55496cf |
| (5) Claude Code 기준선 일정, 사용자 합의 | done | 정정 1 (R17, 2026-10-18). 기준선 파일 `.docs/baselines/claude-code-m19.toml`은 M19 팔 f 실행 뒤 생성 (M19a 종료 조건 아님) |

### 정정 4: 자리표시자 `{TS}`
- 2부 `### M19a 종료 기준` (4)행의 `{TS}`는 2부 절 제목의 시각 2026-10-18T08:03:40Z입니다. 2부 커밋 해시는 `55496cf`입니다. 등록 원문의 `{TS}` 글자는 덧붙이기 전용 규칙 때문에 고치지 않고, 이 정정으로 대체합니다.
- 로드맵(`.ensemble/roadmap.md`)과 청사진(`.ensemble/blueprint.md`)에는 `{TS}` 자리표시자가 없습니다.

### 정정 5: 엄격 arm-first 절단 목록 (R13)
- 위치: `.docs/bench-results.md`의 `## M19a 비용 계획 (2026-10-18T07:40:31Z)` 3b절(표와 절단 목록).
- 누적 절단선(순수 누적 열): c_s(m2) 행이 처음으로 $6.00을 넘습니다(누적 6.5678). 이 행과 그 아래 b(m1), b(m2), d1(m1), d1(m2)가 절단 목록입니다.
- 1.5× 시작 규칙(결정 5)을 적용하면 건너뜀은 c_cc(m1→m2), b(m1), b(m2)이고, 실행 집합은 member-first와 같은 8개 셀, 51호출입니다. 예상 합 5.7299, 남는 액 0.2701.
- 팔 e의 상한 열(e = 24 × S = 7.20)은 결정 3에 따라 채택하지 않습니다. 이 열로 보면 누적 절단선은 e 행(누적 8.5951)입니다.
- 3b절의 이전 문장("누적 6.4656")은 a(m3)를 빼고 계산한 값이었습니다. 3b절 표에서 바로잡았습니다.

## M19 사전 등록 수정 (2026-10-20T07:18:53Z)

이 절은 사용자 결정 시나리오 A (2026-10-20)에 따라 요청 시간 제한을 고치고, 오류로 끝난 시간 초과 실행을 한 번씩 재실행하며, 분석 규칙을 정합니다. 1부와 2부 본문은 바꾸지 않습니다 (덧붙이기 전용 규칙). 이 절은 첫 재실행과 M19-29보다 먼저 커밋됩니다.

### 정정 6: 원인 (요청 시간 제한)
- 처리량 (출력 300 토큰 초과 호출, 출력 토큰/s): gemini-2.5-flash-lite p50 약 385; qwen3-coder-30b p50 약 31 (p10 21); deepseek-v3.2 p50 약 27 (p10 19). `react_max_tokens = 4096`이면 전체 길이 응답은 느린 모델에서 약 130–210 s 걸립니다.
- 90 s 초과 호출: qwen 384건 중 18건; deepseek 약 330건 중 3건; gemini 542건 중 0건 (최대 13 s). 성공한 가장 긴 호출은 264 s (재시도 뒤).
- 시간 제한 연쇄: 시도당 `request_deadline_s` (D = 90), 시도 3회 (대기 1 s, 2 s): 공급자는 최대 3 × 90 + 3 = 273 s 뒤에 `ProviderError(RequestDeadlineExceeded)`로 끝납니다. `[agent].call_timeout_s` (T = 300)는 273 < 300이라 그 전에 끝나야 하지만, a-m2-i03의 `call_latencies_s`에 273.019 s 항목이 있습니다.
- 효과 1 (계량): 시간 초과된 시도도 공급자가 과금하지만 그 비용은 기록되지 않습니다. 지속 불일치 8건 중 7건에서 과금액이 보고서 비용보다 높습니다: M19-07, 08, 09, 10, 17, 21, 26. M19-28의 불일치 (과금이 보고서보다 7.8% 낮음)는 이 원인과 무관합니다.
- 효과 2 (검열): 모든 시도가 시간 초과되면 실행은 `error`로 끝납니다 (`ProviderError: ... RequestDeadlineExceeded`). 지금까지 오류 실행 5건:
  - M19-08 (qwen, 출력 `.cora/bench/m19/runs/a-m2-i03`): e2e_h04 r0, e2e_h05 r2
  - M19-09 (qwen, 출력 `.cora/bench/m19/runs/a-m2-i04`): e2e_h06 r0
  - M19-21 (deepseek, 출력 `.cora/bench/m19/runs/e-i11`): e2e_h04 r0
  - M19-26 (deepseek, 출력 `.cora/bench/m19/runs/e-i16`): e2e_h06 r0

### 정정 7: 시간 제한 설정
- 새 값은 deadline 설정에만 적용합니다. 기본값 (`cora.toml`, `src/cora/data/cora.toml`: 90 / 300 / 120)은 그대로 둡니다.

| 키 | 기본 | 새 값 | 이유 |
|---|---|---|---|
| `[providers.openrouter] request_deadline_s` | 90 | **300** | 4096 토큰 전체 응답이 p10 19 tok/s에서 약 216 s + 프롬프트/대기; 300 s는 약 13.7 tok/s까지 허용 (p10 대비 39% 여유) |
| `[agent] call_timeout_s` | 300 | **960** | 규칙 T ≥ 3·D + 1 + 2 = 903: 공급자의 3회 시도가 T보다 먼저 끝나고, T는 시도별 시한 밖의 멈춤만 잡음; 57 s 여유 |
| `[providers.openrouter] timeout_s` | 120 | **300** | 비스트리밍 요청에서 httpx 바이트 간격 시한이 120 s를 넘는 시도를 끊을 수 있음 (OpenRouter keep-alive 바이트 전송은 미확인, 정정 12); = D로 의존 제거; 그 밖에는 영향 없음 |

- 최악의 경우: 호출 하나가 오류가 되기까지 최대 약 903 s (그 이상 멈춤은 최대 2 × 960 s).
- 규칙: `call_timeout_s ≥ 3 × request_deadline_s + 3`.
- `-c FILE`은 설정 파일 전체를 대체합니다 (병합 없음). 따라서 각 새 파일 = 기본 파일 전체 복사본 + 같은 세 값 변경입니다.

#### 설정 deadline

```diff
--- cora.toml
+++ .cora/bench/m19/deadline.toml
@@ -4,8 +4,8 @@
 [providers.openrouter]
 base_url = "https://openrouter.ai/api/v1"
 api_key_env = "OPENROUTER_API_KEY"
-timeout_s = 120
-request_deadline_s = 90        # total time per HTTP attempt incl. body (keep-alive bytes do not extend it); retried like a network error
+timeout_s = 300
+request_deadline_s = 300       # total time per HTTP attempt incl. body (keep-alive bytes do not extend it); retried like a network error
 stream_stall_timeout_s = 30    # streaming: stop an attempt when no data chunk arrives for this long; same retries
 # provider_sort = "throughput" # optional OpenRouter provider routing: "throughput" | "latency" | "price" (unset = OpenRouter default)
 # require_parameters = true  # optional: route only to endpoints that support every request parameter (e.g. tools for native runs); unset = OpenRouter default
@@ -134,7 +134,7 @@
 tamper_guard = false       # with a check: fail the gate (tests_modified) when pre-existing test files are edited or deleted
 selftest = false           # Python workspace, no check: model writes tests under .cora/selftest/; run as soft feedback only
 ladder = false             # with a check: sensor retries, then one reflection + one more check, then ladder_exhausted
-call_timeout_s = 300       # max wait per model call in seconds (10-3600), incl. stalled streams; one retry, then stop provider_timeout
+call_timeout_s = 960       # max wait per model call in seconds (10-3600), incl. stalled streams; one retry, then stop provider_timeout
 verify_before_final = true  # refuse the first Final Answer once when no check/run command succeeded after the last edit
 compile_check = true      # report Python syntax errors (file:line) after edits; refuse a Final Answer once while they remain
 edge_case_prompt = true   # after edits, refuse the first Final Answer once and ask to test empty, punctuation-only and boundary inputs
```

위 diff는 `uv run python -c "import difflib,pathlib as p;a=p.Path('cora.toml').read_text().splitlines();b=p.Path('tests/fixtures/m19/arms/deadline.toml').read_text().splitlines();print('\n'.join(difflib.unified_diff(a,b,'cora.toml','.cora/bench/m19/deadline.toml',n=3,lineterm='')))"` 의 출력입니다.

| 파일 | 원본 |
|---|---|
| `.cora/bench/m19/deadline.toml` (미러 `tests/fixtures/m19/arms/deadline.toml`) | `cora.toml` |
| `.cora/bench/m19/deadline-cascade-strong.toml` (미러 `tests/fixtures/m19/arms/deadline-cascade-strong.toml`) | `.cora/bench/m19/cascade-strong.toml` |
| `.cora/bench/m19/deadline-cascade-m1-m2.toml` (미러 `tests/fixtures/m19/arms/deadline-cascade-m1-m2.toml`) | `.cora/bench/m19/cascade-m1-m2.toml` |
| `.cora/bench/m19/deadline-deleg-nudge.toml` (미러 `tests/fixtures/m19/arms/deadline-deleg-nudge.toml`) | `.cora/bench/m19/deleg-nudge.toml` |
| `.cora/bench/m19/deadline-keys-on.toml` (미러 `tests/fixtures/m19/arms/deadline-keys-on.toml`) | `.cora/bench/m19/keys-on.toml` |

### 정정 8: 적용 호출
| 호출 | 모델 도달 | 설정 |
|---|---|---|
| 호출 M19-29..34 (e) | deepseek-v3.2 | `deadline.toml` |
| 호출 M19-35..39 c_s(m1) | gemini, 상위 모델(deepseek)으로 승격 | `deadline-cascade-strong.toml` |
| 호출 M19-40 d1(m1) | gemini만 | 변경 없음 (d2(m1) 비교 정확성 유지) |
| 호출 M19-41..45 c_s(m2) | qwen, deepseek | `deadline-cascade-strong.toml` |
| 호출 M19-46 d1(m2) | qwen | `deadline-deleg-nudge.toml` |
| 호출 M19-47..51 a(m3) | mistral-small-3.2 | 변경 없음 (느린 모델 근거 없음) — **사용자 결정 D1** |
| 조건부 B1 b(m1) | gemini | 변경 없음 |
| 조건부 CC c_cc | gemini, qwen | `deadline-cascade-m1-m2.toml` |
| 조건부 B2 b(m2), G2 g(m2) | qwen | `deadline.toml`, `deadline-keys-on.toml` |
| 재실행 RR-01..05 | qwen, deepseek | `deadline.toml` |

조건부 셀은 각자 날짜가 붙은 수정과 차례의 사용자 확인이 여전히 필요합니다. 계획 TOTAL은 가격이 같으므로 바뀌지 않습니다.

| 구분 호출 | 명령 |
|---|---|
| 수정 M19-29 | `uv run cora bench -c .cora/bench/m19/deadline.toml --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_hx1 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i19` |
| 수정 M19-30 | `uv run cora bench -c .cora/bench/m19/deadline.toml --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_hx1 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i20` |
| 수정 M19-31 | `uv run cora bench -c .cora/bench/m19/deadline.toml --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_hx1 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i21` |
| 수정 M19-32 | `uv run cora bench -c .cora/bench/m19/deadline.toml --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_hx2 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i22` |
| 수정 M19-33 | `uv run cora bench -c .cora/bench/m19/deadline.toml --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_hx2 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i23` |
| 수정 M19-34 | `uv run cora bench -c .cora/bench/m19/deadline.toml --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_hx2 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i24` |
| 수정 M19-35 | `uv run cora bench -c .cora/bench/m19/deadline-cascade-strong.toml --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h01,e2e_h02 --repeats 3 --max-cost 0.42 --out .cora/bench/m19/runs/c_s-m1-i01` |
| 수정 M19-36 | `uv run cora bench -c .cora/bench/m19/deadline-cascade-strong.toml --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h03 --repeats 3 --max-cost 0.36 --out .cora/bench/m19/runs/c_s-m1-i02` |
| 수정 M19-37 | `uv run cora bench -c .cora/bench/m19/deadline-cascade-strong.toml --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h04,e2e_h05 --repeats 3 --max-cost 0.45 --out .cora/bench/m19/runs/c_s-m1-i03` |
| 수정 M19-38 | `uv run cora bench -c .cora/bench/m19/deadline-cascade-strong.toml --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h06 --repeats 3 --max-cost 0.27 --out .cora/bench/m19/runs/c_s-m1-i04` |
| 수정 M19-39 | `uv run cora bench -c .cora/bench/m19/deadline-cascade-strong.toml --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_hx2 --repeats 3 --max-cost 0.24 --out .cora/bench/m19/runs/c_s-m1-i05` |
| 수정 M19-41 | `uv run cora bench -c .cora/bench/m19/deadline-cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h01,e2e_h02 --repeats 3 --max-cost 0.42 --out .cora/bench/m19/runs/c_s-m2-i01` |
| 수정 M19-42 | `uv run cora bench -c .cora/bench/m19/deadline-cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h03 --repeats 3 --max-cost 0.36 --out .cora/bench/m19/runs/c_s-m2-i02` |
| 수정 M19-43 | `uv run cora bench -c .cora/bench/m19/deadline-cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h04,e2e_h05 --repeats 3 --max-cost 0.45 --out .cora/bench/m19/runs/c_s-m2-i03` |
| 수정 M19-44 | `uv run cora bench -c .cora/bench/m19/deadline-cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h06 --repeats 3 --max-cost 0.27 --out .cora/bench/m19/runs/c_s-m2-i04` |
| 수정 M19-45 | `uv run cora bench -c .cora/bench/m19/deadline-cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_hx2 --repeats 3 --max-cost 0.24 --out .cora/bench/m19/runs/c_s-m2-i05` |
| 수정 M19-46 | `uv run cora bench -c .cora/bench/m19/deadline-deleg-nudge.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab deleg-on-par-on --tasks e2e_hx1,e2e_hx2 --repeats 3 --max-cost 0.39 --out .cora/bench/m19/runs/d1-m2-i01` |

### 정정 9: 출력 경로 편차 기록 (M19-11..M19-28, 사후 기록)
- M19-11..28은 등록과 달리 `--out .cora/bench/m19/runs/e-iNN` (반복 명명 규칙, NN = n − 10)으로 실행되었습니다. 등록된 출력은 `e-strong-iNN`입니다. 나머지 토큰은 모두 등록과 같습니다. 증거: 원장 `report` 필드와 보고서 설정.
- 측정에는 영향이 없습니다 (보고서 설정에는 출력 경로가 없음). 이 절은 사후 편차 기록이며 사전 변경이 아닙니다.

| 구분 호출 | 명령 |
|---|---|
| 편차 M19-11 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h01 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i01` |
| 편차 M19-12 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h01 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i02` |
| 편차 M19-13 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h01 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i03` |
| 편차 M19-14 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h02 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i04` |
| 편차 M19-15 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h02 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i05` |
| 편차 M19-16 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h02 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i06` |
| 편차 M19-17 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h03 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i07` |
| 편차 M19-18 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h03 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i08` |
| 편차 M19-19 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h03 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i09` |
| 편차 M19-20 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h04 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i10` |
| 편차 M19-21 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h04 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i11` |
| 편차 M19-22 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h04 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i12` |
| 편차 M19-23 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h05 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i13` |
| 편차 M19-24 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h05 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i14` |
| 편차 M19-25 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h05 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i15` |
| 편차 M19-26 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h06 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i16` |
| 편차 M19-27 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h06 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i17` |
| 편차 M19-28 | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h06 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i18` |

### 정정 10: 재실행 규칙
- 시간 제한 (`RequestDeadlineExceeded`)으로 생긴 `error` 실행은 정확히 한 번 재실행합니다: 호출 한 번, `--repeats 1`, 같은 과제, 모델, 플래그, 정정 8의 deadline 설정 (`-c`가 없는 호출은 `deadline.toml`), `--max-cost` = ceil_cent(원 `--max-cost` / 원 실행 수), `--out .cora/bench/m19/runs/rerun-NN`.
- 원래 보고서와 실행은 그대로 남아 계속 보입니다. 재실행도 오류이면 미해결로 남고, 더 재실행하지 않습니다.
- 재실행은 51개 등록 호출에 포함되지 않습니다. ID는 `RR-NN`입니다. 원장 검사 C1–C13을 적용합니다 (예산 C6/C7, 사용 C5, 키 만료 C10, e 중단 C8). 지출은 $6.00 배정에 포함되고, 이후 1.5× 셀 결정과, e에 대해서는 $2.16 e 중단에도 포함됩니다.
- 순서: 원 호출의 셀이 평가된 뒤, 그 다음 셀이 평가되기 전에 실행합니다. 셀 e까지의 재실행은 체크포인트 2 전에 실행합니다.
- 재실행의 반복 인덱스는 0입니다 (`--repeats 1`). M19-29..51에서 앞으로 생기는 시간 초과 오류 실행의 RR 행은 실행 전에 날짜가 붙은 추가 수정으로 넣습니다.

| 재실행 | 원 호출 | 과제 | 원 반복 | --max-cost | plan TOTAL | 명령 |
|---|---|---|---|---|---|---|
| 재실행 RR-01 | M19-08 | e2e_h04 | 0 | 0.08 | 0.042202 | `uv run cora bench -c .cora/bench/m19/deadline.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_h04 --repeats 1 --max-cost 0.08 --out .cora/bench/m19/runs/rerun-01` |
| 재실행 RR-02 | M19-08 | e2e_h05 | 2 | 0.08 | 0.042202 | `uv run cora bench -c .cora/bench/m19/deadline.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_h05 --repeats 1 --max-cost 0.08 --out .cora/bench/m19/runs/rerun-02` |
| 재실행 RR-03 | M19-09 | e2e_h06 | 0 | 0.07 | 0.035168 | `uv run cora bench -c .cora/bench/m19/deadline.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_h06 --repeats 1 --max-cost 0.07 --out .cora/bench/m19/runs/rerun-03` |
| 재실행 RR-04 | M19-21 | e2e_h04 | 0 | 0.30 | 0.147302 | `uv run cora bench -c .cora/bench/m19/deadline.toml --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h04 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/rerun-04` |
| 재실행 RR-05 | M19-26 | e2e_h06 | 0 | 0.30 | 0.122752 | `uv run cora bench -c .cora/bench/m19/deadline.toml --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h06 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/rerun-05` |

상한 합 0.389626.

### 정정 11: 분석 규칙
- 주 분석: 재실행이 대체하는 원래 오류 실행을 대체합니다 (`--error-policy replace`).
- 비용: 청구 기준 (`--cost-basis billed`). 호출마다 max(청구 `/credits` 차이, 보고서 비용)을 쓰고, 초과분은 그 보고서의 완료 실행들에 실행 비용 비례로 나눕니다 (실행 비용이 모두 0이면 균등 분배).
- 근거: 사용자 결정 2026-10-19 (비용 지표에 청구 비용) 및 2026-10-20 시나리오 A. 시나리오 A는 2026-10-19의 "재실행 없음, 오류는 미해결" 결정을 대체합니다.
- 민감도 (g): 영향받는 (팔, 모델)마다 오류를 미해결 / 제외 / 재실행으로 대체 × 보고서 / 청구 비용으로 보고합니다. (g2): 셀마다 오류 실행과 90 s 초과 호출 수를 보고합니다.
- 등록된 기본 출력 (오류 미해결, 보고서 비용)은 `panel-registered.md`로 보존합니다.
- d2(m2) 주의: a(m2)의 X 과제 실행은 90 s, d1(m2)은 300 s를 씁니다. (g2)의 90 s 초과 호출 수는 d2 결과 옆에 함께 보고합니다.

### 정정 12: 열린 항목
- a(m3) (mistral-small-3.2)은 M19 처리량 근거가 없으므로, 사용자가 달리 결정하지 않는 한 기본값을 유지합니다 (D1).
- 비스트리밍 요청에서 OpenRouter keep-alive 동작은 미확인입니다 (`timeout_s = 300`을 쓰는 이유).

## M19 사전 등록 수정 (2026-10-21T00:43:16Z)

이 절은 사용자 결정 2026-10-20 ("ok 1번으로 합시다")에 따라 OpenRouter 제공자 제외 설정 (`provider_ignore`)을 추가하고, 오류로 끝난 HTTP 400 (stopSequences) 실행을 한 번씩 재실행하며, 호출 M19-44..46의 설정을 정합니다 (재실행 상한은 사용자 결정 D-R1 = B: 원 실행의 과제별 상한). 1부와 2부 본문은 바꾸지 않습니다 (덧붙이기 전용 규칙). 이 절은 RR-06과 M19-44보다 먼저 커밋됨.

### 정정 13: 원인 (HTTP 400 stopSequences)
- M19-43 (c_s(m2), 출력 `.cora/bench/m19/runs/c_s-m2-i03`): 6회 실행 중 4회가 `error`로 끝났고 모두 `HTTP 400`과 `stopSequences`입니다 (e2e_h04 r0, r1, r2; e2e_h05 r2). e2e_h05 r0, r1은 `failed`입니다.
- 실패한 요청은 qwen 저비용 호출입니다. 세션 `…-5a612a`와 `…-97bf7e`는 이벤트가 `models`, `route` (cheap, qwen), `attempt_start`뿐이므로 첫 qwen 요청에서 실패했습니다. HTTP 400은 재시도되지 않으므로 (`_raise_for_status` → `ProviderError`) 실행이 바로 `error`로 끝납니다.
- qwen3-coder-30b의 엔드포인트 (OpenRouter Endpoints API, 2026-10-20): `siliconflow/fp8` (`stop`이 supported_parameters에 없음, 약 28 tok/s)와 `amazon-bedrock/us-west-2` (`stop` 표시됨, 약 92 tok/s).
- 출력 300 토큰을 넘는 qwen 호출 296건 (M19 모든 실행)은 어느 것도 51 tok/s보다 빠르지 않습니다. 따라서 Bedrock에서 성공한 요청은 한 번도 없었습니다. Bedrock은 `stop` (`stopSequences`)을 받을 때마다 거부합니다.
- 결론: 모든 이전 qwen 측정 (a(m2), M19-41/42/43의 성공분, RR-01..03)은 Bedrock이 아닌 느린 엔드포인트에서 나왔습니다. Bedrock을 제외하면 이전 qwen 측정과 같은 조건이 됩니다.
- P0 탐색 (2026-10-21 00:39Z, qwen3-coder-30b, `max_tokens` 1, 요청 3회):
  - P1 (`stop` + `provider.only: ["amazon-bedrock"]`, `allow_fallbacks: false`): HTTP 400, `stopSequences`.
  - P2 (P1에서 `stop` 제거): HTTP 200, 제공자 `Amazon Bedrock`.
  - P3 (`stop` + `provider.ignore: ["amazon-bedrock"]`): HTTP 200, 제공자 `SiliconFlow`.
  - 슬러그 `amazon-bedrock`과 가설이 확인되었습니다.
- 기각한 대안:
  - `only: ["siliconflow"]`: deepseek-v3.2도 SiliconFlow로 강제됩니다 (약 13 tok/s, `stop` 없음). 기각.
  - `require_parameters = true`: 메타데이터상 SiliconFlow에 `stop`이 없으므로 qwen을 Bedrock으로 강제합니다. 기각.
  - `stop` 제거: 하네스 동작을 바꿉니다. 기각.

### 정정 14: 제공자 제외 설정
- 새 선택 키 `[providers.openrouter] provider_ignore = ["<슬러그>", ...]`: 요청 본문의 `provider.ignore`로 보내며, OpenRouter는 그 제공자의 엔드포인트로 라우팅하지 않습니다. 값은 소문자 `[a-z0-9][a-z0-9._/-]*` 슬러그의 비어 있지 않고 중복 없는 목록이며, 설정 로드와 제공자 생성자 두 곳에서 검증합니다.
- 기본값은 미설정입니다. 미설정이면 요청이 바뀌지 않습니다 (`stop`도 그대로 보냅니다). 제공자 전체 설정이므로 같은 실행의 모든 OpenRouter 호출에 적용되며 모델별 설정이 아닙니다.
- 구현은 커밋으로 들어갑니다. 기본 설정 `cora.toml`과 `src/cora/data/cora.toml`은 바꾸지 않습니다 (주석 줄도 넣지 않음; 등록된 M19 설정 diff 보존).
- 규칙: 각 새 파일 = 대응하는 deadline 파일 + 한 줄 (아래 anchor 줄 뒤에 한 줄 추가; 다른 줄은 바뀌지 않음).

| 파일 | 원본 |
|---|---|
| `.cora/bench/m19/deadline-nobedrock-cascade-strong.toml` (미러 `tests/fixtures/m19/arms/deadline-nobedrock-cascade-strong.toml`) | `.cora/bench/m19/deadline-cascade-strong.toml` |
| `.cora/bench/m19/deadline-nobedrock-deleg-nudge.toml` (미러 `tests/fixtures/m19/arms/deadline-nobedrock-deleg-nudge.toml`) | `.cora/bench/m19/deadline-deleg-nudge.toml` |

#### 설정 deadline-nobedrock-cascade-strong

```diff
--- .cora/bench/m19/deadline-cascade-strong.toml
+++ .cora/bench/m19/deadline-nobedrock-cascade-strong.toml
@@ -9,6 +9,7 @@
 stream_stall_timeout_s = 30    # streaming: stop an attempt when no data chunk arrives for this long; same retries
 # provider_sort = "throughput" # optional OpenRouter provider routing: "throughput" | "latency" | "price" (unset = OpenRouter default)
 # require_parameters = true  # optional: route only to endpoints that support every request parameter (e.g. tools for native runs); unset = OpenRouter default
+provider_ignore = ["amazon-bedrock"]   # M19 정정 14: Amazon Bedrock rejects the stop field for qwen3-coder-30b (HTTP 400 stopSequences); unset = OpenRouter default
 
 [providers.gemini]
 type = "openai_compat"
```

#### 설정 deadline-nobedrock-deleg-nudge

```diff
--- .cora/bench/m19/deadline-deleg-nudge.toml
+++ .cora/bench/m19/deadline-nobedrock-deleg-nudge.toml
@@ -9,6 +9,7 @@
 stream_stall_timeout_s = 30    # streaming: stop an attempt when no data chunk arrives for this long; same retries
 # provider_sort = "throughput" # optional OpenRouter provider routing: "throughput" | "latency" | "price" (unset = OpenRouter default)
 # require_parameters = true  # optional: route only to endpoints that support every request parameter (e.g. tools for native runs); unset = OpenRouter default
+provider_ignore = ["amazon-bedrock"]   # M19 정정 14: Amazon Bedrock rejects the stop field for qwen3-coder-30b (HTTP 400 stopSequences); unset = OpenRouter default
 
 [providers.gemini]
 type = "openai_compat"
```

위 두 diff는 각각 위 표의 원본과 새 파일 이름을 넣은 `uv run python -c` (difflib, `n=3`)의 출력입니다.

- 이 키는 invocation의 모든 OpenRouter 호출에 적용됩니다. deepseek-v3.2에는 Bedrock 엔드포인트가 없으므로 (gmicloud, siliconflow, deepinfra, atlas-cloud, venice, baidu, digitalocean, friendli, google-vertex, phala, mara, sambanova) 이 키는 deepseek 호출을 바꾸지 않습니다.
- 보고서 `settings`에는 제공자 설정이 없습니다. 따라서 이 설정의 출처는 원장 명령과 설정 파일입니다.

### 정정 15: 적용 호출
| 호출 | 모델 도달 | 설정 |
|---|---|---|
| 호출 M19-44..45 c_s(m2) | qwen, deepseek | `deadline-nobedrock-cascade-strong.toml` |
| 호출 M19-46 d1(m2) | qwen | `deadline-nobedrock-deleg-nudge.toml` |
| 호출 M19-47..51 a(m3) | mistral-small-3.2 | 변경 없음 (Bedrock 엔드포인트 없음, 모두 `stop` 지원) |
| 조건부 B2 b(m2), G2 g(m2), CC c_cc | qwen, gemini | 변경 없음 (not_measured 결정 유지; 채택에는 별도 수정 필요) |
| 재실행 RR-06..09 | qwen | 정정 16 (`deadline-nobedrock-cascade-strong.toml` / `deadline-nobedrock-deleg-nudge.toml`) |

이 행들은 정정 8의 같은 호출 행을 대체합니다 (나중 행이 우선; 원장은 등록 → deadline → nobedrock 순서만 받습니다). 계획 TOTAL은 가격이 같으므로 바뀌지 않습니다.

| 구분 호출 | 명령 |
|---|---|
| 수정 M19-44 | `uv run cora bench -c .cora/bench/m19/deadline-nobedrock-cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h06 --repeats 3 --max-cost 0.27 --out .cora/bench/m19/runs/c_s-m2-i04` |
| 수정 M19-45 | `uv run cora bench -c .cora/bench/m19/deadline-nobedrock-cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_hx2 --repeats 3 --max-cost 0.24 --out .cora/bench/m19/runs/c_s-m2-i05` |
| 수정 M19-46 | `uv run cora bench -c .cora/bench/m19/deadline-nobedrock-deleg-nudge.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab deleg-on-par-on --tasks e2e_hx1,e2e_hx2 --repeats 3 --max-cost 0.39 --out .cora/bench/m19/runs/d1-m2-i01` |

### 정정 16: 재실행 규칙 확장
- 정정 10의 규칙은 오류 상세에 `HTTP 400`과 `stopSequences`가 모두 들어 있는 `error` 실행에도 적용합니다.
  - 정확히 한 번 재실행합니다. 원 실행은 그대로 남깁니다. 재실행도 오류이면 미해결로 남고 더 재실행하지 않습니다.
  - 설정 = 원 호출의 등록된 설정에 대응하는 nobedrock 파일.
  - `--max-cost` = 원 실행의 과제별 상한 = min(원 `settings.max_task_cost_usd`, 과제의 `settings.e2e.tasks[].cost_usd`). ledger C14가 이 값을 검사합니다. 이유: bench는 과제별 상한을 `--max-cost`로 낮춥니다 (정정 10의 ceil_cent(…)는 이 재실행에만 대체됩니다).
  - 사후 발견: RR-01과 RR-03은 상한 0.08 / 0.07로 실행되었습니다 (원 0.10 / 0.09). 상한은 구속력이 없었습니다 (비용 0.013779 / 0.008055, 두 실행 모두 `final_answer`로 끝남). 따라서 결과는 유효합니다. RR-02, RR-04, RR-05의 상한은 원 실행과 같습니다.
  - 순서: c_s(m2) 셀 뒤, b(m2)를 평가하기 전, M19-44 전에 실행합니다.
  - C11은 이제 수정 이벤트가 원 실행의 원장 기록 뒤에 있을 것을 요구합니다.
  - 예산 (M19-43 시점): M19 2.750130 / 6.00; RR 상한 0.35 + M19-44..46 상한 0.90.

| 재실행 | 원 호출 | 과제 | 원 반복 | --max-cost | plan TOTAL | 명령 |
|---|---|---|---|---|---|---|
| 재실행 RR-06 | M19-43 | e2e_h04 | 0 | 0.10 | 0.100000 | `uv run cora bench -c .cora/bench/m19/deadline-nobedrock-cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h04 --repeats 1 --max-cost 0.10 --out .cora/bench/m19/runs/rerun-06` |
| 재실행 RR-07 | M19-43 | e2e_h04 | 1 | 0.10 | 0.100000 | `uv run cora bench -c .cora/bench/m19/deadline-nobedrock-cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h04 --repeats 1 --max-cost 0.10 --out .cora/bench/m19/runs/rerun-07` |
| 재실행 RR-08 | M19-43 | e2e_h04 | 2 | 0.10 | 0.100000 | `uv run cora bench -c .cora/bench/m19/deadline-nobedrock-cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h04 --repeats 1 --max-cost 0.10 --out .cora/bench/m19/runs/rerun-08` |
| 재실행 RR-09 | M19-43 | e2e_h05 | 2 | 0.05 | 0.050000 | `uv run cora bench -c .cora/bench/m19/deadline-nobedrock-cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h05 --repeats 1 --max-cost 0.05 --out .cora/bench/m19/runs/rerun-09` |

상한 합 0.350000.

### 정정 17: 분석과 열린 항목
- 정정 11을 적용합니다 (대체 + 청구 기준). c_s(m2)에서 h04의 세 실행은 모두 재실행 대상이며, (g)는 미해결 / 제외 / 대체를 보고합니다.
- 상위 제공자 이름은 보고서에 기록되지 않습니다 (열린 항목). OpenRouter 응답의 `provider` 필드를 기록하는 것은 M19 범위 밖의 후속 변경입니다.
- Bedrock이 아닌 qwen 엔드포인트를 쓸 수 없으면 요청은 "no endpoints"로 실패합니다. 이 경우 R8 중단으로 보고 원인을 찾으며, 재실행 원인으로 세지 않습니다.
- d2(m2): a(m2)와 d1(m2)은 둘 다 실질적으로 Bedrock이 아닌 엔드포인트에서 실행되었습니다 (정정 13 근거).

## M19 사전 등록 수정 (2026-10-21T03:10:52Z)

이 절은 사용자 결정 2026-10-21 (규칙 (c), 시나리오 A)에 따라 M19-44의 요청 시간 제한 오류 실행 1개를 같은 설정으로 한 번 재실행합니다 (RR-10). 시간 제한 값과 설정 파일은 바꾸지 않습니다. 1부와 2부 본문은 바꾸지 않습니다 (덧붙이기 전용 규칙). 이 절은 RR-10, M19-45, b(m2) 평가보다 먼저 커밋됨.

### 정정 18: 원인 (M19-44 요청 시간 제한)
- M19-44 (c_s(m2), 설정 `.cora/bench/m19/deadline-nobedrock-cascade-strong.toml`, 출력 `.cora/bench/m19/runs/c_s-m2-i04`): e2e_h06 3회 실행 중 r0 `solved`, r1 `failed` (`max_iterations`), r2 `error`입니다.
- r2 상세: `ProviderError: openrouter request failed: RequestDeadlineExceeded: no complete response within request_deadline_s=300s`. 오류는 강한 단계 deepseek-v3.2 호출 (반복 8 → 9)에서 났습니다. `HTTP 400` / `stopSequences` 오류가 아닙니다 (정정 13과 무관).
- 실행 설정은 정정 7의 값 (request_deadline_s 300, call_timeout_s 960, timeout_s 300)과 정정 14의 `provider_ignore`입니다. 사용자 결정에 따라 이 값들은 바꾸지 않습니다.
- 정산: M19-44는 청구 기준으로 정산되었습니다 (`/credits` 차이 0.058750, 보고서 비용 0.043149; 사용자 결정 2026-10-21). 차이는 보고서에 기록되지 않은 시간 초과 deepseek 시도의 청구분으로 설명됩니다.

### 정정 19: 재실행 규칙 (같은 설정)
- 정정 10의 규칙은 정정 15의 nobedrock 설정으로 실행된 호출의 `RequestDeadlineExceeded` `error` 실행에도 적용합니다.
  - 정확히 한 번 재실행합니다. 원 실행은 그대로 남습니다. 재실행도 오류이면 미해결로 남고 더 재실행하지 않습니다.
  - 설정 = 원 호출이 실제로 실행된 설정 (정정 15 행의 파일). 시간 제한 값은 바뀌지 않습니다.
  - `--max-cost` = ceil_cent(원 `--max-cost` / 원 실행 수) (정정 10). 이 값은 원 실행의 과제별 상한 (정정 16의 정의)과도 같아야 합니다 (ledger C14). 두 값이 다르면 재실행하지 않고 별도의 날짜 있는 수정이 필요합니다. RR-10: ceil_cent(0.27 / 3) = 0.09 = min(0.09, e2e_h06 `cost_usd` 0.09).
  - 원장의 원인 구분: 재실행 설정이 원 호출의 실효 설정과 같으면 원인은 `RequestDeadlineExceeded` (C12)입니다. 원 호출이 deadline 설정으로 실행되었고 재실행이 nobedrock 설정이면 정정 16 (`HTTP 400` + `stopSequences`)입니다.
  - 순서: c_s(m2) 셀 안에서, M19-45 전, b(m2) 평가 전에 실행합니다. C11은 수정 이벤트가 M19-44의 원장 기록 뒤에 있을 것을 요구합니다.
  - 정산 불일치 규칙 (b)는 그대로입니다: |청구 차이 − 보고서 비용| ≤ max(보고서 비용의 20%, $0.01)이고 `error` 실행이 없을 때만 자동 해결합니다. 그 밖에는 멈추고 사용자가 결정합니다.
  - 예산 (M19-44 시점): M19 2.935727 / 6.00; RR-10 상한 0.09; M19-45..51 plan TOTAL 합 1.825560.

| 재실행 | 원 호출 | 과제 | 원 반복 | --max-cost | plan TOTAL | 명령 |
|---|---|---|---|---|---|---|
| 재실행 RR-10 | M19-44 | e2e_h06 | 2 | 0.09 | 0.090000 | `uv run cora bench -c .cora/bench/m19/deadline-nobedrock-cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h06 --repeats 1 --max-cost 0.09 --out .cora/bench/m19/runs/rerun-10` |

상한 합 0.090000.

### 정정 20: 분석과 열린 항목
- 정정 11을 적용합니다 (대체 + 청구 기준). c_s(m2)의 (g)는 e2e_h06 r2를 미해결 / 제외 / 대체로 보고합니다.
- M19-44의 청구 초과분 (시간 초과 시도)은 청구 기준 비용에 들어갑니다 (정정 11의 배분 규칙).
- 열린 항목: 300 s 제한에서도 deepseek-v3.2 강한 단계 호출 하나가 완료되지 않았습니다. 제한 값은 바꾸지 않으며, 그 호출의 증거 (지연, 토큰, 시도 수)는 측정 기록 (§2/§10)에 남깁니다.
