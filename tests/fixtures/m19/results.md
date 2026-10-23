# M19 측정 — git 추적 기록

이 파일은 `.docs/bench-results.md` 의 `## M19 측정` 절을 그대로 옮긴 사본이다.

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
