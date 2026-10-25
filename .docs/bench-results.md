# CORA live bench results

실측일: 2026-10-14 (KST). 키·민감정보 없음. 방향성 증거이며 통계적으로 유의하지 않다.

## Runs

| run | command (no secrets) | max_cost | reported spend | 결과 |
|---|---|---|---|---|
| AC15 스모크 | `cora bench --live --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks fix_off_by_one,implement_fizzbuzz --max-cost 0.05` | $0.05 | $0.002295 | 2/2 해결 |
| AC17 낮은 상한 | `... --protocols react --max-cost 0.01` (태스크당 상한 $0.001) | $0.01 | $0.005568 | 6/11 해결, 5개는 태스크당 상한으로 stopped_budget |
| AC17 총 상한 | `... --max-cost 0.003 --max-task-cost 0.003 --tasks <6개>` | $0.003 | $0.002804 | 총 상한 도달 후 진행 중 태스크 stopped_budget, 나머지 2개 skipped_budget, 초과 없음 |
| AC16 전체 | `cora bench --live --max-cost 0.30` (모델 2 × react·native × 태스크 11) | $0.30 | $0.026705 | 아래 표 |

## Model × protocol (AC16 전체 실행, 태스크 11개, 1회 시도)

| model | protocol | solved | solve_rate | total_cost_usd | cost_per_solved_usd | avg_calls | avg_latency_s |
|---|---|---|---|---|---|---|---|
| qwen/qwen3-coder-30b-a3b-instruct | react | 11/11 | 100.0% | 0.008571 | 0.000779 | 4.64 | 34.60 |
| qwen/qwen3-coder-30b-a3b-instruct | native | 8/11 | 72.7% | 0.007201 | 0.000900 | 5.45 | 18.93 |
| mistralai/mistral-small-3.2-24b-instruct | react | 9/11 | 81.8% | 0.004613 | 0.000513 | 6.00 | 12.83 |
| mistralai/mistral-small-3.2-24b-instruct | native | 7/11 | 63.6% | 0.006321 | 0.000903 | 5.09 | 15.11 |

모든 비용은 OpenRouter 응답의 usage 비용(provider-reported 233/233 호출)이다.

## Total spend

- 이번 마일스톤 실호출 합계(보고 기준): 약 $0.037. OpenRouter `/auth/key` 사용량 조회: $0.0366. 두 값이 일치한다.
- 마일스톤 한도 $1 대비 약 3.7%.

## 관찰

- 5개 실패 중 대부분이 두 가지 패턴이다. (1) 작업을 끝내지 않고 일찍 최종 답변 (예: qwen native `fix_off_by_one`은 1회 호출 후 수정 없이 종료, `explore_count_todos`·`explore_find_raiser` native는 2~3회 호출 후 틀린 답). (2) 반복 한도(12) 소진 (mistral react `fix_sort_order`, qwen native `refactor_rename`, mistral native `explore_find_port`).
- native 모드는 두 모델 모두 react보다 해결률이 낮았다. 호출 형식 오류보다는 "일찍 끝내기"와 반복 소진이 많았고, 지연은 qwen에서 더 짧았다(34.6s -> 18.9s).
- 태스크당 상한이 너무 낮으면(`--max-cost 0.01` -> 태스크당 $0.001) 정상 태스크도 stopped_budget이 된다. 기본값($0.30 -> 태스크당 $0.03)은 충분했다.
- 응답 지연은 호출당 수 초~수십 초로 편차가 컸다(qwen 3 same-task 재실행에서 26s와 125s).

## Recommended default tool_protocol

**react 유지.** 두 모델 모두 react가 native보다 해결률이 높았다(qwen 100% vs 72.7%, mistral 81.8% vs 63.6%). 표본이 작고 시도가 1회라 확정은 아니다. native를 기본으로 바꾸려면 "최종 답변 전에 결정적 검사(테스트/체크)를 통과시키는" 센서 게이트 같은 조기 종료 방지책을 넣은 뒤 같은 벤치로 다시 비교해야 한다.

## Baseline

baseline not provided (Claude Code/Codex 기준값은 사용자가 baseline.toml로 제공해야 비교할 수 있다. 어떤 기준 수치도 임의로 만들지 않았다).

## Notes / limitations

- 방향성 증거만 제공한다. 태스크당 시도 1회, 태스크 11개로 작다.
- 태스크는 작은 단일 파일 위주의 합성 과제다. 실제 대형 저장소 작업의 난이도를 대표하지 않는다.
- 비용 우위 주장에는 같은 태스크를 Claude Code/Codex로 돌린 baseline이 필요하다.

---

## 재기준선과 센서 게이트 실측 (2026-10-14, 도구 확장·그룹 적용 후)

조건: 고정 도구 세트 core 5개(list_files, read_file, search, edit_file, run_shell), 모델 2개 × react·native × 태스크 11개, 태스크당 1회 시도, `--max-cost 0.30`. 비용은 모두 OpenRouter 응답 usage 기준(provider-reported 238/238, 250/250 호출).

### Run 1 — 센서 없음 (재기준선, 첫 실행과 같은 조건)
| model | protocol | solved | solve_rate | total_cost_usd | cost_per_solved_usd | avg_calls | avg_latency_s |
|---|---|---|---|---|---|---|---|
| qwen/qwen3-coder-30b-a3b-instruct | react | 10/11 | 90.9% | 0.012871 | 0.001287 | 5.27 | 54.56 |
| qwen/qwen3-coder-30b-a3b-instruct | native | 8/11 | 72.7% | 0.006861 | 0.000858 | 5.00 | 22.82 |
| mistralai/mistral-small-3.2-24b-instruct | react | 9/11 | 81.8% | 0.005230 | 0.000581 | 6.18 | 13.10 |
| mistralai/mistral-small-3.2-24b-instruct | native | 7/11 | 63.6% | 0.008494 | 0.001213 | 5.18 | 15.37 |

합계: 34/44 해결(77.3%), 지출 $0.0335 -> 해결당 약 $0.00098.

### Run 2 — `--sensor` (각 태스크의 자체 check를 최종 답변 전 게이트로 사용, 트립와이어 포함)
| model | protocol | solved | solve_rate | total_cost_usd | cost_per_solved_usd | avg_calls | avg_latency_s |
|---|---|---|---|---|---|---|---|
| qwen/qwen3-coder-30b-a3b-instruct | react | 11/11 | 100.0% | 0.014500 | 0.001318 | 4.73 | 62.20 |
| qwen/qwen3-coder-30b-a3b-instruct | native | 10/11 | 90.9% | 0.009149 | 0.000915 | 6.73 | 26.03 |
| mistralai/mistral-small-3.2-24b-instruct | react | 10/11 | 90.9% | 0.005540 | 0.000554 | 6.36 | 15.46 |
| mistralai/mistral-small-3.2-24b-instruct | native | 8/11 | 72.7% | 0.005967 | 0.000746 | 4.91 | 14.77 |

합계: 39/44 해결(88.6%), 지출 $0.0352 -> 해결당 약 $0.00090.
센서 통계: check 실행 34회, 재시도 4회, 센서로 추가된 LLM 호출 22회, 추가 비용 $0.003276(전체의 약 9%), 에스컬레이션 0회(벤치는 모델을 pin하므로 트립와이어는 중단만 한다).

### 비교와 해석
- 센서 게이트가 해결 수를 34 -> 39(+5, +11.3%p)로 올렸고 총 지출은 $0.0335 -> $0.0352(+5%)였다. 네 조합 모두 해결 수가 같거나 늘었다(qwen react 10->11, qwen native 8->10, mistral react 9->10, mistral native 7->8). native의 조기 종료(최종 답변을 먼저 내고 수정 안 함) 실패가 센서로 상당히 줄었다.
- 센서가 켜져도 react가 native보다 같거나 높았다. 기본 프로토콜은 react 유지가 맞다.
- 같은 조건의 첫 실행(2026-10-14 01:08, 도구 확장 전)과 비교: qwen react 11/11 $0.00078 -> Run 1 10/11 $0.00129, mistral react 9/11 $0.00051 -> $0.00058. 같은 설정에서도 해결 수·비용이 흔들린다(예: qwen react `refactor_rename`이 한 번은 12회 반복 소진, $0.0058). 표본 1회라서 이 정도 차이는 노이즈 범위로 봐야 한다.
- 한계: 센서 모드의 벤치는 태스크의 check 파일을 작업 디렉터리에 써서 모델이 읽을 수 있다(refactor 과제). 합성 소형 과제이며 시도 1회라서 방향성 증거일 뿐이다. Claude Code/Codex baseline은 아직 없다(baseline not provided).

### 도구 그룹 프롬프트 크기 (오프라인 측정)
| 구성 | react 설명(글자) | native 스키마(글자) |
|---|---|---|
| 전체 + submit_plan(기준) | 1606 (~401 tok) | 5418 (~1354 tok) |
| 전체(계획 모드 꺼짐) | 1505 (~376 tok) | 5122 (~1280 tok) |
| core만 / simple 자동 규칙 | 638 (~159 tok) | 2020 (~505 tok) |
core만 쓰면 기준 대비 react -60.3%(-968자, ~242 tok), native -62.7%(-3398자, ~849 tok). 요청마다 반복 청구되는 입력 토큰이다.

### 지출 합계 (이번 프로젝트 라이브 단계)
- OpenRouter 키 사용량: $0.1074 (한도 $1 대비 약 10.7%, 키 한도 $3).
- 이번 두 실행 보고 합계 $0.0687과 사용량 증가분($0.0387 -> $0.1074 = $0.0687)이 일치한다.

---

## M3: 위임·모델 티어 A/B (다중 파일 과제)

상태: 구현과 오프라인 검증 완료. 라이브 A/B는 아직 실행하지 않았다(측정 대기). 아래 표는 빈 템플릿이다.

### (a) 결정 규칙 (R23)

- 위임(`delegate`)의 기본값은 꺼짐(OFF)으로 유지한다.
- 오케스트레이터는 라이브 A/B에서 `deleg-on-*` 구성의 해결률이 `deleg-off` 이상이고, 해결당 비용이 더 낮거나 벽시계 시간이 더 짧을 때에만 기본값 변경을 검토할 수 있다. 두 조건을 모두 만족해야 한다.
- 동점이거나 그보다 나쁘면 OFF를 유지한다.
- 각 셀은 1회 시도이므로 결과는 방향성이며 통계적 결론이 아니다.
- `strong-only`와 `auto-routed`의 티어 비교 데이터는 이후 SALE 방식 라우팅 마일스톤을 위해 기록만 한다. 이 마일스톤은 라우팅 기본값이나 기본 티어를 정하지 않는다.

### (b) 명령

측정 전 스모크 실행(상한 $0.05 / 태스크당 $0.02):

```
uv run cora bench --live --ab all --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks query_client_timeout --max-cost 0.05 --max-task-cost 0.02 --out .cora/bench/m3-smoke
```

본 실행(상한 $0.40 / 태스크당 $0.05):

```
uv run cora bench --live --ab all --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --max-cost 0.40 --max-task-cost 0.05 --out .cora/bench/m3-ab
```

두 실행의 상한 합은 $0.45로 하드 상한 $0.50 이내다. 보고서에 `budget_exhausted=yes`가 이른 시점에 나오면 중단한다.

### (c) 빈 템플릿

구성별 표 (`deleg-off`는 cheap-only를 겸한다):

| arm | model | attempted | solved | skipped | solve_rate | total_cost_usd | cost_per_solved_usd | resolved_per_dollar | wall_s | avg_latency_s | deleg_calls | deleg_explore | deleg_general | deleg_ok | deleg_failed | deleg_refused | deleg_in | deleg_out | deleg_cost_usd | deleg_wall_s | deleg_max_fanout | avoided_tokens_est |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

난이도별 표 (easy ≤ 2분, medium ≤ 10분, hard > 10분; 구성 × 구간마다 한 행):

| config | bin | tasks | solved | cost_usd | wall_s |
|---|---|---|---|---|---|

작업별 모델 티어 표:

| task | difficulty | cheap-only | strong-only | auto-routed | auto tiers | flags |
|---|---|---|---|---|---|---|

지출 표:

| 실행 | max_cost | 보고된 지출 (total_spend_usd) | budget_exhausted | 비고 |
|---|---|---|---|---|
| 스모크 | $0.05 | | | |
| 본 실행 | $0.40 | | | |

### (d) 참고

`avoided_tokens_est`는 추정치(estimate)다. 위임 하위 에이전트의 도구 결과 토큰 합에서 메인 에이전트로 돌아온 요약 토큰을 뺀 단일 통과 하한 추정이며, 반사실(counterfactual) 측정이 아니다.

---

## 모델 비교 (shootout, 2026-10-14, 단일 파일 과제 11개, react, 코어 도구 5개, 시도 1회)
| 모델 | 입력/출력 $/Mtok | 해결 | 총비용 | 해결당 비용 | 평균 지연/과제 | 평균 호출 |
|---|---|---|---|---|---|---|
| google/gemini-2.5-flash-lite | 0.10 / 0.40 | **11/11** | $0.0158 | $0.00144 | **10.1s** | 5.0 |
| openai/gpt-4o-mini | 0.15 / 0.60 | 7/11 | $0.0129 | $0.00185 | 13.3s | 6.9 |
| openai/gpt-4.1-nano | 0.10 / 0.40 | 3/11 | $0.0081 | $0.00270 | 10.7s | 8.7 |
(참고: 같은 과제에서 qwen3-coder-30b react는 10~11/11, 해결당 $0.0008~0.0013, 평균 지연 35~62s; mistral-small-3.2 react 9/11, $0.0005~0.0006, 13s.)
- gemini-2.5-flash-lite가 해결률은 qwen과 같고 3~6배 빠르며 해결당 비용은 약 1.1~1.8배다. gpt-4.1-nano와 gpt-4o-mini는 이 ReAct 텍스트 프로토콜에서 해결률이 낮다(조기 반복 소진 12회가 많음). 시도 1회라 방향성 증거다.
- 속도 원인: qwen3-coder-30b는 OpenRouter에서 사실상 제공자 1곳(SiliconFlow, 중앙값 19 tok/s). gemini-2.5-flash-lite는 제공자 5곳, 중앙값 150~190 tok/s.

## 위임 A/B (M3, qwen3-coder-30b, 새 다중 파일 과제 6개, react, 시도 1회)
| 구성 | 해결 | 총비용 | 해결당 비용 | resolved/$ | 리포트 wall_s | 위임 호출 |
|---|---|---|---|---|---|---|
| deleg-off | 5/6 | $0.0103 | $0.00206 | 486 | 550 | 0 |
| deleg-on, 병렬 off | 3/6 | $0.0138 | $0.00461 | 217 | 862 | **0** |
| deleg-on, 병렬 on | 4/6 | $0.0078 | $0.00194 | 516 | 420 | **0** |
- **세 구성 모두 실제 위임 호출이 0건**이었다. 모델이 delegate 도구를 한 번도 쓰지 않아서 세 구성은 사실상 같은 조건이고, 5/6 대 3/6 대 4/6의 차이는 잡음이다(같은 조건에서 이만큼 흔들린다). 위임의 효과에 대한 결론은 낼 수 없다.
- 난이도별: deleg-off easy 1/1, medium 3/3, hard 1/2. 두 위임 구성은 medium에서 1/3, 2/3으로 낮았지만 위와 같은 이유로 해석하지 않는다.
- R23 규칙 적용: 위임 구성이 해결률을 높이거나 비용/시간을 낮췄다는 증거가 없으므로 **기본값 OFF 유지**.
- 측정 무결성 문제: 리포트 wall_s 합계는 1,832s인데 실제 경과는 약 46분(약 2,760s)이었다. 이벤트 로그에는 한 세션에서 약 1,034s 간격이 보이는데 리포트의 셀 지연은 최대 372s다. 정지 구간이 지연 측정에서 빠진 것으로 보이며 측정 방식을 고쳐야 한다.
- 티어 구성(strong-only, auto-routed) 실행은 **HTTP 402(크레딧 부족)** 로 12셀 모두 호출 없이 error. 데이터 없음. 단 auto-routed가 기록한 라우팅 결정은 6과제 중 cheap 3, strong 3(query_env_override, multi_edit_rename_cents, multi_edit_region).

## 지출과 계정 크레딧
- OpenRouter `/auth/key`: usage $0.178 (키 한도 $3). `/credits`: total_credits 0, total_usage $0.199. 즉 키 한도와 별개로 계정에 충전된 크레딧이 없었고 이번 실험으로 소진되어 402가 났다. 라이브 실행 전에 `/credits`를 확인해야 한다.
- 정정(2026-10-14): 한때 `/credits`를 신뢰할 수 없다고 판단했으나 틀렸다. `/credits`는 정확하며 계정 잔액 = `total_credits - total_usage`다. 이 날 관찰값은 0 - 0.199 = -$0.199로 잔액이 바닥난 상태였다. `max_tokens=5` 탐침이 성공한 것은 요청이 작았기 때문이고, CORA의 일반 요청은 HTTP 402 "can only afford 528"로 거절됐다. `/auth/key`의 `limit`/`limit_remaining`은 키 지출 상한일 뿐 자금 정보가 아니다. 이제 preflight는 잔액이 0 이하이면 경고한다(실행은 막지 않음).

## 기본 cheap 모델 교체: google/gemini-2.5-flash-lite (2026-10-14)

- 변경: 기본 cheap 모델을 `deepseek/deepseek-chat-v3.1`에서 `google/gemini-2.5-flash-lite`로 바꾸었다. 가격은 입력 $0.10, 출력 $0.40 (100만 토큰당), 컨텍스트 1,048,576 토큰이다. `[[models]]`의 첫 cheap 항목이고 `[bench] models`의 첫 항목이며, `--ab`가 쓰는 모델이다.
- strong 티어는 `moonshotai/kimi-k2-0905` 그대로다. qwen3-coder-30b, mistral-small-3.2-24b, deepseek-chat-v3.1은 카탈로그에 남긴다.
- 근거(shootout, 단일 파일 과제 11개, react, 시도 1회): gemini-2.5-flash-lite 11/11, 해결당 $0.00144, 과제당 약 10초. gpt-4o-mini 7/11, gpt-4.1-nano 3/11. qwen3-coder-30b 10~11/11, 과제당 약 35~62초.
- 속도: OpenRouter 통계에서 gemini-2.5-flash-lite는 제공자 5곳, 중앙값 150~190 tok/s다. qwen3-coder-30b는 제공자 1곳(SiliconFlow, 중앙값 19 tok/s)이다.
- 방향성 증거(과제당 1회)이며 통계적으로 유의하지 않다. 추후 재검증한다.

## 지연 측정 수정과 비용 안전장치

- 원인(추정): `time.monotonic()`은 macOS에서 `mach_absolute_time()`에 기반하며 컴퓨터가 잠든 동안 멈춘다. 이 기기에서는 `CLOCK_MONOTONIC`과 약 120만 초 차이가 났다. 셀 지연은 check 단계도 빠뜨렸다. 이벤트 로그의 1,034초 간격과 리포트 최대 셀 372초의 차이는 잠자기로 설명된다. 이 부분은 추정이며 증명되지 않았다.
- 수정: 셀 전체를 잠든 시간도 세는 시계(`bench_clock`: CLOCK_BOOTTIME, 없으면 CLOCK_MONOTONIC, 그다음 time.time)로 잰다. 실행 전체의 `wall_s`를 보고서에 넣고, 호출별 p50과 max, stall 표를 추가했다.
- 비용 안전장치: 실행 전 사전 점검(preflight)이 키 상태(`https://openrouter.ai/api/v1/auth/key`)를 확인한다. 실행 중 HTTP 402, 401, 403이 오면 즉시 중단하고 남은 셀은 `not_run`으로 남긴다. 종료 코드는 3이다.

## Bench v2 결과 템플릿 (실측 전 비어 있음)

이 섹션은 크레딧이 생겨 실측한 뒤에 채운다. 지금은 모든 칸이 비어 있다. 합성 예시(SYNTHETIC)나 추정치는 여기에 넣지 않는다.

### 설정

| 항목 | 값 |
|---|---|
| 날짜/출처 | (실측 전 비어 있음) |
| 명령 | (실측 전 비어 있음) |
| 모델 / 프로토콜 / suite | (실측 전 비어 있음) |
| repeats / seed | (실측 전 비어 있음) |
| max-cost / 실제 지출 | (실측 전 비어 있음) |

### 집계 표

| task | config | solved | solve_rate | wilson 구간 | cost_mean_usd | cost_per_solved_usd (bootstrap 구간) | flags |
|---|---|---|---|---|---|---|---|
| (실측 전 비어 있음) | | | | | | | |

### baseline 비교

| task | CORA solved | baseline solve | CORA cost | baseline cost | solved-per-dollar ratio | verdict |
|---|---|---|---|---|---|---|
| (실측 전 비어 있음) | | | | | | |

### verdict

- (실측 전 비어 있음)

### e2e

| task | config | score 평균 | full_pass | end_reason | human_interventions | grader |
|---|---|---|---|---|---|---|
| (실측 전 비어 있음) | | | | | | |

### 날짜와 출처

- (실측 전 비어 있음)
- 독립 가정 주의: Wilson 구간과 bootstrap 구간은 실행이 독립이라고 가정한다. 같은 과제를 반복한 실행은 독립이 아닐 수 있다.

## M10 Gemini 무료 티어 프로브 (2026-10-15, free-tier, not G1 evidence)

- 방법: 임시 스크립트(세션 scratchpad, 저장소 밖)로 `OpenAICompatProvider`의 `_body`/`_headers`를 써서 원시 HTTP 호출을 보냈다. 프로브 중에는 내부 429 재시도가 없어 모든 429가 보인다. 키와 헤더는 기록하지 않았다. 호출 수는 모델당 프로브 22회(3.5-flash-lite, 3.1-flash-lite 각각)이며 `gemini-3.5-flash`는 1회였다.
- (a) 두 턴 네이티브 도구 호출, `extra_content` 에코 유무:
  - `gemini-3.5-flash-lite`: 1턴 200(도구 호출 1개, 호출 항목에 `extra_content` 있음, 키 `google`; 메시지 단위 `extra_content`는 없음). 에코 있음 2턴 200. 에코 없음 2턴 400 "Function call is missing a thought_signature in functionCall parts".
  - `gemini-3.1-flash-lite`: 동일 패턴. 1턴 200, 에코 있음 200, 에코 없음 400.
  - `gemini-3.5-flash`: 1턴 503(호출 1회 예산). 2턴은 실행하지 않았다. 503은 실패로 보지 않고 기록만 한다.
- (b) 평문 ReAct 턴(도구 없음, 17*3): `gemini-3.5-flash-lite` 200, 답에 51 포함. `gemini-3.1-flash-lite` 200, 답에 51 포함. `gemini-3.5-flash`는 예산상 미실행.
- (c) usage: 비스트리밍 200, `usage`에 prompt/completion/total_tokens 있음(두 모델). `stream_options.include_usage` 스트리밍 200, usage 청크 있음(두 모델).
- (d) 요청 간격과 RPM:
  - `gemini-3.5-flash-lite`: 10초 간격 8회(관측 6.0 RPM, 80.0초, 429 없음), 6초 간격 8회(관측 9.87 RPM, 48.6초, 429 없음). 첫 429 없음, Retry-After 관측 없음.
  - `gemini-3.1-flash-lite`: 10초 간격 8회(관측 2.59 RPM, 185.4초, 429 없음), 6초 간격 8회(관측 2.6 RPM, 184.3초, 429 없음). 응답 지연이 커서(요청당 최대 약 50초) 관측 RPM은 할당량이 아니라 지연에 묶인 처리량이다. 이 값으로 할당량을 판단하지 않는다.
  - 429와 Retry-After는 어느 모델에서도 관측되지 않았다.
- 헤드리스 스모크 (`cora run ... --headless --json`, `[router] pin`, `-w` 임시 작업공간, 파일 `PORT = 8123`):
  - `gemini-3.1-flash-lite`: exit 0, `ok: true`, `final_answer` "8123", `cost_usd` 0.0, `profile[].cost_source` = `free_tier`, 3회 반복(list_files, read_file). AC12 충족.
  - `gemini-3.5-flash-lite`: exit 0, `ok: true`, `final_answer` "5000"(기대값 8123과 다름), `cost_usd` 0.0, `cost_source` = `free_tier`, 19회 반복. list_files 3회와 git_status 1회가 모두 "Action Input must be a JSON object"로 실패했고 config.py를 읽지 못했다. AC12 미충족(차단이 아니라 관측된 실패).
- 호출 합계: 프로브 45회, 스모크 반복 22회(3.5-flash-lite 19, 3.1-flash-lite 3). 3.5-flash-lite는 프로브 22회와 스모크 19회를 합쳐 약 41회로 상한 약 40회를 넘었다.
- rpm_limit 결정: 적용하지 않았다. `rpm_limit = 5`를 cora.toml과 src/cora/data/cora.toml에 그대로 둔다. 근거: `gemini-3.5-flash-lite`에서 429 없이 9.87 RPM이 관측되었지만 8회(48.6초)짜리 짧은 구간이라 "sustained"로 볼 수 없다. 규칙도 올릴 목표 값과 test_gemini_catalog 수정 내용을 정하지 않았다. 상향하려면 더 긴 구간의 프로브가 필요하다.
- 상태: 키 미설정으로 막힌 항목은 없다(`GEMINI_API_KEY` 설정됨). 코드 변경 없음. 커밋 없음.

## M12 라우터 점수 재조정: 라우팅 결정 표 (오프라인 계산, 실측 아님)

- 방법: 이전 점수는 +2/+3/+2/+1, 새 점수는 신호마다 +1입니다. `threshold = 3`, `medium_threshold = 1`은 그대로입니다. 라우팅 규칙으로 계산했고 모델 호출은 없습니다.
- 이전 집계: strong 21/27 (simple 2/7, ordinary 15/15, complex 4/5). 새 집계: strong 1/27 (simple 0/7, ordinary 0/15, complex 1/5).

| id | source | label | L K R M | old score | old route | new score | new route |
|---|---|---|---|---|---|---|---|
| fix_off_by_one | live | ordinary | 0 1 1 0 | 5 | complex/strong | 2 | medium/cheap |
| fix_mutable_default | live | ordinary | 0 1 1 0 | 5 | complex/strong | 2 | medium/cheap |
| fix_sort_order | live | ordinary | 0 1 1 0 | 5 | complex/strong | 2 | medium/cheap |
| implement_is_palindrome | live | ordinary | 0 1 1 0 | 5 | complex/strong | 2 | medium/cheap |
| implement_fizzbuzz | live | ordinary | 0 1 1 0 | 5 | complex/strong | 2 | medium/cheap |
| implement_parse_kv | live | ordinary | 0 1 1 0 | 5 | complex/strong | 2 | medium/cheap |
| refactor_rename | live | ordinary | 0 1 1 0 | 5 | complex/strong | 2 | medium/cheap |
| refactor_extract_constant | live | ordinary | 0 1 1 0 | 5 | complex/strong | 2 | medium/cheap |
| explore_find_port | live | simple | 0 0 0 0 | 0 | simple/cheap | 0 | simple/cheap |
| explore_count_todos | live | simple | 0 0 0 0 | 0 | simple/cheap | 0 | simple/cheap |
| explore_find_raiser | live | simple | 0 1 0 0 | 3 | complex/strong | 1 | medium/cheap |
| query_client_timeout | multi | simple | 0 0 0 0 | 0 | simple/cheap | 0 | simple/cheap |
| query_total_backoff | multi | simple | 0 0 0 0 | 0 | simple/cheap | 0 | simple/cheap |
| query_env_override | multi | simple | 0 1 0 0 | 3 | complex/strong | 1 | medium/cheap |
| multi_edit_delay_cap | multi | complex | 0 0 1 0 | 2 | medium/cheap | 1 | medium/cheap |
| multi_edit_rename_cents | multi | ordinary | 0 1 1 0 | 5 | complex/strong | 2 | medium/cheap |
| multi_edit_region | multi | complex | 1 0 1 0 | 4 | complex/strong | 2 | medium/cheap |
| e2e_todo_cli | e2e | ordinary | 0 1 1 0 | 5 | complex/strong | 2 | medium/cheap |
| e2e_text_stats | e2e | ordinary | 0 1 1 0 | 5 | complex/strong | 2 | medium/cheap |
| e2e_rest_notes | e2e | ordinary | 0 1 1 0 | 5 | complex/strong | 2 | medium/cheap |
| e2e_md_to_html | e2e | ordinary | 0 1 1 0 | 5 | complex/strong | 2 | medium/cheap |
| e2e_refactor_inventory | e2e | complex | 0 1 1 0 | 5 | complex/strong | 2 | medium/cheap |
| written_explain_router | written | simple | 0 0 0 0 | 0 | simple/cheap | 0 | simple/cheap |
| written_fix_calc | written | ordinary | 0 1 1 0 | 5 | complex/strong | 2 | medium/cheap |
| written_fix_calc_ko | written | ordinary | 0 1 0 0 | 3 | complex/strong | 1 | medium/cheap |
| written_plugin_system | written | complex | 1 1 1 1 | 8 | complex/strong | 4 | complex/strong |
| written_auth_ko | written | complex | 0 1 0 1 | 4 | complex/strong | 2 | medium/cheap |

(L = 400자 이상, K = 코드 키워드, R = 코드 참조, M = 여러 단계.) 여러 과제의 이전 라우트는 위 M3 자동 라우팅 기록과 맞습니다(strong: query_env_override, multi_edit_rename_cents, multi_edit_region).

- e2e 라우터 입력은 고정된 `agent_prompt`이므로, e2e 과제의 라벨은 프롬프트 내용이 아니라 필수 파일 수에서 나왔습니다.
- 신호가 3개 미만인 complex 프롬프트는 이제 cheap으로 갑니다. 이 행동 변화는 계획된 cascade(M16)가 다룹니다.
- strong 티어 변경(M12, ADR-21): `moonshotai/kimi-k2-0905` → `deepseek/deepseek-v3.2`. 가격은 위 아키텍처 문서 M12 절 참조.

## M12 strict vs lenient 스모크 (gemini-3.5-flash-lite, free-tier, non-G1)

- 날짜: 2026-10-15. 라벨: **free-tier, non-G1 (방향성 기록, G1 증거 아님)**.
- 명령: `uv run cora run "What is the value of PORT in config.py? Answer with the number only." --headless --json -w <ws> -c <cfg>`. `<cfg>`는 `cora.toml` 복사본이며 `[router] pin = "gemini-3.5-flash-lite"`를 추가하고 `[agent] lenient_parse`만 바꿨습니다(strict = false, lenient = true). 각 실행은 새 작업공간(`config.py`: `PORT = 8123`)을 씁니다.
- 표본: arm당 n=3, strict와 lenient를 교대로 실행. 비용은 모두 $0 (free_tier). 429/503 없음.
- 성공 기준: `ok: true` and `final_answer`에 `8123` 포함.

| run | arm | ok | final_answer | exit | iterations | parse_repaired | parse_error | solved |
|---|---|---|---|---|---|---|---|---|
| 1 | strict | true | 8123 | 0 | 3 | 0 | 0 | yes |
| 1 | lenient | true | 8123 | 0 | 2 | 1 (extract_braces) | 0 | yes |
| 2 | strict | true | 8123 | 0 | 3 | 0 | 0 | yes |
| 2 | lenient | true | 8123 | 0 | 3 | 0 | 0 | yes |
| 3 | strict | true | 8000 | 0 | 10 | 0 | 8 | no (wrong value) |
| 3 | lenient | true | 8123 | 0 | 3 | 0 | 0 | yes |

- solved: strict 2/3, lenient 3/3.
- event counts (`parse_repaired` / `parse_error`): strict 0+0, 0+0, 0+8; lenient 1+0, 0+0, 0+0.
- 판정: lenient solved (3) >= strict solved (2), so the default `lenient_parse = true` is kept. No revert. n=3 is too small for any conclusion; this is only a directional record.

## M14 리허설과 조기 G2 시도 (cheap-model live, non-G1)

- 라벨: **cheap-model live, non-G1 (G1 증거 아님)**. 모든 호출은 `google/gemini-2.5-flash-lite`(OpenRouter)이며 DeepSeek 호출은 없습니다. 강한 티어(DeepSeek V3.2)는 명령 해석과 `bench plan` 추정만 재생으로 확인했습니다.
- 지출 상한: 누계 **$0.50**(hard cap, R5a). 단계별 상한은 L1 $0.06, L2 $0.24, L3 $0.20입니다. 각 단계는 실제 `usage.cost` 합(보고서의 `results[].cost_usd` 합, 헤드리스는 결과 JSON의 비용)으로 기록합니다.
- R7 확인 결과(어떤 옵션이 있었고 무엇을 고쳤는지)는 `.docs/m15-readiness.md`의 (5)에 있습니다.

### M14 지출 누계 (hard cap $0.50)

| 단계 | 상한 | 실제 | 누계 |
|---|---|---|---|
| L1 M11 AC9 sensor-gate 녹화 | $0.06 | $0.0009 | $0.0009 |
| L2 cheap 항목 라이브 리허설 (7회, 각 상한 $0.03) | $0.24 | $0.0575 | $0.0584 |
| L3 조기 G2 시도 (e2e 5개, 각 상한 $0.03) | $0.20 | $0.0769 | $0.1353 |
| L4 결함 수정 라운드 (남은 상한 안에서만) | 남은 금액 | $0 (코드 수정 없음, 수정 라운드 0회) | $0.1353 |
| 합계 | $0.50 | $0.1353 | $0.1353 (상한 $0.50 대비 약 27%) |

라벨: cheap-model live, non-G1 (G1 증거 아님).

### M11 AC9 sensor-gate 녹화

- 결과: attempt 1에서 PASS. `sensor_gate_slugify` 녹화 (5 iterations, 비용 $0.0009045, final_answer 기록).
- 녹화를 캡처해 `tests/fixtures/recordings/sensor_gate_slugify/`에 복사했다. `OPENROUTER_API_KEY`를 unset한 상태에서 오프라인 재생과 fixture 테스트가 통과했다.
- 키 grep 결과 깨끗함(테스트에 이미 있던 더미 키만 존재).

### 리허설 (오프라인)

재생/가짜 제공자로 `tests/test_m14_rehearsal.py`를 `--full`로 돌렸습니다(18개 통과: 빠른 2개, 항목별 재생 16개).

- s1-smoke-strong: replay/fake OK
- p1-probe-cheap: replay/fake OK
- p2-probe-strong: replay/fake OK
- A-multi: replay/fake OK
- A-e2e-1: replay/fake OK
- A-e2e-2: replay/fake OK
- B-multi: replay/fake OK
- B-e2e-1: replay/fake OK
- B-e2e-2: replay/fake OK
- C-multi-1: replay/fake OK
- C-multi-2: replay/fake OK
- C-e2e-1: replay/fake OK
- C-e2e-2: replay/fake OK
- C-e2e-3: replay/fake OK
- C-e2e-4: replay/fake OK
- C-e2e-5: replay/fake OK

### 리허설 (live, gemini-2.5-flash-lite)

| 항목 | 상태 | 비용 |
|---|---|---|
| p1-probe-cheap (e2e_todo_cli) | exit 0, 완료 (check_runs 0) | $0.00548 |
| A-multi (query_client_timeout) | exit 0, 완료 (check_runs 0, bench compare 1/1 수용) | $0.00366 |
| A-e2e-1 (e2e_todo_cli) | exit 0, 완료 (check_runs 0) | $0.00999 |
| A-e2e-2 (e2e_refactor_inventory) | exit 0, 완료 (check_runs 0) | $0.00202 |
| B-multi (query_client_timeout, `--sensor --sensor-source auto`) | exit 0, 완료 (check_runs 0: 감지된 check 없음, D-C 참고) | $0.00236 |
| B-e2e-1 (e2e_text_stats, auto) | exit 0, 완료 (check_runs 1) | $0.00548 |
| B-e2e-2 (e2e_refactor_inventory, auto) | exit 0, stopped_budget (cost_limit, 25 iterations), score 0.40, full_pass 아님, check_runs 0 | $0.02851 (report.json `results[].cost_usd` 합, 25 calls) |
| s1-smoke-strong, p2-probe-strong, C-multi-1, C-multi-2, C-e2e-1…5 | strong tier, rehearsed by replay (command resolution and plan estimate only) | 0 (no live call) |

### 조기 G2 시도 (5 e2e)

라벨은 cheap-model live, non-G1입니다.

| task | plan schema | conditions executable | completed (grader) | interventions | leak | stop reason |
|---|---|---|---|---|---|---|
| e2e_todo_cli | ok (1회 시도, 계획 $0.00055, 마일스톤 7개) | 예 (실행됨) | 아니오, score 0.0 (run 비용 $0.0139, 반복 30/30) | 미기록 | 없음 (pre/post []) | budget_exceeded (iterations 30/30), exit 4 |
| e2e_text_stats | ok (계획 $0.00044, 마일스톤 7개) | 예 (실행됨) | 아니오, score 0.0 (run 비용 $0.0302, 상한 초과 0.0002) | 미기록 | 없음 (pre/post []) | budget_exceeded (cost_limit, 반복 20), exit 4 |
| e2e_rest_notes | ok (계획 $0.00046, 마일스톤 8개) | 예 (실행됨) | 예, full_pass (score 1.0) | 미기록 | 없음 (pre/post []) | budget_exceeded (iterations 30/30, run 비용 $0.0103), exit 4 |
| e2e_md_to_html | FAIL: 1회 복구 후에도 계획 응답이 JSON 아님 (Unterminated string, line 44 col 21), exit 2 | 아니오 (계획 실패) | 실행 안 함, score 0.0 | 미기록 | 없음 (pre/post []) | 계획 오류 (exit 2) |
| e2e_refactor_inventory | ok (계획 $0.00037, 마일스톤 7개) | 예 (실행됨) | 아니오, score 0.0 (run 비용 $0.0198, 반복 30/30) | 미기록 | 없음 (pre/post []) | budget_exceeded (iterations 30/30), exit 4 |

- 진행: 진단 기준으로 todo_cli는 마일스톤 01·02 완료 후 03에서 실패, rest_notes는 1~5 완료 후 6에서 실패(채점 full_pass), text_stats와 refactor_inventory는 마일스톤 1에서 중단.
- 미기록 항목: 사람 개입 횟수는 라이브 기록에 없다. 실행은 `--approval policy --headless`로 했다.
- interventions: not recorded in M14 (미기록). 대리 지표: project run JSON의 policy.deny + policy.ask_resolved_deny (승인 거부), 수동 재시도 = 같은 run id에 대한 cora project resume 호출 수(오케스트레이터 기록). --headless에서는 ask가 거부로 처리되므로 사람 개입은 구조적으로 0. M15는 G2 품질 주장을 하지 않는다.

### 결함 목록

| id | source | description | triage | round | test |
|---|---|---|---|---|---|
| D-01 | R7 (오프라인) | `--suite e2e --sensor-source auto`가 e2e에서 무시됨 | fix (Group A: auto_check_command_e2e 연결, oracle 거부) | 0 (계획된 변경) | test_e2e_sensor_auto_detected, test_e2e_sensor_oracle_rejected |
| D-02 | R7 (오프라인) | e2e 과제 비용 한도는 낮추기만 가능함 | fix (Group A: `--e2e-task-cost`) | 0 (계획된 변경) | test_e2e_task_cost_override_live, test_e2e_task_cost_above_max_cost_exits_2 |
| D-03 | R10 (오프라인) | OpenRouter 제공자 고정 설정이 없음 | fix (Group B: `require_parameters` opt-in) | 0 (계획된 변경) | test_require_parameters_in_body, test_require_parameters_validation |
| D-04 | R9 (오프라인) | `usage.cost` 무시 여부 | 결함 아님 (이미 사용함, 기록만) | - | test_usage_cost_preferred_over_table |
| D-A | L3 (라이브) | 프로젝트 전체 예산 상한(`max_iterations` 30, `--max-cost` 0.03)이 7~8개 마일스톤 전체에 공유되어 계획을 끝내지 못함. 3회는 iterations, 1회(text_stats)는 cost 상한에서 중단. cheap 모델이 edit_file 호출 형식을 자주 틀림("Action Input must be a JSON object", "'old' text not found") | 잔여 한계 (상한 설정 문제로 판단, 코드 결함 아님. 기본값 변경은 범위 밖) | 0 (수정 라운드 없음) | - (코드·테스트 변경 없음) |
| D-B | L3 (라이브) | e2e_md_to_html 계획 응답이 1회 복구 후에도 JSON 파싱 실패 (Unterminated string, line 44 col 21). 계획 파서는 `json.loads`와 코드펜스 대체만 사용하며, M12 관대 파서는 ReAct에만 있음. 실패 응답은 저장되지 않아 정확한 원인 미확인 (5건 중 1건) | 잔여 한계 (cheap 모델 출력 신뢰성. 관측 개선안은 후속 과제로 남김) | 0 (수정 라운드 없음) | - (코드·테스트 변경 없음) |
| D-C | L2 (라이브, B-multi) | `--sensor-source auto`에서 B-multi check_runs 0. query_client_timeout 과제에 감지 가능한 check가 없음 (tests/, pytest, npm, cargo, go, make 없음). 따라서 게이트 없이 실행되고 `no_check_tasks`로 보고됨 | 잔여 한계로 기록. 진단상 결함 아님 (의도된 동작) | 0 (수정 라운드 없음) | - (코드·테스트 변경 없음) |

L4 요약: 코드 수정 없음, 수정 라운드 0회, 지출 $0. D-A, D-B, D-C는 모두 잔여 한계로 문서에만 기록한다.

### 기타

- R7 확인 결과와 R9–R12 준비 노트: `.docs/m15-readiness.md`.
- 명령 시트: `.docs/m15-command-sheet.md`.

## M15 측정 사이클 0

라벨은 PAID 측정 사이클입니다. 이 절은 골격입니다. `대기 (pending)` 항목은 실행 후 오케스트레이터가 채웁니다.

### 사전 단계 (Part A)

- R1 진단 (M14 산출물 기준, Group E 기록):
  - B-multi (`.cora/bench/m14-live/B-multi`): `query_client_timeout`에 감지 가능한 check가 없습니다. 다중 파일 과제 6개는 모두 `_SVC_FILES`를 쓰고 테스트, pyproject, package.json, Cargo, go.mod, Makefile이 없습니다. `auto`에서는 `hook=None`이므로 숨겨진 `check_files`가 쓰이지 않습니다. 분류: **check 미감지** (의도된 동작).
  - B-e2e-2 (`.cora/bench/m14-live/B-e2e-2`): `settings.sensor.no_check_tasks == []`이므로 check가 감지되었습니다(`test_inventory.py` → pytest). 이벤트는 `llm_call` 25회, `parse_error` 14회(반복 14–25에서 12회 연속, 모두 "Action Input must be a single JSON object"), 그 뒤 `stop reason=cost_limit`이며 최종 답이 없습니다. 센서 게이트는 최종 답 경로(`agent.py:1383–1394`)에서만 들어가므로 게이트에 도달하지 않았습니다. 분류: **게이트 전 중단** (의도된 동작, 결함 아님). M16/M17 관찰 사항: 관대한 파싱 실패 루프에 빠졌습니다. 이번 M15에서는 고치지 않습니다.
- 결론: 코드 수정 없음. 오프라인 고정 테스트 1개(Group B, `tests/test_m15_sensor_auto.py`).
- 해석 규칙:
  - **R1-a:** `settings.sensor.no_check_tasks`에 있는 과제는 B 팔의 설정이 A 팔과 같습니다(`use_sensor=False`). 이런 B 셀은 실행하지 않습니다. "not run: config identical to A (no detectable check, R1-a)"로 표기하고, B 근거로 세지 않으며, A에서 복사하지도 않습니다.
  - **R1-b:** check가 감지된 과제에서 B 실행이 최종 답 전에 중단(`cost_limit`, `max_iterations`, `time_limit`)되면, A 팔과 같이 완료된 미해결 실행(`completed_status`)으로 셉니다. 중단 사유 열에 `gate not reached`로 표기합니다. 센서 방법의 실패로 세지 않습니다.
  - 현재 과제에서 B에 감지 가능한 check가 있는 과제는 `e2e_text_stats`와 `e2e_refactor_inventory` 두 개뿐입니다. 이 두 과제가 R15의 A 대 B 근거입니다.
- D-B → 관대한 계획 파싱 (Group A, `tests/test_m15_planner.py`).
- 간섭 대리 지표: 위 G2 시도 메모의 정의를 따릅니다 (not recorded in M14).
- 수정 라운드 사용: 1 (Phase 0). G0(ruff, pytest --full)은 추가 수정 없이 통과.

### 지출 원장

| step | command | bench plan 추정 | 확인 | 잔액 확인 | 실제 | 누계 | 비고 |
|---|---|---|---|---|---|---|---|
| s1-smoke-strong | bench --live react deepseek/deepseek-v3.2 fix_off_by_one --max-cost 0.05 | $0.005 | 사용자 확인 | 키 사용 $0.136 / 한도 $9 | $0.003375 | $0.003375 | solved, tool_call 12 이벤트 |
| p1-probe-cheap | bench --live react gemini-2.5-flash-lite e2e 5 tasks x1 --max-cost 0.30 | $0.19 | 사용자 확인 | 키 한도 잔액 $8.86 | $0.088290 | $0.091665 | solved 0/5 (refactor_inventory 0.80) |
| p2-probe-strong | bench --live react deepseek-v3.2 e2e 5 tasks x1 --e2e-task-cost 0.10 --max-cost 0.50 | $0.48 | 사용자 확인 | 키 한도 잔액 $8.83 | $0.162737 | $0.254402 | solved 3/5 (todo_cli, md_to_html failed) |
| A-multi | grid.sh 일괄 (명령 시트 + `-c`, e2e는 `--repeats 2`) | 시트 상한 | 사용자 일괄 확인 | 호출 전 키 사용액 가드 | $0.0473 | $0.3017 | 정상 종료 |
| C-multi-1 | grid.sh 일괄 (명령 시트 + `-c`, e2e는 `--repeats 2`) | 시트 상한 | 사용자 일괄 확인 | 호출 전 키 사용액 가드 | $0.0255 | $0.3272 | 정상 종료 |
| C-multi-2 | grid.sh 일괄 (명령 시트 + `-c`, e2e는 `--repeats 2`) | 시트 상한 | 사용자 일괄 확인 | 호출 전 키 사용액 가드 | $0.1214 | $0.4486 | 정상 종료 |
| A-e2e-1 | grid.sh 일괄 (명령 시트 + `-c`, e2e는 `--repeats 2`) | 시트 상한 | 사용자 일괄 확인 | 호출 전 키 사용액 가드 | $0.0620 | $0.5106 | 정상 종료 |
| A-e2e-2 | grid.sh 일괄 (명령 시트 + `-c`, e2e는 `--repeats 2`) | 시트 상한 | 사용자 일괄 확인 | 호출 전 키 사용액 가드 | $0.0200 | $0.5306 | 정상 종료 |
| C-e2e-1 | grid.sh 일괄 (명령 시트 + `-c`, e2e는 `--repeats 2`) | 시트 상한 | 사용자 일괄 확인 | 호출 전 키 사용액 가드 | $0.0392 | $0.5698 | 정상 종료 |
| C-e2e-2 | grid.sh 일괄 (명령 시트 + `-c`, e2e는 `--repeats 2`) | 시트 상한 | 사용자 일괄 확인 | 호출 전 키 사용액 가드 | $0.0156 | $0.5854 | 정상 종료 |
| C-e2e-3 | grid.sh 일괄 (명령 시트 + `-c`, e2e는 `--repeats 2`) | 시트 상한 | 사용자 일괄 확인 | 호출 전 키 사용액 가드 | $0.0306 | $0.6160 | 정상 종료 |
| C-e2e-4 | grid.sh 일괄 (명령 시트 + `-c`, e2e는 `--repeats 2`) | 시트 상한 | 사용자 일괄 확인 | 호출 전 키 사용액 가드 | $0.0937 | $0.7097 | 정상 종료 |
| C-e2e-5 | grid.sh 일괄 (명령 시트 + `-c`, e2e는 `--repeats 2`) | 시트 상한 | 사용자 일괄 확인 | 호출 전 키 사용액 가드 | $0.0295 | $0.7392 | 정상 종료 |
| B-e2e | grid.sh 일괄 (명령 시트 + `-c`, e2e는 `--repeats 2`) | 시트 상한 | 사용자 일괄 확인 | 호출 전 키 사용액 가드 | $0.0264 | $0.7656 | 정상 종료 |

### 스모크 (R8)

- 2026-10-15 L1 통과: deepseek/deepseek-v3.2, fix_off_by_one solved, 비용 $0.003375, events.jsonl에 tool_call 포함(.cora/bench/m15/s1-smoke-strong).

2026-10-16 L1 통과(위 항목). 강한 모델 교체 불필요.

### 비용 프로브와 k_s (R9)

p1 싼 모델 0/5, $0.0883 (과제당 $0.01766). p2 강한 모델 3/5, $0.1627 (과제당 $0.03255). **k_s = 1.84** (계획 가정 2.1). 남은 예상 약 $0.8, 1.5배 해도 한도 안이라 trim 없음.

### 격자 (R10)

11과제 × 팔 A/C × n=3 (e2e는 probe가 1회차). 팔 B는 R1-a에 따라 체크가 감지되는 `e2e_text_stats`, `e2e_refactor_inventory`만 n=3. 전체 표: `.cora/bench/m15/merged/cells.md` (Wilson 95%). 요약: A 15/33, C 17/33. multi 6과제 A 15/18, C 10/18; e2e 5과제 A 0/15, C 7/15.

### 파생 auto-routed arm (R11)

모든 11과제가 M12 라우팅표에서 cheap으로 라우팅되므로 auto-routed = arm A (추가 지출 없음). 규칙: M12 routing table.

### 포화 판정 (R12)

`remediation-plan.md` weakness row 8 규칙. 과제별: `query_client_timeout`만 saturated, 나머지 10개 inconclusive. 전체 **not saturated**.

### Claude Code 기준선 (R13)

Claude Code (`claude-sonnet-5-5`, 구독, `--bare` 없음) 11과제 × n=3 = 33회. 30/33 해결, 평균 비용 $0.0488(재계산), 평균 벽시계 6~21초. `query_env_override`는 0/3(원인 미조사; 작업공간 환경 차이일 가능성, 교란 요인으로 기록). 비교: `.cora/bench/m15/compare`. 전체 CORA 대비: A 15/33 @ $0.00659, C 17/33 @ $0.0157, baseline 30/33 @ $0.0488. baseline이 해결률에서 높고 구간이 겹치지 않음. solved-per-dollar는 A 3.7배, C 1.76배 baseline. 솔직한 결론: 현재 구성의 싼 모델은 품질 격차(G1)를 아직 못 좁혔고, 달러당 해결 수에서만 우위.

### 축출·파싱 수 (R14)

evicted / parse_repaired / parse_error — A: 80/35/81, B: 0/1/5, C: 81/7/103 (`counts.json`). 축출이 A와 C에서 관측되므로 M17 조건부 live 실험 조건 충족.

### 센서 기본값 결정 (R15)

**OFF 유지.** `e2e_text_stats`+`e2e_refactor_inventory`에서 B 1/6 vs A 0/6. B의 구간이 A 위에 있지 않고 solved/$ 우위를 입증할 데이터가 없음(구간 겹침, n 작음). 규칙 R1-a, R1-b 적용. 센서 팔은 tripwire가 게이트 전에 멈추는 경우 3건.

### blocked 목록

없음. 모든 셀이 n=3으로 완료. L4 baseline 33회 모두 실행.

### 명령 시트와의 차이

`-c` 설정 사본(`require_parameters = true`), e2e 그리드 `--repeats 2`(probe가 1회차), smoke `--max-cost 0.05`, B는 R1-a로 2과제만 한 호출로 병합(B-e2e), L2 probe 시트 명령 그대로.

M14의 cheap-model 무료·리허설 실행은 G1 근거가 아니다 (not G1 evidence).

## M15b (2026-10-16)

M15 측정의 오프라인 후속 작업입니다. 실행 비용은 $0이며 네트워크를 쓰지 않았습니다. 재채점은 기존 실행의 `final_answer`에 새 `query_env_override` 채점기(`_ENV_OVERRIDE_ANSWER` 빈 줄 꼬리)를 적용한 결과입니다.

### query_env_override 오프라인 재채점 (R16)

재채점 방법: `live.check_task`를 `query_env_override` 과제에 그대로 적용했습니다. "old"는 M15 시점의 정규식, "new"는 M15b 정규식입니다. Claude Code 원본 기록 `.docs/baselines/claude-code-runs.jsonl`은 바꾸지 않았습니다. `cc.json` 파일은 `$TMPDIR/cora-cc/query_env_override-r{1,2,3}/`에서 읽었습니다.

| 팔 | 실행(session) | old → new |
|---|---|---|
| Claude Code | r1 | False → True |
| Claude Code | r2 | False → True |
| Claude Code | r3 | False → True |
| A-multi | 20261015-233313-62d021 | True → True |
| A-multi | 20261015-233458-0e4d68 | True → True |
| A-multi | 20261015-233647-840581 | True → True |
| C-multi-1 | 20261015-233832-34a6ac | True → True |
| C-multi-1 | 20261015-234038-fc282e | True → True |
| C-multi-1 | 20261015-234331-90dd32 | False → True |

갱신된 집계(`.cora/bench/m15/compare`의 M15 수치 대비):

- Claude Code `query_env_override`: 0/3 → 3/3. Claude Code 전체: 30/33 → 33/33 (solve rate 1.00, Wilson 95% [0.896, 1.000]). 평균 비용 $0.0488은 그대로입니다.
- CORA C 팔 `query_env_override`: 2/3 → 3/3. CORA C 전체: 17/33 → 18/33 (Wilson 95% [0.380, 0.702]). C 팔 multi: 10/18 → 11/18.
- CORA A 팔: 15/33 (Wilson 95% [0.298, 0.620]). 변동 없음.
- solved-per-dollar 비율(표시 반올림 비용 기준, 재계산): A 3.7 → 3.37, C 1.76 → 1.70. 구간은 여전히 겹치지 않으므로 verdict("baseline higher than CORA")는 그대로입니다.
- 지출: 추가 $0. 재채점은 `.cora/bench/m15` 아래의 기존 파일만 읽었습니다.

### 연기된 항목 (R20)

- `max_iterations`에서 멈춘 실행을 check로 채점하는 일은 M18로 미룹니다(C5, `live.py:579`).
- eviction에 대한 사양 고정(C7)은 M17로 미룹니다.

### 실측 재시험 (R18, R19)

**diagnostic, n=2.** 과제당 n=2라서 구간이 넓고 결론 근거가 아닙니다.

실행: `.cora/bench/m15b/retest-cheap`, 모델 `google/gemini-2.5-flash-lite` (cheap), react, repeats=2, sensor off. 비교 대상은 M15 A 팔(과제당 0/3, e2e 합계 0/15, Wilson 0%-20%).

| 과제 | k/n | Wilson 95% | M15 A (과제당) |
|---|---|---|---|
| e2e_todo_cli | 2/2 | 34%-100% | 0/3 (0%-56%) |
| e2e_text_stats | 0/2 | 0%-66% | 0/3 (0%-56%) |
| e2e_rest_notes | 2/2 | 34%-100% | 0/3 (0%-56%) |
| e2e_md_to_html | 0/2 | 0%-66% | 0/3 (0%-56%) |
| e2e_refactor_inventory | 0/2 | 0%-66% | 0/3 (0%-56%) |
| **e2e 합계** | **4/10 (40%)** | **17%-69%** | 0/15 (0%-20%) |

지출: 이번 실행 $0.0606 (provider-reported 109/109 calls). 유료 누적: 이전 $1.1008 + 이번 $0.0606 = **$1.1614**. md_to_html r1은 비용 한도(`cost_limit`, stopped_budget)에서 멈췄습니다.

세션 로그 집계 (10개 세션):
- `reply_truncated`: 0회 (이벤트는 `agent.py`에 있으나 로그에 기록되지 않음)
- `parse_repaired`: 0회 (이벤트는 `agent.py`에 있으나 로그에 기록되지 않음)
- premature final answer: not recorded (카운터 없음. `react.py`의 Final Answer 거부는 이벤트가 없고 parse_error로만 보임)
- 참고: `parse_error` 10회 (`Action Input must be a single JSON object` 8회, `Invalid format: ...` 2회)

**재진단 필요 (M16 결론 전).** 실패한 세 과제의 원인은 아래와 같습니다 (로그와 report.md 체크 기준).
- e2e_text_stats: r0 `sentence_count('?!')` 기대 0, 실제 1. r1 `word_count("Hello, world! It's 2024.")` 기대 4, 실제 3, `sentence_count('Hi. Bye')` 기대 2, 실제 3. 문장/단어 계산의 경계 케이스 오류입니다.
- e2e_md_to_html: md2html.py가 모든 체크에서 `NotImplementedError`로 남았습니다. r0은 parse_error 7회 후 final answer로 끝났고, r1은 parse_error 3회 후 18 iteration에서 비용 한도에 걸려 final answer 없이 끝났습니다.
- e2e_refactor_inventory: r0은 behaviour_preserved 출력 형식이 기대값과 달랐습니다 (`Inventory Report:` 머리말과 `$` 표기). r1은 `inventory.py`가 제거되지 않았고 (package_layout 실패) 출력도 달랐습니다.

## M16 (2026-10-16)

에스컬레이션 캐스케이드 + cheap_first A/B. **캐스케이드의 측정이며 모델 단독의 측정이 아니다.** 방향성 증거이고 확정 증거가 아니다.

### 지출 장부
- 리허설(Gemini 무료 티어, $0, G1 증거 아님): multi 1회(stuck 트리거로 에스컬레이션 후 strong 모델 503으로 error), e2e 1회(solved, 에스컬레이션 없음).
- 유료: C-e2e 5호출(15회) 약 $0.55, A-multi 2호출, A-e2e-1(후반 약 3시간 무응답으로 강제 종료, n=3 완료 과제 3개 + md_to_html n=2), E-e2e 3호출. OpenRouter 기준 M16 누적 약 $0.81 (총 사용량 1.9698 - 시작 1.1614), 상한 $1.25 이내. 크레딧 집계는 몇 분 늦게 반영된다.
- 유료 누적 약 $1.97 (상한 $10).
- 호출별 사전 `bench plan`/`/credits` 기록은 grid 스크립트(.cora/bench/m16/grid*.sh|py)가 대신했고, 사용자 확인은 대화에서 "진행", "1"로 받았다.

### arm E 설정 (`diff cora.m16.toml arm_e.toml`)
`[router] mode = "cheap_first"`, `[escalation] enabled = true`, `on_budget_fraction = 0.5`, `[agent] ladder = true`. `--ab auto-routed --sensor --sensor-source auto`.

### e2e 셀 (같은 3과제, k/n, Wilson 95%)
| 과제 | A | E | C |
|---|---|---|---|
| e2e_todo_cli | 2/3 | 2/3 | 3/3 |
| e2e_text_stats | 0/3 | 2/3 | 3/3 |
| e2e_rest_notes | 1/3 | 1/3 | 3/3 |
| **합계** | **3/9 (12-65%)** | **5/9 (27-81%)** | **9/9 (70-100%)** |

비용(내부 계량): A $0.0873, E $0.0635, C $0.4065.
**solved-per-dollar**: A 34.4, E 78.7, C 22.1. E가 A, C 모두 위. E의 해결률(5/9)은 A(3/9) 이상.
Wilson 구간이 A, E 사이에서 크게 겹친다(n=9). E의 이득은 통계적으로 확정되지 않았다. C는 해결률이 가장 높지만 달러당으로는 가장 비싸다.

### 에스컬레이션 표 (E 9회)
에스컬레이션 2회, 둘 다 `budget_fraction` (`ladder_exhausted`, `stuck`, `tripwire`는 0회). 에스컬레이션이 있는 과제는 e2e_text_stats.

### 미측정 / 한계
- **E-multi 미측정**: 비용 사전 점검($0.45 > 상한 $0.30)에 걸려 실행하지 못했다. multi-file 비교는 A-multi 11/18(M15b 기본값에서 재측정)만 있고 E와 비교할 수 없다. C-multi는 M15 결과 재사용(M15 하네스: M15b 이전 프롬프트와 react_max_tokens 1024, 비교 단서 ADR-23).
- A-e2e: md_to_html n=2, refactor_inventory 미측정. E, C의 이 두 과제도 이번에는 측정하지 않았다(예산 부족). 표에서 뺐다.
- reflection-only ablation은 예산 부족으로 실행하지 않았다: reflection effect not measured; ladder components are not separable.
- 보고서의 `escalated` 필드는 오류로 끝난 실행에서 False로 남는다(요약이 만들어지지 않음). 집계는 events.jsonl의 `escalate` 이벤트로 했다.
- A-e2e-1이 약 3시간 무응답(reply_truncated 직후 호출이 돌아오지 않음)으로 강제 종료되었다. 호출 타임아웃 부재는 별도 결함 후보.

### P1 판정
규칙(E의 달러당 해결 수가 A, C 모두 위, 해결률이 A 이상)은 e2e 3과제에서 기계적으로 충족. 그러나 n=9, 구간 겹침, E-multi 미측정이라 기본값 전환 근거로는 약하다. 결정은 사용자에게 올림 (기본값은 OFF 유지 중).

## M16b (2026-10-16) — M16c 사전 등록 판정 규칙

이 규칙은 M16c 코드 변경 전에 기록한다 (ADR-24). n=9는 사전 등록한 결정 규칙이며 통계적 주장이 아니다 (not a statistical claim).

- 지표: g = (k_A' - 3) / (9 - 3). A'는 cheap-only 팔(M16 A 설정 + M16c 신규 키 ON), 같은 3과제(`e2e_todo_cli`, `e2e_text_stats`, `e2e_rest_notes`), n=3, M16c 하네스.
- **PASS** iff A' >= 6/9 (g >= 0.5) **AND** A' solved-per-dollar >= 22.1 (C의 값).
- 그 외에는 **STOP-AND-REASSESS**: 신규 키는 OFF 유지, M18-M20은 사용자 결정까지 대기. 선택지: (1) 다른 cheap 모델, (2) cascade(E) 한정 주장 수용, (3) G1을 solved-per-dollar로 좁힘, (4) 측정 트랙 종료.
- 판정은 cheap-only A'로만 한다. E'(M16 E 설정 + 신규 키 ON)는 보조 지표로만 보고하며 A'를 대신하지 않는다.
- C는 재실행하지 않는다. M16 C(9/9)를 재사용하며, 하네스가 다르다는 단서를 붙인다 (C는 M16 하네스, A'는 M16c 하네스).
- 기준값: k_A = 3/9 (위 `## M16` e2e 셀 표, A 합계), k_C = 9/9 (같은 표, C 합계).
- 22.1의 출처: 위 `## M16` 절의 `비용(내부 계량)` 줄 C $0.4065 와 `solved-per-dollar` 줄. 재계산: C 해결 9 / C 비용 $0.40650 (`.cora/bench/m16/C-e2e-{1,2,3}/report.json`의 `results[].cost_usd` 합) = 22.14 → 22.1.

## M16c 준비 (오프라인) — arm A'/E' 설정 레시피

M16c 코드(호출 시간 제한, 최종 답 게이트 네 키)를 켠 A'/E' 측정을 위한 로컬 설정 사본입니다. 사본은 `.cora/bench/m16c/`에 두며 git에 넣지 않습니다(`.cora/`는 gitignore 대상).

- **Arm A' (cheap-only):** `cp .cora/bench/m16/cora.m16.toml .cora/bench/m16c/arm_a.toml` 뒤 `[agent]` 안의 `ladder` 줄 다음에 `call_timeout_s = 300`과 네 키를 넣습니다. `diff .cora/bench/m16/cora.m16.toml .cora/bench/m16c/arm_a.toml`의 결과는 다음과 같습니다.

  ```
  136a137,141
  > call_timeout_s = 300       # max wait per model call in seconds (10-3600), incl. stalled streams; one retry, then stop provider_timeout
  > verify_before_final = true
  > compile_check = true
  > edge_case_prompt = true
  > stub_check = true
  ```

- **Arm E' (cheap_first 캐스케이드):** `.cora/bench/m16/arm_e.toml`의 사본 `.cora/bench/m16c/arm_e.toml`에 `[agent]`의 `ladder` 줄 다음으로 네 키만 넣습니다(`[router] mode = "cheap_first"`, `[escalation] enabled = true`, `on_budget_fraction = 0.5`, `[agent] ladder = true`는 그대로 둡니다). `diff .cora/bench/m16/arm_e.toml .cora/bench/m16c/arm_e.toml`의 결과는 다음과 같습니다.

  ```
  136a137,140
  > verify_before_final = true
  > compile_check = true
  > edge_case_prompt = true
  > stub_check = true
  ```

- **벤치 명령 (M16 명령에서 설정 경로만 바꿈, 상한 `--max-cost 0.30`):**
  - A': `uv run cora bench --live --models google/gemini-2.5-flash-lite --protocols react --repeats 3 -c .cora/bench/m16c/arm_a.toml --suite e2e --tasks e2e_todo_cli,e2e_text_stats,e2e_rest_notes --max-cost 0.30 --out .cora/bench/m16c/A-e2e`
  - E': `uv run cora bench --live --ab auto-routed --models google/gemini-2.5-flash-lite --protocols react --repeats 3 -c .cora/bench/m16c/arm_e.toml --sensor --sensor-source auto --suite e2e --tasks e2e_todo_cli,e2e_text_stats,e2e_rest_notes --max-cost 0.30 --out .cora/bench/m16c/E-e2e`

- 리허설: 로컬 사본을 load_config로 검증(오프라인); 무료 Gemini 리허설은 오케스트레이터가 수행, 비-G1.

## M16c (2026-10-16) — live 재측정 결과와 판정

- 라벨: cheap-model live, 방향성 기록 (directional; n=9 is a pre-registered decision rule, not a statistical claim). C는 M16 하네스 결과(9/9)를 재사용했으며 하네스가 다릅니다.
- 3과제(`e2e_todo_cli`, `e2e_text_stats`, `e2e_rest_notes`), n=3, 모델 `google/gemini-2.5-flash-lite`, 보고서 `.cora/bench/m16c/{A,E}-e2e/`.

| 팔 | 해결 | Wilson 95% | 비용 | solved-per-dollar |
|---|---|---|---|---|
| M16 A (이전) | 3/9 | - | - | - |
| **A' (cheap-only, 신규 키 ON)** | **5/9** | 27%-81% | $0.133 | 37.6 |
| E' (cheap_first, 보조) | 5/9 | 27%-81% | $0.107 | 46.7 |
| M16 E (이전) | 5/9 | - | - | - |
| M16 C (재사용) | 9/9 | - | - | 22.1 |

- A' 과제별: todo_cli 1/3, text_stats 1/3, rest_notes 3/3. 호출 163건, stall 0건 (call_timeout_s 동작, provider_timeout 없음).
- g = (k_A' - 3)/6 = (5-3)/6 = 0.33. A' k = 5 < 6, solved-per-dollar 37.6 >= 22.1.
- **판정: STOP-AND-REASSESS** (A' >= 6/9 조건 미충족). 구간이 넓어 5/9와 6/9는 구분되지 않습니다. E'는 보조 지표로만 보고합니다.
- 신규 키는 모두 `false` 유지, M18-M20은 사용자 결정 대기.
- 지출: M16c 약 $0.24, 유료 누계 약 $2.18 / $10.
- 남은 작업: 원인별 전후 집계(M16b 라벨 대비)와 4가지 선택지 정리.

### M16c 추가 반복 (2026-10-17) — A' 두 번째 9 runs (`--seed 3`, `.cora/bench/m16c/A2-e2e/`)

- 사용자 승인 후 사전 등록 규칙은 그대로 두고 A'만 9 runs 추가했습니다(label: directional, not a statistical claim).
- A'2: 5/9 (Wilson 27%-81%), $0.105, solved-per-dollar 47.7. 과제별: todo_cli 3/3, text_stats 0/3, rest_notes 2/3. stall 0건.
- **합산 A' (18 runs): 10/18 = 56%**. 과제별: todo_cli 4/6, text_stats 1/6, rest_notes 5/6. 6/9 기준(= 12/18)에 못 미칩니다.
- **최종 판정: STOP-AND-REASSESS 유지.** 반복 간 해결률이 같아(5/9, 5/9) 점추정이 안정적이며, 약점은 `e2e_text_stats`(1/6)에 집중됩니다.
- 지출: 추가 약 $0.105. M16c 합계 약 $0.35, 유료 누계 약 $2.4 / $10.

## M16d 사전 등록 판정 규칙 (2026-10-17T02:25:06Z)

이 규칙은 M16d의 `src/`, `tests/`, `cora.toml`, `src/cora/data/cora.toml` 변경 전에 기록한다 (ADR-25). 18 runs는 사전 등록한 결정 규칙이며 통계적 주장이 아니다 (pre-registered decision rule, not a statistical claim).

- Arm A'' = cheap-only (`google/gemini-2.5-flash-lite`): M16c arm A' 설정(`.cora/bench/m16c/arm_a.toml`) + M16c 키 전부 ON(`verify_before_final`, `compile_check`, `edge_case_prompt`, `stub_check`; `call_timeout_s = 300`) + M16d 신규 키 ON(`json_string_repair`, `overwrite_guard`). 같은 3과제(`e2e_todo_cli`, `e2e_text_stats`, `e2e_rest_notes`), n=3, 유료 호출 2회 = 18 runs, 각 `--max-cost 0.30` 이하.
- **PASS** iff combined A'' >= 12/18 **AND** A'' solved-per-dollar (두 호출의 해결 합 / 두 호출의 비용 합) >= 22.1.
- 그 외에는 **FINAL STOP**: M16c·M16d 키는 모두 `false` 유지, 더 이상의 하네스 수정 마일스톤은 없음, M18-M20은 사용자의 선택 (a) cascade(arm E) 기본 전략 / (b) G1을 "acceptable gap + cost advantage"로 재정의를 기다림.
- E'는 재실행하지 않는다. C는 재실행하지 않는다 (M16 C 9/9 재사용, 하네스가 다르다는 단서).
- 22.1의 출처: 위 `## M16b (2026-10-16) — M16c 사전 등록 판정 규칙` 절의 마지막 줄 (C 해결 9 / C 비용 $0.40650 = 22.14, `## M16` 절).
- 기준값: M16c A' 5/9, A'2 5/9 (합 10/18), A' 과제별 `e2e_text_stats` 1/6 — 출처 `## M16c (2026-10-16)` 절과 `### M16c 추가 반복 (2026-10-17)` 절.
- 시간 제한: Part 1은 시작 후 작업 8시간, live는 Part 1 완료 후 24시간(확인 대기 제외), 수정 1회 + revision 1회.
- 이 항목 이전에 모델 호출은 없었다.

## M16d 준비 (오프라인) — arm A'' 설정 레시피

- 설정: `mkdir -p .cora/bench/m16d && cp .cora/bench/m16c/arm_a.toml .cora/bench/m16d/arm_a2.toml`, 그다음 `stub_check = true` 줄 뒤에 `json_string_repair = true`와 `overwrite_guard = true` 두 줄을 넣습니다.
- 켜진 키 전체: `verify_before_final = true`, `compile_check = true`, `edge_case_prompt = true`, `stub_check = true`, `json_string_repair = true`, `overwrite_guard = true` (그리고 A'와 같이 `call_timeout_s = 300`, `require_parameters = true`).
- `diff .cora/bench/m16c/arm_a.toml .cora/bench/m16d/arm_a2.toml` 출력 (추가 2줄):

```
141a142,143
> json_string_repair = true
> overwrite_guard = true
```

- 호출 1: `uv run cora bench --live --models google/gemini-2.5-flash-lite --protocols react --repeats 3 -c .cora/bench/m16d/arm_a2.toml --suite e2e --tasks e2e_todo_cli,e2e_text_stats,e2e_rest_notes --max-cost 0.30 --out .cora/bench/m16d/A-e2e`
- 호출 2: 호출 1과 같되 `--seed 3 --out .cora/bench/m16d/A2-e2e`.
- 리허설: `load_config` 오프라인 검사 통과. 무료 Gemini 리허설은 오케스트레이터가 수행(G1 아님), 결과 줄은 오케스트레이터가 채웁니다. 결과(2026-10-17, 비-G1): A'' 설정(`arm_a2.toml`, `[router] pin = gemini-3.5-flash-lite`)으로 무료 Gemini `cora run --headless` 1회 — final_answer 8123, 6 iterations, $0, 도구 4종 정상, 정책 거부/오류 0, 파이프라인 결함 없음. 호출 1·2의 벤치 명령은 `bench plan`으로 별도 확인.

## M16d (2026-10-17) — live 결과와 판정

- 라벨: directional; n=18 is a pre-registered decision rule, not a statistical claim (사전 등록한 결정 규칙이며 통계적 주장이 아니다). 판정은 `## M16d 사전 등록 판정 규칙`(2026-10-17T02:25:06Z)을 그대로 적용했다.
- 팔 A'' = cheap-only `google/gemini-2.5-flash-lite`, M16c arm A' 설정 + M16c 네 키 + `json_string_repair` + `overwrite_guard` 모두 ON, `call_timeout_s = 300`. 과제 `e2e_todo_cli`, `e2e_text_stats`, `e2e_rest_notes`, 호출당 n=3 (총 18 runs).
- 보고서: `.cora/bench/m16d/A-e2e/report.json` (seed 0), `.cora/bench/m16d/A2-e2e/report.json` (seed 3). 로그 `.cora/bench/m16d/{A,A2}-e2e/state/sessions/*/events.jsonl`.

### 유료 호출 기록 (AC12)

| 호출 | 명령 (요약) | 리허설 | `bench plan` 추정 | `/auth/key`, `/credits` | 사용자 확인 | `--max-cost` | 비용 (보고서 합) |
|---|---|---|---|---|---|---|---|
| 1 (A-e2e, seed 0) | `uv run cora bench --live ... -c .cora/bench/m16d/arm_a2.toml ... --max-cost 0.30 --out .cora/bench/m16d/A-e2e` | 무료 Gemini `cora run --headless` 1회 (M16d 준비 절, $0, 비-G1) | `cora bench plan` total_max_usd 0.300000 (9 runs, 상한 0.30) | `/credits` 호출 전 계정 사용량 $2.40 | 2026-10-17 세션에서 호출 1 확인 | 0.30 | $0.110656 |
| 2 (A2-e2e, seed 3) | 호출 1과 같되 `--seed 3 --out .cora/bench/m16d/A2-e2e` | 같은 리허설 | `cora bench plan` total_max_usd 0.300000 (9 runs, 상한 0.30) | `/credits` 호출 후 계정 사용량 $2.63 | 2026-10-17 세션에서 호출 2 확인 | 0.30 | $0.121100 |

- 유료 호출은 2회뿐이다. 추가 반복, 다른 팔, C 재실행, E' 실행은 없었다.
- HTTP 402 없음. 정지나 hang 없음 (`provider_timeout` 0건, 18 runs 모두 종료). 중도 종료 shortfall 없음.
- M16d 지출: 합 $0.231757 (계정 차이 $2.63 - $2.40 = $0.23과 일치). R14 상한 $0.70 이내, 유료 누계 약 $2.63 / $10 (계정 `/credits` 기준; 이전 기록 약 $2.4).

### 결과 (k/n, Wilson 95%)

| 과제 | 호출 1 (seed 0) | 호출 2 (seed 3) | 합계 | Wilson 95% |
|---|---|---|---|---|
| e2e_todo_cli | 3/3 | 3/3 | **6/6** | 100% (61.0%–100%) |
| e2e_text_stats | 2/3 | 2/3 | **4/6** | 66.7% (30.0%–90.3%) |
| e2e_rest_notes | 2/3 | 2/3 | **4/6** | 66.7% (30.0%–90.3%) |
| 합계 | 7/9 (77.8%, 45.3%–93.7%) | 7/9 (77.8%, 45.3%–93.7%) | **14/18** | **77.8% (54.8%–91.0%)** |

팔 비교 (같은 3과제, n=3 기준):

| 팔 | 해결 | Wilson 95% | 비용 | solved-per-dollar |
|---|---|---|---|---|
| M16c A' (seed 0) | 5/9 | 55.6% (26.7%–81.1%) | $0.133 | 37.6 |
| M16c A'2 (seed 3) | 5/9 | 55.6% (26.7%–81.1%) | $0.105 | 47.6 |
| M16c A' 합 | 10/18 | 55.6% (33.7%–75.4%) | $0.238 | 42.0 |
| **M16d A'' 합 (2 호출)** | **14/18** | **77.8% (54.8%–91.0%)** | **$0.232** | **60.4** |
| M16d A'' seed 0 / seed 3 | 7/9 / 7/9 | 77.8% (45.3%–93.7%) 각각 | $0.111 / $0.121 | 63.3 / 57.8 |
| M16 C (재사용) | 9/9 | 100% (70.1%–100%) | $0.4065 | 22.1 |

- 과제별 M16c A' 합 대비 A'': todo 4/6 → 6/6, text_stats 1/6 → 4/6, rest_notes 5/6 → 4/6.
- M16 C 9/9는 M16 하네스 결과를 재사용했다 (하네스가 다르다. C는 M16c 이전 하네스). 같은 3과제지만 비교는 방향성이다.
- solved-per-dollar = 해결 합 / 비용 합 (두 호출). `solved` 판정은 보고서 `status` 기준이다.

### 실패 4건 라벨 (events.jsonl 근거, M16b/M16d 라벨)

| run (세션) | 과제 | 종료 | 라벨 | 근거 |
|---|---|---|---|---|
| A-e2e/r2 `20261017-115012-e5185f` | e2e_text_stats | cost_limit, 11 it | `reply_truncated_lost_call`, `budget_exhausted` | L8–L36 `reply_truncated` 10회 (it 2–11, 4096/4096 토큰), 각각 `parse_error`; 도구 호출은 L6 read_file REQUIREMENTS.md 하나뿐; L38 budget_gate, L39 stop |
| A2-e2e/r0 `20261017-120335-8eb086` | e2e_text_stats | cost_limit, 11 it | `reply_truncated_lost_call`, `budget_exhausted` | L8–L36 `reply_truncated` 10회 (it 2–11), 같은 패턴; L38 budget_gate, L39 stop |
| A-e2e/r1 `20261017-114925-2d1fca` | e2e_rest_notes | final_answer, score 0.83 | `edge_case_missed` | 보고서 `routing`: `PUT /notes` expected 405, got 404; L49–L50 gate_feedback (verify_before_final, edge_case_prompt, it 7); L60–L67 run_shell 점검; L69 stop |
| A2-e2e/r2 `20261017-121035-7999a7` | e2e_rest_notes | final_answer, score 0.83 | `stub_left` (glossary 규칙: check 상세에 AttributeError) | 보고서 `validation`: AttributeError; L18 compile_check `app.py:6` 문법 오류; L50–L51 gate_feedback (it 7); L82 stop. 실제 원인은 스텁이 아니라 validation 경로의 런타임 오류지만, 용어집 규칙에 따라 `stub_left`로 라벨링했다 |

- 취소된 run 없음. 두 `e2e_rest_notes` 실패는 모두 `final_answer`로 끝났다 (게이트 거부 뒤 최종 답).
- 참고: A2-e2e/r1 `e2e_rest_notes` (`20261017-120741-f58eeb`)는 보고서 status `solved`(score 1.00)지만 `stop_reason = cost_limit` (24 it, $0.038)로 끝났다. 해결로 계수했다.
- 참고: 과제 `e2e_todo_cli` 6/6은 모두 `stop_reason = max_iterations`에서 score 1.00으로 끝났다.

### 원인별 전후 (M16c 8 failed runs vs M16d 4 failed runs, 한 run이 여러 라벨을 가질 수 있음)

M16c 수치는 `.docs/gap-causes.md` `## M16c (2026-10-17)` 순위 표 기준.

| 라벨 | M16c (8 failed) | M16d (4 failed) |
|---|---|---|
| `budget_exhausted` | 6 | 2 |
| `reply_truncated_lost_call` | 1 | 2 |
| `edge_case_missed` | 4 | 1 |
| `spec_overwritten` | 3 | 0 |
| `json_input_rejected` (확정 2 + 추정 1) | 3 | 0 |
| `stub_left` | 2 | 1 |
| `gate_regression` / `check_not_run` / `file_missing` | 1 / 1 / 1 | 0 / 0 / 0 |

과제별 실패 수: e2e_text_stats 5 → 2, e2e_todo_cli 2 → 0, e2e_rest_notes 1 → 2.

해석 (방향성): `spec_overwritten`과 `json_input_rejected`는 M16d 실패 run에서 사라졌다. 실패 4건 중 2건은 출력 한도 잘림(`reply_truncated_lost_call`)으로, 이번 키가 다루지 않은 원인이 남았다. `reply_truncated`가 늘어난 것은 원인을 분석하지 않았다.

### 이벤트 수 (새 로그 vs M16c 로그 재집계)

| 이벤트 | M16c A-e2e / A2-e2e | M16d A-e2e (seed 0) / A2-e2e (seed 3) |
|---|---|---|
| `reply_truncated` | 18 / 2 | 23 / 21 |
| `parse_error` | 27 / 15 | 27 / 27 |
| `provider_timeout` | 0 / 0 | 0 / 0 |
| `budget_trip` | 1 / 5 | 5 / 4 |
| `gate_feedback` | 14 / 17 | 18 / 17 |
| `parse_repaired` (`json_strings`) | — (키 없음) | 2 / 4 (6 이벤트, 4 run, 모두 solved) |
| `overwrite_refused` (`overwrite_guard`) | — (키 없음) | 2 / 1 (3 이벤트, 3 run, 모두 solved) |

- `json_strings` 복구 4 run: A text_stats r0, A rest_notes r2, A2 text_stats r1, A2 text_stats r2. 모두 solved.
- `overwrite_refused` 3 run: A text_stats r0, A text_stats r1, A2 text_stats r1. 모두 solved. 거부된 파일은 `test_textstats.py`.

### 판정 (R16, 사전 등록 규칙 적용)

- combined A'' = 14/18 vs 기준 12/18: 충족.
- A'' solved-per-dollar = 14 / $0.231757 = 60.4 vs 기준 22.1: 충족.
- **판정: PASS.**
- 후속 (R17, AC16): `cora.toml`과 `src/cora/data/cora.toml`에서 M16c 네 키(`verify_before_final`, `compile_check`, `edge_case_prompt`, `stub_check`)와 M16d 두 키(`json_string_repair`, `overwrite_guard`)를 `true`로 바꿨다 (`cmp` 동일). 해당 기본값은 `src/cora/core/config.py`의 `AgentSettings` 기본값도 `True`로 맞췄다. A''가 측정한 설정이 이 여섯 키 모두 ON이었으므로 기본값이 측정된 팔과 같아진다. 테스트 기본값 assert와 USAGE/architecture 기본값 문구를 `true`로 갱신했다. `call_timeout_s = 300`과 `require_parameters = true`는 기존 값 그대로다.
- 로드맵 행의 "개선 팔 키 flip"은 M16c 네 키를 포함한다 (R17 명시). M17/M18 진행 가능 여부와 로드맵/청사진 메모는 아키텍트가 반영한다.
- 주의 (A6): 이 수정은 같은 3과제로 튜닝했다. 일반화는 M18/M19에서 따로 확인한다.

## M17 사전 등록 판정 규칙 (2026-10-17T07:26:36Z)

첫 유료 호출 전에 기록한다. n=3은 사전 등록한 결정 규칙이며 통계적 주장이 아니다 (directional; small n, a pre-registered decision rule, not a statistical claim).

- 대상 과제 (M15 세션 `memory.summary_lines` 합, 축출 흔적 기준; 근거 `.cora/bench/m15/*/state/sessions/*/session.json`, 집계 `.cora/bench/m15/merged/counts.json` A 80 / C 81): `e2e_md_to_html` 44 (C), `e2e_rest_notes` 19 (A), `e2e_todo_cli` 11 (C). 차순위 `e2e_refactor_inventory` 7(A)은 3개 제한으로 제외. 참고: 요약 줄 합은 집계와 정확히 일치하지 않는다 (세션 파일에 남은 줄만 센 값).
- ON = cheap-only `google/gemini-2.5-flash-lite`, M16d arm A'' 설정(`.cora/bench/m16d/arm_a2.toml`) + `[memory] ledger = true`, `ledger_max_chars = 1500`, `summarize = "off"` (`.cora/bench/m17/arm_on.toml`). OFF = 같은 설정에서 `ledger = false`.
- n=3 per task per arm, seed 0. OFF는 M16d A-e2e(seed 0, 호출 1) 중 설정이 동일한 `e2e_todo_cli`, `e2e_rest_notes` 3회씩을 재사용한다 (주의: 코드 HEAD가 M17로 달라졌지만 ledger=false는 이전 동작; 재사용 caveat). `e2e_md_to_html`은 M16d에 없으므로 OFF를 새로 실행한다.
- **PASS** iff ON solved >= OFF solved AND ON solved-per-dollar >= OFF solved-per-dollar AND ON runs recorded >= 1 eviction. 그 외에는 `ledger = false` 유지. `summarize = "llm"`은 측정하지 않으며 어떤 결과여도 `"off"`.
- 호출 계획 (각 `--max-cost` <= 0.30; `bench plan` 상한): ON-1 `e2e_todo_cli,e2e_rest_notes`, ON-2 `e2e_md_to_html` (상한 0.12), OFF-md `e2e_md_to_html` (상한 0.12). 세 과제 한 호출은 상한 0.33으로 0.30 초과라 나눈다. M17 상한 $0.75, 유료 누계 약 $2.64 / $10.

## M17 (2026-10-17) — live A/B 결과와 판정

라벨: directional; small n, a pre-registered decision rule, not a statistical claim. 판정은 `## M17 사전 등록 판정 규칙`을 그대로 적용했다. 과제와 ON/OFF 설정은 그 절과 같다 (`.cora/bench/m17/arm_on.toml`, `arm_off.toml`).

| 호출 | 내용 | 리허설 | `bench plan` 상한 | `/credits` 사용액(호출 전) | `--max-cost` | 실제 비용 |
|---|---|---|---|---|---|---|
| ON-1 | `e2e_todo_cli,e2e_rest_notes` ledger ON n=3 | 무료 Gemini headless 1회, `ledger_update` 6건, 결함 없음 (비-G1) | 0.22 | $2.64 | 0.30 | $0.0533 |
| ON-2 | `e2e_md_to_html` ledger ON n=3 | 같은 리허설 | 0.12 | $2.69 | 0.30 | $0.1058 |
| OFF-md | `e2e_md_to_html` ledger OFF n=3 | 같은 리허설 | 0.12 | $2.80 | 0.30 | $0.0975 |

모든 호출은 사용자가 호출별로 확인했다. M17 지출 $0.2566 (상한 $0.75), 유료 누계 약 $2.90 / $10.

| 과제 | ON k/n (Wilson 95%) | OFF k/n (Wilson 95%) |
|---|---|---|
| e2e_todo_cli | 2/3 (20.8%–93.9%) | 3/3 (43.8%–100%) — M16d seed 0 재사용 |
| e2e_rest_notes | 1/3 (6.1%–79.2%) | 2/3 (20.8%–93.9%) — M16d seed 0 재사용 |
| e2e_md_to_html | 0/3 (0%–56.2%) | 0/3 (0%–56.2%) |
| **합계** | **3/9 (12.1%–64.6%)** | **5/9 (26.7%–81.1%)** |
| 비용 | $0.1591 | $0.1623 |
| solved-per-dollar | 18.9 | 30.8 |

- 축출 (세션 `memory.summary_lines` 합): ON todo 0 / rest 0 / md 84(17+36+31), OFF todo 0 / rest 54(재사용 M16d) / md 92(27+37+28). ON 실행에서 축출 관측됨 (조건 충족).
- 이벤트: ON `ledger_update` 125 (ON-1 73, ON-2 52), `ledger_evict_note` 26 (모두 ON-2), `summary_call` 0 (summarize off).
- 오류·중단 run: 없음. ON-2 두 run과 OFF-md 한 run은 비용 한도·max_iterations로 종료.
- 판정: ON solved 3 < OFF solved 5 → **FAIL**. `ledger = false` 유지. `summarize = "off"` 유지.
- 해석 (방향성): 차이는 `e2e_todo_cli`, `e2e_rest_notes`에서 나왔고 두 과제 ON run에는 축출이 없었다 (ledger는 축출 전에는 입력만 늘림). 축출이 있던 `e2e_md_to_html`은 양쪽 0/3으로 ledger 효과를 가릴 수 없다. n이 작아 구간이 크게 겹친다. 주의 (A6): OFF의 두 과제는 M16d 재사용 run이라 코드 HEAD와 시점이 다르다.

## M17b 사전 등록 판정 규칙 (2026-10-17T09:42:35Z)

첫 유료 호출 전에 기록한다. directional; small n, a pre-registered decision rule, not a statistical claim. md_to_html 한 과제에서 튜닝됨, 일반화는 M18/M19에서 확인.

- 모델: cheap `google/gemini-2.5-flash-lite` 단독. 설정: M17 OFF 설정(`.cora/bench/m17/arm_off.toml` = M16d A'' 설정 + `ledger = false`, `summarize = "off"`)에 `[agent] raw_file_body = true`, `repeat_breaker = true`, `located_errors = true`만 추가(`.cora/bench/m17b/arm_on.toml`). 나머지 키·프롬프트·한도 동일.
- 과제와 반복(seed 0): 호출 1 `e2e_md_to_html` n=3, 호출 2 `e2e_todo_cli,e2e_rest_notes` n=3(과제당 3회). 각 `--max-cost 0.30`, M17b 상한 $0.40.
- OFF 비교군 재사용(한계): md_to_html = M17 OFF-md 0/3 (`.cora/bench/m17/OFF-md`), todo+rest = M16d seed 0 A-e2e 3/3 + 2/3 = 5/6. 코드 HEAD와 시점이 다르다.
- PASS iff (md_to_html ON solved >= 1/3) AND (todo+rest ON solved >= 5/6) AND (md_to_html ON의 parse_error 이벤트 수 + edit_file old-not-found 실패 수 < OFF-md의 같은 합). 오류 합은 두 팔의 events.jsonl에 같은 $0 스크립트 `uv run python tests/m17b_counts.py <dir>`(필드 `loop_errors`)를 적용한다. OFF-md 기준값(사전 계산): parse_error 22 + old_not_found 16 = 38.
- PASS → 세 키를 두 toml 사본에서 기본 true(cmp 동일, --full 통과). 그 외 → false 유지하고 원인을 조사한다(사용자 상시 규칙: 문제를 회피하지 않는다; 한계로 기록하고 넘어가는 선택은 사용자 승인 후에만).

## M17b 라이브 1차 결과와 2차 시도 사전 등록 (2026-10-17T16:07:57Z)

- 1차 시도 (세 키 ON, 커밋 b77a02a..a1b2cc7 시점 코드; `.cora/bench/m17b/ON-md`): `e2e_md_to_html` 0/3 (점수 0.00/0.25/0.75, 종료 cost_limit/final_answer/final_answer), 비용 $0.0797. 루프 오류 합계 22 (parse_error 21 + old_not_found 1) vs OFF-md 38 (22 + 16). reply_truncated 12 (OFF 4), repeat_detected 17. 판정: md_to_html >= 1/3 미충족 → FAIL. todo+rest 호출은 실행하지 않았다(전체 판정이 이미 FAIL).
- 진단 (`.ensemble/milestones/M17b/on-md-diagnosis.md`): raw 채널 결함 3건(닫기 마커 `>>>`/`<<<TAG` 불허, 잘림 시 원인 가림, JSON 안 마커 혼입). 이후 설계 개정 2회와 Revision 3으로 상태 기계와 부착 검사로 재설계(커밋 a7105a7..1627573). 오프라인 검증 PASS (속성 테스트, 뮤테이션 점검, 180만 건 적대적 퍼징).
- 2차 시도: 위 사전 등록 규칙(PASS iff md_to_html >= 1/3 AND todo+rest >= 5/6 AND 루프 오류 합계 < 38)을 **그대로** 적용한다. 규칙, 설정(`.cora/bench/m17b/arm_on.toml`), 모델은 바꾸지 않았고 코드만 수정 후 버전이다. 1차 결과는 폐기하지 않고 위에 기록한다.
- 추가 보고: `RAW_ACTION_ERROR` 발생 횟수를 따로 센다 (검증자 위험 R1: 줄 중간에 붙은 진짜 Action 헤더도 거절될 수 있음).
- 모델 편차 확인용: 다른 cheap 모델 `qwen/qwen3-coder-30b-a3b-instruct` 로 `e2e_md_to_html` n=2를 별도로 돌린다. 판정에는 쓰지 않고 마커 동작 확인만 한다(비-판정).
- 호출 계획: 호출 2 `e2e_md_to_html` n=3 (상한 $0.12), 호출 3 qwen `e2e_md_to_html` n=2 (상한 $0.07), 호출 4 `e2e_todo_cli,e2e_rest_notes` n=3 (상한 $0.21; 호출 2가 md_to_html >= 1/3 일 때만 실행). 각 `--max-cost` <= 0.30. M17b 한도 $0.40, 1차 지출 $0.0797 포함.

## M18 (2026-10-18) — max_iterations 채점 결정과 하드 과제 보정

### 결정 (2026-10-18)

- 결정: e2e 경로(`--suite e2e`, 하드 세트 포함, 모든 arm과 모델 동일)는 종료 사유와 무관하게 채점기로 판정합니다. `full_pass`이면 solved입니다.
- 이미 구현되어 있습니다. 근거 위치는 `src/cora/bench/live.py` `_run_e2e_task`의 상태 블록입니다. `if g.full_pass: status = "solved"`가 `end_reason` 검사보다 먼저 옵니다.
- 근거 증거: `.docs/gap-causes.md` M16 표의 `E-e2e-1/r0 20261016-195236-9cd32c` 행(`max_iterations`, solved 1.00)입니다. 고정 테스트는 `tests/test_m18_max_iterations.py`입니다. 이 파일의 5개 테스트는 반복 한도에서 통과한 작업 공간이 solved가 되는 경우, 실패한 작업 공간이 failed가 되는 경우, 비용 한도(`stopped_budget`), 제공자 계정 오류(`error`), 시간 한도(`failed`)의 상태를 각각 고정합니다.
- 종료 사유는 `end_reason`/`stop_reason`/`detail`에 그대로 보고됩니다.
- 범위: 내장 단일 파일 작업 경로 `_run_task`(`live.py:579`)는 바뀌지 않습니다. 이 경로는 반복 한도로 멈춘 실행을 채점 없이 실패로 셉니다. M19는 이 경로를 쓰지 않습니다.
- bench 코드 변경 없음(P7). 이 결정은 기존 코드를 고정하는 것입니다.
- 이 절은 line 522의 "max_iterations에서 멈춘 실행을 check로 채점하는 일은 M18로 미룹니다"를 닫습니다.

### 비용 환산 규칙 (D4)

- 가격 출처: `cora.toml`의 `google/gemini-2.5-flash-lite`(입력 $0.10, 출력 $0.40 per 1M 토큰, 2026-10-14 기준). M19a에서 갱신합니다.
- 보정 실행은 `gemini-3.5-flash-lite`(무료 등급)로 합니다. 이 모델의 토큰을 위 가격으로 환산한 값이 "flash-lite 가격 환산 비용"입니다.
- 과제 한도: `limits.cost_usd` = max(0.05, 3 x (입력 토큰 x 0.10 + 출력 토큰 x 0.40) / 1e6)을 cent 단위로 올림한 값입니다.

### 보정 표 (calibration, 비-G1 증거, n=1 선별 전용)

| 과제 | run id | solved | score | iterations | end_reason | input_tokens | output_tokens | 환산 비용 $ | cost_usd 설정 | 상태 |
|---|---|---|---|---|---|---|---|---|---|---|
| e2e_h01 | -\|gemini-3.5-flash-lite\|react\|e2e_h01\|r0 | solved | 1.0 | 26 | final_answer | 246267 | 9929 | 0.0286 | 0.09 | done (n=1, calibration) |
| e2e_h02 | -\|gemini-3.5-flash-lite\|react\|e2e_h02\|r0 | solved | 1.0 | 24 | final_answer | 108664 | 3358 | 0.0122 | 0.05 | done (n=1, calibration) |
| e2e_h03 | -\|gemini-3.5-flash-lite\|react\|e2e_h03\|r0 | solved | 1.0 | 30 | max_iterations | 328796 | 12511 | 0.0379 | 0.12 | done (n=1, calibration) |
| e2e_h04 | -\|gemini-3.5-flash-lite\|react\|e2e_h04\|r0 | solved | 1.0 | 26 | final_answer | 250495 | 13641 | 0.0305 | 0.10 | done (n=1, calibration) |
| e2e_h05 | -\|gemini-3.5-flash-lite\|react\|e2e_h05\|r0 | solved | 1.0 | 23 | final_answer | 139187 | 6123 | 0.0164 | 0.05 | done (n=1, calibration) |
| e2e_h06 | -\|gemini-3.5-flash-lite\|react\|e2e_h06\|r0 | solved | 1.0 | 25 | max_iterations | 229851 | 13565 | 0.0284 | 0.09 | done (n=1, calibration) |
| e2e_hx1 | -\|gemini-3.5-flash-lite\|react\|e2e_hx1\|r0 | solved | 1.0 | 19 | final_answer | 105752 | 2606 | 0.0116 | 0.05 | done (n=1, calibration) |
| e2e_hx2 | -\|gemini-3.5-flash-lite\|react\|e2e_hx2\|r0 | solved | 1.0 | 30 | max_iterations | 193487 | 10185 | 0.0234 | 0.08 | done (n=1, calibration) |

### 보정 규칙 (R13, R14)

- R13: 과제마다 `gemini-3.5-flash-lite`로 한 번 실행합니다(무료 키). 5회 이하 반복(iterations <= 5)에 전체 통과한 과제(trivial)나 정답이 실패하는 과제는 새 과제로 바꾸고 다시 보정합니다. 과제별 입력·출력 토큰과 flash-lite 가격 환산 비용은 보정 값으로 이 표에 기록합니다(비-G1 증거).
- R14: Gemini 503/429로 실패한 항목은 실패가 아니라 `blocked`로 기록하고 M19a 전에 재시도합니다. 그 밖의 실패는 원인을 찾아 고칩니다(과제 결함 또는 하네스 결함). 실패를 면제하지 않습니다.

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

## M19a Q7 모델 목록 확인 (2026-10-18T06:28:21Z)
이 절은 M19a O1 단계(Q7)의 기록입니다. 사전 등록이 아니므로 `tests/fixtures/m19/preregistration.md`에는 복사하지 않습니다.

- 출처: `https://openrouter.ai/api/v1/models`(목록), `https://openrouter.ai/api/v1/models/<id>/endpoints`(다섯 id 각각의 엔드포인트). 원본 응답은 `.cora/bench/m19a/q7/`에 저장했고, 시각은 `.cora/bench/m19a/q7/fetch_time.txt`에 있습니다.
- 완료 호출(completion call)은 하지 않았고, API 키도 쓰지 않았습니다(`Authorization` 헤더 없이 GET만 했습니다).
- 가격은 `pricing.prompt` / `pricing.completion`에 1e6을 곱한 USD/1M 토큰 값입니다. 처리량은 엔드포인트의 `throughput_last_30m` / `latency_last_30m` 필드를 보았는데 다섯 id 모두 `null`이어서 "not given"입니다.
- `max_tokens` / `temperature` / `stop` 지원 열은 엔드포인트의 `supported_parameters`에 각 파라미터가 있는 엔드포인트 수 / 전체 엔드포인트 수입니다.

| id | 목록 | 입력 $/1M | 출력 $/1M | 제공자 수 | 처리량 | max_tokens/temperature/stop 지원 엔드포인트 |
|---|---|---|---|---|---|---|
| google/gemini-2.5-flash-lite | yes | 0.10 | 0.40 | 5 | not given | 5/5 |
| deepseek/deepseek-v3.2 | yes | 0.28 | 0.42 | 12 | not given | 9/12 (stop 없음: GMICloud, SiliconFlow, DigitalOcean) |
| qwen/qwen3-coder-30b-a3b-instruct | yes | 0.07 | 0.28 | 2 | not given | 1/2 (stop 없음: SiliconFlow) |
| mistralai/mistral-small-3.2-24b-instruct | yes | 0.09375 | 0.25 | 4 | not given | 4/4 |
| openai/gpt-4o-mini | yes | 0.15 | 0.60 | 3 | not given | 1/3 (max_tokens 없음: Azure 2곳) |

- 캐시 읽기 가격: deepseek/deepseek-v3.2 엔드포인트 목록의 `input_cache_read`가 0.000000028(1e6 곱하면 0.028)입니다. gemini-2.5-flash-lite 목록에는 0.00000001(0.01), gpt-4o-mini 목록에는 0.000000075(0.075)이 있고, 나머지 id에는 캐시 가격이 없습니다.
- 컨텍스트 길이(목록의 `context_length`): flash-lite 1,048,576 / deepseek 163,840(공급자 기준 상한 131,072) / qwen 262,144 / mistral 256,000 / gpt-4o-mini 128,000.
- 다섯 id 모두 목록에 있습니다. 가격이 m1(flash-lite) 가격의 3배를 넘는 id는 없습니다(gpt-4o-mini 출력 0.60은 m1 출력 0.40의 1.5배). 따라서 사용자에게 보고하고 기다릴 항목은 없습니다.
- `[[models]]` 가격 갱신(이전 → 새 값, `cora.toml`과 `src/cora/data/cora.toml`에 같은 내용으로 반영):
  - google/gemini-2.5-flash-lite: 입력 0.10 → 0.10, 출력 0.40 → 0.40 (값 변화 없음, 출처 주석만 추가)
  - deepseek/deepseek-v3.2: 입력 0.26 → 0.28, 출력 0.38 → 0.42, 캐시 읽기 0.14 → 0.028
  - qwen/qwen3-coder-30b-a3b-instruct: 입력 0.07 → 0.07, 출력 0.28 → 0.28 (값 변화 없음, 출처 주석만 추가)
  - mistralai/mistral-small-3.2-24b-instruct: 입력 0.094 → 0.09375, 출력 0.25 → 0.25
- 갱신 근거에 따라 `USAGE.md`의 strong 가격 문장과 `.docs/architecture.md`의 모델 항목을 같은 값으로 고쳤습니다(출처 날짜 2026-10-18 명시).

## M19a 탐침 (probe) (2026-10-18T06:47:49Z)

- 과제: `e2e_h05`(우선순위). 보정 실행 23/30 반복에서 `final_answer`로 끝났고(최대 아님, 사소하지 않음), 보이는 검사가 있으며, 상한 `cost_usd = 0.05`(≤ 0.10)입니다. 세 후보 모두 같은 과제를 씁니다.
- 순서: qwen(m2) → mistral(m3, 사용자 요청). 두 번 모두 수락되어 `gpt-4o-mini`(B2)와 그 탐침은 실행하지 않았습니다.
- 유료 누적 합계는 `/credits` 차이로 셉니다(아래 "실행 누적").

### 리허설 (rehearsal, $0)
- 명령: `uv run cora bench --live --suite e2e --models gemini-3.5-flash-lite --protocols react --tasks e2e_h05 --repeats 1 --max-cost 0.10 --out .cora/bench/m19a/rehearse-h05`
- 시작 2026-10-18T06:42:08Z. 결과: status `solved`, end `final_answer`, score 1.0, cost $0.0(무료 티어), llm_call 27, parse_error 3, tool_call ok 26/31, latency 313.6 s. 보고서: `.cora/bench/m19a/rehearse-h05/report.json`. 명령 형태는 바뀌지 않았으므로 한 번만 실행했습니다.

### 탐침 1: qwen/qwen3-coder-30b-a3b-instruct (m2)
- bench plan TOTAL (`uv run cora bench plan --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_h05 --repeats 1 --max-cost 0.10`): `| TOTAL | | | | 1 runs | | | | 0.042202 |`
- 확인: 사용자의 1회 명시 승인(O2 (d)), 날짜 2026-10-18. 승인 원문: 질문 "유료 프로브 1회를 실행해도 될까요? 모델 qwen/qwen3-coder-30b-a3b-instruct, 과제 e2e_h05, 1회, --max-cost 0.10. bench plan 상한은 $0.042입니다..." 에 대한 사용자 답 "실행 (Recommended)".
- 명령: `uv run cora bench --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_h05 --repeats 1 --max-cost 0.10 --out .cora/bench/m19a/probe-qwen3-coder`. `--max-cost 0.10`, n = 1.
- `/credits` 기록: 전(credits-before-qwen.txt) total_usage 3.037530307 · 후(credits-after-qwen.txt, 첫 읽기) 3.045456687 · 정산 후(credits-before-mistral.txt, 두 번째 탐침 직전) 3.050298867. 첫 읽기 차이 0.007926은 지연된 것이고, 정산 후 누적 차이는 0.012768입니다.
- 보고서: `.cora/bench/m19a/probe-qwen3-coder/report.json`. 비용 `cost_usd` 0.01276856, latency 225.3 s, end `final_answer`, status `solved`, llm_call 30, tool_call ok 24/29, parse_repaired 8, parse_error 0.
- 수락 검사(수치):
  1. 제공자 오류: 없음(status `solved`, 제공자 오류 이벤트 없음) → 통과.
  2. 성공 도구 호출 ≥ 1: 24 → 통과.
  3. parse 비율 = parse_error / llm_call = 0 / 30 = 0.00 ≤ 0.50 → 통과.
  4. 벽시계: latency 225.3 s, 벽시계 비율 225.3 / 2400 = 0.094 ≤ 0.50, 225.3 s ≤ 1200 s → 통과.
- 판정: 수락. 거절 원인 분석 해당 없음.
- 탐침 비율(cost plan용) = 0.01276856 / (139187 × 0.07 + 6123 × 0.28) / 10^6 = 0.01276856 / 0.01145753 = **1.1144**.

### 탐침 2: mistralai/mistral-small-3.2-24b-instruct (m3, 사용자 요청)
- bench plan TOTAL (`uv run cora bench plan --suite e2e --models mistralai/mistral-small-3.2-24b-instruct --protocols react --tasks e2e_h05 --repeats 1 --max-cost 0.10`): `| TOTAL | | | | 1 runs | | | | 0.050000 |`
- 확인: 사용자 요청(2026-10-18). 오케스트레이터가 m3 = mistral-small-3.2 (세 번째 저가 멤버, 탐침 약 $0.01–0.05, 누적 $0.20 한도 안)라고 알린 뒤 사용자 답 원문 "m3 넣으세요".
- 명령: `uv run cora bench --live --suite e2e --models mistralai/mistral-small-3.2-24b-instruct --protocols react --tasks e2e_h05 --repeats 1 --max-cost 0.10 --out .cora/bench/m19a/probe-mistral-small`. `--max-cost 0.10`, n = 1.
- `/credits` 기록: 전(credits-before-mistral.txt, 07:32Z) total_usage 3.050298867 · 후(credits-after-mistral.txt) 3.053248517. 차이 0.002950.
- 보고서: `.cora/bench/m19a/probe-mistral-small/report.json`. status `failed`(score 0.75, 수락 기준이 아님), `cost_usd` 0.00294965, latency 54.1 s, end `final_answer`, llm_call 13, tool_call ok 9/11, parse_error 0.
- 수락 검사(수치): 1 제공자 오류 없음 → 통과. 2 성공 도구 호출 9 ≥ 1 → 통과. 3 parse 비율 0 / 13 = 0.00 ≤ 0.50 → 통과. 4 벽시계 54.1 / 2400 = 0.023 ≤ 0.50, 54.1 s ≤ 1200 s → 통과.
- 판정: 수락(수락 기준은 제공자 오류, 성공 도구 호출, parse, 벽시계이며 solved 여부는 기준이 아닙니다).
- 탐침 비율 = 0.00294965 / (139187 × 0.09375 + 6123 × 0.25) / 10^6 = 0.00294965 / 0.01457953 = **0.2023**. 실행이 13회 호출로 짧게 끝났고 status가 failed여서 이 비율은 낮게 나옵니다. 비용 계획의 a(m3)에 그대로 쓰되 과소 추정 가능성을 표시합니다.

### 실행 누적 (유료)
- 방법: `/credits`의 total_usage 차이(정산 후 값). 전 3.037530307 → 후 3.053248517. 차이 = 0.015718.
- 교차 확인: 보고서 `cost_usd` 합 0.01276856 + 0.00294965 = 0.01571821. 일치합니다.
- 누적 0.0157 ≤ $0.20 한도. 다음 탐침은 없습니다.
- 발견: 첫 `/credits` 읽기(qwen 직후)는 0.004842만큼 지연되었습니다. 이후 읽기에서 정산되었습니다. 이 때문에 탐침 비용은 보고서 `cost_usd`와 정산 후 `/credits`를 함께 씁니다.

### 체크포인트 1 (2026-10-18)
- 보고한 내용(O3 항목): 두 탐침의 수락 검사 수치, 탐침 비용과 벽시계, 갱신된 `[[models]]` 가격(Q7 기록 참조), 실행 누적 0.0157.
- 사용자 결정(`.ensemble/milestones/M19a/iterations.md`): 패널 = m1 `google/gemini-2.5-flash-lite`, m2 `qwen/qwen3-coder-30b-a3b-instruct`, m3 `mistralai/mistral-small-3.2-24b-instruct`, 강한 모델 `deepseek/deepseek-v3.2`. `gpt-4o-mini`와 B2는 필요 없음.
- 계속 여부: 계속(이 기록은 Group C 실행 지시를 따른 것입니다). R18 항목 답변은 O4에서 받습니다.

## M19a 비용 계획 (2026-10-18T07:40:31Z)

이 절은 M19 배정 계산입니다. 사전 등록 절이 아니므로 `tests/fixtures/m19/preregistration.md`에는 넣지 않습니다. 2부(`## M19 사전 등록 2부`)가 이 절의 확정 숫자를 인용합니다. 모든 `bench plan` 줄은 $0이며 네트워크를 쓰지 않았습니다. 키 파일은 읽지 않았습니다.

**갱신 (2026-10-18T08:03:40Z, O4 사용자 결정 반영)**: M19 배정 $6.00(종전 $5.00 대체), 순서 member-first, `--max-cost` ≤ $0.50, 셀 단위 건너뛰기 규칙(1.5× 시작 규칙), 팔 e 예상 비용 = 보정 × 1.5 = $2.16, 만료 셀은 그 시점에 재결정. 아래 1–6절은 이 갱신 값입니다. 종전 $5.00 기준의 절단선과 0.30 기준 호출 목록은 이 갱신으로 대체되었습니다.

### 1. 현재 예산 (O4 갱신)
- `/credits`(credits-after-mistral.txt, 2026-10-18 약 07:33Z): total_credits 10, total_usage 3.053248517, 잔액 6.946751. O4 재판독에서 `/credits` 값은 기록에 없으므로 이 마지막 기록을 씁니다(열린 항목).
- `/auth/key`의 `limit_remaining` = 6.1457(O4 재판독, 사용자 결정 기록의 값).
- 사용 가능액 = min(키 한도 잔액 6.1457, `/credits` 잔액 6.946751, 헌장 산술 6.9443) = **6.1457**(키 한도가 묶는 값).
- M19a 지출 = 0.0157(`/credits` 차이). M19a 이후 `/credits` 잔액과 키 한도 잔액은 0.80 차이가 나는데, 기록에 설명이 없습니다(열린 질문).
- M19 배정 = **$6.00**(사용자 결정 1).
- 배정 뒤 남는 액 = 6.1457 − 6.00 = 0.1457.
- 부족분(요청 합 대 키 한도 잔액): M19a 0.0157 + M19 6.00 + M20 1.00 + 예비 0.76 = 7.7757 대 6.1457 → **부족 1.6300**. M19a 지출을 빼고 계산해도 1.6143입니다. `/credits` 잔액 기준이면 부족 0.8289입니다.
- 사용자 답: M20 $1.00은 잔액이 부족할 때 나중에 다시 정합니다(결정 1). 예비 $0.76 미확보는 사용자 답이 없으므로 열린 질문입니다. 집행자는 선택지(M20 축소, 예비 축소, M19 축소, 충전) 중 어느 것도 고르지 않습니다.

### 2. 역할별 상한
- 저가(cheap) 상한 = task.toml `cost_usd`: h01 0.09, h02 0.05, h03 0.12, h04 0.10, h05 0.05, h06 0.09, hx1 0.05, hx2 0.08.
- 강한 상한 S = ceil_cent(3 × max_t cal_t(S)) = ceil_cent(3 × 0.0973175) = ceil_cent(0.2919525) = **$0.30**(h03이 최대). 이 값은 2부에서 고정됩니다.
- 팔 e: 실행 1회당 상한 $0.30. 과제당 3회 = $0.90 > $0.50이므로 과제마다 1회씩 3개 호출로 나눕니다(호출 24개).
- `--max-cost`는 최대 $0.50까지 허용됩니다(결정 4). 이 절의 모든 호출은 $0.50 이하입니다.

### 3. 예상 비용표
- 셀당 예상 = Σ_과제 (3 × 보정 비용_과제 at 멤버 가격) × 요율. 요율: m1 = 1.5(탐침 없음), m2 = 탐침 비율 1.1144, m3 = 탐침 비율 0.2023. b, c_s, c_cc, d1은 추가로 × 1.5. c_cc는 m1 가격으로 셉니다.
- 팔 e 예상 열 = Σ_과제 3 × cal_t(S) × 1.5 = **2.1551 ≈ $2.16**(결정 3). 상한 열 = 24 × S = 7.20(결정 3에서 채택하지 않음, 비교용).
- 셀 과제: a = 8개 전부, b와 c_s = F(h01–h06) + hx2, d1 = hx1, hx2, g = F, e = 8개 전부.

#### 3a. member-first 순서 (확정: a(m1), a(m2), e, c_s(m1), b(m1), d1(m1), c_cc, c_s(m2), b(m2), d1(m2), a(m3), g(m2))

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

- 1.5× 시작 규칙(결정 1, 셀 단위 건너뛰기): 셀은 시작 전 남은 배정 ≥ 1.5 × 그 셀의 예상 비용일 때만 시작합니다. 예상 열 기준 남은 액은 a(m1) 뒤 5.1494, a(m2) 뒤 4.7070, e 뒤 2.5519, c_s(m1) 뒤 1.3545, d1(m1) 뒤 1.1180, c_s(m2) 뒤 0.4952, d1(m2) 뒤 0.3722, a(m3) 뒤 **0.2701**.
- 실행 집합(예상 열): **a(m1), a(m2), e, c_s(m1), d1(m1), c_s(m2), d1(m2), a(m3)**. 예상 합 **5.7299**, 남는 액 0.2701.
- 건너뜀(예상 열): b(m1)(누적 5.84 ≤ 6.00이지만 1.5 × 1.1974 = 1.7961 > 남은 1.3545이므로 건너뜀), c_cc(m1→m2), b(m2), g(m2). 건너뜀 셀은 호출 목록에 없습니다. 나중에 시작 규칙이 통과하더라도 새 확인이 필요합니다(열린 질문).
- 절단선(누적 열, 예상 열): 누적 > $6.00인 첫 행은 **d1(m1)**(누적 6.0794). 1.5× 규칙을 함께 쓰면 위 실행 집합이 됩니다.
- 절단선(상한 열, e = 상한, 채택 안 함): 첫 행은 **e**(누적 8.4930). 1.5× 규칙으로 e는 건너뜀(1.5 × 7.20 = 10.80 > 남은 4.71). 이 읽기를 쓰면 e가 빠지고 c_s(m1), b(m1), d1(m1), c_cc, d1(m2), a(m3), g(m2)가 실행 후보가 됩니다. 결정 3에 따라 이 읽기는 쓰지 않습니다.

#### 3b. strict arm-first 순서 (O4 결정 2로 대체됨, 참고용, R13 절단 목록)
- arm-first는 확정 순서가 아닙니다. 순서는 a(m1), a(m2), a(m3), e, c_s(m1), c_cc, c_s(m2), b(m1), b(m2), d1(m1), d1(m2)입니다. g(m2)는 실행 집합 밖이라 뺍니다. 예상 열은 3a와 같은 값(e = 보정 × 1.5 = $2.16)이고, 누적은 전체 셀 기준입니다(3a와 같은 방식). 이 표가 2부 수정 절(`## M19 사전 등록 수정`)이 가리키는 절단 목록입니다.

| 순서 | 셀 | runs | 예상 $ | 누적 $ | 절단선 (누적 열 > $6.00) | 1.5× 시작 판정 (남은 액 = $6.00 − 실제 지출) | 판정 결과 |
|---|---|---|---|---|---|---|---|
| 1 | a(m1) | 24 | 0.8506 | 0.8506 | | 남음 6.0000, 1.5× = 1.2759 | 실행 → 남음 5.1494 |
| 2 | a(m2) | 24 | 0.4424 | 1.2930 | | 남음 5.1494, 1.5× = 0.6636 | 실행 → 남음 4.7070 |
| 3 | a(m3) | 24 | 0.1021 | 1.3951 | | 남음 4.7070, 1.5× = 0.1532 | 실행 → 남음 4.6049 |
| 4 | e | 24 | 2.1551 | 3.5502 | | 남음 4.6049, 1.5× = 3.2327 | 실행 → 남음 2.4498 |
| 5 | c_s(m1) | 21 | 1.1974 | 4.7476 | | 남음 2.4498, 1.5× = 1.7961 | 실행 → 남음 1.2524 |
| 6 | c_cc(m1→m2) | 21 | 1.1974 | 5.9450 | | 남음 1.2524, 1.5× = 1.7961 | 건너뜀 (남음 1.2524 유지) |
| 7 | c_s(m2) | 21 | 0.6228 | 6.5678 | **첫 행 (> 6.00)** | 남음 1.2524, 1.5× = 0.9342 | 실행 → 남음 0.6296 |
| 8 | b(m1) | 21 | 1.1974 | 7.7652 | 절단 | 남음 0.6296, 1.5× = 1.7961 | 건너뜀 |
| 9 | b(m2) | 21 | 0.6228 | 8.3880 | 절단 | 남음 0.6296, 1.5× = 0.9342 | 건너뜀 |
| 10 | d1(m1) | 6 | 0.2365 | 8.6245 | 절단 | 남음 0.6296, 1.5× = 0.3548 | 실행 → 남음 0.3931 |
| 11 | d1(m2) | 6 | 0.1230 | 8.7475 | 절단 | 남음 0.3931, 1.5× = 0.1845 | 실행 → 남음 0.2701 |

- 누적 절단선(R13, 순수 누적 열): c_s(m2) 행이 처음으로 $6.00을 넘습니다(6.5678). 이 행과 그 아래 b(m1), b(m2), d1(m1), d1(m2)가 절단 목록입니다. 1.5× 시작 규칙(결정 5)을 함께 적용한 실행 집합은 a(m1), a(m2), a(m3), e, c_s(m1), c_s(m2), d1(m1), d1(m2)이며, 예상 합 5.7299, 남는 액 0.2701입니다. 건너뜀은 c_cc(m1→m2), b(m1), b(m2)입니다.
- 실행 집합은 3a(member-first)와 같은 8개 셀이며 호출 목록 51호출도 같습니다. 순서만 다릅니다. 호출 목록의 번호는 바뀌지 않습니다.
- 건너뜀 셀 c_cc는 호출 목록에 없습니다. 순수 누적 규칙만 쓰면 c_cc가 실행되고 d1이 잘리므로, 그 읽기를 쓰려면 새 호출 목록이 필요합니다(열린 항목, 사용자 확인 전 실행 금지).
- 팔 e의 상한 열(e = 24 × S = 7.20, 결정 3에서 채택하지 않음, 비교용): 누적 열은 e 행(누적 8.5951)에서 처음 $6.00을 넘고, 1.5× 규칙으로는 e가 건너뜀(1.5 × 7.20 = 10.80 > 남은 4.6049)입니다.

### 4. 호출 목록 (확정 순서, 실행 집합 51호출, --max-cost ≤ $0.50)
- 묶음 규칙: 과제를 id 순서로 탐욕적으로 담습니다. 과제 블록 = 3 × 과제 상한. 블록을 같은 호출에 더해도 기록 상한이 $0.50을 넘지 않으면 묶고, 넘으면 새 호출을 만듭니다. 블록이 $0.50을 넘는 과제만 반복 수로 나눕니다(팔 e의 모든 과제).
- 기록 상한 = max(plan TOTAL, Σ repeats × 상한). `--max-cost` = 기록 상한(센트 단위). 모든 plan TOTAL은 기록 상한 이하입니다.
- 실행 집합별 호출 수: a(m1) 5, a(m2) 5, e 24, c_s(m1) 5, d1(m1) 1, c_s(m2) 5, d1(m2) 1, a(m3) 5 = 51.
- Σ 기록 상한 = 17.13(모든 실행이 상한까지 쓰는 최악값). 예상 합 5.7299. 키 한도 잔액 6.1457가 묶는 값입니다. 최악값 합은 잔액을 넘으므로, 집행은 (a) 1.5× 셀 규칙, (b) 호출 전 실측 누적 지출 점검, (c) 키 한도가 막는 402 중단 규칙으로 관리합니다.
- 호출 전 점검: 호출 기록 상한 ≤ min($10 − 유료 누적, 키 한도 잔액). 그리고 실측 M19 누적 지출 < $6.00. 실측 누적이 $6.00 이상이면 그 호출과 남은 호출을 멈추고 "측정 안 함(예산)"으로 보고합니다.

[M19-01 · a(m1) · e2e_h01,e2e_h02 · repeats 3] 기록 상한 0.42 (plan TOTAL 0.330864), --max-cost 0.42
  live: `uv run cora bench --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --tasks e2e_h01,e2e_h02 --repeats 3 --max-cost 0.42 --out .cora/bench/m19/runs/a-m1-i01`
  plan: `uv run cora bench plan --suite e2e --models google/gemini-2.5-flash-lite --protocols react --tasks e2e_h01,e2e_h02 --repeats 3 --max-cost 0.42`
[M19-02 · a(m1) · e2e_h03 · repeats 3] 기록 상한 0.36 (plan TOTAL 0.180864), --max-cost 0.36
  live: `uv run cora bench --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --tasks e2e_h03 --repeats 3 --max-cost 0.36 --out .cora/bench/m19/runs/a-m1-i02`
  plan: `uv run cora bench plan --suite e2e --models google/gemini-2.5-flash-lite --protocols react --tasks e2e_h03 --repeats 3 --max-cost 0.36`
[M19-03 · a(m1) · e2e_h04,e2e_h05 · repeats 3] 기록 상한 0.45 (plan TOTAL 0.330864), --max-cost 0.45
  live: `uv run cora bench --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --tasks e2e_h04,e2e_h05 --repeats 3 --max-cost 0.45 --out .cora/bench/m19/runs/a-m1-i03`
  plan: `uv run cora bench plan --suite e2e --models google/gemini-2.5-flash-lite --protocols react --tasks e2e_h04,e2e_h05 --repeats 3 --max-cost 0.45`
[M19-04 · a(m1) · e2e_h06,e2e_hx1 · repeats 3] 기록 상한 0.42 (plan TOTAL 0.300720), --max-cost 0.42
  live: `uv run cora bench --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --tasks e2e_h06,e2e_hx1 --repeats 3 --max-cost 0.42 --out .cora/bench/m19/runs/a-m1-i04`
  plan: `uv run cora bench plan --suite e2e --models google/gemini-2.5-flash-lite --protocols react --tasks e2e_h06,e2e_hx1 --repeats 3 --max-cost 0.42`
[M19-05 · a(m1) · e2e_hx2 · repeats 3] 기록 상한 0.24 (plan TOTAL 0.180864), --max-cost 0.24
  live: `uv run cora bench --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --tasks e2e_hx2 --repeats 3 --max-cost 0.24 --out .cora/bench/m19/runs/a-m1-i05`
  plan: `uv run cora bench plan --suite e2e --models google/gemini-2.5-flash-lite --protocols react --tasks e2e_hx2 --repeats 3 --max-cost 0.24`
[M19-06 · a(m2) · e2e_h01,e2e_h02 · repeats 3] 기록 상한 0.42 (plan TOTAL 0.232109), --max-cost 0.42
  live: `uv run cora bench --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_h01,e2e_h02 --repeats 3 --max-cost 0.42 --out .cora/bench/m19/runs/a-m2-i01`
  plan: `uv run cora bench plan --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_h01,e2e_h02 --repeats 3 --max-cost 0.42`
[M19-07 · a(m2) · e2e_h03 · repeats 3] 기록 상한 0.36 (plan TOTAL 0.126605), --max-cost 0.36
  live: `uv run cora bench --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_h03 --repeats 3 --max-cost 0.36 --out .cora/bench/m19/runs/a-m2-i02`
  plan: `uv run cora bench plan --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_h03 --repeats 3 --max-cost 0.36`
[M19-08 · a(m2) · e2e_h04,e2e_h05 · repeats 3] 기록 상한 0.45 (plan TOTAL 0.253210), --max-cost 0.45
  live: `uv run cora bench --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_h04,e2e_h05 --repeats 3 --max-cost 0.45 --out .cora/bench/m19/runs/a-m2-i03`
  plan: `uv run cora bench plan --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_h04,e2e_h05 --repeats 3 --max-cost 0.45`
[M19-09 · a(m2) · e2e_h06,e2e_hx1 · repeats 3] 기록 상한 0.42 (plan TOTAL 0.232109), --max-cost 0.42
  live: `uv run cora bench --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_h06,e2e_hx1 --repeats 3 --max-cost 0.42 --out .cora/bench/m19/runs/a-m2-i04`
  plan: `uv run cora bench plan --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_h06,e2e_hx1 --repeats 3 --max-cost 0.42`
[M19-10 · a(m2) · e2e_hx2 · repeats 3] 기록 상한 0.24 (plan TOTAL 0.126605), --max-cost 0.24
  live: `uv run cora bench --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_hx2 --repeats 3 --max-cost 0.24 --out .cora/bench/m19/runs/a-m2-i05`
  plan: `uv run cora bench plan --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_hx2 --repeats 3 --max-cost 0.24`
[M19-11 · e · e2e_h01 · repeats 1] 기록 상한 0.30 (plan TOTAL 0.147302), --max-cost 0.30
  live: `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h01 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i01`
  plan: `uv run cora bench plan --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h01 --repeats 1 --max-cost 0.30`
[M19-12 · e · e2e_h01 · repeats 1] 기록 상한 0.30 (plan TOTAL 0.147302), --max-cost 0.30
  live: `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h01 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i02`
  plan: `uv run cora bench plan --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h01 --repeats 1 --max-cost 0.30`
[M19-13 · e · e2e_h01 · repeats 1] 기록 상한 0.30 (plan TOTAL 0.147302), --max-cost 0.30
  live: `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h01 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i03`
  plan: `uv run cora bench plan --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h01 --repeats 1 --max-cost 0.30`
[M19-14 · e · e2e_h02 · repeats 1] 기록 상한 0.30 (plan TOTAL 0.122752), --max-cost 0.30
  live: `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h02 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i04`
  plan: `uv run cora bench plan --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h02 --repeats 1 --max-cost 0.30`
[M19-15 · e · e2e_h02 · repeats 1] 기록 상한 0.30 (plan TOTAL 0.122752), --max-cost 0.30
  live: `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h02 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i05`
  plan: `uv run cora bench plan --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h02 --repeats 1 --max-cost 0.30`
[M19-16 · e · e2e_h02 · repeats 1] 기록 상한 0.30 (plan TOTAL 0.122752), --max-cost 0.30
  live: `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h02 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i06`
  plan: `uv run cora bench plan --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h02 --repeats 1 --max-cost 0.30`
[M19-17 · e · e2e_h03 · repeats 1] 기록 상한 0.30 (plan TOTAL 0.147302), --max-cost 0.30
  live: `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h03 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i07`
  plan: `uv run cora bench plan --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h03 --repeats 1 --max-cost 0.30`
[M19-18 · e · e2e_h03 · repeats 1] 기록 상한 0.30 (plan TOTAL 0.147302), --max-cost 0.30
  live: `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h03 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i08`
  plan: `uv run cora bench plan --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h03 --repeats 1 --max-cost 0.30`
[M19-19 · e · e2e_h03 · repeats 1] 기록 상한 0.30 (plan TOTAL 0.147302), --max-cost 0.30
  live: `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h03 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i09`
  plan: `uv run cora bench plan --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h03 --repeats 1 --max-cost 0.30`
[M19-20 · e · e2e_h04 · repeats 1] 기록 상한 0.30 (plan TOTAL 0.147302), --max-cost 0.30
  live: `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h04 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i10`
  plan: `uv run cora bench plan --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h04 --repeats 1 --max-cost 0.30`
[M19-21 · e · e2e_h04 · repeats 1] 기록 상한 0.30 (plan TOTAL 0.147302), --max-cost 0.30
  live: `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h04 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i11`
  plan: `uv run cora bench plan --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h04 --repeats 1 --max-cost 0.30`
[M19-22 · e · e2e_h04 · repeats 1] 기록 상한 0.30 (plan TOTAL 0.147302), --max-cost 0.30
  live: `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h04 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i12`
  plan: `uv run cora bench plan --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h04 --repeats 1 --max-cost 0.30`
[M19-23 · e · e2e_h05 · repeats 1] 기록 상한 0.30 (plan TOTAL 0.147302), --max-cost 0.30
  live: `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h05 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i13`
  plan: `uv run cora bench plan --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h05 --repeats 1 --max-cost 0.30`
[M19-24 · e · e2e_h05 · repeats 1] 기록 상한 0.30 (plan TOTAL 0.147302), --max-cost 0.30
  live: `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h05 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i14`
  plan: `uv run cora bench plan --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h05 --repeats 1 --max-cost 0.30`
[M19-25 · e · e2e_h05 · repeats 1] 기록 상한 0.30 (plan TOTAL 0.147302), --max-cost 0.30
  live: `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h05 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i15`
  plan: `uv run cora bench plan --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h05 --repeats 1 --max-cost 0.30`
[M19-26 · e · e2e_h06 · repeats 1] 기록 상한 0.30 (plan TOTAL 0.122752), --max-cost 0.30
  live: `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h06 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i16`
  plan: `uv run cora bench plan --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h06 --repeats 1 --max-cost 0.30`
[M19-27 · e · e2e_h06 · repeats 1] 기록 상한 0.30 (plan TOTAL 0.122752), --max-cost 0.30
  live: `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h06 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i17`
  plan: `uv run cora bench plan --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h06 --repeats 1 --max-cost 0.30`
[M19-28 · e · e2e_h06 · repeats 1] 기록 상한 0.30 (plan TOTAL 0.122752), --max-cost 0.30
  live: `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h06 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i18`
  plan: `uv run cora bench plan --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h06 --repeats 1 --max-cost 0.30`
[M19-29 · e · e2e_hx1 · repeats 1] 기록 상한 0.30 (plan TOTAL 0.147302), --max-cost 0.30
  live: `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_hx1 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i19`
  plan: `uv run cora bench plan --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_hx1 --repeats 1 --max-cost 0.30`
[M19-30 · e · e2e_hx1 · repeats 1] 기록 상한 0.30 (plan TOTAL 0.147302), --max-cost 0.30
  live: `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_hx1 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i20`
  plan: `uv run cora bench plan --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_hx1 --repeats 1 --max-cost 0.30`
[M19-31 · e · e2e_hx1 · repeats 1] 기록 상한 0.30 (plan TOTAL 0.147302), --max-cost 0.30
  live: `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_hx1 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i21`
  plan: `uv run cora bench plan --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_hx1 --repeats 1 --max-cost 0.30`
[M19-32 · e · e2e_hx2 · repeats 1] 기록 상한 0.30 (plan TOTAL 0.147302), --max-cost 0.30
  live: `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_hx2 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i22`
  plan: `uv run cora bench plan --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_hx2 --repeats 1 --max-cost 0.30`
[M19-33 · e · e2e_hx2 · repeats 1] 기록 상한 0.30 (plan TOTAL 0.147302), --max-cost 0.30
  live: `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_hx2 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i23`
  plan: `uv run cora bench plan --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_hx2 --repeats 1 --max-cost 0.30`
[M19-34 · e · e2e_hx2 · repeats 1] 기록 상한 0.30 (plan TOTAL 0.147302), --max-cost 0.30
  live: `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_hx2 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i24`
  plan: `uv run cora bench plan --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_hx2 --repeats 1 --max-cost 0.30`
[M19-35 · c_s(m1) · e2e_h01,e2e_h02 · repeats 3] 기록 상한 0.42 (plan TOTAL 0.420000), --max-cost 0.42
  live: `uv run cora bench -c .cora/bench/m19/cascade-strong.toml --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h01,e2e_h02 --repeats 3 --max-cost 0.42 --out .cora/bench/m19/runs/c_s-m1-i01`
  plan: `uv run cora bench plan -c .cora/bench/m19/cascade-strong.toml --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab auto-routed --tasks e2e_h01,e2e_h02 --repeats 3 --max-cost 0.42`
[M19-36 · c_s(m1) · e2e_h03 · repeats 3] 기록 상한 0.36 (plan TOTAL 0.360000), --max-cost 0.36
  live: `uv run cora bench -c .cora/bench/m19/cascade-strong.toml --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h03 --repeats 3 --max-cost 0.36 --out .cora/bench/m19/runs/c_s-m1-i02`
  plan: `uv run cora bench plan -c .cora/bench/m19/cascade-strong.toml --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab auto-routed --tasks e2e_h03 --repeats 3 --max-cost 0.36`
[M19-37 · c_s(m1) · e2e_h04,e2e_h05 · repeats 3] 기록 상한 0.45 (plan TOTAL 0.450000), --max-cost 0.45
  live: `uv run cora bench -c .cora/bench/m19/cascade-strong.toml --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h04,e2e_h05 --repeats 3 --max-cost 0.45 --out .cora/bench/m19/runs/c_s-m1-i03`
  plan: `uv run cora bench plan -c .cora/bench/m19/cascade-strong.toml --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab auto-routed --tasks e2e_h04,e2e_h05 --repeats 3 --max-cost 0.45`
[M19-38 · c_s(m1) · e2e_h06 · repeats 3] 기록 상한 0.27 (plan TOTAL 0.270000), --max-cost 0.27
  live: `uv run cora bench -c .cora/bench/m19/cascade-strong.toml --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h06 --repeats 3 --max-cost 0.27 --out .cora/bench/m19/runs/c_s-m1-i04`
  plan: `uv run cora bench plan -c .cora/bench/m19/cascade-strong.toml --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab auto-routed --tasks e2e_h06 --repeats 3 --max-cost 0.27`
[M19-39 · c_s(m1) · e2e_hx2 · repeats 3] 기록 상한 0.24 (plan TOTAL 0.240000), --max-cost 0.24
  live: `uv run cora bench -c .cora/bench/m19/cascade-strong.toml --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_hx2 --repeats 3 --max-cost 0.24 --out .cora/bench/m19/runs/c_s-m1-i05`
  plan: `uv run cora bench plan -c .cora/bench/m19/cascade-strong.toml --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab auto-routed --tasks e2e_hx2 --repeats 3 --max-cost 0.24`
[M19-40 · d1(m1) · e2e_hx1,e2e_hx2 · repeats 3] 기록 상한 0.39 (plan TOTAL 0.390000), --max-cost 0.39
  live: `uv run cora bench -c .cora/bench/m19/deleg-nudge.toml --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab deleg-on-par-on --tasks e2e_hx1,e2e_hx2 --repeats 3 --max-cost 0.39 --out .cora/bench/m19/runs/d1-m1-i01`
  plan: `uv run cora bench plan -c .cora/bench/m19/deleg-nudge.toml --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab deleg-on-par-on --tasks e2e_hx1,e2e_hx2 --repeats 3 --max-cost 0.39`
[M19-41 · c_s(m2) · e2e_h01,e2e_h02 · repeats 3] 기록 상한 0.42 (plan TOTAL 0.420000), --max-cost 0.42
  live: `uv run cora bench -c .cora/bench/m19/cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h01,e2e_h02 --repeats 3 --max-cost 0.42 --out .cora/bench/m19/runs/c_s-m2-i01`
  plan: `uv run cora bench plan -c .cora/bench/m19/cascade-strong.toml --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --tasks e2e_h01,e2e_h02 --repeats 3 --max-cost 0.42`
[M19-42 · c_s(m2) · e2e_h03 · repeats 3] 기록 상한 0.36 (plan TOTAL 0.360000), --max-cost 0.36
  live: `uv run cora bench -c .cora/bench/m19/cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h03 --repeats 3 --max-cost 0.36 --out .cora/bench/m19/runs/c_s-m2-i02`
  plan: `uv run cora bench plan -c .cora/bench/m19/cascade-strong.toml --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --tasks e2e_h03 --repeats 3 --max-cost 0.36`
[M19-43 · c_s(m2) · e2e_h04,e2e_h05 · repeats 3] 기록 상한 0.45 (plan TOTAL 0.450000), --max-cost 0.45
  live: `uv run cora bench -c .cora/bench/m19/cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h04,e2e_h05 --repeats 3 --max-cost 0.45 --out .cora/bench/m19/runs/c_s-m2-i03`
  plan: `uv run cora bench plan -c .cora/bench/m19/cascade-strong.toml --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --tasks e2e_h04,e2e_h05 --repeats 3 --max-cost 0.45`
[M19-44 · c_s(m2) · e2e_h06 · repeats 3] 기록 상한 0.27 (plan TOTAL 0.270000), --max-cost 0.27
  live: `uv run cora bench -c .cora/bench/m19/cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h06 --repeats 3 --max-cost 0.27 --out .cora/bench/m19/runs/c_s-m2-i04`
  plan: `uv run cora bench plan -c .cora/bench/m19/cascade-strong.toml --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --tasks e2e_h06 --repeats 3 --max-cost 0.27`
[M19-45 · c_s(m2) · e2e_hx2 · repeats 3] 기록 상한 0.24 (plan TOTAL 0.240000), --max-cost 0.24
  live: `uv run cora bench -c .cora/bench/m19/cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_hx2 --repeats 3 --max-cost 0.24 --out .cora/bench/m19/runs/c_s-m2-i05`
  plan: `uv run cora bench plan -c .cora/bench/m19/cascade-strong.toml --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --tasks e2e_hx2 --repeats 3 --max-cost 0.24`
[M19-46 · d1(m2) · e2e_hx1,e2e_hx2 · repeats 3] 기록 상한 0.39 (plan TOTAL 0.390000), --max-cost 0.39
  live: `uv run cora bench -c .cora/bench/m19/deleg-nudge.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab deleg-on-par-on --tasks e2e_hx1,e2e_hx2 --repeats 3 --max-cost 0.39 --out .cora/bench/m19/runs/d1-m2-i01`
  plan: `uv run cora bench plan -c .cora/bench/m19/deleg-nudge.toml --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab deleg-on-par-on --tasks e2e_hx1,e2e_hx2 --repeats 3 --max-cost 0.39`
[M19-47 · a(m3) · e2e_h01,e2e_h02 · repeats 3] 기록 상한 0.42 (plan TOTAL 0.289740), --max-cost 0.42
  live: `uv run cora bench --live --suite e2e --models mistralai/mistral-small-3.2-24b-instruct --protocols react --tasks e2e_h01,e2e_h02 --repeats 3 --max-cost 0.42 --out .cora/bench/m19/runs/a-m3-i01`
  plan: `uv run cora bench plan --suite e2e --models mistralai/mistral-small-3.2-24b-instruct --protocols react --tasks e2e_h01,e2e_h02 --repeats 3 --max-cost 0.42`
[M19-48 · a(m3) · e2e_h03 · repeats 3] 기록 상한 0.36 (plan TOTAL 0.158040), --max-cost 0.36
  live: `uv run cora bench --live --suite e2e --models mistralai/mistral-small-3.2-24b-instruct --protocols react --tasks e2e_h03 --repeats 3 --max-cost 0.36 --out .cora/bench/m19/runs/a-m3-i02`
  plan: `uv run cora bench plan --suite e2e --models mistralai/mistral-small-3.2-24b-instruct --protocols react --tasks e2e_h03 --repeats 3 --max-cost 0.36`
[M19-49 · a(m3) · e2e_h04,e2e_h05 · repeats 3] 기록 상한 0.45 (plan TOTAL 0.308040), --max-cost 0.45
  live: `uv run cora bench --live --suite e2e --models mistralai/mistral-small-3.2-24b-instruct --protocols react --tasks e2e_h04,e2e_h05 --repeats 3 --max-cost 0.45 --out .cora/bench/m19/runs/a-m3-i03`
  plan: `uv run cora bench plan --suite e2e --models mistralai/mistral-small-3.2-24b-instruct --protocols react --tasks e2e_h04,e2e_h05 --repeats 3 --max-cost 0.45`
[M19-50 · a(m3) · e2e_h06,e2e_hx1 · repeats 3] 기록 상한 0.42 (plan TOTAL 0.281700), --max-cost 0.42
  live: `uv run cora bench --live --suite e2e --models mistralai/mistral-small-3.2-24b-instruct --protocols react --tasks e2e_h06,e2e_hx1 --repeats 3 --max-cost 0.42 --out .cora/bench/m19/runs/a-m3-i04`
  plan: `uv run cora bench plan --suite e2e --models mistralai/mistral-small-3.2-24b-instruct --protocols react --tasks e2e_h06,e2e_hx1 --repeats 3 --max-cost 0.42`
[M19-51 · a(m3) · e2e_hx2 · repeats 3] 기록 상한 0.24 (plan TOTAL 0.158040), --max-cost 0.24
  live: `uv run cora bench --live --suite e2e --models mistralai/mistral-small-3.2-24b-instruct --protocols react --tasks e2e_hx2 --repeats 3 --max-cost 0.24 --out .cora/bench/m19/runs/a-m3-i05`
  plan: `uv run cora bench plan --suite e2e --models mistralai/mistral-small-3.2-24b-instruct --protocols react --tasks e2e_hx2 --repeats 3 --max-cost 0.24`

### 5. 벽시계 일정
- 벽시계 근거: qwen 실행당 = 탐침 latency 225.3 s × (과제 보정 입출력 토큰 합 / h05 보정 토큰 합 145310). m1과 강한 모델 = M18 보정 `latency_s`(무료 티어 상한 추정). b, c_s, c_cc는 × 1.5. d1은 × 1.5를 곱하지 않았습니다(열린 질문).
- 시작 기준은 2026-10-18 08:00Z(하한)입니다. 실제 시작은 2부 커밋 뒤입니다.
- 최악값 = 모든 실행이 wall_s 상한 2400 s까지 쓰는 경우입니다.
| 셀 (member-first, 실행 집합) | 예상 벽시계 (h) | 예상 끝 (누적, 하한 시작 08:00Z) | 최악 끝 (wall_s 2400 s 전부 사용) | 만료 플래그 |
|---|---|---|---|---|
| a(m1) | 1.96 | 10-18 09:57Z | 10-19 00:00Z |  |
| a(m2) | 2.16 | 10-18 12:07Z | 10-19 16:00Z |  |
| e | 1.96 | 10-18 14:04Z | 10-20 08:00Z |  |
| c_s(m1) | 2.67 | 10-18 16:45Z | 10-21 05:00Z |  |
| d1(m1) | 0.47 | 10-18 17:13Z | 10-21 09:00Z |  |
| c_s(m2) | 3.04 | 10-18 20:15Z | 10-22 06:00Z |  |
| d1(m2) | 0.40 | 10-18 20:39Z | 10-22 10:00Z | 최악값이 만료 뒤 (열린 질문, 만료 시점에 재결정) |
| a(m3) | 0.52 | 10-18 21:10Z | 10-23 02:00Z | 최악값이 만료 뒤 (열린 질문, 만료 시점에 재결정) |

- 예상 합계 13.18 h(예상 끝 약 2026-10-18 21:10Z, 만료 전). 최악값 합계 114.0 h. 최악값 기준으로 d1(m2)와 a(m3)는 만료 뒤에 끝납니다. 만료 뒤 셀은 2026-10-22 09:11 UTC 이전에 다시 결정합니다(결정 6). 키 교체는 만료 24 h 전까지 사용자에게 요청합니다.

### 6. 열린 질문과 해결 상태 (O4 답 반영, 2026-10-18)
- Q-O4-1 (절단 규칙): **해결**. 셀 단위 건너뛰기(1.5× 시작 규칙)(결정 5).
- Q-O4-2 (순서): **해결**. member-first(결정 2).
- Q-O4-3 (같은 한도 해석, R37): **해결(기본값)**. 계획 제안(역할별 상한, 1부 8항)을 적용. 사용자의 명시 답은 없음.
- Q-O4-4 (`--max-cost` ≤ 0.50): **해결**. 허용(결정 4).
- Q-O4-5 (선택 셀): a(m3) **포함**(결정 7). g(m2): **열린 질문**(답 없음, 실행 집합 밖).
- Q-O4-6 (팔 e 예상 열): **해결**. 보정 × 1.5 = $2.16(결정 3). 누적 e 지출이 $2.16을 넘으면 e를 멈추고 보고합니다(이 문구의 해석, 2부 사용자 확인 기록 참조).
- Q-O4-7 (벽시계 만료 플래그): **해결**. 만료 셀은 그 시점에 다시 결정(결정 6).
- Q-O4-8 (d2 재사용): **해결(기본값)**. 계획 제안(팔 a의 X 셀 재사용, 설정 일치 확인 뒤; 아니면 `--ab deleg-off`). d2는 실행 집합에 없습니다.
- Q-O4-9 ("$1.00 project-wide" 문구): **열린 질문**. 마일스톤 종료 때 사용자와 확인(결정 7 텍스트).
- Q-O4-10 (R16 일괄 확인 목록): **열린 질문**. 사용자 확인 전에는 유료 호출을 하지 않습니다.
- `/credits` O4 재판독 값, 키 한도와 계정 잔액의 0.80 차이, 예비 $0.76 부족분, `.ensemble/roadmap.md`의 M19 $5.00 문구: **열린 질문**.

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

## M19 측정 (2026-10-18T10:20:00Z)

### §0 준비
- 게이트(2026-10-18): `uv run pytest --full` 통과, `uv run pytest` 통과, `uv run ruff check src tests` 통과, `cmp cora.toml src/cora/data/cora.toml` 일치, arm 설정 4개 `.cora/bench/m19/` 와 `tests/fixtures/m19/arms/` 바이트 일치.
- Group A-D 커밋: 80ea2d2 (.gitignore 와 bench-results 추적), 48d1678 (패널 스크립트를 등록 규칙에 맞춤: oracle, n>=3 완결성, 합산 S 기준 최선 구성, S_cc 구간, blocked 행, P1 표, `--baseline none`), 3f2dd0f, ba79a0d, 0158249. 패널 스크립트 보정은 등록 항목의 변경이 아니며 첫 유료 호출 전에 기록한다.
- 등록 증거 (git 날짜는 사용자의 커밋 날짜 규칙으로 백데이트되어 시간 증거가 아니다. 시간 증거는 HEAD 조상 관계와 커밋 객체 mtime):

| 커밋 | 문서 시각 | 객체 mtime UTC | HEAD 조상 |
|---|---|---|---|
| 68afa71 | 2026-10-18T06:16:09Z | 2026-10-18T06:28:10Z | yes |
| 55496cf | 2026-10-18T08:03:40Z | 2026-10-18T08:07:00Z | yes |
| df188b7 | 2026-10-18T08:22:23Z | 2026-10-18T08:25:28Z | yes |

### §1 잔액 (2026-10-18, 유료 호출 전)
- `/auth/key`: limit 9, limit_remaining 6.145693928, usage 2.854306072, 만료 2026-10-22T09:11Z.
- `/credits`: total_credits 10, total_usage 3.053248517 (잔액 6.946751483).
- 0.80 차이의 원인: 키 한도가 $9 라 계정 크레딧 $10 중 $1 이 키에 배정되지 않았고(1.0), 이전에 다른 키로 쓴 $0.199 는 계정 사용량에만 잡힌다(1 - 0.199 = 0.801). 구속 한도는 키의 limit_remaining 이다.

### §2 리허설 (무료 Gemini, `env -u OPENROUTER_API_KEY`)
| 레시피 | 종료 | 결과 | 비용 | 설정 확인 |
|---|---|---|---|---|
| a | exit 0 | e2e_h05 solved (final_answer) | 0.0 | - |
| e | exit 0 | e2e_h05 solved | 0.0 | 과제 cost_usd 0.3 |
| c_s | exit 0 | e2e_h05 solved (final_answer), escalated False | 0.0 | escalation_target gemini-3.5-flash, sensor.source auto |
| d1 | exit 0 | e2e_hx1 solved (final_answer), deleg_attempts 0 | 0.0 | ab.arms [deleg-on-par-on] |
- `/credits` total_usage 리허설 전 3.053248517, 후 3.053248517 (변화 없음). 전 레시피 합격.
- 개정 1 점검 (2026-10-20, O4): (a) `plan-cmd` 상한 RR-01 0.042202, RR-02 0.042202, RR-03 0.035168, RR-04 0.147302, RR-05 0.122752, M19-29 0.147302, M19-35 0.420000, M19-41 0.420000, M19-46 0.390000 (계획 값과 일치). (b) deadline 리허설 `-c .cora/bench/m19/deadline.toml`, gemini-3.5-flash-lite, e2e_h05: exit 0, solved 1/1, 비용 0.0, 호출 30건 p50 11.66 s / 최대 19.03 s, 지연 호출 0; `/credits` total_usage 전 4.52036002, 후 4.52036002 (변화 없음). 소요 5분 46초. 설정 복사본 5개 `.cora/bench/m19/`에 설치, `cmp` 일치.
- 개정 2 점검 (2026-10-21, P4, 정정 13–16 적용 후): (a) `plan-cmd` 상한 RR-06 0.100000, RR-07 0.100000, RR-08 0.100000, RR-09 0.050000, M19-44 0.270000, M19-45 0.240000, M19-46 0.390000 (계획 값과 일치). (b) `live-cmd` RR-06, M19-44 모두 `deadline-nobedrock-cascade-strong.toml` (계획과 일치). (c) 무료 Gemini 리허설 `env -u OPENROUTER_API_KEY`, `.cora/bench/m19/deadline-nobedrock-deleg-nudge.toml`, gemini-3.5-flash-lite, react, `deleg-on-par-on`, e2e_hx1, repeats 1, `--max-cost 0.39`, `--out .cora/bench/m19/rehearsal/nobedrock`: rc 0, e2e_hx1 solved (final_answer, full_pass yes), 호출 21건, 정지 호출 0 (p50 11.95 s / 최대 14.03 s), 비용 0.000000, 지연 241.41 s, 보고서 `deleg_calls` 0 (위임 경로 미실행). `/credits` total_usage 5.800813871 로 변화 없음. 이 리허설이 증명하는 것은 새 키 설정의 라이브 로드와 검증까지이며, 위임 동작은 증명하지 않는다.
- 개정 3 점검 (2026-10-21, Q4, 유료 호출 없음): (a) `plan-cmd` RR-10 `total_max_usd: 0.090000` (계획 값과 일치; 커밋 21e036540d2eb7315f25dd991e3f4fe6c2e535d8, 객체 mtime 2026-10-21T03:15:11Z). (b) `live-cmd` RR-10 은 `deadline-nobedrock-cascade-strong.toml`, `--tasks e2e_h06 --repeats 1 --max-cost 0.09`, `--out .cora/bench/m19/runs/rerun-10` 명령을 출력 (계획과 일치). (c) 장부 사본 `/tmp/m19-rr10-dry.jsonl` (실제 장부에는 check 기록 없음), `/credits` usage 5.986411478, key limit_remaining 3.212530967, balance 4.013588522 (total_credits 10 에서 계산): PASS C1–C14, exit 0 (C12 `M19-44 e2e_h06 r2 is a RequestDeadlineExceeded error run`, C14 `--max-cost 0.090000 vs original task cap 0.090000`).

### §6 팔 f — Claude Code 기준선 (구독, 격리, n=3)
- 실행: 2026-10-18T10:30:47Z ~ 10:40:24Z (UTC), 과제 8개 x 3 = 24건, 모델 `claude-sonnet-5-5`, `--max-budget-usd 0.50`, 건마다 새 템플릿 복사본, 정답/채점기/숨은 검사/보정/이전 결과 없음. 24건 모두 세션 격리 감사 `clean`. `--max-budget-usd` 에 걸려 멈춘 실행 0건, 할당량 부족 0건, `is_error` 0건 (n 은 전 과제 3).
- 합계: 21/24 해결 (S_cc = 0.875). 보고된 `total_cost_usd` 합 $2.50 (구독 환산값, 실제 지출 아님; 사전 등록의 R29 가격 재계산 값은 `cost_recomputed_usd`).

| 과제 | 해결 | 평균 wall_s | 평균 재계산 비용 |
|---|---|---|---|
| e2e_h01 | 3/3 | 24.2 | 0.080 |
| e2e_h02 | 3/3 | 19.5 | 0.062 |
| e2e_h03 | 3/3 | 27.6 | 0.087 |
| e2e_h04 | 0/3 | 37.3 | 0.104 |
| e2e_h05 | 3/3 | 18.7 | 0.069 |
| e2e_h06 | 3/3 | 20.5 | 0.069 |
| e2e_hx1 | 3/3 | 13.9 | 0.062 |
| e2e_hx2 | 3/3 | 26.4 | 0.098 |
- e2e_h04 0/3 원인 조사 (표준 규칙: 우회 금지): 3건 모두 같은 숨은 검사 `variables_and_functions` 에서 `TypeError` 로 실패, 나머지 7개 검사 통과. 작업공간 재현: `calc("min(3)")` 가 `TypeError: 'float' object is not iterable` (요구사항 "min/max 는 인자 1개 이상" 위반). 과제/채점기 결함이 아니라 모델의 실제 오류. 해결 판정 유지. 이 환경에는 pytest 가 없어 Claude Code 가 테스트를 직접 호출해 확인했다고 보고함 (과제 환경 동일 조건).
- 산출: `.docs/baselines/claude-code-m19.toml`, `claude-code-m19-runs.jsonl` (사본 `tests/fixtures/m19/`). 수용 검사 `tests/m19_panel.py a=... --baseline .docs/baselines/claude-code-m19.toml` exit 0.

### §3 사용자 확인 (L1, 2026-10-18)
- 사용자가 51건 호출 목록(예상 합 $5.7299, 배정 $6.00, 건너뜀 b(m1), c_cc(m1→m2), b(m2), g(m2))과 멈춤 11곳에 "오케이 좋습니다"로 확인함. 같은 caps 해석(A1)과 조건부 셀 편입은 별도 확인이 필요하다는 조건도 함께 제시되었고 이의 없음.
- 멈춤 11곳(보고 후 사용자 "계속"을 받고 다음 호출로 진행; 규칙, 순서, 호출 목록은 불변): M19-05, M19-10, M19-19, M19-28, M19-34(필수 체크포인트 2), M19-37, M19-40, M19-45, M19-46, M19-49, M19-51.
- 원장 초기화: paid_total 3.07, /credits usage 3.053249, key limit_remaining 6.145694, balance 6.946751 (`tests/fixtures/m19/ledger.jsonl`). 첫 유료 호출은 아직 나가지 않음.

### §10 편차 (2026-10-21, 개정 2 P4)
- P0 탐침 (qwen3-coder-30b, `max_tokens` 1, 요청 3회, 2026-10-21 00:39Z)은 유료 호출이었다 (선택 사항으로 계획했으나 실행됨). `/credits` total_usage 5.800810791 → 5.800813871 (차이 0.000003080). M19 원장 (m19_total) 밖의 지출이며, 결과는 정정 13의 P1–P3과 같다.
- 개정 2 커밋 c528549b83eb937a419c25824584c33b82039794 (객체 mtime 2026-10-21T00:52:56Z)은 RR-06과 M19-44 보다 앞선다 (HEAD 조상). 리허설 보고서 (2026-10-21T00:57:20Z)는 그 뒤다.
- P4 (a)–(c)는 계획 값과 모두 일치했다 (§2). 그 밖의 편차는 없다.
- P4 시점에 새로 나간 유료 호출은 P0 탐침뿐이다. RR-06..09 와 M19-44..46 은 아직 실행하지 않았으며 P5 사용자 확인을 기다린다.

### §10 편차 (2026-10-21, 개정 3 Q4)
- 유료 호출 없음. Q4 는 $0 점검과 증거 기록만 했다. (a)–(c) 결과는 §2 의 개정 3 점검 항목에 있다.
- (d) 실패 호출 증거 (정정 19 재실행 전, 사용자 결정 불변: 제한 값 300 s 유지). 대상은 M19-44 e2e_h06 r2 (세션 `20261021-112525-045e85`, `.cora/bench/m19/runs/c_s-m2-i04/`).
  - 실패 호출: 강한 단계 deepseek-v3.2 호출, 반복 8→9 (edit_file 트립와이어 3회 실패 후 02:28:26Z 에 강한 단계로 에스컬레이션). 최종 오류는 `RequestDeadlineExceeded` (request_deadline_s=300 s, no complete response).
  - 이벤트 기록: `events.jsonl` 에 이 호출의 `llm_call` 기록은 없다. 시간 초과된 시도는 공급자가 과금하지만 기록되지 않는다. 시도 횟수는 기록되어 있지 않다. 보고서 r2 행의 `calls` 는 8이고 `call_latencies_s` 는 9개 항목이며, 마지막 항목 903.022 s 가 이 실패 호출에 해당하는 것으로 보인다. 903.022 = 3 × 300 + 3 (정정 6 의 대기 1 s, 2 s) 와 같은 산술 값이며, 3회 시도와 일치한다. 이 값만으로 호출이 멈췄다거나 느렸다고 결론짓지 않는다.
  - 프롬프트 크기: 실패 호출의 입력 토큰은 기록되지 않았다. 같은 세션의 기록된 deepseek 호출 입력 토큰은 9709–11469 이다.
  - 같은 M19-44 의 기록된 deepseek-v3.2 호출 (latency_s / output_tokens / input_tokens): 20.64 s / 127 / 9709; 3.88 s / 88 / 10885; 192.78 s / 2630 / 11418; 100.45 s / 1160 / 9760; 19.35 s / 273 / 11469. 같은 세션의 qwen3-coder-30b 호출 3건 latency_s: 35.02 s, 75.68 s, 70.57 s.
  - 정산: M19-44 장부 정산 과금 델타 0.058750 과 보고서 비용 0.043149 의 차이 0.015601 은 기록되지 않은 과금 시도와 일치한다 (consistent with; 증명이 아니다).
- 그 밖의 편차는 없다. RR-10 은 아직 실행하지 않았으며 Q5 사용자 확인을 기다린다.

### §4 호출 기록

- 등록 51건 (M19-01..51) 전부 `executed`. 재실행 RR-01..10 은 등록 호출 밖의 재실행으로 장부에 별도 행이다. 조건부 셀 19행은 `not_measured` 로 기록되었다 (§5, §10).
- 명령 열은 실행된 유효 명령이다 (`수정`/`편차` 표기 포함). 아래 표는 `uv run python tests/m19_ledger.py table` 출력 그대로다.
- `/credits 차이` = 호출 전후 `/credits` total_usage 차이. `M19 누적` = 장부 spend 누적이며 spend = max(/credits 차이, 보고서 비용) (정정 11). `유료 누적` = 3.07 + (`/credits` total_usage − 3.053249) (원장 기준).

#### 호출

| 호출 | 셀 | 상태 | 명령 | plan TOTAL | --max-cost | 키 잔액 | 계정 잔액 | /credits 전 | /credits 후 | 보고서 | 보고서 비용 | /credits 차이 | M19 누적 | 유료 누적 | 비고 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M19-01 | a(m1) | executed | `uv run cora bench --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --tasks e2e_h01,e2e_h02 --repeats 3 --max-cost 0.42 --out .cora/bench/m19/runs/a-m1-i01` | 0.330864 | 0.420000 | 6.145694 | 6.946751 | 3.053249 | 3.197650 | .cora/bench/m19/runs/a-m1-i01/report.json | 0.144401 | 0.144401 | 0.144401 | 3.214401 |  |
| M19-02 | a(m1) | executed | `uv run cora bench --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --tasks e2e_h03 --repeats 3 --max-cost 0.36 --out .cora/bench/m19/runs/a-m1-i02` | 0.180864 | 0.360000 | 6.001293 | 6.802350 | 3.197650 | 3.438253 | .cora/bench/m19/runs/a-m1-i02/report.json | 0.240603 | 0.240603 | 0.385005 | 3.455005 |  |
| M19-03 | a(m1) | executed | `uv run cora bench --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --tasks e2e_h04,e2e_h05 --repeats 3 --max-cost 0.45 --out .cora/bench/m19/runs/a-m1-i03` | 0.330864 | 0.450000 | 5.760689 | 6.561747 | 3.438253 | 3.587821 | .cora/bench/m19/runs/a-m1-i03/report.json | 0.149568 | 0.149568 | 0.534572 | 3.604572 |  |
| M19-04 | a(m1) | executed | `uv run cora bench --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --tasks e2e_h06,e2e_hx1 --repeats 3 --max-cost 0.42 --out .cora/bench/m19/runs/a-m1-i04` | 0.300720 | 0.420000 | 5.611122 | 6.412179 | 3.587821 | 3.680482 | .cora/bench/m19/runs/a-m1-i04/report.json | 0.092661 | 0.092661 | 0.627234 | 3.697234 |  |
| M19-05 | a(m1) | executed | `uv run cora bench --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --tasks e2e_hx2 --repeats 3 --max-cost 0.24 --out .cora/bench/m19/runs/a-m1-i05` | 0.180864 | 0.240000 | 5.518460 | 6.319518 | 3.680482 | 3.701158 | .cora/bench/m19/runs/a-m1-i05/report.json | 0.020676 | 0.020676 | 0.647910 | 3.717910 |  |
| M19-06 | a(m2) | executed | `uv run cora bench --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_h01,e2e_h02 --repeats 3 --max-cost 0.42 --out .cora/bench/m19/runs/a-m2-i01` | 0.232109 | 0.420000 | 5.497784 | 6.298842 | 3.701158 | 3.770906 | .cora/bench/m19/runs/a-m2-i01/report.json | 0.068788 | 0.069748 | 0.717658 | 3.787658 |  |
| M19-07 | a(m2) | executed | `uv run cora bench --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_h03 --repeats 3 --max-cost 0.36 --out .cora/bench/m19/runs/a-m2-i02` | 0.126605 | 0.360000 | 5.428036 | 6.229094 | 3.770906 | 3.822875 | .cora/bench/m19/runs/a-m2-i02/report.json | 0.049047 | 0.051969 | 0.769626 | 3.839626 |  |
| M19-08 | a(m2) | executed | `uv run cora bench --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_h04,e2e_h05 --repeats 3 --max-cost 0.45 --out .cora/bench/m19/runs/a-m2-i03` | 0.253210 | 0.450000 | 5.376068 | 6.177125 | 3.822875 | 3.933850 | .cora/bench/m19/runs/a-m2-i03/report.json | 0.088309 | 0.110975 | 0.880601 | 3.950601 |  |
| M19-09 | a(m2) | executed | `uv run cora bench --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_h06,e2e_hx1 --repeats 3 --max-cost 0.42 --out .cora/bench/m19/runs/a-m2-i04` | 0.232109 | 0.420000 | 5.265093 | 6.066150 | 3.933850 | 3.968593 | .cora/bench/m19/runs/a-m2-i04/report.json | 0.029524 | 0.034744 | 0.915345 | 3.985345 |  |
| M19-10 | a(m2) | executed | `uv run cora bench --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_hx2 --repeats 3 --max-cost 0.24 --out .cora/bench/m19/runs/a-m2-i05` | 0.126605 | 0.240000 | 5.229751 | 6.030808 | 3.969192 | 3.974632 | .cora/bench/m19/runs/a-m2-i05/report.json | 0.003684 | 0.005440 | 0.920785 | 3.991383 |  |
| M19-11 | e | executed | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h01 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i01` | 0.147302 | 0.300000 | 5.224310 | 6.025368 | 3.974632 | 4.013220 | .cora/bench/m19/runs/e-i01/report.json | 0.038588 | 0.038588 | 0.959374 | 4.029972 | 출력 경로 편차 (사전 등록 수정 참조) |
| M19-12 | e | executed | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h01 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i02` | 0.147302 | 0.300000 | 5.185722 | 5.986780 | 4.013220 | 4.040911 | .cora/bench/m19/runs/e-i02/report.json | 0.027691 | 0.027691 | 0.987065 | 4.057663 | 출력 경로 편차 (사전 등록 수정 참조) |
| M19-13 | e | executed | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h01 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i03` | 0.147302 | 0.300000 | 5.158031 | 5.959089 | 4.040911 | 4.072811 | .cora/bench/m19/runs/e-i03/report.json | 0.031900 | 0.031900 | 1.018965 | 4.089563 | 출력 경로 편차 (사전 등록 수정 참조) |
| M19-14 | e | executed | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h02 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i04` | 0.122752 | 0.300000 | 5.126131 | 5.927189 | 4.072811 | 4.088164 | .cora/bench/m19/runs/e-i04/report.json | 0.015353 | 0.015353 | 1.034318 | 4.104916 | 출력 경로 편차 (사전 등록 수정 참조) |
| M19-15 | e | executed | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h02 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i05` | 0.122752 | 0.300000 | 5.110778 | 5.911836 | 4.088164 | 4.112594 | .cora/bench/m19/runs/e-i05/report.json | 0.024430 | 0.024430 | 1.058747 | 4.129345 | 출력 경로 편차 (사전 등록 수정 참조) |
| M19-16 | e | executed | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h02 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i06` | 0.122752 | 0.300000 | 5.086349 | 5.887406 | 4.112594 | 4.131421 | .cora/bench/m19/runs/e-i06/report.json | 0.018827 | 0.018827 | 1.077574 | 4.148172 | 출력 경로 편차 (사전 등록 수정 참조) |
| M19-17 | e | executed | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h03 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i07` | 0.147302 | 0.300000 | 5.067522 | 5.868579 | 4.131421 | 4.173151 | .cora/bench/m19/runs/e-i07/report.json | 0.037989 | 0.041731 | 1.119305 | 4.189903 | 출력 경로 편차 (사전 등록 수정 참조) |
| M19-18 | e | executed | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h03 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i08` | 0.147302 | 0.300000 | 5.025791 | 5.826849 | 4.173151 | 4.223189 | .cora/bench/m19/runs/e-i08/report.json | 0.050038 | 0.050038 | 1.169342 | 4.239940 | 출력 경로 편차 (사전 등록 수정 참조) |
| M19-19 | e | executed | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h03 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i09` | 0.147302 | 0.300000 | 4.975754 | 5.776811 | 4.223189 | 4.282628 | .cora/bench/m19/runs/e-i09/report.json | 0.059439 | 0.059439 | 1.228781 | 4.299379 | 출력 경로 편차 (사전 등록 수정 참조) |
| M19-20 | e | executed | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h04 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i10` | 0.147302 | 0.300000 | 4.916315 | 5.717372 | 4.282628 | 4.321771 | .cora/bench/m19/runs/e-i10/report.json | 0.039144 | 0.039144 | 1.267924 | 4.338523 | 출력 경로 편차 (사전 등록 수정 참조) |
| M19-21 | e | executed | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h04 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i11` | 0.147302 | 0.300000 | 4.877171 | 5.678229 | 4.321771 | 4.343177 | .cora/bench/m19/runs/e-i11/report.json | 0.012349 | 0.021406 | 1.289330 | 4.359929 | 출력 경로 편차 (사전 등록 수정 참조) |
| M19-22 | e | executed | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h04 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i12` | 0.147302 | 0.300000 | 4.855765 | 5.656823 | 4.343177 | 4.389334 | .cora/bench/m19/runs/e-i12/report.json | 0.046157 | 0.046157 | 1.335488 | 4.406086 | 출력 경로 편차 (사전 등록 수정 참조) |
| M19-23 | e | executed | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h05 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i13` | 0.147302 | 0.300000 | 4.809608 | 5.610666 | 4.389334 | 4.419329 | .cora/bench/m19/runs/e-i13/report.json | 0.029995 | 0.029995 | 1.365483 | 4.436081 | 출력 경로 편차 (사전 등록 수정 참조) |
| M19-24 | e | executed | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h05 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i14` | 0.147302 | 0.300000 | 4.779613 | 5.580671 | 4.419329 | 4.443845 | .cora/bench/m19/runs/e-i14/report.json | 0.024516 | 0.024516 | 1.389998 | 4.460596 | 출력 경로 편차 (사전 등록 수정 참조) |
| M19-25 | e | executed | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h05 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i15` | 0.147302 | 0.300000 | 4.755098 | 5.556155 | 4.443845 | 4.467185 | .cora/bench/m19/runs/e-i15/report.json | 0.023340 | 0.023340 | 1.413338 | 4.483936 | 출력 경로 편차 (사전 등록 수정 참조) |
| M19-26 | e | executed | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h06 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i16` | 0.122752 | 0.300000 | 4.731758 | 5.532815 | 4.467185 | 4.472726 | .cora/bench/m19/runs/e-i16/report.json | 0.000720 | 0.005541 | 1.418879 | 4.489478 | 출력 경로 편차 (사전 등록 수정 참조) |
| M19-27 | e | executed | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h06 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i17` | 0.122752 | 0.300000 | 4.726216 | 5.527274 | 4.472726 | 4.497864 | .cora/bench/m19/runs/e-i17/report.json | 0.025138 | 0.025138 | 1.444017 | 4.514615 | 출력 경로 편차 (사전 등록 수정 참조) |
| M19-28 | e | executed | `uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h06 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i18` | 0.122752 | 0.300000 | 4.701079 | 5.502136 | 4.497864 | 4.520360 | .cora/bench/m19/runs/e-i18/report.json | 0.022496 | 0.022496 | 1.466513 | 4.537112 | 출력 경로 편차 (사전 등록 수정 참조) |
| M19-29 | e | executed | `uv run cora bench -c .cora/bench/m19/deadline.toml --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_hx1 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i19` | 0.147302 | 0.300000 | 4.581023 | 5.382080 | 4.617920 | 4.641112 | .cora/bench/m19/runs/e-i19/report.json | 0.023193 | 0.023192 | 1.590431 | 4.657864 | 명령 수정 (사전 등록 수정 참조) |
| M19-30 | e | executed | `uv run cora bench -c .cora/bench/m19/deadline.toml --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_hx1 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i20` | 0.147302 | 0.300000 | 4.557830 | 5.358888 | 4.641112 | 4.661949 | .cora/bench/m19/runs/e-i20/report.json | 0.020837 | 0.020837 | 1.611268 | 4.678701 | 명령 수정 (사전 등록 수정 참조) |
| M19-31 | e | executed | `uv run cora bench -c .cora/bench/m19/deadline.toml --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_hx1 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i21` | 0.147302 | 0.300000 | 4.536993 | 5.338051 | 4.661949 | 4.679823 | .cora/bench/m19/runs/e-i21/report.json | 0.017874 | 0.017874 | 1.629142 | 4.696575 | 명령 수정 (사전 등록 수정 참조) |
| M19-32 | e | executed | `uv run cora bench -c .cora/bench/m19/deadline.toml --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_hx2 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i22` | 0.147302 | 0.300000 | 4.519119 | 5.320177 | 4.679823 | 4.727644 | .cora/bench/m19/runs/e-i22/report.json | 0.047821 | 0.047821 | 1.676963 | 4.744395 | 명령 수정 (사전 등록 수정 참조) |
| M19-33 | e | executed | `uv run cora bench -c .cora/bench/m19/deadline.toml --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_hx2 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i23` | 0.147302 | 0.300000 | 4.471299 | 5.272356 | 4.727644 | 4.751141 | .cora/bench/m19/runs/e-i23/report.json | 0.023497 | 0.023497 | 1.700460 | 4.767892 | 명령 수정 (사전 등록 수정 참조) |
| M19-34 | e | executed | `uv run cora bench -c .cora/bench/m19/deadline.toml --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_hx2 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i24` | 0.147302 | 0.300000 | 4.447801 | 5.248859 | 4.751141 | 4.771617 | .cora/bench/m19/runs/e-i24/report.json | 0.020476 | 0.020476 | 1.720936 | 4.788369 | 명령 수정 (사전 등록 수정 참조) |
| M19-35 | c_s(m1) | executed | `uv run cora bench -c .cora/bench/m19/deadline-cascade-strong.toml --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h01,e2e_h02 --repeats 3 --max-cost 0.42 --out .cora/bench/m19/runs/c_s-m1-i01` | 0.420000 | 0.420000 | 4.427325 | 5.228383 | 4.771617 | 4.948506 | .cora/bench/m19/runs/c_s-m1-i01/report.json | 0.170333 | 0.176889 | 1.897825 | 4.965258 | 명령 수정 (사전 등록 수정 참조) |
| M19-36 | c_s(m1) | executed | `uv run cora bench -c .cora/bench/m19/deadline-cascade-strong.toml --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h03 --repeats 3 --max-cost 0.36 --out .cora/bench/m19/runs/c_s-m1-i02` | 0.360000 | 0.360000 | 4.250436 | 5.051494 | 4.948506 | 5.075367 | .cora/bench/m19/runs/c_s-m1-i02/report.json | 0.126861 | 0.126861 | 2.024686 | 5.092119 | 명령 수정 (사전 등록 수정 참조) |
| M19-37 | c_s(m1) | executed | `uv run cora bench -c .cora/bench/m19/deadline-cascade-strong.toml --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h04,e2e_h05 --repeats 3 --max-cost 0.45 --out .cora/bench/m19/runs/c_s-m1-i03` | 0.450000 | 0.450000 | 4.123575 | 4.924633 | 5.075367 | 5.284712 | .cora/bench/m19/runs/c_s-m1-i03/report.json | 0.209345 | 0.209345 | 2.234031 | 5.301464 | 명령 수정 (사전 등록 수정 참조) |
| M19-38 | c_s(m1) | executed | `uv run cora bench -c .cora/bench/m19/deadline-cascade-strong.toml --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h06 --repeats 3 --max-cost 0.27 --out .cora/bench/m19/runs/c_s-m1-i04` | 0.270000 | 0.270000 | 3.914230 | 4.715288 | 5.284712 | 5.348517 | .cora/bench/m19/runs/c_s-m1-i04/report.json | 0.063805 | 0.063805 | 2.297836 | 5.365268 | 명령 수정 (사전 등록 수정 참조) |
| M19-39 | c_s(m1) | executed | `uv run cora bench -c .cora/bench/m19/deadline-cascade-strong.toml --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_hx2 --repeats 3 --max-cost 0.24 --out .cora/bench/m19/runs/c_s-m1-i05` | 0.240000 | 0.240000 | 3.850425 | 4.651483 | 5.348517 | 5.392033 | .cora/bench/m19/runs/c_s-m1-i05/report.json | 0.043516 | 0.043516 | 2.341352 | 5.408785 | 명령 수정 (사전 등록 수정 참조) |
| M19-40 | d1(m1) | executed | `uv run cora bench -c .cora/bench/m19/deleg-nudge.toml --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab deleg-on-par-on --tasks e2e_hx1,e2e_hx2 --repeats 3 --max-cost 0.39 --out .cora/bench/m19/runs/d1-m1-i01` | 0.390000 | 0.390000 | 3.806909 | 4.607967 | 5.392033 | 5.437342 | .cora/bench/m19/runs/d1-m1-i01/report.json | 0.045308 | 0.045308 | 2.386661 | 5.454093 |  |
| M19-41 | c_s(m2) | executed | `uv run cora bench -c .cora/bench/m19/deadline-cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h01,e2e_h02 --repeats 3 --max-cost 0.42 --out .cora/bench/m19/runs/c_s-m2-i01` | 0.420000 | 0.420000 | 3.761601 | 4.562658 | 5.437342 | 5.672727 | .cora/bench/m19/runs/c_s-m2-i01/report.json | 0.235385 | 0.235385 | 2.622046 | 5.689478 | 명령 수정 (사전 등록 수정 참조) |
| M19-42 | c_s(m2) | executed | `uv run cora bench -c .cora/bench/m19/deadline-cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h03 --repeats 3 --max-cost 0.36 --out .cora/bench/m19/runs/c_s-m2-i02` | 0.360000 | 0.360000 | 3.526216 | 4.327273 | 5.672727 | 5.749935 | .cora/bench/m19/runs/c_s-m2-i02/report.json | 0.077208 | 0.077208 | 2.699254 | 5.766687 | 명령 수정 (사전 등록 수정 참조) |
| M19-43 | c_s(m2) | executed | `uv run cora bench -c .cora/bench/m19/deadline-cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h04,e2e_h05 --repeats 3 --max-cost 0.45 --out .cora/bench/m19/runs/c_s-m2-i03` | 0.450000 | 0.450000 | 3.449007 | 4.250065 | 5.749935 | 5.800811 | .cora/bench/m19/runs/c_s-m2-i03/report.json | 0.050876 | 0.050876 | 2.750130 | 5.817562 | 명령 수정 (사전 등록 수정 참조) |
| M19-44 | c_s(m2) | executed | `uv run cora bench -c .cora/bench/m19/deadline-nobedrock-cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h06 --repeats 3 --max-cost 0.27 --out .cora/bench/m19/runs/c_s-m2-i04` | 0.270000 | 0.270000 | 3.271281 | 4.072339 | 5.927661 | 5.986411 | .cora/bench/m19/runs/c_s-m2-i04/report.json | 0.043149 | 0.058750 | 2.935727 | 6.003163 | 명령 수정 (사전 등록 수정 참조) |
| M19-45 | c_s(m2) | executed | `uv run cora bench -c .cora/bench/m19/deadline-nobedrock-cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_hx2 --repeats 3 --max-cost 0.24 --out .cora/bench/m19/runs/c_s-m2-i05` | 0.240000 | 0.240000 | 3.181521 | 3.982578 | 6.017422 | 6.052194 | .cora/bench/m19/runs/c_s-m2-i05/report.json | 0.034772 | 0.034772 | 3.001509 | 6.068945 | 명령 수정 (사전 등록 수정 참조) |
| M19-46 | d1(m2) | executed | `uv run cora bench -c .cora/bench/m19/deadline-nobedrock-deleg-nudge.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab deleg-on-par-on --tasks e2e_hx1,e2e_hx2 --repeats 3 --max-cost 0.39 --out .cora/bench/m19/runs/d1-m2-i01` | 0.390000 | 0.390000 | 3.146749 | 3.947806 | 6.052194 | 6.115855 | .cora/bench/m19/runs/d1-m2-i01/report.json | 0.062302 | 0.063662 | 3.065171 | 6.132607 | 명령 수정 (사전 등록 수정 참조) |
| M19-47 | a(m3) | executed | `uv run cora bench --live --suite e2e --models mistralai/mistral-small-3.2-24b-instruct --protocols react --tasks e2e_h01,e2e_h02 --repeats 3 --max-cost 0.42 --out .cora/bench/m19/runs/a-m3-i01` | 0.289740 | 0.420000 | 3.083087 | 3.884145 | 6.115855 | 6.186307 | .cora/bench/m19/runs/a-m3-i01/report.json | 0.070452 | 0.070452 | 3.135623 | 6.203058 |  |
| M19-48 | a(m3) | executed | `uv run cora bench --live --suite e2e --models mistralai/mistral-small-3.2-24b-instruct --protocols react --tasks e2e_h03 --repeats 3 --max-cost 0.36 --out .cora/bench/m19/runs/a-m3-i02` | 0.158040 | 0.360000 | 3.012635 | 3.813693 | 6.186307 | 6.267977 | .cora/bench/m19/runs/a-m3-i02/report.json | 0.081670 | 0.081670 | 3.217293 | 6.284729 |  |
| M19-49 | a(m3) | executed | `uv run cora bench --live --suite e2e --models mistralai/mistral-small-3.2-24b-instruct --protocols react --tasks e2e_h04,e2e_h05 --repeats 3 --max-cost 0.45 --out .cora/bench/m19/runs/a-m3-i03` | 0.308040 | 0.450000 | 2.930965 | 3.732023 | 6.267977 | 6.345232 | .cora/bench/m19/runs/a-m3-i03/report.json | 0.077255 | 0.077255 | 3.294548 | 6.361984 |  |
| M19-50 | a(m3) | executed | `uv run cora bench --live --suite e2e --models mistralai/mistral-small-3.2-24b-instruct --protocols react --tasks e2e_h06,e2e_hx1 --repeats 3 --max-cost 0.42 --out .cora/bench/m19/runs/a-m3-i04` | 0.281700 | 0.420000 | 2.853710 | 3.654768 | 6.345232 | 6.379840 | .cora/bench/m19/runs/a-m3-i04/report.json | 0.034608 | 0.034608 | 3.329156 | 6.396591 |  |
| M19-51 | a(m3) | executed | `uv run cora bench --live --suite e2e --models mistralai/mistral-small-3.2-24b-instruct --protocols react --tasks e2e_hx2 --repeats 3 --max-cost 0.24 --out .cora/bench/m19/runs/a-m3-i05` | 0.158040 | 0.240000 | 2.819103 | 3.620160 | 6.379840 | 6.408055 | .cora/bench/m19/runs/a-m3-i05/report.json | 0.028215 | 0.028215 | 3.357370 | 6.424806 |  |
| B1-01 | b(m1) | not_measured | `uv run cora bench --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --verify-attempts 3 --tasks e2e_h01,e2e_h02 --repeats 3 --max-cost 0.42 --out .cora/bench/m19/runs/b-m1-i01` | — | 0.420000 | — | — | — | — | — | 0.000000 | 0.000000 | 2.341352 | 5.408785 | 2026-10-20 user decision (제안대로): conditional cell b(m1) not run; outside the confirmed 51 calls (prereg 1부 11항: not measured (budget)) |
| B1-02 | b(m1) | not_measured | `uv run cora bench --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --verify-attempts 3 --tasks e2e_h03 --repeats 3 --max-cost 0.36 --out .cora/bench/m19/runs/b-m1-i02` | — | 0.360000 | — | — | — | — | — | 0.000000 | 0.000000 | 2.341352 | 5.408785 | 2026-10-20 user decision (제안대로): conditional cell b(m1) not run; outside the confirmed 51 calls (prereg 1부 11항: not measured (budget)) |
| B1-03 | b(m1) | not_measured | `uv run cora bench --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --verify-attempts 3 --tasks e2e_h04,e2e_h05 --repeats 3 --max-cost 0.45 --out .cora/bench/m19/runs/b-m1-i03` | — | 0.450000 | — | — | — | — | — | 0.000000 | 0.000000 | 2.341352 | 5.408785 | 2026-10-20 user decision (제안대로): conditional cell b(m1) not run; outside the confirmed 51 calls (prereg 1부 11항: not measured (budget)) |
| B1-04 | b(m1) | not_measured | `uv run cora bench --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --verify-attempts 3 --tasks e2e_h06 --repeats 3 --max-cost 0.27 --out .cora/bench/m19/runs/b-m1-i04` | — | 0.270000 | — | — | — | — | — | 0.000000 | 0.000000 | 2.341352 | 5.408785 | 2026-10-20 user decision (제안대로): conditional cell b(m1) not run; outside the confirmed 51 calls (prereg 1부 11항: not measured (budget)) |
| B1-05 | b(m1) | not_measured | `uv run cora bench --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --verify-attempts 3 --tasks e2e_hx2 --repeats 3 --max-cost 0.24 --out .cora/bench/m19/runs/b-m1-i05` | — | 0.240000 | — | — | — | — | — | 0.000000 | 0.000000 | 2.341352 | 5.408785 | 2026-10-20 user decision (제안대로): conditional cell b(m1) not run; outside the confirmed 51 calls (prereg 1부 11항: not measured (budget)) |
| CC-01 | c_cc(m1→m2) | not_measured | `uv run cora bench -c .cora/bench/m19/deadline-cascade-m1-m2.toml --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h01,e2e_h02 --repeats 3 --max-cost 0.42 --out .cora/bench/m19/runs/c_cc-m1-i01` | — | 0.420000 | — | — | — | — | — | 0.000000 | 0.000000 | 2.386661 | 5.454093 | 2026-10-20 user decision (제안대로): conditional cell c_cc(m1→m2) not run; outside the confirmed 51 calls (prereg 1부 11항: not measured (budget)) |
| CC-02 | c_cc(m1→m2) | not_measured | `uv run cora bench -c .cora/bench/m19/deadline-cascade-m1-m2.toml --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h03 --repeats 3 --max-cost 0.36 --out .cora/bench/m19/runs/c_cc-m1-i02` | — | 0.360000 | — | — | — | — | — | 0.000000 | 0.000000 | 2.386661 | 5.454093 | 2026-10-20 user decision (제안대로): conditional cell c_cc(m1→m2) not run; outside the confirmed 51 calls (prereg 1부 11항: not measured (budget)) |
| CC-03 | c_cc(m1→m2) | not_measured | `uv run cora bench -c .cora/bench/m19/deadline-cascade-m1-m2.toml --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h04,e2e_h05 --repeats 3 --max-cost 0.45 --out .cora/bench/m19/runs/c_cc-m1-i03` | — | 0.450000 | — | — | — | — | — | 0.000000 | 0.000000 | 2.386661 | 5.454093 | 2026-10-20 user decision (제안대로): conditional cell c_cc(m1→m2) not run; outside the confirmed 51 calls (prereg 1부 11항: not measured (budget)) |
| CC-04 | c_cc(m1→m2) | not_measured | `uv run cora bench -c .cora/bench/m19/deadline-cascade-m1-m2.toml --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h06 --repeats 3 --max-cost 0.27 --out .cora/bench/m19/runs/c_cc-m1-i04` | — | 0.270000 | — | — | — | — | — | 0.000000 | 0.000000 | 2.386661 | 5.454093 | 2026-10-20 user decision (제안대로): conditional cell c_cc(m1→m2) not run; outside the confirmed 51 calls (prereg 1부 11항: not measured (budget)) |
| CC-05 | c_cc(m1→m2) | not_measured | `uv run cora bench -c .cora/bench/m19/deadline-cascade-m1-m2.toml --live --suite e2e --models google/gemini-2.5-flash-lite --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_hx2 --repeats 3 --max-cost 0.24 --out .cora/bench/m19/runs/c_cc-m1-i05` | — | 0.240000 | — | — | — | — | — | 0.000000 | 0.000000 | 2.386661 | 5.454093 | 2026-10-20 user decision (제안대로): conditional cell c_cc(m1→m2) not run; outside the confirmed 51 calls (prereg 1부 11항: not measured (budget)) |
| B2-01 | b(m2) | not_measured | `uv run cora bench -c .cora/bench/m19/deadline.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --verify-attempts 3 --tasks e2e_h01,e2e_h02 --repeats 3 --max-cost 0.42 --out .cora/bench/m19/runs/b-m2-i01` | — | 0.420000 | — | — | — | — | — | 0.000000 | 0.000000 | 3.001509 | 6.068945 | 2026-10-20 user decision (제안대로): conditional cell b(m2) not run; outside the confirmed 51 calls (prereg 1부 11항: not measured (budget)) |
| B2-02 | b(m2) | not_measured | `uv run cora bench -c .cora/bench/m19/deadline.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --verify-attempts 3 --tasks e2e_h03 --repeats 3 --max-cost 0.36 --out .cora/bench/m19/runs/b-m2-i02` | — | 0.360000 | — | — | — | — | — | 0.000000 | 0.000000 | 3.001509 | 6.068945 | 2026-10-20 user decision (제안대로): conditional cell b(m2) not run; outside the confirmed 51 calls (prereg 1부 11항: not measured (budget)) |
| B2-03 | b(m2) | not_measured | `uv run cora bench -c .cora/bench/m19/deadline.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --verify-attempts 3 --tasks e2e_h04,e2e_h05 --repeats 3 --max-cost 0.45 --out .cora/bench/m19/runs/b-m2-i03` | — | 0.450000 | — | — | — | — | — | 0.000000 | 0.000000 | 3.001509 | 6.068945 | 2026-10-20 user decision (제안대로): conditional cell b(m2) not run; outside the confirmed 51 calls (prereg 1부 11항: not measured (budget)) |
| B2-04 | b(m2) | not_measured | `uv run cora bench -c .cora/bench/m19/deadline.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --verify-attempts 3 --tasks e2e_h06 --repeats 3 --max-cost 0.27 --out .cora/bench/m19/runs/b-m2-i04` | — | 0.270000 | — | — | — | — | — | 0.000000 | 0.000000 | 3.001509 | 6.068945 | 2026-10-20 user decision (제안대로): conditional cell b(m2) not run; outside the confirmed 51 calls (prereg 1부 11항: not measured (budget)) |
| B2-05 | b(m2) | not_measured | `uv run cora bench -c .cora/bench/m19/deadline.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --verify-attempts 3 --tasks e2e_hx2 --repeats 3 --max-cost 0.24 --out .cora/bench/m19/runs/b-m2-i05` | — | 0.240000 | — | — | — | — | — | 0.000000 | 0.000000 | 3.001509 | 6.068945 | 2026-10-20 user decision (제안대로): conditional cell b(m2) not run; outside the confirmed 51 calls (prereg 1부 11항: not measured (budget)) |
| G2-01 | g(m2) | not_measured | `uv run cora bench -c .cora/bench/m19/deadline-keys-on.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_h01,e2e_h02 --repeats 3 --max-cost 0.42 --out .cora/bench/m19/runs/g-m2-i01` | — | 0.420000 | — | — | — | — | — | 0.000000 | 0.000000 | 3.357370 | 6.424806 | 2026-10-20 user decision (제안대로): conditional cell g(m2) not run; outside the confirmed 51 calls (prereg 1부 11항: not measured (budget)) |
| G2-02 | g(m2) | not_measured | `uv run cora bench -c .cora/bench/m19/deadline-keys-on.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_h03 --repeats 3 --max-cost 0.36 --out .cora/bench/m19/runs/g-m2-i02` | — | 0.360000 | — | — | — | — | — | 0.000000 | 0.000000 | 3.357370 | 6.424806 | 2026-10-20 user decision (제안대로): conditional cell g(m2) not run; outside the confirmed 51 calls (prereg 1부 11항: not measured (budget)) |
| G2-03 | g(m2) | not_measured | `uv run cora bench -c .cora/bench/m19/deadline-keys-on.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_h04,e2e_h05 --repeats 3 --max-cost 0.45 --out .cora/bench/m19/runs/g-m2-i03` | — | 0.450000 | — | — | — | — | — | 0.000000 | 0.000000 | 3.357370 | 6.424806 | 2026-10-20 user decision (제안대로): conditional cell g(m2) not run; outside the confirmed 51 calls (prereg 1부 11항: not measured (budget)) |
| G2-04 | g(m2) | not_measured | `uv run cora bench -c .cora/bench/m19/deadline-keys-on.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_h06 --repeats 3 --max-cost 0.27 --out .cora/bench/m19/runs/g-m2-i04` | — | 0.270000 | — | — | — | — | — | 0.000000 | 0.000000 | 3.357370 | 6.424806 | 2026-10-20 user decision (제안대로): conditional cell g(m2) not run; outside the confirmed 51 calls (prereg 1부 11항: not measured (budget)) |

#### 재실행

| 재실행 | 원 호출 | 셀 | 과제 | 원 반복 | 상태 | 결과 | 명령 | plan TOTAL | --max-cost | 키 잔액 | 계정 잔액 | /credits 전 | /credits 후 | 보고서 | 보고서 비용 | /credits 차이 | M19 누적 | 유료 누적 | 비고 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| RR-01 | M19-08 | a(m2) | e2e_h04 | 0 | executed | failed | `uv run cora bench -c .cora/bench/m19/deadline.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_h04 --repeats 1 --max-cost 0.08 --out .cora/bench/m19/runs/rerun-01` | 0.042202 | 0.080000 | 4.678582 | 5.479640 | 4.520360 | 4.534139 | .cora/bench/m19/runs/rerun-01/report.json | 0.013779 | 0.013779 | 1.480292 | 4.550890 |  |
| RR-02 | M19-08 | a(m2) | e2e_h05 | 2 | executed | solved | `uv run cora bench -c .cora/bench/m19/deadline.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_h05 --repeats 1 --max-cost 0.08 --out .cora/bench/m19/runs/rerun-02` | 0.042202 | 0.080000 | 4.664803 | 5.465861 | 4.534139 | 4.540091 | .cora/bench/m19/runs/rerun-02/report.json | 0.005952 | 0.005952 | 1.486244 | 4.556842 |  |
| RR-03 | M19-09 | a(m2) | e2e_h06 | 0 | executed | solved | `uv run cora bench -c .cora/bench/m19/deadline.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_h06 --repeats 1 --max-cost 0.07 --out .cora/bench/m19/runs/rerun-03` | 0.035168 | 0.070000 | 4.658852 | 5.459909 | 4.540091 | 4.548145 | .cora/bench/m19/runs/rerun-03/report.json | 0.008055 | 0.008055 | 1.494299 | 4.564897 |  |
| RR-04 | M19-21 | e | e2e_h04 | 0 | executed | failed | `uv run cora bench -c .cora/bench/m19/deadline.toml --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h04 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/rerun-04` | 0.147302 | 0.300000 | 4.650797 | 5.451855 | 4.548145 | 4.596950 | .cora/bench/m19/runs/rerun-04/report.json | 0.051971 | 0.048805 | 1.546269 | 4.613702 |  |
| RR-05 | M19-26 | e | e2e_h06 | 0 | executed | solved | `uv run cora bench -c .cora/bench/m19/deadline.toml --live --suite e2e --models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 --tasks e2e_h06 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/rerun-05` | 0.122752 | 0.300000 | 4.601992 | 5.403050 | 4.596950 | 4.617920 | .cora/bench/m19/runs/rerun-05/report.json | 0.017804 | 0.020969 | 1.567239 | 4.634671 |  |
| RR-06 | M19-43 | c_s(m2) | e2e_h04 | 0 | executed | failed | `uv run cora bench -c .cora/bench/m19/deadline-nobedrock-cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h04 --repeats 1 --max-cost 0.10 --out .cora/bench/m19/runs/rerun-06` | 0.100000 | 0.100000 | 3.398129 | 4.199186 | 5.800814 | 5.854477 | .cora/bench/m19/runs/rerun-06/report.json | 0.053663 | 0.053663 | 2.803792 | 5.871228 |  |
| RR-07 | M19-43 | c_s(m2) | e2e_h04 | 1 | executed | failed | `uv run cora bench -c .cora/bench/m19/deadline-nobedrock-cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h04 --repeats 1 --max-cost 0.10 --out .cora/bench/m19/runs/rerun-07` | 0.100000 | 0.100000 | 3.344466 | 4.145523 | 5.854477 | 5.900702 | .cora/bench/m19/runs/rerun-07/report.json | 0.046225 | 0.046225 | 2.850018 | 5.917453 |  |
| RR-08 | M19-43 | c_s(m2) | e2e_h04 | 2 | executed | failed | `uv run cora bench -c .cora/bench/m19/deadline-nobedrock-cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h04 --repeats 1 --max-cost 0.10 --out .cora/bench/m19/runs/rerun-08` | 0.100000 | 0.100000 | 3.298240 | 4.099298 | 5.900702 | 5.918422 | .cora/bench/m19/runs/rerun-08/report.json | 0.017720 | 0.017720 | 2.867738 | 5.935174 |  |
| RR-09 | M19-43 | c_s(m2) | e2e_h05 | 2 | executed | solved | `uv run cora bench -c .cora/bench/m19/deadline-nobedrock-cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h05 --repeats 1 --max-cost 0.05 --out .cora/bench/m19/runs/rerun-09` | 0.050000 | 0.050000 | 3.280520 | 4.081578 | 5.918422 | 5.927661 | .cora/bench/m19/runs/rerun-09/report.json | 0.009239 | 0.009239 | 2.876977 | 5.944413 |  |
| RR-10 | M19-44 | c_s(m2) | e2e_h06 | 2 | executed | failed | `uv run cora bench -c .cora/bench/m19/deadline-nobedrock-cascade-strong.toml --live --suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed --sensor --sensor-source auto --tasks e2e_h06 --repeats 1 --max-cost 0.09 --out .cora/bench/m19/runs/rerun-10` | 0.090000 | 0.090000 | 3.212531 | 4.013589 | 5.986411 | 6.017422 | .cora/bench/m19/runs/rerun-10/report.json | 0.031010 | 0.031010 | 2.966738 | 6.034173 |  |

#### 이벤트

| UTC | 종류 | 셀 | 내용 |
|---|---|---|---|
| 2026-10-18T12:36:28Z | user | — | 2026-10-18 멈춤 지점 11곳 확정; 보고만, 규칙/순서 불변 |
| 2026-10-19T12:56:15Z | deviation | a(m2) | 2026-10-19 qwen billed cost exceeds bench-reported cost by ~1-6% (M19-06 +0.00096, M19-07 +0.0029); accepted by user, spend uses billed delta; unexplained |
| 2026-10-19T14:30:47Z | deviation | a(m2) | 2026-10-19 M19-08: 2 error runs (provider request deadline 90s); billed cost exceeds report by 0.0227; whether error runs are rerun/counted pending prereg check (R5) and harness-defect review |
| 2026-10-19T14:48:32Z | user | a(m2) | 2026-10-19 user approved: no rerun, no code/config change; error runs counted unsolved per prereg; at cell a(m2) end report sensitivity analysis (errors as unsolved vs excluded) and per-cell error / >90s-call counts; billed cost used for cost metrics. a(m2) so far: M19-06 1 call>90s, M19-07 2, M19-08 9 + 2 error runs. |
| 2026-10-20T07:27:14Z | user | — | 2026-10-20 scenario A: deadline fix (request_deadline_s 300, call_timeout_s 960, timeout_s 300) via -c deadline configs; RequestDeadlineExceeded error runs rerun once; original runs kept |
| 2026-10-20T07:27:14Z | amend | rerun | 2026-10-20T07:26:12Z 사전 등록 수정 (2026-10-20T07:18:53Z) commit d9c1696 (object mtime 2026-10-20T07:26:12Z): RR-01..RR-05, M19-29..39/41..46 deadline configs, M19-11..28 out deviation recorded |
| 2026-10-20T07:37:12Z | deviation | e | 2026-10-20 RR-01 check C5 failed (credits 4.520360 vs 4.518597, +0.001763): late billing of M19-28 caught up; re-settled M19-28 at 4.520360, delta 0.022496 == report cost 0.022496 (mismatch false). Cause of the earlier 'below report' note identified: usage lag, not a real discrepancy. No new spend. |
| 2026-10-20T09:59:02Z | checkpoint | — | 2026-10-20 checkpoint 2 (after M19-34): panel a(m1) class c, a(m2) indeterminate, e 19/24 (replace+billed); rule (iv) not literally triggered (m1 is c); user answer: option 1, continue as planned, each segment needs separate approval |
| 2026-10-20T11:39:47Z | user | b(m1) | 2026-10-20 user decision (제안대로): conditional cell b(m1) recorded not_measured, no amendment |
| 2026-10-20T11:47:20Z | user | c_cc(m1→m2) | 2026-10-20 user decision (제안대로): conditional cell c_cc(m1→m2) recorded not_measured, no amendment |
| 2026-10-21T00:53:09Z | user | c_s(m2) | 2026-10-20 user option 1: OpenRouter provider_ignore=[amazon-bedrock] via -c deadline-nobedrock configs for M19-44..46 and RR-06..09; HTTP 400 stopSequences error runs rerun once at the original task cap; originals kept |
| 2026-10-21T00:53:09Z | deviation | c_s(m2) | M19-43: 4 of 6 runs error HTTP 400 stopSequences (e2e_h04 r0-r2, e2e_h05 r2); qwen requests routed to Amazon Bedrock, which rejects stop (정정 13) |
| 2026-10-21T00:53:09Z | deviation | rerun | 정정 16: RR-01/RR-03 ran with per-task cap 0.08/0.07 (originals 0.10/0.09) under 정정 10; non-binding (cost 0.013779/0.008055, final_answer); results stand |
| 2026-10-21T00:53:09Z | deviation | c_s(m2) | 2026-10-21 D-R2 probe P1/P2/P3: 400 stopSequences/200 Amazon Bedrock/200 SiliconFlow; /credits 5.800810791 -> 5.800813871 (outside m19_total) |
| 2026-10-21T00:53:09Z | amend | rerun | 2026-10-21T00:43:16Z 사전 등록 수정 (2026-10-21T00:43:16Z) commit c528549b83eb937a419c25824584c33b82039794 (object mtime 2026-10-21T00:52:56Z): RR-06..RR-09, M19-44..46 deadline-nobedrock configs, provider_ignore |
| 2026-10-21T03:04:46Z | user | c_s(m2) | 2026-10-21 user: M19-44 e2e_h06 r2 error RequestDeadlineExceeded (strong-tier deepseek call >300s): rerun once (RR-10) under rule (c), keep deadline settings 300/960/300, settle M19-44 on billed cost |
| 2026-10-21T03:15:11Z | deviation | c_s(m2) | M19-44: e2e_h06 r2 error RequestDeadlineExceeded at request_deadline_s=300 in a strong-tier deepseek-v3.2 call (iteration 8->9); not stopSequences (정정 18) |
| 2026-10-21T03:15:11Z | amend | rerun | 2026-10-21T03:15:11Z 사전 등록 수정 (2026-10-21T03:10:52Z) commit 21e036540d2eb7315f25dd991e3f4fe6c2e535d8 (object mtime 2026-10-21T03:15:11Z): RR-10 = M19-44 e2e_h06 r2, same config deadline-nobedrock-cascade-strong.toml, --max-cost 0.09 (정정 19) |
| 2026-10-21T09:38:28Z | user | b(m2) | 2026-10-20 user decision (제안대로): conditional cell b(m2) recorded not_measured, no amendment |
| 2026-10-21T12:03:38Z | user | g(m2) | 2026-10-20 user decision (제안대로): conditional cell g(m2) recorded not_measured, no amendment |

### §5 셀 판정

- 셀 표의 `판정` 열은 할당 산술 (예상 $, 남은 배정, 1.5× 필요) 만으로 계산된 값이다. 조건부 셀 b(m1), c_cc(m1→m2), b(m2), g(m2) 는 이 열에서 RUN 으로 남아 있으나, 사용자 결정으로 `not_measured` 가 기록되었고 호출은 나가지 않았다 (이벤트 2026-10-20T11:39:47Z, 2026-10-20T11:47:20Z, 2026-10-21T09:38:28Z, 2026-10-21T12:03:38Z).
- 셀별 판정 결과 (장부 spend, 청구 규칙, 재실행 포함):

| 셀 | 판정 | 등록 호출 | 재실행 | 장부 spend |
|---|---|---|---|---|
| a(m1) | 실행 완료 | M19-01..05 (5/5) | - | 0.647910 |
| a(m2) | 실행 완료 | M19-06..10 (5/5) | RR-01..03 | 0.300661 |
| e | 실행 완료 (e 정지 C8 미발생, e 의 `not_measured` 0) | M19-11..34 (24/24) | RR-04, RR-05 | 0.772365 |
| c_s(m1) | 실행 완료 | M19-35..39 (5/5) | - | 0.620416 |
| d1(m1) | 실행 완료 | M19-40 (1 호출, 6 실행) | - | 0.045308 |
| c_s(m2) | 실행 완료 | M19-41..45 (5/5) | RR-06..10 | 0.614849 |
| d1(m2) | 실행 완료 | M19-46 (1 호출, 6 실행) | - | 0.063662 |
| a(m3) | 실행 완료 | M19-47..51 (5/5) | - | 0.292199 |
| b(m1) | not_measured (budget) | 0 (행 5개 모두 `not_measured`) | - | 0.000000 |
| c_cc(m1→m2) | not_measured (budget) | 0 (행 5개 모두 `not_measured`) | - | 0.000000 |
| b(m2) | not_measured (budget) | 0 (행 5개 모두 `not_measured`) | - | 0.000000 |
| g(m2) | not_measured (budget) | 0 (행 4개 모두 `not_measured`) | - | 0.000000 |

- 합계 장부 spend 3.357370 = 8개 실행 셀 합. 등록 51건 3.098788 + 재실행 RR-01..10 0.258583 (반올림 차이 0.000001).
- 셀 표 (`table` 출력 그대로):

#### 셀

| 셀 | 예상 $ | 남은 배정 | 1.5× 필요 | 판정 |
|---|---|---|---|---|
| a(m1) | 0.850600 | 6.000000 | 1.275900 | RUN |
| a(m2) | 0.442400 | 5.352090 | 0.663600 | RUN |
| e | 2.155100 | 5.080329 | 3.232650 | RUN |
| c_s(m1) | 1.197400 | 4.279064 | 1.796100 | RUN |
| b(m1) | 1.197400 | 3.658648 | 1.796100 | RUN |
| d1(m1) | 0.236500 | 3.658648 | 0.354750 | RUN |
| c_cc(m1→m2) | 1.197400 | 3.613339 | 1.796100 | RUN |
| c_s(m2) | 0.622800 | 3.613339 | 0.934200 | RUN |
| b(m2) | 0.622800 | 2.998491 | 0.934200 | RUN |
| d1(m2) | 0.123000 | 2.998491 | 0.184500 | RUN |
| a(m3) | 0.102100 | 2.934829 | 0.153150 | RUN |
| g(m2) | 0.360400 | 2.642630 | 0.540600 | RUN |

### §6 팔 f

- §6 은 2026-10-18 에 기록되어 있으며 이번 기록에서 변경하지 않았다 (n=3 전 과제, 예산 중지 0건, 격리 감사 24/24 clean, 실행 시각 2026-10-18T10:30:47Z ~ 10:40:24Z).

### §7 분석

- 1차 분석 `tests/fixtures/m19/panel.md` 원문: 오류 정책 replace, 청구 비용 billed, 민감도 (g/g2) 포함, `--extras` 포함, `--d2` 인자 없음 (d2 not measured, §10).

```text
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
```

- 등록 기본 보기 `tests/fixtures/m19/panel-registered.md` 원문: 같은 호출, 오류 실행 unsolved, 보고서 비용 (네 추가 플래그 없음).

```text
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
```

- 미측정 셀 (두 보기 공통):
  - b(m1): not measured (budget)
  - c_cc(m1→m2): not measured (budget)
  - b(m2): not measured (budget)
  - g(m2): not measured (budget)
  - d2(m1), d2(m2): not measured (d2check DIFF, 등록 51건 밖, §10)
- 사실 요약 (1차 / 등록 기본):
  - 팔 a, 8 과제 × n=3: gemini 2/24 (0.083) / 2/24; mistral 2/24 (0.083) / 2/24; qwen 6/24 (0.250) / 4/24 (0.167).
  - 팔 c_s, 7 과제: gemini 5/21 (0.238) / 5/21; qwen 3/21 (0.143) / 2/21 (0.095).
  - 팔 d1, 2 과제 (e2e_hx1, e2e_hx2) × n=3: gemini 0/6 / 0/6; qwen 2/6 (0.333) / 2/6.
  - 참조 e (strong, deepseek-v3.2): 19/24 (0.792) / 18/24 (0.750). Claude Code S_cc: 21/24 (0.875, Wilson [0.690, 0.957]).
  - 팔 a 합집합 (R41): 1차 4 of 8 과제, oracle ratio 0.250, oracle spd 23.1; 등록 기본 3 of 8 과제, oracle ratio 0.167, oracle spd 17.3.
  - 위임 (패널 (e)): d1 gemini 6 실행, attempts 6, started 5, solved 0. d1 qwen 6 실행, attempts 0, started 0, solved 2 (이 6회에서 위임 시도가 기록되지 않음).
  - 오류 민감도 (g): 팔 a qwen 4/24 (unsolved) ~ 6/24 (replace), c_s qwen 2/21 ~ 3/21, e 18/24 ~ 19/24. 90 s 초과 호출 수와 오류 실행 수는 (g2) 표.

### §8 P1

- P1 b: not measured (budget). b(m1), b(m2) 셀 미측정. 기본값 변경 없음.
- P1 c_s: OFF. c_s gemini 7 과제 S 0.238, spd 8.1 대 같은 과제의 팔 a 최선 (qwen) S 0.238, spd 18.5 (1차). 등록 기본 보기: 0.238 / 8.1 대 0.143 / 13.1. spd 가 팔 a 보다 낮아 ON 조건 불충족. c_s qwen S 0.143 (기본 0.095) 은 팔 a 보다 낮다.
- P1 c_cc: not measured (budget). c_cc(m1→m2) 셀 미측정. 기본값 변경 없음.
- P1 d1: OFF. d1 qwen 2 과제 S 0.333, spd 31.4 (1차; 기본 보기 32.1) 대 같은 과제의 팔 a 최선 (qwen) S 0.167, spd 57.3 (기본 보기 72.0). spd 가 팔 a 보다 낮아 ON 조건 불충족. d1 gemini S 0.000 (0/6).
- M17b 키 `raw_file_body`, `repeat_breaker`, `located_errors` 는 `false` 로 유지 (cora.toml 에서 확인, ADR-32).

### §9 분류와 중단 규칙

- 최선 구성 (사후 선택; 후보 a, b, c_s, c_cc, d1, d2; 기준 풀이 비율, 타이 spd; e 는 후보 아님): d1 qwen/qwen3-coder-30b-a3b-instruct, 2/6, S 0.333, 구간 [0.097, 0.700].
- 최선 구성 분류: `indeterminate` (구간이 분류 경계를 넘음; 상위 분류는 주장하지 않음). S_cc (같은 2 과제 Claude Code 6/6) 1.000, 구간 [0.610, 1.000]. 비용 우위 판정 yes (spd 31.4 대 Claude Code 12.5, 1차; 등록 기본 32.1 대 12.5).
- 팔 a 분류 (1차 / 등록 기본): gemini-2.5-flash-lite c (2/24) / c; mistral-small-3.2-24b-instruct c (2/24) / c; qwen3-coder-30b-a3b-instruct indeterminate (6/24, 구간 [0.137, 0.513]) / indeterminate (4/24, 구간 [0.076, 0.410]).
- 한계: (1) 과제당 n=3, 구간 폭 약 ±0.2 (A6). (2) 최선 구성은 사후 선택 (후보 중 최대 풀이 비율)이므로 낙관적 (A20). (3) d1 은 과제 2개 (e2e_hx1, e2e_hx2) 의 6 실행뿐이다. (4) d1 qwen 의 위임 시도는 이 6 실행에서 0 으로 기록되었다 (패널 (e)).

- 사용자 결정 (2026-10-22): 현재 결과로 종결 (최선 구성 d1 qwen 2/6, `indeterminate` 그대로 기록), M20 으로 진행.

### §10 편차 (L4 최종 기록, 2026-10-21)

- 건너뜀 (skip): 조건부 셀 4개, 호출 19행 (b(m1) B1-01..05, c_cc CC-01..05, b(m2) B2-01..05, g(m2) G2-01..04). 사유: 사용자 결정 (이벤트 2026-10-20T11:39:47Z, 2026-10-20T11:47:20Z, 2026-10-21T09:38:28Z, 2026-10-21T12:03:38Z), 수정 없이 `not_measured` 기록. M19-51 후 잔여 M19 배정 2.642630.
- 멈춤 (stop points): 사용자 확인 멈춤 11곳 (§3) 은 확인 조건대로 진행. 장부의 중간 결정: checkpoint 2 (M19-34 후, 2026-10-20T09:59:02Z) 사용자 답 옵션 1 (계속, 구간마다 별도 승인). 셀 e 의 정지 (C8) 는 발생하지 않았다.
- 예산 중지 (보고서 상태 `stopped_budget`, stop_reason `cost_limit`) 5건, 등록 호출 안: M19-35 c_s(m1) e2e_h02 1건; M19-37 c_s(m1) e2e_h05 2건; M19-41 c_s(m2) e2e_h01 1건과 e2e_h02 1건. 전부 c_s 셀이며 a, e, d1 보고서에는 없다. 이 실행은 미해결로 집계되었다. 편향 신호로 보고한다.
- 재실행 (정정 10·16·19): 원 오류 실행 10건 각 1회, `--repeats 1`, 원 실행 유지. 원 오류 분포: a(m2) 3 (M19-08 2, M19-09 1), e 2 (M19-21, M19-26), c_s(m2) 5 (M19-43 4, M19-44 1).
  - RR-01 (M19-08 a e2e_h04 r0) failed; RR-02 (M19-08 a e2e_h05 r2) solved; RR-03 (M19-09 a e2e_h06 r0) solved.
  - RR-04 (M19-21 e e2e_h04 r0) failed; RR-05 (M19-26 e e2e_h06 r0) solved.
  - RR-06 (M19-43 c_s e2e_h04 r0) failed; RR-07 (e2e_h04 r1) failed; RR-08 (e2e_h04 r2) failed; RR-09 (M19-43 c_s e2e_h05 r2) solved; RR-10 (M19-44 c_s e2e_h06 r2) failed.
  - 결과: solved 4 (RR-02, RR-03, RR-05, RR-09), failed 6 (RR-01, RR-04, RR-06, RR-07, RR-08, RR-10). 재실행 실패 후 추가 재실행 없음.
  - 편차 (정정 16): RR-01 과 RR-03 은 과제 상한 0.08 / 0.07 로 실행 (원 0.10 / 0.09). 비구속 (비용 0.013779 / 0.008055, final_answer), 결과 유지.
  - 1차 분석은 재실행 결과가 원 오류 실행을 대체한다 (replace). 등록 기본 보기는 원 오류 실행을 unsolved 로 둔다.
- 라우팅 수정 (정정 13·14; 사용자 결정 2026-10-20, 옵션 1): M19-43 c_s(m2) 6 실행 중 4건 HTTP 400 stopSequences (e2e_h04 r0–r2, e2e_h05 r2). 요청이 Amazon Bedrock 으로 라우팅되어 거부되었다. 이후 M19-44..46 과 RR-06..09 는 `deadline-nobedrock-*` 설정 (`provider_ignore = [amazon-bedrock]`). 원 실행은 유지. 유료 탐침 P1–P3 (원장 밖): 400 stopSequences / 200 Amazon Bedrock / 200 SiliconFlow; /credits 5.800810791 → 5.800813871 (0.000003080).
- 요청 시간 제한 (정정 6–7, 18): 원 90 s 제한의 오류 5건 (M19-08 2, M19-09 1, M19-21 1, M19-26 1) → RR-01..05 를 `deadline.toml` (request_deadline_s 300, call_timeout_s 960, timeout_s 300) 로 재실행. M19-44 e2e_h06 r2 (strong 단계 deepseek 호출, 반복 8→9) 는 300 s 에서 RequestDeadlineExceeded, 재실행 RR-10 도 failed. 상세는 §10 개정 3 Q4 항목 (d). 보고서의 c_s qwen e2e_h06 최대 호출 903.0 s (3×300+3 산술과 일치) 는 시도 횟수의 추정이며 기록된 호출 증거가 아니다. M19-44 정산은 사용자 결정 (청구 기준, 0.058750; 보고서 0.043149).
- 정산 격차: 13 호출 (M19-07, 08, 09, 10, 17, 21, 26, 28, 35, 44, 46, RR-04, RR-05) 에서 /credits 차이와 보고서 비용이 불일치했고 각각 `resolve` 기록이 있다. M19-28 은 첫 정산 후 재정산 (2026-10-20T07:36:57Z, 일치). RR-01 의 C5 점검 실패는 지연 청구 탓으로 기록되었고 신규 지출은 없다 (이벤트 2026-10-20T07:37:12Z).
- 출력 경로 편차 (정정 9, 사후 기록): M19-11..28 (18 호출) `--out .cora/bench/m19/runs/e-iNN` (등록 `e-strong-iNN`). 명령 수정 (정정 8·14): M19-29..39, 41..46 (17 호출) 의 `-c` 설정 교체 (`deadline*`, `deadline-nobedrock-*`). 등록 명령 그대로인 호출: M19-40 (`deleg-nudge.toml`), M19-47..51.
- d2 (A4): `d2check` m1 과 m2 모두 `DIFF max_task_cost_usd: a=0.09 d1=0.08` (exit 1). d2(m1), d2(m2) = not measured (등록 51건 밖, 패널 인자에 `--d2` 없음). 정정 11 caveat, (g2) 90 s 초과 호출 수: m2 의 a(m2) X 과제 (90 s 제한) e2e_hx1 1, e2e_hx2 2; d1(m2) (300 s) e2e_hx1 12, e2e_hx2 1. m1 의 a(m1) 과 d1(m1) X 과제는 0, 0.
- 리허설 설정 편차: 없음 (§2 의 네 리허설과 개정 1·2·3 점검, 계획 값과 일치).
- 팔 f 편차: 없음 (§6).
- 그 밖: 유료 탐침 P0 (qwen3-coder-30b, 요청 3회) 는 원장 밖 지출이며 개정 2 항목에 기록되어 있다.

### §11 종료 보고

- 유료 누적 (원장, 최종 M19-51 및 RR-10 후): 6.424806 ≤ $10. 충족.
- M19 누적 (원장): 3.357370 ≤ $6.00. 충족. 잔여 배정 2.642630. 구성: 등록 51건 3.098788, 재실행 0.258583.
- 잔액 (M19-51 호출 전, 장부): 키 limit_remaining 2.819103, 계정 잔액 3.620160 (차이 0.801057, §1 과 같음). 마지막 호출 후 값은 장부에 없고 같은 차이로 계산하면 키 약 2.790888, 계정 약 3.591945. 키 만료 2026-10-22T09:11Z; 마지막 정산 2026-10-21T12:03:38Z.
- A1 (같은 caps 해석): 등록 해석 (역할별 caps, 패널 구성원 간) 을 적용했다. 사용자의 명시 답은 없고 2026-10-18 확인에서 이의가 없었다 (§3). 최종 보고에서 사용자에게 알린다.
- A5 (지출 예상과 잔액): 등록 예상 합 5.7299 (8개 실행 셀, 6.00 대비 잔여 0.27) 대 실제 M19 누적 3.357370 (잔여 2.642630). 호출별 plan TOTAL 합 (51행) 11.138322 은 셀 예상 표와 기준이 달라 직접 비교하지 않는다. M20 과 예비금 부족 (키 잔액 6.1457 대 charter 산술) 은 이 기록에서 결정하지 않으며 사용자에게 보고한다.
- 로드맵 exit (M19 행):
  - (1) 셀 순서, 셀별 건너뜀, 호출 전 점검 (plan, `/credits`, check/record/settle): done. 등록 51건 실행. 조건부 4셀은 not measured (budget) (§5).
  - (2) 측정 셀 n=3 과 Wilson, Claude Code 기준 n=3: done. `(a2)` 불완전 셀 없음. 기준 24건 21/24 (S_cc 0.875).
  - (3) panel 출력 (R38 분류, 비용 우위 판정, R41 합집합/oracle, 위임 표): done (§7, §9).
  - (4) P1 (b, c_s, c_cc, d1): partial. c_s OFF, d1 OFF; b, c_cc = not measured (budget) (§8). M17b 키 false 유지.
  - (5) 분류별 중단 규칙 과 지출 상한: 지출 상한 done (6.424806 ≤ $10). 분류 결정: 최선 구성 indeterminate, 사용자 결정 2026-10-22 (현재 결과로 종결, M20 진행; §9).


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

## M19d 완전 사전 라우터 상한 (2026-10-22T00:58:58Z)

### 규칙

- 오라클 규칙 (계산 전에 고정): 과제마다 싼 그룹과 강한 그룹 중 관측 풀이율 k/n이 높은 쪽을 고른다.
- 동률 (k/n 같음): 시도당 평균 비용(cost/n)이 싼 그룹을 고른다. 평균 비용도 같으면 싼 그룹.
- 싼 그룹 = 과제별 최선 `a` 모델: k/n 높은 순, 다음 평균 비용 낮은 순, 다음 모델 이름 오름차순. 대상 모델: google/gemini-2.5-flash-lite, mistralai/mistral-small-3.2-24b-instruct, qwen/qwen3-coder-30b-a3b-instruct.
- 강한 그룹 = arm `e` 단일 모델 (deepseek/deepseek-v3.2).
- 제외 arm: `c_s`, `d1` (싼 모델과 강한 모델이 섞여 있음).
- 한 그룹에만 데이터가 있으면 그 그룹을 고른다 (`only data`). 둘 다 없으면 과제 이름을 missing으로 적고 모든 분모에서 뺀다. 대체하지 않는다.
- 오라클 합계 = 선택 그룹의 k, n, 비용을 과제에 걸쳐 합한 값.

### 보기

- 청구 기준 보기: 정정 11 기준 (대체 + 청구, `tests/fixtures/m19/panel-extras.json`, `panel.md`와 같음).
- 등록 보기: 등록 기본 보기 (오류 실행 미해결, 보고서 비용, `panel-registered.md`와 같음).
- Claude Code 비용: 두 보기 모두 toml (`claude-code-m19.toml`) 비용이며 원장 금액이 없다.

### 결과

청구 기준 보기 비교 표:

| row | config | tasks | solved/total | ratio | wilson95 | cost_usd | solved/$ | missing |
|---|---|---|---|---|---|---|---|---|
| oracle | per-task choice | 8/8 | 19/24 | 0.792 | [0.595, 0.908] | 0.7454 | 25.5 | none |
| best single cheap | qwen/qwen3-coder-30b-a3b-instruct | 8/8 | 6/24 | 0.250 | [0.120, 0.449] | 0.2830 | 21.2 | none |
| strong | deepseek/deepseek-v3.2 | 8/8 | 19/24 | 0.792 | [0.595, 0.908] | 0.7454 | 25.5 | none |
| Claude Code | claude-code-m19.toml (toml cost, no ledger) | 8/8 | 21/24 | 0.875 | [0.690, 0.957] | 1.8933 | 11.1 | none |

등록 보기 비교 표:

| row | config | tasks | solved/total | ratio | wilson95 | cost_usd | solved/$ | missing |
|---|---|---|---|---|---|---|---|---|
| oracle | per-task choice | 8/8 | 18/24 | 0.750 | [0.551, 0.880] | 0.6818 | 26.4 | none |
| best single cheap | qwen/qwen3-coder-30b-a3b-instruct | 8/8 | 4/24 | 0.167 | [0.067, 0.359] | 0.2394 | 16.7 | none |
| strong | deepseek/deepseek-v3.2 | 8/8 | 18/24 | 0.750 | [0.551, 0.880] | 0.6818 | 26.4 | none |
| Claude Code | claude-code-m19.toml (toml cost, no ledger) | 8/8 | 21/24 | 0.875 | [0.690, 0.957] | 1.8933 | 11.1 | none |

청구 기준 보기 과제별 표:

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

- 과제별 선택: 두 보기 모두 8개 과제 중 강한 그룹 8개, 싼 그룹 0개. 누락 과제 없음. oracle 행은 강한 모델 행과 같다.
- 등록 보기 차이: 오류 실행을 미해결로 세어 deepseek e2e_h06 3/3→2/3, qwen 싼 구성 e2e_h05 2/3→1/3, e2e_h06 1/3→0/3 (최선 단일 6→4). 비용은 보고서 비용이다.

### 한계

- 상한이며 라우터가 아니다.
- 같은 시도에 대한 사후 지식을 쓴다 (선택 편향, 낙관적).
- 과제 8개, 칸당 n=3.
- 어떤 라우터도 여기에 도달한다고 주장하지 않는다.
- 라우터·기본값 채택 없음 (P1: 새 과제 유료 검증 전 채택 없음).

### 원문

- 결과 파일: `tests/fixtures/m19/m19d-oracle.md`
- 재현 명령: `uv run python tests/m19_oracle.py`

## M19e 1단계 사전 등록 (2026-10-22T13:11:22Z)
이 절은 신호, 판정자 점수, 라벨, 지표를 하나도 계산하기 전에 커밋한다 (R42, ADR-36). 변경은 새 날짜의 수정 절로만 한다. 비용 $0 (OpenRouter 호출 없음).

공개: Scout가 셀 이름을 찾으면서 셀별 k/n을 화면에 출력했고, M15/M16d/M17/M19 결과는 이미 이 문서에 있다. 셀 선택 규칙은 횟수가 아니라 "plain cheap arm의 가장 최근 하네스 셀"이다.

### 데이터셋 (19 과제)
| 과제 | 세트 | cheap 셀 (구성원) | strong 셀 | 하네스 |
|---|---|---|---|---|
| query_client_timeout, query_total_backoff, query_env_override, multi_edit_delay_cap, multi_edit_rename_cents, multi_edit_region | multi | M15 `A cheap` (`.cora/bench/m15/merged/report.json`, google/gemini-2.5-flash-lite, n=3) | M15 `C strong` (같은 파일, deepseek/deepseek-v3.2, n=3) | M15, 2026-10-15/16 |
| e2e_todo_cli, e2e_text_stats, e2e_rest_notes | e2e | M16d A'' = `.cora/bench/m16d/A-e2e` + `A2-e2e` (flash-lite, n=6) | M15 `C strong` (n=3) | cheap M16d 2026-10-17; strong M15 |
| e2e_md_to_html | e2e | M17 OFF = `.cora/bench/m17/OFF-md` (flash-lite, n=3) | M15 `C strong` (n=3) | cheap M17 2026-10-17; strong M15 |
| e2e_refactor_inventory | e2e | M15b `retest-cheap` (`.cora/bench/m15b/retest-cheap`, flash-lite, n=2) | M15 `C strong` (n=3) | cheap M15b 2026-10-16; strong M15 |
| e2e_h01..e2e_h06, e2e_hx1, e2e_hx2 | hard | M19 arm `a`, 구성원 m1 google/gemini-2.5-flash-lite, m2 qwen/qwen3-coder-30b-a3b-instruct, m3 mistralai/mistral-small-3.2-24b-instruct (n=3 each) | M19 arm `e` deepseek/deepseek-v3.2 (n=3) | M19 2026-10-18..21 |
- M19 행: `tests/m19_oracle.py`의 registered view와 같다 (`view_rows(read_args_file("tests/fixtures/m19/panel-args.txt"), None, "unsolved", "report")`; c_s, d1 제외; rerun 대체 없음).
- 모든 report는 `cora_version 0.1.0`이며 하네스 커밋 해시는 기록돼 있지 않다 (날짜만).
- 셀 이름 매핑: blueprint의 "M16d A''"는 디스크의 `A-e2e`(seed 0)와 `A2-e2e`(seed 3) 두 호출이다 (이 문서 M16d 절). "M17 OFF"는 md_to_html에만 있다.
- 해결 = 결과 행의 `full_pass is True` (M19는 `Row.solved`). 비용 = 행의 `cost_usd` (M19는 report 기준).
- 제외: cheap 셀 또는 strong 셀이 없는 과제는 없음. 실행 시 매칭되지 않는 run은 이름을 밝히고 제외하며 대체하지 않는다.

### 라벨
- `cheap_ok(t)` = cheap 구성원별 k/n의 최댓값 ≥ 2/3 (등록 셀 안에서, 분수 비교). 양성(positive) = `not cheap_ok` (strong 필요).
- S4 run 라벨: cheap run이 미해결이면 양성.

### 신호 (모두 "높을수록 strong 필요")
- S1a: 격리 Claude Code 판정자, judge id `claude-sonnet-5-5` (실행 시 `modelUsage` 키를 그대로 기록), 프롬프트 `tests/fixtures/m19e/judge-prompt-s1a.txt` (hash `ecaa4d1f1247bcd8`), 점수 = c1..c8 합 (0-24). 작업 폴더는 저장소 밖의 새 임시 폴더, 입력은 판정 입력 텍스트뿐 (정답, grader, 결과, calibration, 이전 결과 없음), 도구는 Read/Glob/Grep만, MCP/웹 끔, `ANTHROPIC_API_KEY`/`OPENROUTER_API_KEY`/`GEMINI_API_KEY` 제거. 구독, $0.
- S1b: 무료 Gemini `gemini-3.5-flash-lite` (cora.toml의 첫 무료 flash-lite 항목), `llm` Decider, temperature 0, `score(question, 0, 24, text=판정 입력)`, question = `tests/fixtures/m19e/judge-prompt-s1b.txt` (hash `9f6a7cd92846bee7`). 입력 상한 8000자 (러너 안에서만 패치). 503/429/기타 fallback은 1회 재시도 후 `blocked`, 대체하지 않음.
- 루브릭 전문 (두 판정자 공통):
```
c1 files_to_touch: how many files must be created or changed (0 = one file, 1 = two, 2 = three or four, 3 = five or more).
c2 spec_ambiguity: how much the spec leaves open or could be read two ways.
c3 hidden_requirement_risk: how likely an unstated detail (edge case, exact output format, error handling) decides success.
c4 repo_exploration: how much existing code must be read and understood before editing (0 = none).
c5 algorithmic_difficulty: how hard the core logic is (0 = plumbing, 3 = non-trivial algorithm or state handling).
c6 verification_gap: how hard it is to check the work locally (0 = runnable tests or exact examples are given, 3 = nothing to check against).
c7 cross_module_consistency: how much separate parts must agree on names, signatures or data formats.
c8 instruction_volume: how many distinct requirements must all be met (0 = one or two, 3 = more than ten).
total = c1 + c2 + c3 + c4 + c5 + c6 + c7 + c8 (0-24). Higher = a stronger model is more likely needed.
```
- 판정 입력 = `read_inputs(prompt, workspace)`의 `RouteInputs`만으로 만든 텍스트 (`tests/m19e_data.py render_judge_input`): 과제 프롬프트, 프롬프트가 지명한 spec 파일(6000자 상한), 저장소 probe 요약. 워크스페이스는 `tests/m15_baseline.py prepare`와 같은 방식(숨은 grader 없음).
- S2: `scope_files + named_missing` (`RepoProbe`, 모델 호출 없음).
- S3: `knn_score`, k=3, 특성 (`judge`=S1a 합, `scope_files`, `named_missing`), z-score는 자기 과제를 뺀 나머지로 맞춤, leave-one-task-out. 학습 가중치 없음.
- S4: cheap run마다 첫 2 모델 턴(첫 시도의 `purpose == "react"` `llm_call` 1, 2번째와 그 뒤 3번째 `llm_call` 전까지의 이벤트)의 실패 표지 수 = `parse_error` 이벤트 수 + `ok`가 거짓인 `tool_call` 수 (edit_file old-not-found, 없는 경로 read 포함; 하위 수도 기록). run 단위. 혼자 통과하면 사전 라우터가 아니라 escalation 트리거 후보로 보고한다.
- 세트 식별 기준선: 과제 t의 점수 = 같은 세트의 다른 과제 중 `not cheap_ok` 비율 (세트에 다른 과제가 없으면 0.5).

### 지표 (`tests/m19e_signals.py`, stdlib + `cora.core.prerouter`, 오프라인, 키 없음)
- AUROC (Mann-Whitney, 동점 0.5): 과제 단위 S1a, S1b, S2, S3, 기준선; run 단위 S4. 한 클래스뿐이면 n/a.
- 단측 순열 p = P(AUROC_perm ≥ AUROC_obs): 조합 수 ≤ 10^5이면 완전 열거, 아니면 10^5회 Monte-Carlo, seed 20261022, p = (1 + 횟수) / (1 + 10^5).
- M19 hard 세트 안의 AUROC (한 클래스면 n/a).
- 모의 정책표: always-best-cheap (multi/e2e는 flash-lite, hard는 hard 세트 합계 k가 가장 큰 구성원, 동률이면 비용 낮은 쪽), always-strong, 신호별 routed, oracle (과제마다 cheap/strong 중 해결률 높은 셀, 동률이면 평균 비용 낮은 셀). 지표: 해결률 K/N (선택 셀의 run 합), Wilson 95%, solved-per-dollar = K / 선택 셀 run 비용 합.
- routed 임계값 (leave-one-task-out): 과제 t마다 나머지 과제로 후보 θ ∈ {나머지 과제 점수의 서로 다른 값} ∪ {+inf} 중 "해결률 ≥ (나머지 과제의 always-strong 해결률 − 0.05)"를 만족하고 solved-per-dollar가 가장 큰 θ를 고른다 (동률이면 큰 θ). 결정: 점수 ≥ θ → strong (동점은 strong). S4 정책: cheap run의 표지 ≥ θ이면 첫 2턴 비용 + 그 과제 strong 셀 평균 비용, 해결 = strong 셀 해결률(기댓값); 아니면 그 run 그대로. Wilson은 반올림한 K로 계산하고 "approx"로 표시.
- 차단(`blocked`)된 판정 항목은 그 신호에서 빼고 n과 이름을 보고한다.

### 통과 규칙 (blueprint 2.31 원문)
> **Pass rule (pre-registered, committed before any signal is computed).** PASS iff at least one signal meets all of: (i) AUROC ≥ 0.75; (ii) permutation p ≤ 0.025 (0.10 Bonferroni over 4 signals); (iii) S1–S3: AUROC > the set-identity baseline's; (iv) its simulated policy has solved-per-dollar > always-strong's AND solved ratio ≥ always-strong's − 0.05. FAIL otherwise → M19e closes with no paid spend (A21e); M19e2/M19e3 are dropped; the pure module stays unwired; the result (all four signals, all metrics) is recorded. S1b alone passing is enough; S1a alone passing means a product router would need a paid strong-judge call — then M19e3 measures with that judge model and the call's cost is counted in the routed arm.
- 적용: S1a, S1b, S2, S3에 (i)-(iv), S4에 (i), (ii), (iv). S1a와 S1b는 같은 신호군 S1로 Bonferroni 4개에 속한다.

### 주의 (caveats)
- 셀마다 하네스 버전이 다르다 (multi와 초기 e2e의 strong 셀은 이후 수정 전 M15).
- e2e 5과제는 M15b-M17 튜닝 대상이었다.
- 약 19 과제: FAIL 가능성이 높고, 그것도 받아들인 결과다 (ADR-36).
- Bonferroni 4 신호 (p ≤ 0.025).
- S4 run 단위 순열은 과제 내 군집을 무시한다. cheap 셀의 n이 2, 3, 6으로 다르다.

## M19e 1단계 결과 (2026-10-22T13:28:43Z)

- 전체 신호 출력: `tests/fixtures/m19e/signals.md` (사전 등록: 위 `## M19e 1단계 사전 등록` 절, 커밋 P가 먼저다).
- 비용: $0, OpenRouter 호출 0 (S1b는 무료 Gemini, S1a는 구독 Claude Code CLI). 차단(blocked) 항목: 없음.
- 데이터: 과제 19개, 양성(strong 필요) 11개, 비양성 8개. 기준선(세트 동일성) AUROC 0.727 — 같은 신호를 쓰는 비교 기준이다.
- 표본 한계: 과제 19개뿐이라 신호마다 구간이 넓다 (S1b Wilson [0.518, 0.736], always-strong [0.484, 0.729]은 크게 겹친다). hard 세트 AUROC는 S1b 0.714, S1a 0.786 (과제 8개). S1b 통과는 단일 판정자(`gemini-3.5-flash-lite`, temperature 0, 과제당 1회 점수)와 셀마다 다른 하네스 버전에서 나온 결과다. 반올림 Wilson 구간은 "approx"로 표시했다.

### 지표

| signal | n | n_pos | AUROC | p | method | AUROC hard-only | > baseline | policy ratio | Wilson | spd | (i) | (ii) | (iii) | (iv) | pass |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S1a | 19 | 11 | 0.727 | 0.053 | exact | 0.786 | False | 0.412 | [0.303, 0.530] | 30.56 | False | False | False | False | False |
| S1b | 19 | 11 | 0.830 | 0.006 | exact | 0.714 | True | 0.634 | [0.518, 0.736] | 46.83 | True | True | True | True | True |
| S2 | 19 | 11 | 0.864 | 0.003 | exact | 0.500 | True | 0.548 | [0.434, 0.657] | 52.31 | True | True | True | False | False |
| S3 | 19 | 11 | 0.614 | 0.222 | exact | 0.214 | False | 0.469 | [0.352, 0.589] | 28.53 | False | False | False | False | False |
| S4 | 121 | 80 | 0.754 | 0.000 | monte_carlo | 0.701 | n/a | 0.554 | [0.465, 0.639] (approx) | 25.68 | True | True | n/a | False | False |
| baseline | 19 | 11 | 0.727 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | | | | | |

### 정책 표

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

### 판정

PASS — M19e2 proceeds.

결과: PASS → M19e2 진행. S1b 단독 통과. S1a, S2, S3, S4는 실패 (S1a: (i)-(iv) 모두 불통과; S2: (iv) 불통과; S3: (i)-(iii) 불통과; S4: (iv) 불통과).

cost: $0, OpenRouter 호출 0

## M19e2 (2026-10-22T16:35:25Z) — 새 혼합 과제 세트 보정 (calibration, 비-G1, n=1 선별 전용)

- (1) 직접 작성한 과제 14개 `e2e_n01`…`e2e_n14`(디렉터리 `201_n01_*`…`214_n14_*`)입니다. 티어(easy/medium/hard)는 `tests/fixtures/m19e2/manifest.toml`에만 기록되며 에이전트 프롬프트와 채점에는 쓰이지 않습니다. 외부 자료는 쓰지 않았습니다. 과제 설계와 REQUIREMENTS.md는 M19e1 루브릭, 심사 프롬프트, signals.md, 신호 출력을 보지 않고 작성했습니다. 보정은 gemini-3.5-flash-lite, react 프로토콜, 과제당 n=1로 했습니다.
- (2) 보정 표 (`cal-<id>/report.json`의 `results[0]`, 과제별 최종 실행):

| 과제 | run id | solved | score | iterations | end_reason | input_tokens | output_tokens | 환산 비용 $ | cost_usd 설정 | 상태 |
|---|---|---|---|---|---|---|---|---|---|---|
| e2e_n01 | -\|gemini-3.5-flash-lite\|react\|e2e_n01\|r0 | yes | 1.0 | 12 | error | 61484 | 7281 | 0.0091 | 0.05 | 해결 후 late 503, iterations 하한 |
| e2e_n02 | -\|gemini-3.5-flash-lite\|react\|e2e_n02\|r0 | yes | 1.0 | 13 | error | 29607 | 2979 | 0.0042 | 0.05 | 해결 후 late 503, iterations 하한 |
| e2e_n03 | -\|gemini-3.5-flash-lite\|react\|e2e_n03\|r0 | yes | 1.0 | 30 | final_answer | 232196 | 14350 | 0.0290 | 0.09 | final |
| e2e_n04 | -\|gemini-3.5-flash-lite\|react\|e2e_n04\|r0 | yes | 1.0 | 16 | final_answer | 77535 | 6444 | 0.0103 | 0.05 | final |
| e2e_n05 | -\|gemini-3.5-flash-lite\|react\|e2e_n05\|r0 | yes | 1.0 | 22 | final_answer | 113025 | 7098 | 0.0141 | 0.05 | final |
| e2e_n06 | -\|gemini-3.5-flash-lite\|react\|e2e_n06\|r0 | yes | 1.0 | 21 | error | 135062 | 10951 | 0.0179 | 0.06 | 해결 후 late 503, iterations 하한 |
| e2e_n07 | -\|gemini-3.5-flash-lite\|react\|e2e_n07\|r0 | yes | 1.0 | 20 | max_iterations | 60305 | 1165 | 0.0065 | 0.05 | final |
| e2e_n08 | -\|gemini-3.5-flash-lite\|react\|e2e_n08\|r0 | no | 0.0 | 7 | final_answer | 22793 | 4784 | 0.0042 | 0.05 | unsolved (retry 보고서, 모델 실패) |
| e2e_n09 | -\|gemini-3.5-flash-lite\|react\|e2e_n09\|r0 | yes | 1.0 | 20 | max_iterations | 66617 | 3577 | 0.0081 | 0.05 | final |
| e2e_n10 | -\|gemini-3.5-flash-lite\|react\|e2e_n10\|r0 | yes | 1.0 | 30 | max_iterations | 243280 | 7190 | 0.0272 | 0.09 | final |
| e2e_n11 | -\|gemini-3.5-flash-lite\|react\|e2e_n11\|r0 | yes | 1.0 | 18 | error | 117645 | 8636 | 0.0152 | 0.05 | 해결 후 late 503, iterations 하한 |
| e2e_n12 | -\|gemini-3.5-flash-lite\|react\|e2e_n12\|r0 | yes | 1.0 | 20 | max_iterations | 171194 | 12425 | 0.0221 | 0.07 | final |
| e2e_n13 | -\|gemini-3.5-flash-lite\|react\|e2e_n13\|r0 | yes | 1.0 | 23 | final_answer | 208599 | 10303 | 0.0250 | 0.08 | final (첫 시도 503, 재시도 완료) |
| e2e_n14 | -\|gemini-3.5-flash-lite\|react\|e2e_n14\|r0 | yes | 1.0 | 25 | max_iterations | 212925 | 14038 | 0.0269 | 0.09 | final |

  - e2e_n01, n02, n06, n11은 해결했지만 end_reason=error입니다(해결 상태 이후 늦은 503). 따라서 이 네 과제의 iterations는 하한입니다.
  - e2e_n08은 미해결입니다. 진단(`.ensemble/milestones/M19e2/diagnosis.md`)에 따르면 4096 토큰 응답이 잘렸고 파일이 작성되지 않았습니다. 과제나 채점기의 결함이 아닌 모델 실패로 판정했으며, 저비용 미해결 증거로 유지합니다.
- (3) 교체: 없음. 보정 중 교체된 과제는 없습니다.
  blocked: e2e_n08과 e2e_n13은 첫 시도에서 Gemini 503을 받아 각각 한 번 재시도했고, 두 재시도 모두 완료되었습니다(e2e_n08의 재시도 결과는 실패 보고서이며 위 표에 사용했습니다).
- (4) 혼합 점검: 미해결 또는 iterations>5 = 14개, 해결 = 13개 → 충족
- (5) R14: `cost_usd = max(0.05, ceil_to_cent(3 × (in×0.10 + out×0.40) / 1e6))`. 표의 환산 비용은 `(in×0.10 + out×0.40) / 1e6`입니다.
- (6) 지출: $0 (무료 Gemini, OpenRouter 호출 0)
- (7) 동결: 7096ee1239a6ee92e8a5ec8726434079757addc8. 이 커밋 이후 `src/cora/bench/e2e_tasks/2*`와 `tests/fixtures/m19e2/`의 과제 파일은 M19e3 사전 등록 전까지 바꾸지 않습니다. 변경이 필요하면 과제명을 적은 날짜 있는 수정 기록이 있어야 합니다.

## M20 사전 등록 (2026-10-23T11:40:43Z)
이 절은 M20 live 세그먼트(P1 계획 품질, P2–P4 실행)가 시작되기 전에 커밋한다. 변경은 새 날짜의 수정 절로만 한다. 이 절 커밋 시점에는 OpenRouter 호출이 없다 (비용 $0). G2 결과는 report-only이며, 완료율에 대한 사전 설정 임계값은 없고 M20은 기본값을 바꾸지 않는다.

1. **의존성.** M19e closed: M19e1 PASS, M19e2 PASS, M19e3 deferred by user 2026-10-23 (M19e3 보류 기록이 여기에 함께 남는다). 사전 라우터(pre-router)와 cascade는 M20에서 사용하지 않는다.
2. **구성 (R1).** 모델은 `deepseek/deepseek-v3.2` 단일. 구성 파일은 `uv run python tests/m20_trial.py config deepseek/deepseek-v3.2 $TMPDIR/cora-m20/cora-m20-deepseek.toml`로 생성하며, 내용은 `cora.toml`에 `[router]` 바로 다음 줄로 `pin = "deepseek/deepseek-v3.2"` 한 줄을 넣은 것이다. `cora.toml`의 sha256 = `7704ace8db75918f63e2f4df8e6b7d009cabf3d73cc98e0165f6c677abcd883a` (`shasum -a 256 cora.toml`), `cmp cora.toml src/cora/data/cora.toml`은 동일하다. 저장소 안의 두 toml 사본은 바꾸지 않는다. 그 밖의 기본값은 M19/M19e에서 남긴 그대로다. 리허설 구성은 같은 방식으로 `gemini-3.5-flash-lite`를 고정한다.
3. **플래그.** `--headless --approval policy --json --max-cost min(0.30, remaining)`, `--max-iterations`/`--max-wall-s`는 과제 `[limits]`에서 가져온다 (h01 30/2400, h03 30/2400, n08 25/1800). 계획 품질 호출은 `--max-cost 0.05`와 `CORA_RECORD_MODE=record`를 쓴다. 주의(caveat): planner 비용은 프로젝트 예산 안에 포함된다.
4. **과제 (R6).** `e2e_h01`, `e2e_h03` (hard 세트; M19에서 Claude Code 3/3씩, deepseek arm e 2/3과 1/3, cheap 0), `e2e_n08` (M19e2; 무료 flash-lite 미해결). 과제 교체는 첫 유료 호출 전에만 허용되며, 이유를 적어 이 절을 수정해야 한다. 계획 품질 목표는 `e2e_h01, e2e_h02, e2e_h03, e2e_h05, e2e_h06`이며 목표 문장은 `tests/m20_trial.py goal <task>`가 출력하는 텍스트다 (h04 제외, A1과 같다).
5. **팔 (arm).** 팔은 하나: deepseek 고정 상태의 CORA `project run --goal`, 과제당 n=3 (9 run). 계획 품질: 무료 Gemini `gemini-3.5-flash-lite` (non-G1, `cost_source = free_tier`, 503이면 `blocked`로 기록하고 1회 재시도) 다음 deepseek (비용 계산 포함).
6. **정의.** Completed, intervention, leak, error run은 이 계획의 Fixed decisions 원문을 그대로 따른다.
   - Completed = 과제의 숨은 grader `full_pass`가 최종 워크스페이스에서 True인 것. grader는 실행이 끝난 뒤에만 주입한다.
   - Intervention = 사람의 프롬프트 응답, 수동 `project resume`/재시작, 채점 전 수동 워크스페이스 편집, 같은 셀 슬롯의 오케스트레이터 재실행. 헤드리스 정책 자동 거부는 `policy_deny`로 따로 기록하며 intervention이 아니다.
   - Leak = (a) `leakcheck(pre_grade=True)` 결과가 비어 있지 않음, (b) `events.jsonl`의 어떤 줄이든 `HOME_PROTECTED` 절대 경로 또는 저장소 패키지 데이터 경로를 포함, (c) `keygrep`의 키 문자열 일치.
   - Error run = `stop_reason == "error"` 또는 `exit_code == 1`. 단, 계획기 응답 무효(errors에 `"planner reply invalid"`)는 완료되지 않은 것으로 세며 `plan_quality = "failed"`로 기록한다.
7. **보고 전용.** G2 결과는 report-only다. 완료율 임계값을 미리 정하지 않으며, M20은 기본값을 바꾸지 않는다.
8. **지출과 상한 (R12).** 배정 ≤ $2.00. M20 이전 유료 누적은 최신 누적 장부 기록에서 가져오며 (≈ $6.42), M20 이후 유료 누적은 ≤ $8.42이고 $10 미만이어야 한다. 세그먼트별 예상 비용은 Fixed decisions의 공식과 값을 따른다 (P1 계획 품질 ≤ $0.05, P2 h01 $0.20, P3 h03 $0.30, P4 n08 $0.19). 세그먼트는 P1, P2, P3, P4 순서로 실행하며 각각 별도 승인을 받는다.
9. **절단 규칙 (cut rule).** 셀은 남은 배정 ≥ 1.5 × 그 셀의 예상 비용일 때만 시작하며, 아니면 "not measured (budget)"로 적는다. 각 run의 `--max-cost` = min(0.30, remaining). n<3인 셀은 주장을 하지 않는다. error run이 하나라도 나오면 시리즈를 멈추고, 계속하기 전에 원인을 진단한다. 402를 받으면 멈춘다.
10. **기준선 (R10).** Claude Code 기준선은 `.docs/baselines/claude-code-m19.toml`에서 가져온다: h01 solved 1.0, $0.0795/run; h03 solved 1.0, $0.0872/run (toml 추정 가격, caveat). n08은 기준선이 없으며 (no baseline (not measured)) 새 기준선 run을 만들지 않는다.
11. **G1 두 줄 입력 (R2).** 가격: deepseek 입력 0.28 / 출력 0.42, m1 `google/gemini-2.5-flash-lite` 0.10 / 0.40, 모두 2026-10-18 OpenRouter `/api/v1/models` 기준이며 `cora.toml` 주석에 따른다. 가격 규칙 해석: 2.8× / 1.05× ≤ 3× → cheap. 헌장 개정 해석: mid/strong. 수치는 M19 arm e (19/24, $0.7454, solved-per-dollar 25.5)와 Claude Code (21/24, 11.1)에서 가져온다: 비율 0.905, spd 비율 2.30.
12. **후속 (A6).** 같은 모델, 다른 하네스 대조군은 이 범위 밖이다. 하네스는 사용자가 아직 지정하지 않았다.

## M20 사전 등록 수정 (2026-10-25T11:38:12Z)

이 절은 P2 첫 시도(`e2e_h01` r0 `policy_blocked`, r1 `budget_exceeded`, r2 `error` RequestDeadlineExceeded)의 결과를 본 뒤에 만든 편차(deviation)다. 원인 진단은 `.ensemble/milestones/M20/diagnosis.md` (F1-F3)이며, 사용자가 2026-10-25에 승인했다. 원래 사전 등록 절은 바꾸지 않으며, P1과 P2 첫 시도 행은 삭제하거나 덮어쓰지 않는다. 이 절은 다음 유료 호출(RR-M20-01) 전에 커밋한다.

1. **D1 마감 시간 구성 (F3).** 남은 모든 호출은 `uv run python tests/m20_trial.py config <model> <out> --variant deadline`로 만든 구성을 쓴다. 내용은 M19 수정 6-7의 `tests/fixtures/m19/arms/deadline.toml` (sha256 `f32ed786367b204057f8001d3d36a0a5a7f962f28aa3ba9ea822d83a8c4d17c4`; `timeout_s = 300`, `request_deadline_s = 300`, `call_timeout_s = 960`, 규칙 call_timeout_s ≥ 3×D+3)에 같은 `pin` 한 줄을 넣은 것이다. `cora.toml`과 `src/cora/data/cora.toml`은 바뀌지 않으며 `cmp`는 동일하다. 근거: P2 r2의 `request_deadline_s=90` 오류는 M19에서 deepseek를 검열한 것과 같은 종류다.

2. **D2 재실행 RR-M20-01.** `e2e_h01-r2`를 정확히 한 번 재실행한다. 명령은 P2와 같고 (30/2400, 재실행 시점의 src는 사전 등록 커밋과 동일 = pre-fix planner) 구성만 D1이다. 원래 r2 행은 남기고 superseded로 표시하며 대체(replace)하지 않는다. 같은 셀 슬롯의 재실행이므로 정의대로 interventions = 1로 기록한다. 다시 오류가 나면 멈추고 더 재실행하지 않는다.

3. **D3 R11 수정 1회차 (F1).** `src/cora/core/planner.py`의 `PLANNER_SYSTEM`에 한 문장을 추가한다: `"check" is a single runnable shell command that exits 0 when the milestone is done; omit it if no such command exists, and use "conditions" for deterministic checks.` 회귀 테스트는 `tests/test_planner.py::test_planner_system_check_is_shell_command`. M20에서 유일한 src 변경이며 설정 기본값은 바꾸지 않는다 (spec R11 수정 라운드, 사용자 승인 2026-10-25).

4. **D4 계획 품질 재측정.** 수정 후 계획 품질을 다시 잰다: 무료 리허설 `gemini-rehearsal-fix1`, 유료 `deepseek-fix1` (≤ $0.05, 예상 ≈ $0.005). M20에서 세는 계획 품질 표는 `deepseek-fix1`이다. 수정 전 행(`gemini-rehearsal`, `deepseek`)은 pre-fix로 남긴다. 새 차원 `check_runnable` (milestone `check`가 gate에 막히지 않고 실행 가능한 수 / check 수)을 추가하며, pre-fix 계획의 값은 저장된 계획에서 오프라인(`checkq`, $0)으로 `tests/fixtures/m20/checks.jsonl`에 기록한다.

5. **D5 프로젝트 크기 상한 (F2, option b).** `project run`의 상한은 프로젝트 전체 누적이므로 본 시리즈는 `--max-iterations` = 8 (`[project] max_milestones`) × 과제 `max_iterations` (h01 240, h03 240, n08 200), `--max-wall-s` = 반복 상한 × 40 s (P2 r1 실측 25.9 s/iteration의 1.5배; h01 9600, h03 9600, n08 8000, 모두 8 × 과제 `wall_s` 이하)를 쓴다. `--max-cost` = min(0.30, remaining)은 그대로다.

6. **D6 시리즈 구분.** 본 G2 시리즈는 label `deepseek-v2` (D1 + D3 + D5, h01/h03/n08 각 n=3, 새 셀 슬롯)이다. P2 첫 시도(label `deepseek`, 30/2400: r0, r1, superseded r2, RR-M20-01)는 "30/2400 attempt"로 따로 보고하며 본 시리즈와 합치지 않는다. 세 변경이 함께 들어가므로 두 시리즈의 차이를 한 원인에 돌리지 않는다.

7. **D7 예상 비용과 절단 규칙.** RR-M20-01 예상 $0.0655; `deepseek-v2` run당 예상 $0.15 (P2 r1 $0.00113/iteration × 약 130 iteration, 올림), 셀 $0.45, 셀 시작 조건 남은 배정 ≥ $0.675. 배정 $2.00, 정의(completed, intervention, leak, error run), error run 즉시 중단, 402 중단, n<3 무주장 규칙은 바뀌지 않는다. 누적 지출은 `/credits` 차이로 잰다 (P2 r2 outcome은 $0.0으로 과소 보고).

## M20 사전 등록 수정 2 (2026-10-25T12:35:20Z)

이 절은 P1b(`deepseek-fix1`) 결과(check 5/28 실행 가능, 23개가 정책에 막힘; 대부분 `confine:one-liner`, 일부 `confine:brace`)를 본 뒤 만든 편차다. 사용자가 2026-10-25에 승인했다. 앞선 두 절과 기존 행은 바꾸지 않는다. 이 절은 P1c 전에 커밋한다.

- **E1 R11 수정 2회차.** `PLANNER_SYSTEM`에 언어 중립 문장 하나를 더한다 (언어/인터프리터 이름 없음): `"check" runs under the same restricted shell policy as agent commands. Inline code passed to an interpreter by a flag (such as -c or -e) is denied, and so are command substitution, variable expansion, brace expansion (a comma or ".." inside curly braces), subshells, heredocs, newlines and background jobs. Put the assertions in a test or script file inside the repository and make "check" one command that runs that file.` 회귀 테스트 `tests/test_planner.py::test_planner_system_check_policy_sentence`, `test_planner_system_language_neutral`. src 변경은 여전히 `src/cora/core/planner.py`뿐이다.
- **E2 계획 품질 재측정.** 무료 리허설 `gemini-rehearsal-fix2`, 유료 `deepseek-fix2` (deadline 구성, ≤ $0.05, 예상 ≈ $0.003). 본 시리즈가 쓰는 planner가 최신이므로 세는 계획 품질 표는 `deepseek-fix2`다. `deepseek-fix1`과 pre-fix 행은 이력으로 남기고 세지 않는다.
- **E3 중단 규칙.** P1c의 5개 계획 전체에서 `checks_blocked` 합 > `checks_total` 합의 절반이면 본 시리즈(`deepseek-v2`)를 시작하지 않고 사용자에게 보고한다. 그 다음 선택지(프롬프트에 정책 동적 주입, 계획 검증 + 수리 루프)는 승인 없이 하지 않는다. 비교 기준: pre-fix 0/33, fix1 5/28.
- **E4.** `deepseek-v2`는 R11 1·2회차 planner로 돈다. 배정 $2.00, 절단 규칙, 정의는 바뀌지 않는다.
