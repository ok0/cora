# M20d 장부 (ledger)

## S1 e2e_n08 (Group C 1–4단계, 2026-10-28)

- 파트: pin = <HOME>/workspace/ok0/cora-pin-d1 (PIN 0ae6359), CFG_SHA edc1f4e337e9c674c134545d48206b2daf68fd5e78c0ebaa0f088db0535b29ac.
- 1. 리허설 (replay, OPENROUTER/GEMINI 키 제거, 빈 records): PASS. outcome: stop_reason error, errors에 "replay miss" (모델 deepseek/deepseek-v3.2 명시), records 0개, 네트워크 호출 0. runrow exit 3 (예상), leaks []. 행은 $B/rehearsal.jsonl에 추가. 한계: 배관만 확인, 에이전트 루프와 정책 경로는 r0에서 처음 실측.
- 2. bench plan: runs 6 (react 3 + native 3), max_iterations 25, subtotal 0.30. 주의: bench 추정기는 project run (200 iteration, cap 0.30 × 3)과 모델이 다르다. 등록 기대치는 절단 규칙 $0.0067 (하한), 현실 상한 $0.90 (cap 3회).
- 3. 계정 판독 U0 (2026-10-28T01:48:00Z, HTTP 200):
  - /auth/key: usage 0.748457803, limit 4, limit_remaining 3.251542197, expires_at 2026-10-29T02:17:03.294Z, is_free_tier false.
  - /credits: total_credits 10, total_usage 7.15651232 (HTTP 200).
  - U0 = 0.748457803 (key usage, 기준). 잔여 배정 = 1.20 − (usage − U0) = 1.20.
- 4. 검사:
  - 절단 규칙: 잔여 1.20 ≥ 0.0101 (n08 1.5×) → 통과.
  - 가드: 잔여 1.20 ≥ 0.32 → 통과.
  - 시간 규칙: E = 2026-10-29T02:17Z, now 2026-10-28T01:48Z, E − now ≈ 88140 s ≥ 3×8000+600 = 24600 s → 통과. 최신 세그먼트 시작 2026-10-28T19:27Z. run 최신 시작 23:53Z (run 시작 기준 8600 s).
  - 승인 (5단계 이전): 요청 전. 승인 시각: (아직 없음 — 사용자 승인 대기).
- 5단계 (run r0)는 실행하지 않음. 유료 호출 0.

## 지출 (M20d 누적)

- S1 시작 전: usage 0.748457803 (U0), 배정 사용 0.
- 계정 전체 total_usage 7.15651232 (M20d 이전 누적 ≈ 7.167 계획치와 0.0105 차이; 최대 종료 시 8.3565 ≤ 8.37 상한 내).
approval (user, S1 e2e_n08 n=3 cap 0.30 alloc 1.20) recorded: 2026-10-28T01:56:20Z

## S1 e2e_n08 실행 (5–6단계, 2026-10-28)

- 승인 (사용자): 2026-10-28T01:56:20Z 이전 기록됨 (승인 시각 기록: ledger 위쪽 줄 "approval ... recorded: 2026-10-28T01:56:20Z").
- r0: stop policy_blocked, exit 5, iterations 128, cost (outcome) 0.170665, wall 1413.4 s, milestones 4/5, grader completed false (score 0.857), policy_deny 12, leaks [], unmetered 0. 시작 01:56:25Z, 끝 02:20:01Z. auth delta 0.166741.
- r1: stop policy_blocked, exit 5, iterations 171, cost (outcome) 0.257235, wall 2064.0 s, milestones 4/5, grader completed false (score 0.714), policy_deny 16, leaks [], unmetered 0. 시작 02:20:31Z, 끝 02:54:56Z. auth delta 0.256554.
- r2: stop policy_blocked, exit 5, iterations 3, cost (outcome) 0.006229, wall 217.6 s, milestones 0/6, grader completed false (score 0.286), policy_deny 5, leaks [], unmetered 0. 시작 03:04:55Z, 끝 03:08:33Z. auth delta 0.010834 (3번째 run: 1.171753023 → 1.182586883).
- 세그먼트 델타 (auth, 권위값): 0.748457803 → 1.182586883 = 0.434129. outcome 합 = 0.434129 (일치).
- M20d 누적 (S1): 0.434129. 잔여 배정 = 1.20 − 0.434129 = 0.765871.
- 계정 누적 (/credits total_usage): 7.15651232 → 7.5906414 (지출 0.434129 일치). 전체 유료 누적 ≈ 7.5906.
- 절단 규칙 함의: h01 (S3) 시작은 S1 + S2 ≤ 0.2757 이 필요한데 S1만으로 0.434129 이므로 S3 = "not measured (budget)" (한계로 기록).
- S2 (e2e_h03): 잔여 0.765871 ≥ 0.32 (가드) 이지만, 사용자 승인 전이므로 시작하지 않음.
- 비정상: r2는 3 iteration 만에 policy_blocked (정책 deny 5). r0/r1 모두 grader 미완료, 그러나 cap 미도달.
approval (user, S2 e2e_h03 n=3 cap 0.30, remaining ~0.7659) recorded: 2026-10-28T04:01:33Z

## S2 e2e_h03 (2026-10-28)

- 승인 (사용자): 2026-10-28T04:01:33Z (ledger 위쪽 "approval (user, S2 ...) recorded" 줄과 같음). 승인 시점 잔여 배정 0.765871.
- 1. 리허설 (replay, 키 제거, 빈 records, L 240/9600): PASS. stop error, errors "replay miss" (deepseek/deepseek-v3.2), records 0개, runrow exit 3, leaks []. 행은 $B/rehearsal.jsonl에 추가.
- 2. bench plan (e2e_h03, repeats 3, cap 0.30): 6 runs (react + native), total 0.72. 등록 기대치: 절단 규칙 $0.0468 (하한), 현실 완료 시 $0.60–0.81. 추정은 등록 범위와 일치하나 추정기 구조는 project run과 다름.
- 3. 계정 판독 (2026-10-28T04:01:40Z): usage 1.182586883, limit_remaining 2.817413117, expires 2026-10-29T02:17:03.294Z, credits total_usage 7.5906414. 잔여 배정 0.765871.
- 4. 검사: 절단 규칙 0.765871 ≥ 0.0702 통과. 가드 ≥ 0.32 통과. 시간 규칙: 세그먼트 최신 시작 18:07Z, now 04:01Z 통과; run 최신 시작 23:27Z.
- 5. runs:
  - r0: 시작 04:01:47Z, 끝 04:29:20Z, wall 1653 s. stop budget_exceeded, exit 4, iterations 182, cost (outcome) 0.201721, auth delta 0.199749, grader completed TRUE (score 1.0, milestones 6/7), policy_deny 12, leaks [], unmetered 0 (grep 0 lines). 결과로 계속.
  - r1: 시작 04:29:39Z, 끝 05:29:01Z, wall 3561.5 s (약 59분; 등록 현실 상한 약 55분 초과, 시간 상한 9600 s 내). stop budget_exceeded, exit 4, iterations 187, cost (outcome) 0.284423, auth delta 0.282157, grader completed TRUE (score 1.0, milestones 5/8), policy_deny 10, leaks [], unmetered 0. 결과로 계속.
  - r2: 시작하지 않음. 가드 실패: 05:29:23Z 판독 잔여 0.283965 < 0.32. 셀은 n=2이므로 "not measured (budget)" (n<3, 주장 없음; r0, r1은 증거로만 보고).
- 6. 세그먼트 델타 (auth, 권위값): 1.182586883 → 1.664492303 = 0.481906. outcome 합 = 0.486144 (auth보다 0.004238 높음; 권위값은 auth).
- M20d 누적: 0.434129 (S1) + 0.481906 (S2) = 0.916035. 잔여 배정 = 1.20 − 0.916035 = 0.283965.
- 계정 누적 (/credits total_usage): 7.15651232 → 8.07254682 (지출 0.916035 일치). 전체 유료 누적 ≈ 8.0725.
- S3 (e2e_h01): "not measured (budget)". 절단 규칙: S1 + S2 = 0.916035 > 0.2757 이고 잔여 0.283965 < 0.9243. 한계로 기록, 호출 없음.
