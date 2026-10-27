# CORA 사용법

CORA는 요청의 난이도를 보고 저렴한 모델과 강한 모델 중 알맞은 쪽을 골라 쓰는 코딩 에이전트입니다. 이 문서는 CLI 명령과 옵션, 대화형 REPL, 벤치, 설정 파일을 설명합니다. 옵션 목록은 `uv run cora --help`와 각 하위 명령의 `--help` 출력을 기준으로 맞춰 두었습니다.

## 설치와 실행

- Python 3.12 이상과 uv가 필요합니다.
- 의존성을 설치합니다: `uv sync`
- OpenRouter API 키를 환경 변수로 설정합니다: `export OPENROUTER_API_KEY=...`
  - 키는 환경 변수로만 전달하세요. 키를 파일에 적거나 커밋하면 안 됩니다. `.env` 파일은 `.gitignore`에 들어 있지만, 키를 파일에 두는 습관 자체를 피하는 것이 안전합니다.
- 대화형 세션을 시작합니다: `uv run cora`
- 전체 명령과 옵션을 확인합니다: `uv run cora --help`

### 독립 설치 (uv tool)

저장소 밖 어느 디렉터리에서든 `cora`만 입력해 실행하려면 uv tool로 설치합니다. 설치하면 번들 기본 설정(`src/cora/data/cora.toml`)도 패키지에 함께 들어가므로 저장소가 없어도 동작합니다.

- 스냅샷 설치(설치 시점의 소스를 복사): `uv tool install <repo 경로>`
- 독립 설치에는 벤치(`cora/bench`: 벤치 작업, e2e 과제의 정답 구현과 채점 스크립트)가 들어가지 않습니다. `cora bench`, `cora bench plan`, `cora bench compare`, `cora decider eval`, `cora sale eval`은 소스 체크아웃(저장소)에서 `uv run cora bench ...`처럼 `uv run`으로 실행합니다. 독립 설치에서 이 명령을 실행하면 트레이스백 없이 아래 메시지 한 줄을 stderr에 출력하고 종료 코드 2로 끝납니다. 이 명령들의 `--help`는 독립 설치에서도 동작합니다.

```
error: the bench is not part of this installation; run it from a source checkout with `uv run cora bench ...`
```

- 개발용 설치(소스 수정이 즉시 반영됨): `uv tool install --editable <repo 경로>`
- 업그레이드: 패키지 인덱스의 새 버전으로 올릴 때는 `uv tool upgrade cora`를 씁니다. 로컬 저장소에서 설치한 스냅샷은 `uv tool install --reinstall <repo 경로>`로 다시 설치해 갱신합니다. editable 설치는 다시 설치할 필요가 없습니다.
- 제거: `uv tool uninstall cora`
- PATH: 처음 설치한 뒤 `uv tool update-shell`을 한 번 실행하고 새 셸을 엽니다. 실행 파일 위치가 PATH에 없으면 `cora`를 찾지 못합니다.
- 설치 확인: `which cora`로 실행 파일 위치를 보고, `cora --version`으로 버전(`cora 0.1.0`)을 봅니다.
- 어느 디렉터리에서나 `cora`를 실행하면 작업 디렉터리는 현재 디렉터리입니다. `--workdir`로 다른 경로를 지정할 수 있습니다.
- 설정 파일은 현재 디렉터리의 `cora.toml`, 없으면 `~/.config/cora/cora.toml`, 그것도 없으면 번들 기본값을 씁니다. 파일 하나를 통째로 고르며 여러 파일을 합치지 않습니다.
- API 키는 환경 변수 `OPENROUTER_API_KEY`로만 줍니다. 설치 파일이나 설정 파일에 키를 적지 마세요.
- `.cora/`(입력 기록 `history`, 세션 `sessions/`)는 실행할 때의 작업 디렉터리에 만들어집니다.

## CLI 명령과 옵션

`cora`는 하위 명령으로 `run`, `chat`, `resume`, `bench`, `decider`를 가집니다. 하위 명령 없이 `cora`만 실행하면 대화형 REPL이 열립니다. 아래 표는 명령마다 그 명령이 받는 옵션만 적었습니다. `bench`(`plan`, `compare` 포함), `decider eval`, `sale eval`은 소스 체크아웃 전용입니다. 자세한 내용은 독립 설치 (uv tool) 절을 보세요.

### `cora`

인자 없이 실행하면 대화형 REPL을 시작합니다. `-p`를 붙이면 REPL 없이 작업 하나만 실행합니다. 답은 stdout으로, 진행 상황과 요약은 stderr로 출력됩니다.

```
cora -p "README의 설치 방법을 요약해 줘"
```

| 옵션 | 단축 | 설명 |
|---|---|---|
| `--print` | `-p` | 작업 하나를 REPL 없이 실행합니다. 답은 stdout, 진행 상황과 요약은 stderr로 나갑니다. |
| `--workdir` | `-w` | 작업 디렉터리입니다. 기본값은 `.`(현재 디렉터리)입니다. |
| `--config` | `-c` | 사용할 설정 파일입니다. 생략하면 설정 파일 검색 순서를 따릅니다. |
| `--approval` | | 승인 모드입니다. `ask`, `auto`, `deny`, `policy` 중 하나를 씁니다. `policy`는 정책으로 결정하고 묻지 않습니다(자율 승인 정책 섹션 참고). |
| `--max-iterations` | | 요청 하나당 최대 반복 횟수입니다. `[agent] max_iterations`를 덮어씁니다. |
| `--max-cost` | | 세션당 USD 상한입니다. 기본값은 `[agent] max_cost_usd`입니다. |
| `--verbose` | `-v` | 이벤트를 JSON으로 stderr에 출력합니다. |
| `--delegate` | | 이번 실행에서 하위 에이전트 위임을 켭니다. 기본값은 `[delegation] enabled`입니다. |
| `--tui` | | 대화형 터미널에서 전체 화면 TUI를 씁니다(기본). |
| `--no-tui` | | 클래식 인라인 REPL을 씁니다. |
| `--version` | | 버전을 보여주고 끝냅니다. |
| `--headless` | | TUI, REPL, 프롬프트 없이 작업 하나를 무인으로 실행합니다. 작업은 `TASK`, `--task-file`, `-`(stdin, 예: `cora -p - --headless`) 중 하나로 줍니다. 승인 기본값은 `policy`입니다. |
| `--json` | | 결과를 JSON 문서 하나로 stdout에 씁니다. 그 밖의 출력은 stderr로 갑니다. |
| `--quiet` | `-q` | 진행 상황을 stderr에 출력하지 않습니다. 오류와 경고는 그대로 나옵니다. |
| `--task-file` | | 작업 내용을 파일에서 읽습니다. `TASK` 인자와 함께 줄 수 없습니다. |
| `--max-wall-s` | | 실행당 벽시계 시간 상한(초)입니다. 0이면 제한 없음입니다. 헤드리스 기본값은 `[headless] max_wall_s`입니다. |
| `--max-tool-calls` | | 실행당 도구 호출 수 상한입니다(하위 에이전트 호출 포함). 0이면 제한 없음입니다. 헤드리스 기본값은 `[headless] max_tool_calls`입니다. |
| `--resume` | | 저장된 세션 id를 헤드리스로 이어 실행합니다. `--headless`와 함께만 쓰며, 상한은 이전 실행의 누적분을 포함합니다. |
| `--help` | | 도움말을 보여주고 끝냅니다. |

### `cora run`

작업 하나(`TASK`)를 실행하고 끝냅니다. 최종 답이 없으면 종료 코드 1로 끝납니다.

`TASK`는 `--task-file`이나 `--resume`을 쓸 때 생략할 수 있습니다. `-`를 주면 작업을 stdin에서 읽습니다.

```
cora run "tests/test_calc.py 실패를 고쳐 줘"
```

| 옵션 | 단축 | 설명 |
|---|---|---|
| `--workdir` | `-w` | 작업 디렉터리입니다. 기본값은 `.`입니다. |
| `--config` | `-c` | 사용할 설정 파일입니다. |
| `--approval` | | 승인 모드입니다. `ask`, `auto`, `deny`, `policy` 중 하나를 씁니다. `policy`는 정책으로 결정하고 묻지 않습니다(자율 승인 정책 섹션 참고). |
| `--max-iterations` | | 최대 반복 횟수입니다. |
| `--max-cost` | | USD 상한입니다. 기본값은 `[agent] max_cost_usd`입니다. |
| `--verbose` | `-v` | 이벤트를 JSON으로 stderr에 출력합니다. |
| `--check` | | 검사 명령입니다. 최종 답을 받아들이기 전에 실행하며, 실패하면 모델이 고쳐서 다시 시도합니다. `[agent] auto_check = true`이고 `--check`가 없으면 작업 workspace에서 감지한 테스트 명령을 씁니다. 명시한 `--check`가 항상 이깁니다. 자세한 내용은 센서 게이트 섹션을 보세요. |
| `--delegate` | | 이번 실행에서 하위 에이전트 위임을 켭니다. 기본값은 `[delegation] enabled`입니다. |
| `--headless` | | TUI, REPL, 프롬프트 없이 작업 하나를 무인으로 실행합니다. 승인 기본값은 `policy`입니다. |
| `--json` | | 결과를 JSON 문서 하나로 stdout에 씁니다. 그 밖의 출력은 stderr로 갑니다. |
| `--quiet` | `-q` | 진행 상황을 stderr에 출력하지 않습니다. 오류와 경고는 그대로 나옵니다. |
| `--task-file` | | 작업 내용을 파일에서 읽습니다. `TASK` 인자와 함께 줄 수 없습니다. |
| `--max-wall-s` | | 실행당 벽시계 시간 상한(초)입니다. 0이면 제한 없음입니다. 헤드리스 기본값은 `[headless] max_wall_s`입니다. |
| `--max-tool-calls` | | 실행당 도구 호출 수 상한입니다(하위 에이전트 호출 포함). 0이면 제한 없음입니다. 헤드리스 기본값은 `[headless] max_tool_calls`입니다. |
| `--resume` | | 저장된 세션 id를 헤드리스로 이어 실행합니다. `--headless`와 함께만 쓰며, 상한은 이전 실행의 누적분을 포함합니다. |
| `--help` | | 도움말을 보여주고 끝냅니다. |

### `cora chat`

인자 없이 `cora`를 실행하는 것과 같습니다. 대화형 REPL을 엽니다.

| 옵션 | 단축 | 설명 |
|---|---|---|
| `--workdir` | `-w` | 작업 디렉터리입니다. 기본값은 `.`입니다. |
| `--config` | `-c` | 사용할 설정 파일입니다. |
| `--approval` | | 승인 모드입니다. `ask`, `auto`, `deny`, `policy` 중 하나를 씁니다. `policy`는 정책으로 결정하고 묻지 않습니다(자율 승인 정책 섹션 참고). |
| `--max-iterations` | | 요청 하나당 최대 반복 횟수입니다. |
| `--max-cost` | | 세션당 USD 상한입니다. 기본값은 `[agent] max_cost_usd`입니다. |
| `--verbose` | `-v` | 이벤트를 JSON으로 stderr에 출력합니다. |
| `--delegate` | | 이번 실행에서 하위 에이전트 위임을 켭니다. 기본값은 `[delegation] enabled`입니다. |
| `--tui` | | 대화형 터미널에서 전체 화면 TUI를 씁니다(기본). |
| `--no-tui` | | 클래식 인라인 REPL을 씁니다. |
| `--help` | | 도움말을 보여주고 끝냅니다. |

### `cora resume`

저장된 세션(`SESSION_ID`)을 다시 엽니다. 세션 기록은 `.cora/sessions/` 아래에 저장되어 있습니다.

- 대화형 터미널(표준 입력과 표준 출력이 모두 터미널이고 `TERM`이 `dumb`가 아님)에서는 `cora`를 실행하고 `/resume <id>`를 입력한 것과 같습니다. 화면 모드는 `cora chat`과 같은 규칙(`--tui`/`--no-tui` > `CORA_TUI` > `[ui] tui`)으로 고릅니다. 대화 영역에 `Resumed session <id>` 줄과 이전 요청, 이전 답을 보여 준 뒤 입력을 기다리며, 다음 요청은 저장된 컨텍스트를 이어서 씁니다. 끝나면 종료 요약에 같은 세션 id와 `cora resume <id>` 안내가 나옵니다.
- 대화형으로 열 때는 `/resume`처럼 세션을 불러오기만 하고 중단된 실행을 자동으로 이어 가지 않습니다.
- 없는 세션 id면 화면을 바꾸기 전에 `error: session not found: <id>`를 출력하고 종료 코드 2로 끝납니다.
- 파이프, 터미널이 아닌 입출력, `TERM=dumb`에서는 지금처럼 REPL 없이 세션을 한 번 이어서 실행하고 평문으로 출력합니다. 이때 `--tui`/`--no-tui`는 무시됩니다.

| 옵션 | 단축 | 설명 |
|---|---|---|
| `--workdir` | `-w` | 작업 디렉터리입니다. 기본값은 `.`입니다. |
| `--config` | `-c` | 사용할 설정 파일입니다. |
| `--approval` | | 승인 모드입니다. `ask`, `auto`, `deny`, `policy` 중 하나를 씁니다. `policy`는 정책으로 결정하고 묻지 않습니다(자율 승인 정책 섹션 참고). |
| `--max-iterations` | | 요청 하나당 최대 반복 횟수입니다. |
| `--max-cost` | | 세션당 USD 상한입니다. 기본값은 `[agent] max_cost_usd`입니다. |
| `--verbose` | `-v` | 이벤트를 JSON으로 stderr에 출력합니다. |
| `--delegate` | | 이번 실행에서 하위 에이전트 위임을 켭니다. 기본값은 `[delegation] enabled`입니다. |
| `--tui` | | 대화형 터미널에서 세션을 불러온 전체 화면 TUI를 엽니다(기본). |
| `--no-tui` | | 대화형 터미널에서 클래식 인라인 REPL로 엽니다. |
| `--help` | | 도움말을 보여주고 끝냅니다. |

### `cora bench`

내장 벤치 작업을 실행하고 결과 표를 출력합니다. `--live`를 주면 실제 OpenRouter 호출로 모델과 프로토콜 조합을 돌리고 보고서를 씁니다. `--config`, `--workdir`, `--baseline`, `--repeats`, `--seed`를 제외한 모든 옵션은 `--live`와 함께 써야 합니다. `--live` 없이 이런 옵션을 주면 오류 메시지를 내고 종료 코드 2로 끝납니다. 자세한 내용은 벤치 섹션을 보세요.

| 옵션 | 단축 | 설명 |
|---|---|---|
| `--config` | `-c` | 사용할 설정 파일입니다. |
| `--baseline` | | 기준선 TOML 파일입니다. 형식은 벤치 섹션에 있습니다. |
| `--workdir` | `-w` | 작업 디렉터리입니다. 기본값은 `.`입니다. |
| `--live` | | 실제 OpenRouter 호출을 합니다. 비용이 듭니다. |
| `--models` | | 쉼표로 구분한 모델 ID입니다. 기본값은 `[bench] models`입니다. `--live` 전용입니다. |
| `--protocols` | | 쉼표로 구분한 프로토콜(`react`, `native`)입니다. 기본값은 `[bench] protocols`입니다. `--live` 전용입니다. |
| `--tasks` | | 쉼표로 구분한 live 작업 ID입니다. `--live` 전용입니다. |
| `--max-cost` | | 이번 실행 전체의 USD 상한입니다. 기본값은 0.30이고 최대 0.50입니다. `--live` 전용입니다. |
| `--max-task-cost` | | 작업 하나당 USD 상한입니다. 기본값은 `--max-cost`의 10분의 1입니다. `--live` 전용입니다. |
| `--e2e-task-cost` | | `--suite e2e` 전용입니다. 과제 하나의 USD 상한으로, 과제의 task.toml `limits.cost_usd`를 대신합니다. 0보다 크고 `--max-cost` 이하여야 하며, 주지 않으면 task.toml 값을 씁니다. `--live` 전용입니다. |
| `--max-iterations` | | 작업당 최대 반복 횟수입니다. `--live` 전용입니다. |
| `--out` | | 보고서를 저장할 디렉터리입니다. 기본값은 `<workdir>/.cora/bench/live-<ts>`입니다. `--live` 전용입니다. |
| `--tool-groups` | | 쉼표로 구분한 도구 그룹입니다. 기본값은 `core`이며 core는 항상 포함됩니다. 나머지 그룹은 `git`, `web`, `plan-todo`, `delegate`입니다. `--live` 전용입니다. |
| `--sensor` | | `--live`에서 각 작업의 검사 명령을 최종 답 전에 실행하는 센서 게이트를 켭니다(최대 3회 재시도, tripwire도 켜짐). 기본값은 꺼짐이며 `--live` 전용입니다. |
| `--sensor-source` | | `oracle` 또는 `auto`입니다(`--live --sensor`에서만). 기본값은 `oracle`입니다. `auto`는 작업 workspace에서 감지한 검사 명령을 쓰고, 채점기는 에이전트에게 숨깁니다. 감지되지 않은 작업은 게이트 없이 실행되고 `no_check_tasks`로 보고합니다. e2e 과제도 `auto`를 쓸 수 있습니다. `--suite e2e --sensor`는 `--sensor-source auto`를 함께 줘야 하며, 빠뜨리면 종료 코드 2로 끝납니다(e2e 과제에는 정답 검사가 없고 채점기는 숨깁니다). |
| `--verify-attempts` | | 검증 재시도입니다. `--live --suite e2e` 전용이며 정수 2~5입니다. 최종 답 뒤에 workspace의 공개 검사(자동 감지)를 실행하고, 실패하면 반성 1건을 남긴 뒤 새 시도를 시작합니다(최대 N회). `--sensor`와 함께 쓸 수 없고, 어기면 종료 코드 2입니다. 숨김 채점기는 쓰지 않습니다. |
| `--repeats` | | 각 셀을 N번 실행합니다(정수, 최소 1, 기본값 1). 0이거나 정수가 아니면 종료 코드 2입니다. `--live` 없이도 씁니다. |
| `--seed` | | 기준 시드입니다. 기본값은 0입니다. 실행 시드는 기준 시드에 반복 번호를 더한 값이며 보고서에 기록합니다. 제공자에게는 보내지 않습니다. |
| `--resume` | | 지정한 디렉터리의 보고서를 이어서 씁니다. 끝난 실행은 호출 없이 건너뜁니다. 원본은 `report.resume-backup.json`으로 백업합니다. 같은 `--seed`를 써야 합니다. `--live` 전용입니다. |
| `--trim-to-budget` | | 사전 추정이 `--max-cost`를 넘으면 반복 수를 줄여 맞추고, 그 사실을 보고서에 기록합니다. `--live` 전용입니다. |
| `--suite` | | 작업 묶음입니다. `default`(기본값, 내장 live 작업)이거나 `e2e`(요구사항으로 작은 프로젝트를 끝까지 만드는 과제)입니다. `--live` 전용입니다. 자세한 내용은 벤치 섹션의 e2e 항목에 있습니다. |
| `--ab` | | A/B 비교 구성을 쉼표로 고릅니다: `deleg-off`(위임 끔, cheap-only 겸용), `deleg-on-par-off`, `deleg-on-par-on`, `strong-only`, `auto-routed` 또는 `all`(최대 5개). 모델 하나와 프로토콜 하나(기본 react)로 실행하며 위임×모델 조합은 실행하지 않습니다. 기본 작업은 다중 파일 과제 6개입니다. `--live` 전용입니다. |
| `--help` | | 도움말을 보여주고 끝냅니다. |

### `cora bench plan`

호출 없이 `cora bench`의 최대 지출 추정치를 출력합니다. API 키나 네트워크가 필요하지 않습니다. 추정치는 작업마다 `--max-iterations`회 반복에 대해 입력 16000 토큰과 출력 1024 토큰을 가정하고, `cora.toml`의 모델 가격으로 계산한 보수적인 상한입니다. 작업 상한(`--max-task-cost`)을 넘지 않도록 자릅니다. 추정치가 `--max-cost`를 넘어도 종료 코드는 0입니다. 초과 여부는 출력의 `OVER CAP` 줄로 알 수 있습니다.

| 옵션 | 단축 | 설명 |
|---|---|---|
| `--config` | `-c` | 사용할 설정 파일입니다. |
| `--workdir` | `-w` | 작업 디렉터리입니다. 기본값은 `.`입니다. |
| `--models` | | 쉼표로 구분한 모델 ID입니다. 기본값은 `[bench] models`입니다. |
| `--protocols` | | 쉼표로 구분한 프로토콜(`react`, `native`)입니다. 기본값은 `[bench] protocols`입니다. |
| `--tasks` | | 쉼표로 구분한 live 작업 ID입니다. |
| `--ab` | | A/B 구성 목록입니다. 형식은 `cora bench`의 `--ab`와 같습니다. |
| `--repeats` | | 셀마다 반복할 횟수입니다(최소 1, 기본값 1). |
| `--max-cost` | | 전체 USD 상한입니다. 기본값은 0.30입니다. |
| `--max-task-cost` | | 작업 하나의 USD 상한입니다. 기본값은 `--max-cost`의 10분의 1입니다. |
| `--e2e-task-cost` | | `--suite e2e` 전용 과제 하나의 USD 상한입니다. task.toml `limits.cost_usd`를 대신하며, 0보다 크고 `--max-cost` 이하여야 합니다. 주지 않으면 task.toml 값을 씁니다. |
| `--max-iterations` | | 작업당 최대 반복 횟수입니다. |
| `--suite` | | 작업 묶음입니다. `default` 또는 `e2e`입니다. `e2e`이면 e2e 과제를 고르고, 과제별 반복 한도와 비용 한도를 씁니다. |
| `--help` | | 도움말을 보여주고 끝냅니다. |

### `cora bench compare`

`cora bench compare REPORT`는 벤치 실행이 쓴 `report.json`을 기준선 파일(`baseline.toml`)과 작업 ID로 맞춰 비교 표를 출력합니다. 호출을 하지 않으며 API 키나 네트워크가 필요하지 않습니다. 표는 작업마다 CORA의 해결 수, 기준선의 해결 수, CORA와 기준선의 비용, solved-per-dollar 비율, 판정을 적고, 맨 아래에 `ALL` 요약 행을 붙입니다. 판정은 해결률만 비교합니다. 기준선에는 실행마다의 값이 없고 평균 비용만 있기 때문입니다.

| 옵션 | 단축 | 설명 |
|---|---|---|
| `--baseline` | | 기준선 TOML 파일입니다. 형식은 벤치 섹션의 기준선 비교 항목(baseline.toml 스키마)에 있습니다. 파일이 없으면 CORA의 절대 수치만 출력합니다. |
| `--out` | | 이 디렉터리에 `compare.md`와 `compare.json`을 씁니다. |
| `--help` | | 도움말을 보여주고 끝냅니다. |

- `--baseline`을 주지 않았거나 파일이 없으면 `baseline 없음: 비교 생략` 문구와 CORA의 절대 수치만 출력하고 종료 코드 0으로 끝납니다. 파일이 없을 때는 `baseline file not found: <파일 이름>` 줄도 나옵니다.
- 기준선이 잘못되었거나(TOML 문법 오류, 필수 필드 누락, 타입 오류) 보고서를 읽을 수 없거나 `results`가 목록이 아니면 오류 메시지를 내고 종료 코드 2로 끝납니다.
- 출력 표의 열은 `task`, `CORA solve`, `baseline solve`, `CORA cost`, `baseline cost`, `solved-per-dollar ratio`, `verdict`입니다. 기준선의 `n`이 1이면 `baseline n=1, 비교 불확실` 문구가 판정에 붙습니다.
- 기준선이 `synthetic = true`이면 출력 첫 줄에 SYNTHETIC 배너를 항상 붙입니다.
- 조인되지 않은 작업은 `unmatched:` 줄에 나옵니다. 보고서에만 있으면 `CORA only`, 기준선에만 있으면 `baseline only`입니다.

### `cora decider`

결정기(decider)를 오프라인으로 평가합니다. 지금 있는 동작은 `eval` 하나입니다. 케이스 파일을 읽어 결정기가 cheap과 strong을 얼마나 맞히는지와 예상 비용을 출력합니다. 케이스 형식과 출력의 뜻은 결정기 평가 섹션을 보세요. `heuristic`과 `replay`는 호출을 하지 않으며, `llm`은 `--live`가 있을 때만 실제 호출을 합니다.

```
cora decider eval --cases cases.jsonl --decider heuristic
```

| 옵션 | 단축 | 설명 |
|---|---|---|
| `--cases` | | JSONL 케이스 파일입니다. 한 줄에 케이스 하나를 씁니다. `eval`에 필수입니다. |
| `--decider` | | 결정기 종류입니다. `heuristic`(기본값), `replay`, `llm` 중 하나입니다. `llm`은 `--live`가 필요합니다. |
| `--live` | | `--decider llm`에서 실제 OpenRouter 호출을 허용합니다. 비용이 듭니다. |
| `--max-cost` | | `--decider llm`의 USD 상한입니다. 기본값은 0.05이고 최대 0.50입니다. |
| `--model` | | `--decider llm`의 결정 모델입니다. 티어 이름 또는 `[[models]]` ID입니다. 기본값은 `[decider] model`입니다. |
| `--json` | | 보고서를 JSON으로 출력합니다. |
| `--config` | `-c` | 사용할 설정 파일입니다. |
| `--workdir` | `-w` | 작업 디렉터리입니다. 기본값은 `.`입니다. |
| `--help` | | 도움말을 보여주고 끝냅니다. |

### `cora sale`

실험적(experimental) 기능입니다. 에이전트 루프에 연결되지 않은 라이브러리입니다. SALE-lite 라우팅을 오프라인으로 평가합니다. 지금 있는 동작은 `eval` 하나입니다. 네트워크, API 키, 환경 변수가 필요 없습니다. 자세한 내용은 SALE-lite 라우팅 섹션을 보세요.

```
cora sale eval --cases src/cora/data/sale_cases.synthetic.jsonl
```

| 옵션 | 단축 | 설명 |
|---|---|---|
| `--cases` | | JSONL 케이스 파일입니다. `eval`에 필수입니다. |
| `--tiers` | | tier 표 TOML입니다. 기본값은 `[sale] tiers_file`이고, 없으면 내장 M15-measured 표를 씁니다. |
| `--reward` | | 작업 보상입니다. 기본값은 `[sale] reward`이며 0보다 커야 합니다. |
| `--budget-cap` | | 작업당 비용 상한입니다. 기본값은 `[sale] budget_cap`이며 0보다 커야 합니다. |
| `--json` | | 보고서를 JSON으로 출력합니다. |
| `--config` | `-c` | 사용할 설정 파일입니다. |
| `--help` | | 도움말을 보여주고 끝냅니다. |

### `cora mcp`

`cora mcp list`는 설정된 MCP 서버를 하나씩 잠깐 시작해 `tools/list`로 도구 목록을 받아 출력하고, 각 서버를 종료합니다. 서버가 실패해도 그 행에 `failed`와 오류 요약을 표시하고 나머지 서버는 계속 조회합니다. `enabled = false`인 서버는 시작하지 않고 `disabled`로 표시합니다. 서버가 하나도 없으면 설정 방법을 안내하고 종료 코드 0으로 끝납니다. 일부 서버가 실패해도 종료 코드는 0입니다. 설정 파일 오류나 잘못된 사용법이면 종료 코드 2입니다. 출력은 파이프로 받아도 평문입니다.

```
cora mcp list
```

| 옵션 | 단축 | 설명 |
|---|---|---|
| `--config` | `-c` | 사용할 설정 파일입니다. |
| `--workdir` | `-w` | 작업 디렉터리입니다. 서버도 이 디렉터리에서 실행됩니다. 기본값은 `.`입니다. |
| `--help` | | 도움말을 보여주고 끝냅니다. |

`cora mcp serve`는 CORA 자체를 MCP stdio 서버로 실행합니다. MCP 클라이언트(Claude Code, Claude Desktop 등)가 CORA의 `run_task`, `resume_session`, `list_sessions` 도구를 호출합니다. 표준 입력이 닫히면 종료 코드 0으로 끝나고, 설정 오류면 종료 코드 2입니다. 자세한 내용은 `MCP 서버로 실행` 섹션을 보세요.

```
cora mcp serve -w .
```

### `cora project`

`cora project run PLAN.toml`은 TOML 계획 파일의 마일스톤을 순서대로 실행하고, 마일스톤마다 체크포인트를 저장합니다. `cora project resume RUN_ID`는 저장된 체크포인트에서 이어서 실행합니다. `cora project plan GOAL`은 목표를 마일스톤 계획 TOML 파일로 만듭니다. 자세한 내용은 아래 프로젝트 실행 섹션을 보세요.

| 옵션 | 단축 | 설명 |
|---|---|---|
| `--help` | | 도움말을 보여주고 끝냅니다. |

### `cora project run`

계획 파일을 읽고 마일스톤을 계획 순서대로 실행합니다. 마일스톤이 끝날 때마다 체크포인트를 저장하고, 실행 시작 때 `project run id: <run_id>`를 stderr에 출력합니다. 이 run id로 `cora project resume`을 쓸 수 있습니다.

계획 파일 대신 `--goal GOAL`을 주면 먼저 모델로 계획을 만든 뒤 실행합니다. `PLAN.toml`과 `--goal`은 둘 다 주거나 둘 다 없으면 종료 코드 2로 끝납니다.

```
cora project run PLAN.toml --headless --json
cora project run --goal "작은 계산기 모듈" --headless --json
```

| 옵션 | 단축 | 설명 |
|---|---|---|
| `--workdir` | `-w` | 작업 디렉터리입니다. 체크포인트도 `<workdir>/.cora/projects/` 아래에 저장됩니다. 기본값은 `.`입니다. |
| `--config` | `-c` | 사용할 설정 파일입니다. |
| `--approval` | | 승인 모드입니다. `ask`, `auto`, `deny`, `policy` 중 하나를 씁니다. |
| `--max-iterations` | | 프로젝트 전체의 반복 횟수 상한입니다. 여러 마일스톤과 이전 실행의 누적분을 포함합니다. |
| `--max-cost` | | 프로젝트 전체의 USD 상한입니다. 기본값은 `[agent] max_cost_usd`입니다. |
| `--max-wall-s` | | 프로젝트 전체의 벽시계 시간 상한(초)입니다. 0이면 제한 없음입니다. 헤드리스 기본값은 `[headless] max_wall_s`입니다. |
| `--max-tool-calls` | | 프로젝트 전체의 도구 호출 수 상한입니다. 0이면 제한 없음입니다. 헤드리스 기본값은 `[headless] max_tool_calls`입니다. |
| `--headless` | | TUI, REPL, 프롬프트 없이 무인으로 실행합니다. 승인 기본값은 `policy`입니다. |
| `--json` | | 결과를 JSON 문서 한 줄로 stdout에 씁니다. 그 밖의 출력은 stderr로 갑니다. |
| `--quiet` | `-q` | 진행 상황을 stderr에 출력하지 않습니다. 오류와 경고는 그대로 나옵니다. |
| `--verbose` | `-v` | 이벤트를 JSON으로 stderr에 출력합니다. |
| `--goal` | | 목표에서 계획을 만든 뒤 실행합니다. 계획은 `<workdir>/.cora/projects/<run_id>/plan.toml`에 저장하며, 계획 비용은 같은 예산에 포함합니다. |
| `--output` | `-o` | `--goal`과 함께만 씁니다. 생성한 계획을 이 파일에도 저장합니다. |
| `--help` | | 도움말을 보여주고 끝냅니다. |

별도의 간섭 횟수 키는 없습니다. 간섭의 대리 지표는 결과 JSON의 `policy.deny + policy.ask_resolved_deny`입니다.

### `cora project resume`

저장된 체크포인트(`RUN_ID`)에서 이어서 실행합니다. 완료된 마일스톤은 호출 없이 건너뜁니다. 계획은 체크포인트에 저장된 것을 씁니다.

```
cora project resume 20260101-120000-a1b2c3 --headless --json
```

| 옵션 | 단축 | 설명 |
|---|---|---|
| `--workdir` | `-w` | 작업 디렉터리입니다. 체크포인트는 `<workdir>/.cora/projects/` 아래에서 찾습니다. 기본값은 `.`입니다. |
| `--config` | `-c` | 사용할 설정 파일입니다. |
| `--approval` | | 승인 모드입니다. `ask`, `auto`, `deny`, `policy` 중 하나를 씁니다. |
| `--max-iterations` | | 프로젝트 전체의 반복 횟수 상한입니다. 이전 실행의 누적분을 포함합니다. |
| `--max-cost` | | 프로젝트 전체의 USD 상한입니다. 기본값은 `[agent] max_cost_usd`입니다. |
| `--max-wall-s` | | 프로젝트 전체의 벽시계 시간 상한(초)입니다. 0이면 제한 없음입니다. 헤드리스 기본값은 `[headless] max_wall_s`입니다. |
| `--max-tool-calls` | | 프로젝트 전체의 도구 호출 수 상한입니다. 0이면 제한 없음입니다. 헤드리스 기본값은 `[headless] max_tool_calls`입니다. |
| `--headless` | | TUI, REPL, 프롬프트 없이 무인으로 실행합니다. 승인 기본값은 `policy`입니다. |
| `--json` | | 결과를 JSON 문서 한 줄로 stdout에 씁니다. 그 밖의 출력은 stderr로 갑니다. |
| `--quiet` | `-q` | 진행 상황을 stderr에 출력하지 않습니다. 오류와 경고는 그대로 나옵니다. |
| `--verbose` | `-v` | 이벤트를 JSON으로 stderr에 출력합니다. |
| `--help` | | 도움말을 보여주고 끝냅니다. |

### `cora project plan`

목표(`GOAL`)를 모델에 한 번 보내 마일스톤 계획을 받고, `-o`로 준 파일에 TOML로 씁니다. 마일스톤은 실행하지 않습니다. 모델 응답이 계획 형식에 맞지 않으면 오류 내용을 담아 한 번만 다시 요청합니다. 두 번째 응답도 맞지 않으면 종료 코드 2로 끝나고 파일을 쓰지 않습니다. 프롬프트에는 목표 텍스트만 들어가며 작업 디렉터리의 파일 내용은 들어가지 않습니다. 모델은 `[router]`의 기본 모델 설정(`default`)을 따릅니다. 계획 호출 비용이 상한을 넘으면 종료 코드 4로 끝납니다.

```
cora project plan "작은 계산기 모듈" -o plan.toml --json
```

| 옵션 | 단축 | 설명 |
|---|---|---|
| `--output` | `-o` | 만들 계획 파일입니다(TOML). 없으면 종료 코드 2입니다. |
| `--workdir` | `-w` | 작업 디렉터리입니다. 기본값은 `.`입니다. |
| `--config` | `-c` | 사용할 설정 파일입니다. |
| `--max-cost` | | 계획 호출의 USD 상한입니다. 기본값은 `[agent] max_cost_usd`입니다. |
| `--json` | | 결과를 JSON 문서 한 줄로 stdout에 씁니다. 그 밖의 출력은 stderr로 갑니다. |
| `--quiet` | `-q` | 진행 상황을 stderr에 출력하지 않습니다. 오류와 경고는 그대로 나옵니다. |
| `--approval` | | 승인 모드입니다. `ask`, `auto`, `deny`, `policy` 중 하나를 씁니다. 계획이 실행될 헤드리스 실행에 맞춰 계획의 검사 명령을 검증합니다. 기본값은 `[agent] approval`입니다. 헤드리스 실행에 쓸 계획은 `--approval policy`로 만드세요. |
| `--help` | | 도움말을 보여주고 끝냅니다. |

### 종료 코드

| 코드 | 의미 |
|---|---|
| 0 | 최종 답을 얻었거나 REPL을 정상적으로 끝낸 경우입니다. `cora bench`가 `--max-cost` 상한에 닿아 보고서가 `partial: true`인 경우도 0입니다. |
| 1 | 최종 답 없이 멈춘 경우입니다(`run`, `-p`, 비대화형 `resume`). 모델 호출 시간 초과(`provider_timeout`)도 여기에 해당합니다. |
| 2 | 설정 오류 또는 사용법 오류입니다. 잘못된 옵션 조합도 여기에 해당합니다. `cora bench --live`의 사전 점검이 실행을 거부한 경우도 여기에 해당합니다. `cora decider eval`의 잘못된 케이스 파일, `--live` 없이 `--decider llm`을 준 경우(호출 없이 안내만 출력)도 여기에 해당합니다. 제공자 계정 오류(HTTP 401, 402, 403)로 `cora run`, `cora -p`, 비대화형 `cora resume`이 끝난 경우도 여기에 해당합니다(사용자 조치가 필요한 설정·계정 문제). 다른 제공자 오류(5xx, 네트워크)도 지금처럼 종료 코드 2입니다. `cora sale eval`의 잘못된 케이스 파일(줄 번호 포함 오류), 비었거나 없는 파일, 잘못된 tier 표나 옵션 값도 여기에 해당합니다. `cora resume`에 없는 세션 id를 준 경우도 여기에 해당하며, 대화형 터미널에서도 화면을 바꾸기 전에 끝납니다. `cora bench --live`의 사전 추정이 `--max-cost`를 넘어 실행을 거부한 경우(`--repeats`, `--trim-to-budget`, `--resume` 중 하나를 준 경우)도 여기에 해당합니다. `--resume` 디렉터리에 읽을 수 있는 `report.json`이 없거나 `--seed`가 다르면 여기에 해당합니다. 독립 설치에서 소스 체크아웃 전용 명령(`cora bench`, `cora bench plan`, `cora bench compare`, `cora decider eval`, `cora sale eval`)을 실행한 경우도 여기에 해당합니다. |
| 3 | `cora bench --live`가 제공자 계정 오류(HTTP 401, 402, 403)로 중단된 경우입니다. 부분 보고서는 `--out`에 저장되고 오류 메시지를 출력합니다. `cora decider eval --decider llm --live`가 계정 오류로 중단된 경우도 여기에 해당합니다.
| 130 | Ctrl-C로 중단한 경우입니다. `cora resume <id>` 안내를 출력합니다. |
| 4 | `--headless`/`--json` 실행에서 예산 상한에 닿아 멈춘 경우입니다(`budget_exceeded`). |
| 5 | `--headless`/`--json` 실행이 정책 거부로 답 없이 끝난 경우입니다(`policy_blocked`). |
| 143 | `--headless`/`--json` 실행이 SIGTERM으로 중단된 경우입니다. |

제공자의 요청 한도(429)를 재시도로 다 써서 `rate limited`로 멈춘 경우도 종료 코드 1입니다.

4, 5, 143은 `--headless`와 `--json` 실행에만 적용됩니다. 기본 실행은 0, 1, 2, 130을 그대로 씁니다. 3은 `cora bench`용으로 남겨 둡니다. `cora project run`과 `cora project resume`도 `--headless`나 `--json`을 주면 헤드리스 실행과 같이 0, 1, 2, 4, 5, 130, 143을 씁니다. 프로젝트 실행의 뜻은 프로젝트 실행 섹션의 프로젝트 종료 코드를 보세요.

### 제공자 계정 오류 (HTTP 401, 402, 403)

OpenRouter가 계정 오류를 돌려주면 CORA는 원문 대신 영어 안내를 먼저 출력하고, 마지막 줄에 `HTTP <상태>: <원문 메시지 앞부분>`을 붙입니다. 원문은 약 300자로 잘리고 API 키 값은 `[REDACTED]`로 가려집니다. REPL 턴, `cora run`, `cora -p`, `cora resume`, `cora bench --live` 중단 메시지, `cora decider eval --decider llm --live` 중단 메시지에 같은 안내가 나옵니다.

- 402: 계정 크레딧(선불 잔액)이 부족합니다. 키 한도 문제가 아닙니다. OpenRouter는 선불제라서 결제 카드를 저장해 두는 것만으로는 요청마다 결제되지 않습니다. `https://openrouter.ai/settings/credits`에서 크레딧을 구매하거나 auto top-up을 켜세요. 응답에 "can only afford N tokens"가 있으면 잔액이 거의 바닥났다는 힌트(N 포함)를 함께 보여 줍니다.
- 401: API 키가 잘못되었거나 폐기·만료되었습니다. 설정한 `api_key_env`(기본 `OPENROUTER_API_KEY`) 환경 변수의 키를 확인하세요.
- 403: 접근이 거부되었습니다(키 권한, 모델 접근, 지역이나 제공자 정책, 키 한도 등).
- REPL에서는 세션을 끝내지 않고 안내를 출력한 뒤 프롬프트로 돌아갑니다. `cora run`, `cora -p`, 비대화형 `cora resume`은 종료 코드 2, `cora bench --live`와 `cora decider eval --decider llm --live`는 종료 코드 3으로 끝납니다.
- `:free` 모델은 잔액이 0이어도 동작할 수 있고, 402로 거절된 요청에는 비용이 청구되지 않습니다.

### 헤드리스 실행 (`--headless`, `--json`)

`--headless`는 무인 실행입니다. TUI, REPL, 프롬프트를 열지 않고 작업 하나를 실행한 뒤 끝냅니다. `--json`을 붙이면 결과를 JSON 문서 하나로 stdout에 씁니다.

- 승인 모드: 기본값은 `policy`입니다(자율 승인 정책 섹션 참고). `--approval ask`는 답할 사람이 없으므로 거부되고 종료 코드 2로 끝납니다. `--approval auto`는 명시적으로 줄 때만 쓰며, 검토 없이 모든 도구 호출을 실행한다는 경고를 한 번 출력합니다.
- 작업 입력은 한 가지여야 합니다. `TASK` 인자, `--task-file PATH`, `-`(stdin) 중 정확히 하나만 줍니다. 둘 이상이거나 작업이 비어 있으면 종료 코드 2입니다.
- `--json`: 결과 문서 하나만 stdout에 나옵니다. 도구나 다른 코드가 찍는 글자는 stderr로 갑니다.
- `--quiet`(`-q`): 진행 상황을 stderr에 출력하지 않습니다. 오류와 경고는 계속 출력합니다.
- `--resume`: 저장된 세션을 헤드리스로 이어 갑니다. `--headless`와 함께만 씁니다. 예산 상한은 이전 실행의 누적분을 포함합니다.
- SIGINT(Ctrl-C)와 SIGTERM: 신호를 받으면 진행 중인 호출이 끝난 뒤 멈추고, 세션을 저장한 다음 `stop_reason`이 `interrupted`인 결과를 냅니다. 종료 코드는 SIGINT가 130, SIGTERM이 143입니다. 두 번째 신호는 진행 중인 호출도 바로 취소합니다.

`--json` 문서의 키는 다음 15개입니다.

- `ok`: `stop_reason`이 `final_answer`이면 true입니다.
- `stop_reason`: 정지 사유입니다. `final_answer`, `interrupted`, `budget_exceeded`, `policy_blocked` 등이 나옵니다.
- `final_answer`: 최종 답입니다. 없으면 null입니다.
- `session_id`: 세션 id입니다. `cora resume <id>`로 이어 갈 수 있습니다.
- `iterations`: 반복 횟수입니다.
- `cost_usd`: 세션 누적 비용입니다. `--resume`이면 이전 요청의 비용도 포함합니다. 오류로 끝난 실행도 첫 모델 호출 뒤의 오류이면 그때까지 계량한 비용을 담습니다. 모델 호출 전 오류이면 0.0입니다. 응답 없이 시간이 끝난 호출(예: `RequestDeadlineExceeded`)은 사용량이 없어 포함되지 않습니다.
- `tokens`: `{"in": ..., "out": ...}` 형식의 세션 누적 토큰 수입니다.
- `wall_s`: 이번 실행의 벽시계 시간(초)입니다.
- `models`: 쓴 모델 id 목록입니다. 오류 결과에서도 계량된 모델이 나옵니다 (모델 호출 전 오류이면 빈 목록).
- `profile`: (model, provider)별 calls/tokens/`cost_usd`/`cost_source`/`p50_latency_s`/`excluded_from_cost_usd` 목록입니다.
- `tools`: 이번 실행에서 도구별 호출 횟수입니다.
- `policy`: 정책 모드와 결정 요약입니다.
- `budget`: `limits`, `used`, `tripped`, `warned`를 담습니다.
- `warnings`: 경고 문장 목록입니다.
- `errors`: 오류 문장 목록입니다.
- `exit_code`: 프로세스 종료 코드와 같습니다.

예시(값은 실행마다 다릅니다):

```json
{
  "ok": true,
  "stop_reason": "final_answer",
  "final_answer": "42",
  "session_id": "example-session-id",
  "iterations": 2,
  "cost_usd": 0.00031,
  "tokens": {"in": 1820, "out": 96},
  "wall_s": 7.412,
  "models": ["google/gemini-2.5-flash-lite"],
  "profile": [{"model": "google/gemini-2.5-flash-lite", "provider": "openrouter", "calls": 2, "input_tokens": 1820, "output_tokens": 96, "cached_input_tokens": 0, "cost_usd": 0.00031, "cost_source": "provider_usage", "p50_latency_s": 3.1, "excluded_from_cost_usd": false}],
  "tools": {"list_files": 1},
  "policy": {"mode": "policy", "deny": 0, "ask_resolved_deny": 0, "decisions": []},
  "budget": {
    "limits": {"cost_usd": 0.5, "iterations": 30, "wall_s": 900.0, "tool_calls": 200},
    "used": {"cost_usd": 0.00031, "iterations": 2, "wall_s": 7.412, "tool_calls": 1},
    "tripped": null,
    "warned": false
  },
  "warnings": [],
  "errors": [],
  "exit_code": 0
}
```

CI에서는 결과 파일과 종료 코드를 함께 쓸 수 있습니다.

```
cora run --headless --json --task-file task.md --max-cost 0.20 --max-wall-s 600 > result.json
```

`cora bench`는 이 모드와 관계없이 그대로입니다. 종료 코드 3과 자체 예산(`--max-cost`, `[bench]`)을 그대로 씁니다. 헤드리스 실행의 정책 판정은 자율 승인 정책 섹션과 같은 규칙을 따르며, 정책 거부 때문에 답 없이 끝나면 종료 코드 5입니다.

### 예산 상한

한 실행에는 네 가지 상한이 있습니다. 상한에 닿으면 실행을 멈추고 세션을 저장합니다.

| 상한 | CLI 옵션 | 기본 실행 설정 | 헤드리스 설정 | 기본값 |
|---|---|---|---|---|
| 비용(USD) | `--max-cost` | `[agent] max_cost_usd` | `[agent] max_cost_usd` | 0.5 |
| 반복 횟수 | `--max-iterations` | `[agent] max_iterations` | `[agent] max_iterations` | 30 |
| 벽시계 시간(초) | `--max-wall-s` | `[agent] max_wall_s` | `[headless] max_wall_s` | 기본 실행 0, 헤드리스 900 |
| 도구 호출 수 | `--max-tool-calls` | `[agent] max_tool_calls` | `[headless] max_tool_calls` | 기본 실행 0, 헤드리스 200 |

- 벽시계 시간과 도구 호출 수는 0이면 제한 없음입니다.
- 상한은 모델 호출과 도구 호출 전에 확인합니다. 그래서 넘을 수 있는 양은 호출 한 번분이 최대입니다.
- 정지 사유: 기본 실행은 `cost_limit`, `max_iterations`, `budget_exceeded`로 끝납니다. `--json`과 헤드리스 실행은 이 셋을 `budget_exceeded`로 정규화하고, `budget.tripped`에 상한 이름(`cost`, `iterations`, `wall`, `tool_calls`)을 씁니다.
- 경고: 각 상한은 `budget_warn_fraction`(기본 0.8)에 처음 닿을 때 `budget_warning` 이벤트를 한 번만 냅니다. 헤드리스와 `--json`에서만 stderr에 경고 한 줄을 쓰고 `warnings`에도 기록합니다.
- 하위 에이전트(위임)와 결정기 호출의 사용량도 같은 상한에 더해집니다.
- 반복 횟수 상한은 시도(attempt)마다 적용되며 기존 동작과 같습니다. `budget.used.iterations`는 실행 전체 합계입니다.

## REPL

`cora`를 인자 없이 실행하면 REPL이 열립니다. 프롬프트는 `> `이고, 계획 모드에서는 `[plan] > `로 바뀝니다. 입력 중 `/`로 시작하는 줄은 슬래시 명령으로 처리됩니다.

화면 모드는 세 가지입니다. TUI(전체 화면)는 대화형 터미널에서 기본으로 쓰이고, 클래식 인라인 REPL은 `--no-tui`나 `CORA_TUI=0`으로 고르며, 평문은 파이프, `cora -p`, `cora run`, 비대화형 `cora resume`에서 씁니다. 대화형 터미널에서 `cora resume <id>`는 그 세션을 불러온 TUI(또는 클래식 REPL)를 엽니다. 모드를 고르는 순서는 `### TUI (전체 화면)`에서 설명합니다.

### 입력

- 입력 기록은 `.cora/history`에 저장됩니다.
- 줄 끝에 `\`를 쓰면 다음 줄에 이어서 입력할 수 있습니다.
- Esc 다음 Enter로 줄바꿈을 넣을 수 있습니다. 여러 줄을 붙여넣는 것도 됩니다.
- Tab은 슬래시 명령 이름과 `@` 뒤의 경로를 자동 완성합니다.
- Ctrl-C는 진행 중인 턴만 멈추고 프롬프트로 돌아갑니다.
- Ctrl-D 또는 `/exit`로 REPL을 끝냅니다.
- 터미널에서 실행할 때(입력과 출력이 모두 터미널일 때)는 다음 키도 쓸 수 있습니다. 파이프 입력이나 `cora -p`에서는 쓰지 않습니다.
  - Shift+Tab: 승인 모드를 ask, auto, deny 순서로 돌립니다. `/approval`과 같은 경로로 바뀌므로 승인 규칙(deny 우선, 명령별 승인, `/reset` 복원)은 그대로입니다. 바뀐 모드는 한 줄 메시지와 하단 상태 줄에 보입니다. 자동 완성 목록이 열려 있을 때는 목록 이동에 쓰입니다. `policy`는 순환에 넣지 않습니다. `/approval policy`나 `--approval policy`로만 켜고, policy에서 Shift+Tab을 누르면 ask로 돌아갑니다.
  - Ctrl+T: 도구 호출 아래에 보이는 TODO 체크리스트 표시를 켜고 끕니다. 상태 줄의 `todo:on`, `todo:off`로 확인합니다. 입력 중 글자 바꾸기(transpose) 기능 대신 쓰입니다.
  - Ctrl+L: 클래식 인라인 REPL에서는 화면을 지우고 다시 그리며 대화 기록은 그대로입니다. TUI에서는 대화 영역을 다시 그리고 맨 아래로 이동합니다. TUI에서도 대화 기록은 지우지 않으며, 기록을 지우는 `/clear`와는 다릅니다.
  - Ctrl+C: 실행 중인 턴을 멈춥니다. 실행 중 표시에 `Ctrl+C to interrupt` 안내가 붙습니다. Esc로 실행을 멈추는 기능은 아직 없습니다.

### 터미널 화면

터미널에서 실행할 때만 아래 표시를 씁니다. 출력이 파이프이거나 `cora -p`, `cora run`이면 지금처럼 장식 없는 평문만 나옵니다.

- 시작 배너: 이름과 버전, 모델, 작업 디렉터리, 승인 모드, 가이드 파일, git 브랜치, 팁을 둥근 테두리 안에 보여줍니다. 폭이 60칸보다 좁으면 테두리 없이 보여줍니다.
- 하단 상태 줄: 입력을 기다리는 동안 승인 모드, 모델(티어:모델), 세션 비용, 컨텍스트 사용률(마지막 호출의 입력 토큰을 cheap 모델의 `context_tokens`로 나눈 근사치), 계획 모드와 `/check`, 위임 표시, 켜진 도구 그룹, 경과 시간, TODO 표시 여부를 한 줄로 보여줍니다. 모르는 값은 `-`로 보이고, 폭이 좁으면 덜 중요한 항목부터 생략합니다. 턴이 실행되는 동안에는 상태 줄 대신 진행 표시가 보입니다.
- 도구 호출: `● 이름(인자)` 줄과 `⎿` 결과 줄로 보여줍니다. 실패하면 `✗`와 `error:`로 표시합니다. 결과가 10줄을 넘으면 앞 3줄만 보이고 `… +K lines (/expand)`가 붙습니다. `/expand`로 마지막으로 접힌 결과 전체를 봅니다.
- diff: 수정 승인 화면과 `/diff`는 줄 번호와 `+`, `-` 접두어를 붙이고 추가는 녹색, 삭제는 적색으로 칠합니다. 색이 꺼져 있으면 접두어와 줄 번호로 구분합니다.
- TODO: 모델이 `todo_write`를 호출하면 체크리스트(`☐` 대기, `◐` 진행 중, `☒` 완료, ASCII에서는 `[ ]`, `[~]`, `[x]`)를 보여줍니다. Ctrl+T로 끄고 켭니다.
- 색과 글리프: `[ui]` 설정과 `/theme`로 바꿉니다. `NO_COLOR` 환경 변수가 있으면 색을 쓰지 않습니다.

### TUI (전체 화면)

TUI는 대화형 터미널에서 `cora`를 실행하면 시작하는 전체 화면 모드입니다. 시작할 때 전체 화면 영역(alternate screen)에 들어가고, 끝나면 이전 터미널 화면을 그대로 되돌립니다.

- 화면 구성(위에서 아래로): 대화 영역(남는 높이 전부, 스크롤 가능), TODO 패널(Ctrl+T로 켜고 끔, 기본은 숨김, 폭이 100칸 이상이면 오른쪽에, 좁으면 대화 영역 위에 접혀서 보임), 실행 표시줄(턴이 도는 동안 입력창 바로 위 한 줄에 스피너, 경과 시간, 현재 단계를 보여줌), 입력창(하단 고정, 여러 줄이면 최대 8줄까지 커지고 그 이상은 입력창 안에서 스크롤), 상태 줄(맨 아래 한 줄, 승인 모드·모델·비용·`mouse:on|off` 등).
- 모드 선택 우선순위: `--tui`/`--no-tui` > 환경 변수 `CORA_TUI` > 설정 `[ui] tui` > 기본값 true. `CORA_TUI`에서 `0`, `false`, `off`는 TUI를 끄고 `1`은 켭니다. 표준 입력이나 표준 출력이 터미널이 아니거나 `TERM=dumb`이면 TUI를 쓰지 않습니다. 터미널이면서 `TERM=dumb`이거나 `--no-tui`이면 클래식 인라인 REPL을, 터미널이 아니면 평문을 씁니다. `cora chat`과 `cora resume <id>`도 같은 순서를 따릅니다.
- 대화 스크롤: 새 출력이 오면 맨 아래에 있을 때만 따라갑니다. 위로 올려 보고 있으면 따라가기를 멈추고 상태 줄에 `↓ 새 출력`이 뜹니다. `Ctrl+End`로 맨 아래에 가면 다시 따라갑니다. 마우스 휠(트랙패드 스크롤 포함)은 대화 영역을 3줄씩 스크롤하며, 위로 굴리면 따라가기를 멈추고 맨 아래까지 내리면 다시 따라갑니다. 휠은 입력 기록을 움직이지 않습니다. 대화 블록은 `scrollback_blocks`(기본 5000)까지 보관하며, 넘으면 오래된 것부터 버리고 맨 위에 `이전 내용 생략됨`을 표시합니다.

키 조작:

| 키 | 동작 |
|---|---|
| Enter | 입력 전송. 턴이 도는 중에는 전송하지 않고 "실행 중" 안내만 표시합니다 |
| Alt+Enter, Ctrl+J | 입력창에서 줄바꿈 (여러 줄 입력) |
| ↑ / ↓ | 입력 기록 이동 (자동 완성 메뉴가 열려 있으면 메뉴 항목 이동). Ctrl+P/N도 같음 |
| Ctrl+R | 입력 기록 검색 |
| PageUp / PageDown | 대화 영역을 한 화면씩 스크롤 |
| Ctrl+↑/↓ 또는 Alt+↑/↓ | 대화 영역을 한 줄씩 스크롤 |
| Ctrl+End | 맨 아래로 이동하고 따라가기를 다시 켬 |
| 마우스 휠 | 대화 영역을 3줄씩 스크롤 (Ctrl+O 뷰어와 승인 diff 미리보기에서도 동작, 마우스 캡처가 켜져 있을 때) |
| Ctrl+O | 전체 transcript 뷰어 열기. 접힌 도구 출력 전체를 볼 수 있음. ↑/↓, PgUp/PgDn, g/G로 이동하고 q 또는 Esc로 닫음 |
| Ctrl+T | TODO 패널 켜기/끄기 |
| Ctrl+L | 대화 영역을 다시 그리고 맨 아래로 이동. 대화 기록은 지우지 않음 (`/clear`와 다름) |
| Shift+Tab | 승인 모드 순환 (승인 패널이 떠 있을 때도 동작) |
| F2 | 마우스 캡처 켜기/끄기 (`/mouse`와 같음) |
| Ctrl+C | 턴이 도는 중이면 턴 중단, 입력이 있으면 입력 비움, 빈 입력에서 두 번 연속 누르면 종료 |
| Ctrl+D | 입력이 비어 있을 때 종료 (입력이 있으면 무시) |

- 승인 패널: 도구 이름, 인자 요약, 변경이 있으면 색 diff 미리보기가 입력창 자리에 뜹니다. `y` 허용, `n` 거부, `a` 이후 항상 허용, `Esc` 거부입니다. 승인을 기다리는 동안 Ctrl+C는 거부하고 턴을 중단합니다.
- 실행 중 제출: 턴이 도는 중에는 Enter로 입력을 보내지 않습니다(거부하고 안내만 표시). 예외로 `/mouse`는 실행 중에도 쓸 수 있습니다.
- 마우스와 선택: 기본은 켜짐(`[ui] mouse = true`)이라 마우스 휠이 대화 영역을 스크롤하고, 클릭은 입력창 커서를 옮기는 것 외에는 무시합니다. 켜져 있을 때 텍스트를 선택하려면 Shift 또는 Option 키(터미널에 따라 다름; macOS Terminal.app과 iTerm2는 보통 Option)를 누른 채 드래그합니다. 마지막 답변은 `/copy`로 복사할 수 있습니다. `/mouse [on|off]`나 F2로 켜고 끄며, 상태 줄의 `mouse:on`/`mouse:off`로 확인합니다. 끄면(`/mouse off` 또는 `[ui] mouse = false`) 터미널 기본 드래그 선택이 되지만, 많은 터미널이 휠을 ↑/↓ 키로 바꿔 보내므로 휠이 대화 영역 대신 입력 기록을 이전/다음으로 움직일 수 있습니다. 예전 설정 파일에 `mouse = false`가 남아 있으면 이 동작이 계속되니 `true`로 바꾸세요.
- 복사: `/copy`는 마지막 어시스턴트 응답을 OSC 52 시퀀스로 클립보드에 보냅니다. 응답이 너무 크면(약 100 KB base64 이상) 보내지 않고 그 이유를 안내합니다. 터미널이 OSC 52를 막으면 조용히 실패하며, 복사가 됐는지는 CORA가 확인할 수 없습니다.
  - iTerm2: 설정에서 터미널 앱의 클립보드 접근을 허용합니다(Applications in terminal may access clipboard).
  - tmux: `~/.tmux.conf`에 `set -g set-clipboard on`을 넣고 tmux를 다시 불러옵니다.
- 붙여넣기: 여러 줄을 붙여넣어도 바로 실행되지 않고 입력창에 여러 줄로 들어갑니다. 확인 후 Enter로 보냅니다.
- 종료 요약: TUI를 끝내고 나면 일반 화면에 세션 id, 턴 수, 비용과 `cora resume <id>` 안내 몇 줄만 출력합니다. 대화 전체는 출력하지 않습니다. `[ui] exit_summary = false`로 끄면 요약도 나오지 않습니다. 처리되지 않은 오류로 끝나면 화면을 복원한 뒤 오류 메시지를 일반 화면에 출력합니다.
- 작은 터미널: 폭 40, 높이 10보다 작아지면 "터미널이 너무 작음" 안내만 보입니다. 다시 키우면 정상 화면으로 돌아오며, 그동안 앱은 계속 실행됩니다.
- 종료 신호: SIGTERM(143), SIGHUP(129), Ctrl+C(130)로 끝나도 같은 복원 절차를 거칩니다. SIGKILL은 복원할 수 없습니다.
- 문제 해결:
  - 종료 뒤 터미널이 이상하면(입력이 보이지 않거나 줄바꿈이 어긋나면) `reset` 또는 `stty sane`을 실행하세요.
  - 이 터미널에서 TUI가 맞지 않으면 `cora --no-tui`로 클래식 인라인 REPL을 쓰세요. `CORA_TUI=0`으로 기본값을 바꿀 수도 있습니다.
  - 복사가 안 되면 iTerm2 설정이나 tmux의 `set-clipboard` 설정을 확인하세요.

### 슬래시 명령

아래 표는 `/help`로 보는 명령 목록과 같습니다. 인자 형식은 설명 칸에 적었습니다.

| 명령 | 설명 |
|---|---|
| `/help` | 명령 목록과 입력 방법을 보여줍니다. |
| `/model` | 티어별 모델을 보거나 바꿉니다. 자세한 내용은 모델 전환 섹션을 보세요. |
| `/route` | 마지막 라우팅 결정(등급, 모델, 이유)을 보여줍니다. |
| `/cost` | 현재 세션의 비용을 보여줍니다. |
| `/clear` | 대화 컨텍스트를 비웁니다. 다음 요청은 새 세션으로 시작합니다. |
| `/reset` | REPL을 시작 시점 상태로 되돌립니다. 모델 pin, 승인 모드와 "항상 허용" 승인, 도구 그룹 토글, `/check`, 계획 모드, `/delegate`로 바꾼 위임 설정, TODO, 대화 컨텍스트, 첨부를 초기화합니다. 시작 플래그(`--approval`, `--delegate` 등)와 설정 파일은 그대로 쓰며, 저장된 세션(`/sessions`, `/resume`)은 유지합니다. 비용은 저장된 세션에 남으므로 유지되고, 세션 비용 표시는 다음 세션부터 새로 셉니다. `/reset --all`은 확인 후 `.cora/models.toml`(저장된 모델 오버라이드)도 삭제합니다. |
| `/compact` | 오래된 대화 내용을 지금 바로 메모리 요약으로 옮깁니다. |
| `/resume` | 저장된 세션을 이어서 엽니다. `/resume [id]` 형식입니다. |
| `/sessions` | 저장된 세션 목록을 보여줍니다. |
| `/approval` | 승인 모드를 보거나 바꿉니다. `ask`, `auto`, `deny`, `policy` 중 하나를 씁니다. |
| `/diff` | 변경 사항을 보여줍니다. git 저장소에서는 git diff이고, 아니면 이 세션에서 수정한 파일을 보여줍니다. |
| `/plan` | 계획 모드를 켭니다. 읽기 전용 도구만 쓰고 모델이 계획을 제출하면 승인을 받습니다. `/plan off`로 끕니다. |
| `/todo` | 이 세션의 TODO 목록을 보여줍니다. |
| `/tools` | 도구 그룹과 프롬프트 크기를 보고, 이 세션에서만 그룹을 켜거나 끕니다. |
| `/mcp` | MCP 서버별 상태(disabled, not started, running, crashed, failed), 도구 수와 이름, 최근 오류를 보여줍니다. 서버를 새로 시작하지 않으며 인자를 받지 않습니다. 자세한 내용은 MCP 서버 섹션을 보세요. |
| `/check` | 센서 게이트에 쓸 검사 명령을 설정합니다. `/check off`로 끕니다. |
| `/delegate` | 이 세션에서 하위 에이전트 위임(병렬 explore 포함)을 보거나 켜고 끕니다. `/delegate on`, `/delegate off`, 인자 없으면 현재 상태입니다. |
| `/decider` | 활성 결정기(decider)의 종류, 모델, 사용처 켜짐 여부와 최근 결정 10개(종류, 질문, 결과, 신뢰도, 비용, 지연, fallback 여부, 입력 해시)를 보여줍니다. 입력 원문은 보여주지 않습니다. 읽기 전용입니다. |
| `/init` | `CORA.md` 프로젝트 가이드 초안을 만듭니다. 기존 파일은 덮어쓰지 않습니다. |
| `/status` | 모델, 승인 모드, 세션, 비용, 작업 디렉터리를 보여줍니다. |
| `/theme` | 터미널 화면의 색 테마를 보거나 이 세션에서만 바꿉니다. 인자가 없으면 현재 테마와 목록을, `/theme <이름>`은 `default`, `dark`, `light`, `mono` 중 하나로 바꿉니다. 없는 이름이면 오류만 보여주고 테마는 그대로입니다. 설정 파일은 바꾸지 않으며 `/reset`도 테마를 되돌리지 않습니다. |
| `/expand` | 터미널 화면에서 접힌(10줄 초과) 마지막 도구 결과 전체를 보여줍니다. 접힌 결과가 없으면 안내만 보여줍니다. |
| `/mouse` | TUI에서 마우스 캡처를 켜고 끕니다 (`/mouse on`, `/mouse off`, 인자 없으면 전환). F2도 같습니다. |
| `/copy` | TUI에서 마지막 답변을 OSC 52로 클립보드에 복사합니다. |
| `/exit` | REPL을 끝냅니다. Ctrl-D와 같습니다. |
| `/quit` | REPL을 끝냅니다. |

### 세션 초기화 (`/reset`)

- 승인 모드는 시작 때의 값으로 정확히 돌아갑니다. 시작 값보다 느슨해지지 않습니다.
- `/model <tier>`로 저장한 모델 변경은 기본 `/reset`에서 유지됩니다. `/reset --all`만 `.cora/models.toml`을 삭제합니다.
- `--all`의 확인은 `[y/N]`입니다. `y`일 때만 삭제합니다. 입력이 없으면 취소됩니다. 스크립트 입력에서는 다음 줄이 답으로 읽힙니다.
- 다른 인자는 사용법 오류이며 아무것도 바꾸지 않습니다.
- 실제로 바뀐 항목만 출력합니다.
- `/clear`(대화 컨텍스트와 TODO만 비움)나 `/model reset`(저장된 티어 모델만 초기화)과 다릅니다.

### `@file` 멘션

- 입력의 맨 앞이나 공백 뒤에 있는 `@경로`만 파일 멘션으로 인식합니다. 예를 들어 `@README.md`는 파일을 첨부합니다.
- `\@`와 이메일 주소(예: `a@b.com`)의 `@`는 무시합니다.
- 파일은 작업 디렉터리 안에 있어야 합니다. 바깥 경로는 첨부되지 않습니다.
- 바이너리 파일과 없는 파일은 건너뜁니다.
- 크기 상한은 `[tools]`의 `mention_max_file_chars`(파일 하나), `mention_max_total_chars`(프롬프트 하나의 멘션 전체), `mention_max_dir_entries`(디렉터리 목록 항목 수)로 정합니다.
- 디렉터리를 멘션하면 그 디렉터리의 목록(listing)이 첨부됩니다.
- 첨부된 내용은 모델에게 전송됩니다. 비밀 값이 들어 있는 파일은 멘션하지 마세요.

### 도구 그룹 (`/tools`)

- 도구는 그룹으로 나뉩니다. `core`는 항상 켜져 있고(`list_files`, `read_file`, `search`, `edit_file`, `run_shell`), 나머지는 `git`, `web`, `plan-todo`, `delegate`입니다.
- `/tools`는 그룹 상태와 프롬프트 크기를 보여줍니다. `/tools report`는 크기 보고서를 보여줍니다.
- `/tools <group> on`, `/tools <group> off`는 이 세션에서만 그룹을 켜거나 끕니다. 설정 파일은 바뀌지 않습니다.
- `cora.toml`의 `[tool_groups] disabled`에 그룹 이름을 넣으면 시작할 때부터 꺼집니다.
- `[tool_groups] auto_simple = true`(기본값)이면 단순한 요청에는 core 도구만 보여줍니다. git 관련 단어, URL, `@` 멘션, `/plan` 같은 신호가 있을 때만 다른 그룹을 씁니다. `/delegate on`으로 위임을 켠 REPL 세션과, 위임을 켜고 시작한 `cora run`/`cora resume`/`--headless`/`cora project`/`cora mcp serve` 실행에서는 delegate 그룹이 항상 보입니다.

- 각 MCP 서버는 그룹 `mcp:<server>`를 가집니다. `/tools mcp:<server> on|off`로 이 세션에서 켜거나 끌 수 있고, `[tool_groups] disabled`에 `"mcp:<server>"`를 넣을 수도 있습니다. `auto_simple` 규칙은 MCP 그룹을 숨기지 않습니다. `/tools`는 서버가 시작된 뒤에야 그 서버의 크기를 보여줍니다.

### 센서 게이트, tripwire, `/check`

- `/check <명령>`으로 검사 명령을 정하면, 모델이 최종 답을 내기 전에 그 명령을 실행합니다. 검사가 실패하면 실패 출력의 끝부분을 모델에게 돌려주고 고쳐서 다시 답하게 합니다.
- 재검사는 `[agent] sensor_max_retries`(기본값 3)회까지 합니다. 그 안에 통과하지 못하면 결과를 그대로 전달합니다.
- `/check off`로 끕니다.
- tripwire는 같은 오류가 3번 반복되면 멈추거나 한 번 에스컬레이션합니다. `/check`를 설정하면 tripwire는 항상 켜집니다. `/check`를 쓰지 않을 때는 `[agent] tripwire = true`로 켤 수 있습니다(기본값은 `false`).
- `cora run --check "<명령>"`으로 한 번의 실행에 같은 검사를 걸 수 있습니다.

#### 자동 검사 (`auto_check`)

- `[agent] auto_check = true`(기본값 `false`)이면 `/check`나 `--check`가 없을 때 작업 workspace에서 검사 명령을 자동으로 찾습니다.
- 감지 순서는 `pytest` → `npm test` → `cargo test` → `go test ./...` → `make test`입니다. 처음 찾은 명령을 씁니다.
- 명시한 검사(`/check`, `--check`)는 항상 자동 감지보다 우선합니다.
- 감지 결과는 workspace 밖의 파일을 보지 않으며, 자격 증명 보호 규칙에 걸린 파일은 감지에 쓰지 않습니다. npm의 기본 `"no test specified"` 스크립트는 테스트가 없는 것으로 봅니다.

#### 테스트 변조 감지 (`tamper_guard`)

- `[agent] tamper_guard = true`(기본값 `false`)이면 검사 전후의 테스트 파일을 비교해 테스트를 고쳤거나 지웠는지 확인합니다. 결과는 `tests_modified`로 기록합니다.
- 감시하는 파일 이름 패턴은 `test_*.py`, `*_test.py`, `*_test.go`, `*.test.*`, `*.spec.*`입니다.
- 새 테스트 파일을 추가하는 것은 허용합니다. 기존 테스트 파일의 수정과 삭제는 횟수를 세어 보고합니다.
- 이 감시는 센서 게이트와 reflexion 검사 경로 모두에 적용됩니다.

#### 자기 점검 (`selftest`)

- `[agent] selftest = true`(기본값 `false`)이면 최종 답 뒤에 한 번 `python -m pytest -q .cora/selftest`를 실행합니다. Python 프로젝트에서만 동작합니다.
- 자기 점검 파일은 `.cora/selftest/` 아래에만 둡니다. 이 경로는 이번 실행에서 자기 점검이 켜진 동안에만 쓰기가 허용되며, `.cora/`의 나머지는 계속 쓰기 보호됩니다.
- 모델을 한 번 더 부르지 않습니다. 실패 출력은 세션의 작업 메모리에 들어가 다음 요청에서 보이고, `summary["selftest"]`와 `selftest` 이벤트에 기록합니다.
- 자기 점검이 실패해도 최종 답은 그대로 둡니다. 이것은 소프트 피드백입니다.

#### 재시도 사다리 (`ladder`)

- `[agent] ladder = true`(기본값 `false`)이면 검사 실패 순서가 다음과 같습니다. 먼저 `sensor_max_retries`만큼 재검사를 하고, 그래도 통과하지 못하면 반성(reflection) 한 번(5문장 이내, Lessons 형식), 그다음 검사 한 번을 더 합니다. 그 뒤에도 실패하면 `ladder_exhausted` 이벤트 한 번을 남기고 끝냅니다.
- `ladder = true`이면 `cora run --check`와 헤드리스 실행도 센서 게이트를 씁니다. 기본값(`false`)에서는 `cora run`과 헤드리스가 reflexion 경로를 씁니다.
- 실패 중심의 cheap에서 strong으로의 승격(에스컬레이션 캐스케이드)은 아래 `#### 에스컬레이션 캐스케이드 (\`[escalation]\`, M16)` 절을 보세요.

`auto_check`, `tamper_guard`, `selftest`, `ladder`는 모두 `[agent]` 테이블에 둡니다. 기본값은 모두 `false`입니다.

#### 에스컬레이션 캐스케이드 (`[escalation]`, M16)

- 설정은 `[escalation]` 테이블에 둡니다. 키와 기본값은 `enabled = false`, `on_stuck_iterations = 4`(0이면 끔), `on_tripwire = true`, `on_budget_fraction = 0`(0이면 끔), `strong_model = ""`(빈 값이면 라우터의 strong 티어, 아니면 `[[models]]`의 모델 id)입니다.
- 트리거는 다섯 가지입니다. `ladder_exhausted`는 `ladder = true`이고 검사가 있을 때만 일어납니다. `stuck`은 연속된 반복에서 `edit_file`, `write_file`, `delete_file`로 쓰기가 없고 처음 읽는 `read_file`도 없을 때입니다. `tripwire`는 같은 오류 반복 시 멈추는 대신 승격합니다. `budget_fraction`은 실행 비용 상한의 지정 비율을 쓰고도 통과한 검사가 없을 때입니다. `attempt`는 `[router] escalate_on_retry`에 따른 재시도 강제 strong입니다.
- 우선순위는 `ladder_exhausted` > `tripwire` > `stuck` > `budget_fraction`입니다. `enabled = true`일 때 실행당 한 번만 승격하며, 이 한 번은 트리거와 `attempt`를 가리지 않고 적용됩니다.
- strong 티어는 기본으로 DeepSeek V3.2이며, `strong_model`을 설정하면 그 모델을 씁니다.
- `ladder_exhausted` 뒤에는 strong 모델이 `sensor_max_retries + 1`회의 새 검사를 받습니다. 반성은 한 번만 합니다.
- 승격 뒤의 비용도 같은 실행 예산에서 셉니다.
- 승격하면 `escalate` 이벤트(필드 `trigger`, `model`, `tier`, `from_model`)를 남기고, `Session.escalation_trigger`를 기록하며, `summary["escalation"]`(`trigger`, `escalated`, `model`)에 넣습니다.
- `[router] mode = "heuristic" | "cheap_first"`입니다. `cheap_first`는 복잡도 등급과 결정기 티어 선택을 무시하고 처음부터 cheap으로 시작합니다. `enabled = false`에서는 실행 내내 cheap에 머물며, 이 조합에서는 `escalate_on_retry`와 tripwire 승격도 꺼집니다.
- 이 기능은 M16 A/B 결과(`.docs/bench-results.md`)를 기록하기 전까지 모두 기본 OFF입니다.
- 잘못된 값은 종료 코드 2로 끝납니다.

#### 호출 시간 제한 (`call_timeout_s`, M16c)

- `[agent] call_timeout_s`는 모델 호출 한 번이 기다릴 수 있는 최대 시간(초)입니다. 기본값은 `300`이고 허용 범위는 10-3600입니다. 범위 밖이거나 정수가 아니면 종료 코드 2로 끝납니다. 일부만 받은 뒤 멈춘 스트림도 이 시간에 포함됩니다.
- 시간을 넘기면 같은 호출을 한 번 더 시도합니다(`call_timeout` 이벤트). 두 번째도 넘기면 실행을 stop reason `provider_timeout`으로 멈추고 종료 코드 1로 끝냅니다. 이때 `provider_timeout` 이벤트(`model`, `timeout_s`, `attempts`)를 남기며, 세션은 저장됩니다.
- 한 번 넘겼어도 재시도가 성공하면 실행은 그대로 계속되며, `call_timeout` 이벤트만 남습니다.
- `[agent] max_wall_s`와의 관계: 각 대기 시간은 남은 벽시계 시간을 넘지 않습니다. 벽시계 상한에 먼저 닿으면 `provider_timeout`이 아니라 `budget_exceeded`(`budget_trip` 이벤트의 `cap = "wall"`)로 멈춥니다.
- 계획 생성(`cora project plan`)의 모델 호출도 같은 제한을 받습니다. 벤치(`cora bench --live`)도 같은 `[agent]` 설정을 거치므로 벤치에 따로 설정할 것은 없습니다.
- 위임(`/delegate`) 하위 에이전트의 호출도 같은 제한을 받습니다. 하위 에이전트가 시간 초과하면 실행을 멈추지 않고 도구 오류로 돌아갑니다.

#### 최종 답 게이트 (M16c)

- 키는 네 개입니다. `[agent] verify_before_final`(성공한 검사·실행 명령 없이 편집 뒤 최종 답을 거부), `compile_check`(편집한 Python 파일의 문법 오류를 `파일:줄`로 알림), `edge_case_prompt`(편집 뒤 빈 입력·경계값 점검을 요청), `stub_check`(본문이 스텁인 함수나 편집으로 사라진 정의를 거부)입니다. 네 키의 기본값은 모두 `true`입니다(M16d 판정 PASS, 2026-10-17). 끄려면 `false`로 설정합니다. `true`/`false`가 아닌 값이나 알 수 없는 `[agent]` 키는 종료 코드 2입니다. 네 키가 모두 `false`이면 프롬프트와 동작은 이전과 같습니다.
- 각 장치는 실행당 최종 답을 최대 한 번만 거부합니다. 같은 장치는 두 번째 최종 답부터 통과시킵니다.
- 거부하면 `gate_feedback` 이벤트를 남깁니다. 필드는 `mechanism`(키 이름), `stage`(`final`은 최종 답 거부, `edit`는 편집 직후 문법 알림), `iteration`, 그리고 위치 목록 `items`(있을 때)입니다. `stage = "edit"` 알림은 거부가 아니므로 편집마다 나올 수 있으며, 최종 답 거부 한도는 `stage = "final"`에만 적용됩니다.
- "성공한 검사·실행 명령"은 `run_shell` 호출이 종료 코드 0으로 끝났고, 명령의 첫 토큰(앞의 `NAME=value` 환경 변수 제외)이 `ls`, `cat`, `grep`, `git`, `echo` 같은 읽기 전용 명령이 아니며, 마지막으로 성공한 `write_file`/`edit_file`/`delete_file` 뒤에 실행된 것입니다.
- `stub_check`는 본문이 `pass`, `...`, `raise NotImplementedError`(호출 포함) 하나뿐인 함수를 스텁으로 봅니다. `@abstractmethod`, `@overload` 함수와 `Protocol` 클래스 안의 함수는 제외합니다.
- 계획 모드에서는 게이트를 쓰지 않습니다. 반복 한도(`max_iterations`)에 이미 닿았다면 거부하지 않으므로 게이트 때문에 `max_iterations` 중단이 생기지 않습니다.
- 게이트 상태(거부 여부, 편집 기록)는 저장하지 않습니다. 그래서 `cora resume`은 게이트를 처음부터 다시 쓰며, 재개 뒤 한 번 더 거부할 수 있습니다.

#### 입력 복구와 덮어쓰기 보호 (M16d)

- `json_string_repair` (기본값 `true`, 끄려면 `false`): lenient 파싱(`lenient_parse = true`, 기본값)에서 Action Input JSON 문자열 안의 날 제어 문자를 escape하고 잘못된 백슬래시 escape를 문자 그대로의 백슬래시로 바꿔 다시 해석합니다. 복구되면 `parse_repaired` 이벤트의 `repairs`에 `json_strings`가 들어갑니다. 출력 한도에서 잘린 응답은 복구하지 않습니다. 거부가 아니므로 횟수 제한이 없습니다.
- `overwrite_guard` (기본값 `true`, 끄려면 `false`): 실행 시작 시 있던 Python 파일 중 스텁이 아닌 함수가 하나라도 있는 파일을, 이번 실행에서 읽지 않은 채 `write_file`(append 아님)로 덮어쓰려 하면 실행당 한 번 거부하고 현재 내용(최대 60줄)을 보여 줍니다. 같은 호출을 다시 보내면 쓰입니다. `overwrite_refused` 이벤트(`mechanism`, `path`, `iteration`)를 남깁니다.
- 두 키는 `true`/`false`만 허용하며, 다른 값은 종료 코드 2입니다. 둘 다 `false`이면 프롬프트와 동작은 이전과 같습니다.

#### 원문 쓰기 채널, 반복 차단, 위치 있는 오류 (M17b)

- 키는 `[agent]`에 세 개 있으며 기본값은 모두 `false`입니다: `raw_file_body`, `repeat_breaker`, `located_errors`. `true`/`false`가 아닌 값이나 알 수 없는 키는 종료 코드 2입니다. 셋 다 `false`이면 프롬프트, 파서, 도구 결과는 이전과 같습니다.
- `raw_file_body = true` (원문 블록): `write_file`과 `edit_file`에서 JSON 이스케이프 없이 원문을 씁니다. 이 구문은 두 도구 전용이며, 힌트는 키가 `true`이고 react 프로토콜일 때만 보입니다.
  - `write_file`: `Action Input: {"path": "x.py"}` 줄 다음에 `<<<CONTENT`를 단독 줄로 쓰고, 본문을 쓴 뒤 `CONTENT>>>`를 단독 줄로 씁니다.
  - `edit_file`: `Action Input: {"path": "x.py"}` 다음에 `<<<OLD`, 바꿀 원문, `OLD>>>`, `<<<NEW`, 새 원문, `NEW>>>` 순서로 씁니다. 마커는 각각 한 줄을 차지해야 합니다.
  - 본문은 마커 사이 줄들을 `\n`으로 이어 붙인 값입니다. 따라서 본문의 끝 개행은 마커 바로 앞에 빈 줄 하나로 표현합니다.
  - 닫기와 본문 규칙은 응답을 위에서 아래로 한 줄씩 읽는 상태 기계 하나가 정하며, 아래 표가 규칙의 전부입니다(코드 `core/react.py`의 `RAW_RULES` 등을 그대로 옮긴 것이며 테스트가 대조합니다). 요점: 블록 본문에는 마커만 있는 줄(`>>>`, `<<<CONTENT`, `CONTENT>>>`, `<<<OLD`, `OLD>>>`, `<<<NEW`, `NEW>>>`)이나 줄 맨 앞이 `Thought:`, `Action:`, `Action Input:`, `Final Answer:`, `Observation:`인 줄을 넣을 수 없습니다. 그런 내용이 있는 파일은 원문 블록 대신 JSON 문자열로 보냅니다. 정확한 닫기(`라벨>>>`, 예: `CONTENT>>>`)는 언제나 블록을 끝내고, `>>>`나 `<<<라벨`로 닫으면 바로 다음 줄이 응답이 다음으로 넘어갔음을 보여 줄 때만 닫기로 인정합니다. 첫 블록이 열린 뒤 블록 밖에 남은 마커 줄과, 출력 한도에서 잘린 응답 안의 블록은 오류입니다. 이 규칙은 이전보다 엄격하며, 오류가 나면 해당 파일을 JSON 문자열로 다시 보내면 됩니다. 블록은 여는 줄 앞의 마지막 `Action:` 줄의 호출에 붙습니다. 마지막 블록의 호출까지 `Action:`은 모두 줄 맨 앞에만 있어야 하며, 그 앞의 산문이나 `Thought:` 줄 안에 `Action: 이름`이 있으면(예: `Sure, calling Action: foo now.`) 어느 호출의 블록인지 정할 수 없으므로 어떤 도구도 실행하지 않고 오류를 돌려줍니다. CRLF 줄바꿈 응답이면 본문 줄 사이의 CRLF는 그대로 쓰고, 닫는 줄 바로 앞 줄바꿈의 CR은 본문에 넣지 않습니다. 마커 줄은 앞뒤 공백을 무시하고 비교합니다.

| state | line | action |
|---|---|---|
| text | observation | stop |
| text | opener | open |
| text | marker | keep |
| text | header | keep |
| text | other | keep |
| text | end | done |
| text | end_cut | done |
| block | close | close |
| block | weak | weak |
| block | observation | unclosed |
| block | marker | unclosed |
| block | header | unclosed |
| block | other | body |
| block | end | unclosed |
| block | end_cut | unclosed |
| after | observation | stop |
| after | opener | open |
| after | marker | stray |
| after | header | keep |
| after | other | keep |
| after | end | done |
| after | end_cut | unclosed |
- state `text`: no raw block has opened yet in this reply
- state `block`: inside a raw block
- state `after`: outside any raw block, after one has opened
- line `observation`: a line (not the first) starting with Observation:
- line `close`: in a block: exactly LABEL>>> for the open block's LABEL
- line `weak`: in a block: exactly >>> or <<<LABEL for the open block's LABEL
- line `opener`: outside a block: exactly <<<LABEL for a LABEL of the last Action (write_file: CONTENT; edit_file: OLD, NEW) after its Action Input: line
- line `marker`: any other line that is exactly one of >>>, <<<CONTENT, CONTENT>>>, <<<OLD, OLD>>>, <<<NEW, NEW>>>
- line `header`: a line starting with Thought:, Action:, Action Input: or Final Answer:
- line `other`: any other line, blank lines included
- line `end`: the end of the reply
- line `end_cut`: the end of a reply cut at the output token limit
- action `keep`: the line stays ReAct text
- action `stop`: the turn ends here; later lines are ignored and the end rule applies
- action `open`: a block starts; the same field given twice is an error
- action `body`: the line is block text
- action `close`: the block ends; its text is the lines between the opener and this line
- action `weak`: the block ends here only if the weak-close rule holds, else error RAW_UNCLOSED_ERROR
- action `stray`: error RAW_STRAY_ERROR
- action `unclosed`: error RAW_UNCLOSED_ERROR
- action `done`: parsing ends
- weak close: skip blank lines and lines that are exactly >>> or <<<LABEL; the block ends at the weak line only if the next line is one of:
- weak close: the end of the reply;
- weak close: a line starting with Action: or Final Answer:;
- weak close: a line that is exactly <<<OTHER for another LABEL of the same Action (OLD, then NEW);
- weak close: a line starting with Thought: whose next non-blank line starts with Action: or Final Answer:.
- attach: marker lines are compared after removing whitespace at both ends
- attach: a block belongs to the last Action: before its opener; every Action: up to the last block's Action must start its own line, before and after lenient repair, else error RAW_ACTION_ERROR
- attach: a block's text keeps its own line breaks; one CR left at its end by a CRLF line break is dropped

  - 닫히지 않은 블록의 오류는 정확한 닫기 철자(예: `CONTENT>>>`)와, 응답에서 마커처럼 보인 줄(최대 5개, 줄당 60자)을 보여 줍니다. 블록 밖 마커 줄 오류(`RAW_STRAY_ERROR`)도 같은 목록을 보여 주며, 두 오류 모두 본문에 넣을 수 없는 줄을 알려 줍니다.
  - JSON 문자열의 `content`(`write_file`)나 `new`(`edit_file`)가 마커 줄(첫 줄 `<<<CONTENT`/`<<<NEW`, 끝 줄 `CONTENT>>>`/`NEW>>>`/`>>>`)로 시작하거나 끝나면 쓰기를 거절하고, 원문 블록으로 보내라고 안내합니다. 이 거절은 react 프로토콜에서만 나옵니다(native에서는 나오지 않습니다).
  - 같은 블록을 두 번 지정하면 오류입니다. 원문 블록이 있는 응답이 출력 한도에서 잘렸으면 블록이 닫혔든 아니든 오류이며 잘림 안내를 줍니다. 블록의 호출을 정할 수 없을 때의 오류도 블록 마커 줄 목록을 함께 보여 줍니다.
- `repeat_breaker = true` (반복 차단): 같은 응답이나 같은 실패가 연속으로 나오는 것을 감지합니다.
  - 연속 2회째에는 피드백 문구를 한 번 붙입니다.
  - 연속 3회째 이상이면 다음 모델 호출 한 번만 `temperature` 0.7로 보냅니다. 그 다음 호출은 다시 0.0입니다. 연속이 이어지면 회차마다 같은 방식으로 한 번씩 올리며, 연속이 끊기면 0.0입니다.
  - 감지 결과는 `repeat_detected` 이벤트(`iteration`, `kind`, `count`)로 남습니다. `kind` 값은 `same_reply`, `parse_error`, `edit_mismatch` 중 하나입니다.
  - 실행을 멈추지 않으며, tripwire, 에스컬레이션, 예산 상한의 동작은 바뀌지 않습니다. ReAct 루프에서만 동작합니다.
  - 녹화/재생 키에는 `temperature`가 들어가지만, 상승 값은 앞의 녹화된 응답만으로 정해지므로 이 키를 켜고 녹화한 실행은 그대로 재생됩니다. 키를 끈 상태로 녹화한 응답을 키를 켠 상태로 재생하면 피드백 문구가 달라져 `ReplayMissError`(종료 코드 2)가 나며, 다시 녹화해야 합니다.
- `located_errors = true` (위치 있는 오류): 오류 메시지에 위치 정보를 더합니다.
  - Action Input JSON 오류(`INPUT_ERROR`): JSON 디코더 메시지, JSON 객체 기준 문자 오프셋, 60자 이하 발췌, 이스케이프 힌트를 보여 줍니다.
  - `edit_file`의 `old` 찾기 실패(`old-not-found`): 가장 가까운 줄, 첫 불일치 줄과 열, 주변 3줄 이하를 보여 줍니다.
  - 출력 한도에서 잘린 응답(react): 잘림 안내에 "Send one Action per reply and do not repeat the same file body within a reply." 문구(한 응답에 Action 하나만 보내라는 뜻)를 붙이고, 잘림의 원인이 된 Action Input 오류 위치(첫 줄, 예: `character N`)를 덧붙입니다.
  - 보호되거나 자격 증명이 있는 파일은 발췌를 보여 주지 않습니다.

### 위임 (`/delegate`)

- 실험적(experimental) 기능이며 기본값은 꺼짐입니다. M3 A/B에서는 6개 과제 × 3개 구성 모두 시작된 하위 에이전트가 0건이었지만, 과제가 작고(파일 9개, 약 1,000자) 위임을 권하는 문구(nudge)가 없었으며 위임 시도 횟수를 세지 않았습니다. 그래서 이 결과는 위임의 효과를 측정한 것이 아닙니다. M19에서 탐색 과제로 한 번 다시 측정합니다(위임 켬 + nudge 대 위임 끔).
- 하위 에이전트 위임은 기본적으로 꺼져 있습니다. 우선순위는 `/delegate` > `--delegate` > 설정 파일(`[delegation] enabled`) > 기본값(꺼짐)입니다.
- `/delegate on`과 `/delegate off`는 이 REPL 세션에만 적용됩니다. `/delegate on`은 세션 동안 delegate 도구 그룹을 항상 보이게 강제하므로, `[tool_groups] auto_simple = true`이어도 단순한 요청에서 위임 도구가 숨겨지지 않습니다. `/delegate off`는 이 강제를 풀고 원래 규칙으로 돌아갑니다. `/tools delegate off`로 끈 그룹은 계속 꺼져 있습니다. `/delegate`만 입력하면 현재 상태와 출처(source)를 보여줍니다. `--delegate`나 `[delegation] enabled = true`로 위임을 켜고 시작한 `cora run`, `cora resume`, `--headless` 실행, `cora project`, `cora mcp serve`에서도 delegate 그룹이 항상 보입니다. REPL에서는 `/delegate on`일 때만 강제합니다.
- `/reset`은 위임 설정을 시작 값으로 되돌리고 새 세션을 시작합니다. 세션 위임 카운터도 새 세션에서 다시 셉니다.
- `mode: "explore"`는 읽기 전용 하위 에이전트입니다(`list_files`, `read_file`, `search`, git 조회 `git_status`, `git_diff`, `git_log`). 한 응답에 여러 개를 요청하면 병렬로 실행됩니다. `mode: "general"`(기본값)은 편집할 수 있으며 단독으로 실행됩니다. 계획 모드(`/plan`)에서는 general 위임이 거부되고 explore만 실행됩니다.
- `[delegation]`의 병렬 explore 키와 기본값은 `parallel_explore = true`, `explore_concurrency = 3`, `explore_max_calls = 6`, `max_total_tokens = 120000`, `max_total_cost_usd = 0.05`, `summary_max_chars = 1200`입니다.
- `[delegation] nudge = false`(기본값): M19 재측정용 실험 설정입니다. `true`이고 delegate 도구가 보일 때만 메인 에이전트의 시스템 프롬프트 끝에 "여러 파일에 흩어진 정보는 `delegate`(mode `"explore"`)로 나눠 찾으라"는 한 문장(`DELEGATE_NUDGE`)을 붙입니다. 하위 에이전트 프롬프트에는 붙이지 않습니다. true/false가 아닌 값이나 알 수 없는 `[delegation]` 키는 종료 코드 2입니다.
- `/cost`에 `delegated detail` 줄이 나타납니다. 호출 수, 성공·실패·거부 횟수, wall_s, busy_s, max_fanout을 보여줍니다. `avoided_tokens_est`는 하위 에이전트의 도구 결과를 메인 컨텍스트에 넣지 않아 줄인 토큰 수의 추정치(estimate)입니다.
- `attempts`는 메인 에이전트가 보낸 `delegate` 호출 수입니다(정책 거부, 입력 오류, 상한 거부 포함). `attempts_unparsed`는 파싱에 실패했지만 `Action: delegate` 줄이 있던 응답 수이며 `attempts`에도 들어갑니다. 위임이 꺼져 있으면 세지 않습니다. native 프로토콜에서 인자를 해석하지 못한 `delegate` 호출은 실행되지 않으므로 세지 않습니다. 두 값은 `session.json`의 `delegation_stats`와 `delegated detail` 줄에 나옵니다.
- 벤치 결과의 `deleg_calls` 열은 시작된 하위 에이전트 수(`deleg_invocations`)이고, 바로 옆 `deleg_attempts` 열은 위임 시도 수입니다. JSON 결과에는 `deleg_attempts_unparsed`도 들어갑니다.

### 모델 전환 (`/model`)

- `/model`만 입력하면 티어별 모델을 대화형으로 보고 바꿀 수 있습니다.
- `/model cheap <모델 ID> [IN,OUT]` 또는 `/model strong <모델 ID> [IN,OUT]`는 티어 모델을 바꾸고 `.cora/models.toml`에 저장합니다. `IN,OUT`은 100만 토큰당 USD 가격입니다. `cora.toml`은 바뀌지 않습니다. `.cora/models.toml`은 커밋하지 마세요.
- `/model reset [티어]`는 저장된 티어 설정을 지우고 설정 파일의 기본값으로 되돌립니다. 티어를 생략하면 모든 티어가 대상입니다.
- `/model pin <모델 ID> [IN,OUT]`은 이 세션에서만 모든 요청에 그 모델을 씁니다. 라우팅은 쓰지 않습니다.
- `/model unpin`은 고정을 풀고 요청마다 라우팅으로 모델을 고르게 합니다.
- `/route`는 마지막 라우팅 결정을 보여줍니다.
- `/approval`은 승인 모드를 보여주거나 바꿉니다. `ask`는 도구를 실행하기 전에 묻고, `auto`는 묻지 않고 허용하며, `deny`는 승인이 필요한 도구를 거부합니다. `policy`는 정책으로 결정하고 묻지 않습니다(자율 승인 정책 섹션을 보세요). `ask`에서 "이 세션 동안 항상 허용"을 고르면 같은 종류의 요청은 그 세션 안에서 다시 묻지 않습니다.
- `/plan`은 계획 모드를 켭니다. 읽기 전용 도구만 쓰고, 모델이 제출한 계획을 승인하면 실행합니다. `/plan off`로 끕니다.

### 제공자별 모델 항목과 비용 출처 (`id@provider`, `cost_model`)

- 같은 `id`를 여러 `[[models]]` 항목에 `provider`와 가격을 다르게 적을 수 있습니다. 예를 들어 같은 모델을 두 제공자에서 따로 계량할 수 있습니다.

```toml
[[models]]
id = "vendor/m"
provider = "provider_a"
tier = "cheap"
price_in_per_mtok = 1.0
price_out_per_mtok = 2.0

[[models]]
id = "vendor/m"
provider = "provider_b"
tier = "strong"
price_in_per_mtok = 3.0
price_out_per_mtok = 4.0
```

- `(id, provider)` 쌍이 같은 항목이 두 번 나오면 설정 오류이며 종료 코드는 2입니다.
- 모델 참조는 `id@provider` 형식을 씁니다. `/model`, `/model pin`, `.cora/models.toml`, `[decider].model`, `--model`에서 쓸 수 있습니다. `@`가 들어간 정확한 `id`가 있으면 그것을 먼저 씁니다.
- `id`만 쓰면 설정 순서에서 그 `id`가 처음 나오는 항목을 고릅니다.
- `cost_model`은 `"catalog"`(기본값) 또는 `"self_hosted"`입니다. `catalog`는 `cora.toml`의 가격으로 비용을 추정합니다. `self_hosted`는 자체 호스팅 모델로, 비용을 0으로 보지 않고 따로 보고합니다. 이 비용은 `total_estimated_cost_usd`, JSON `cost_usd`, `max_cost_usd` 예산, 기준선 비교에서 빠집니다.
- 호출마다 `provider`, `cost_source`, `latency_s`가 기록됩니다. `cost_source` 값은 `provider_usage`(제공자가 비용을 보고함), `catalog:<id>@<provider>`(설정 가격으로 추정함), `self_hosted`, `unpriced`(가격을 모름)입니다. 이 기능이 생기기 전 세션의 기록은 `legacy`로 읽습니다.
- 요약에는 `by_model_provider`(제공자별 묶음과 `p50_latency_s`)와 `self_hosted_cost_usd`가 추가됩니다.
- 텍스트 요약에는 여러 제공자가 있거나 `catalog`가 아닌 출처가 있을 때만 `profile <id>@<provider>:` 줄이 나옵니다. 단일 제공자 카탈로그 실행의 출력은 예전과 같습니다.

### OpenAI 호환 제공자와 Gemini 무료 티어 (`type = "openai_compat"`)

- `[providers.<name>]` 섹션에 `type = "openai_compat"`을 적으면 OpenAI 호환 채팅 API를 씁니다. `type`이 없으면 섹션 이름으로 제공자를 고릅니다. 이름이 `openrouter`이면 기존 OpenRouter 제공자입니다.
- `base_url`과 `api_key_env`는 필수입니다. 하나라도 없으면 설정 오류이며 종료 코드는 2입니다. `api_key_env`에는 키를 담은 환경 변수 이름을 적습니다.
- 선택 항목은 `timeout_s`, `request_deadline_s`, `stream_stall_timeout_s`, `rpm_limit`, `max_429_retries`입니다. `rpm_limit`은 분당 요청 수 한도이며 요청 간격을 `60/rpm_limit`초로 맞춥니다. 적지 않으면 간격 조절을 끕니다. `max_429_retries`의 기본값은 4입니다.
- 429 응답은 `Retry-After`의 초 값이나 HTTP 날짜를 따릅니다. `Retry-After`가 120초를 넘으면 기다리지 않고 바로 멈춥니다. 그 밖의 경우에는 1, 2, 4, 8초를 기다린 뒤 다시 요청합니다. 429마다 `rate_limited` 이벤트가 기록됩니다. 재시도를 다 쓰면 `rate limited` 오류로 끝나며 종료 코드는 1입니다.
- `extra_content`는 항상 다음 요청에 그대로 다시 보냅니다.
- 스트리밍 사용량은 `include_usage`로 받습니다. 사용량이 오지 않으면 토큰 수는 0으로 기록하고 `cost_source`는 `unpriced`입니다.
- `[[models]]` 항목에 `free_tier = true`를 적으면 비용은 0이고 `cost_source`는 `free_tier`입니다. 이 호출은 비용 상한에 잡히지 않습니다. 다른 상한(호출 횟수 등)은 그대로 적용됩니다.
- 기본 `cora.toml`에 들어 있는 `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-3.5-flash` 항목은 기본 모델이 아닙니다. 쓰려면 `[router] pin = "gemini-3.5-flash-lite"`로 고정하거나 기존 `/model` 명령으로 고릅니다.
- 키는 `export GEMINI_API_KEY=...`처럼 환경 변수로만 줍니다. 설정 파일에는 키를 쓰지 않습니다.
- 제공자 객체는 필요할 때 만듭니다. `GEMINI_API_KEY`가 없어도 Gemini 모델을 고르지 않은 실행은 그대로 동작합니다. Gemini 모델을 고른 실행만 종료 코드 2로 끝나며, 메시지에 환경 변수 이름이 나옵니다.
- 이 제공자는 계정 상태 조회를 지원하지 않습니다. 사전 점검(preflight)에는 `account check not available` 줄이 나오고 조회는 건너뜁니다.

### 모델 응답 녹화와 재생 (`[record]`)

- `[record]` 섹션의 `mode`는 `off`(기본값), `record`, `replay` 중 하나입니다. `record`는 실제 제공자를 호출하고 응답을 파일로 저장합니다. `replay`는 저장된 응답을 돌려주며 네트워크를 쓰지 않고 제공자 객체도 만들지 않습니다.
- `dir`은 저장 위치이며 기본값은 `.cora/recordings`입니다. 상대 경로는 실행의 작업 공간(`-w`)을 기준으로 풉니다.
- 환경 변수 `CORA_RECORD_MODE`와 `CORA_RECORD_DIR`가 설정 파일보다 우선합니다. `CORA_RECORD_MODE`에 잘못된 값을 주면 설정 오류이며 종료 코드는 2입니다.
- 키는 모델, 메시지, 도구, `temperature`, `max_tokens`, `stop`을 정규화한 뒤 sha256으로 만듭니다. 작업 공간 경로는 `<WS>`, 홈 디렉터리는 `<HOME>`, 타임스탬프는 `<TS>`로 바꾸므로 다른 디렉터리나 다른 시각에 실행해도 같은 키가 됩니다. `response_format`과 `cache_prefix`는 키에 들어가지 않습니다.
- 재생할 때 저장된 키가 없으면 `ReplayMissError`가 나오며 종료 코드는 2입니다. 네트워크로 대신 호출하지 않으며, 재생에는 API 키도 필요 없습니다. 오류 메시지에는 모델 ID, 키, 기대 경로가 나오고, 요청이 바뀌었다면 `CORA_RECORD_MODE=record`로 다시 녹화하라는 안내가 나옵니다.
- 스트리밍 제공자를 재생하면 응답 전체가 한 번의 청크로 답변 델타 콜백에 전달됩니다.
- 재생된 호출의 비용 출처에는 `+replay`가 붙습니다(예: `free_tier+replay`). 비용 값은 녹화 시점과 같고, 프로필의 `cost_source`에도 `+replay`가 그대로 보입니다.
- 저장되는 것은 요청과 응답 본문뿐입니다. 헤더, 환경 변수, 설정은 저장하지 않습니다. 응답과 요청에 든 API 키 형태의 문자열(`AIza...`, `sk-...`, 길이 8 이상인 키 환경 변수의 값)은 `[REDACTED]`로 바꿉니다.
- 고정 테스트 자료는 `tests/fixtures/recordings/<name>/`에 둡니다. 가짜 제공자(`scripted`, `scripted_stream`, `fixed_usage`)나 무료 티어 모델의 기록만 커밋합니다. `tests/test_record_fixtures.py`가 키 형태와 금지된 문구를 검사합니다.
- M14부터 상한이 있는 cheap 모델 `google/gemini-2.5-flash-lite`의 실측 기록도 받아들입니다(허용 목록에 한 개만 있음). 다른 유료 모델의 기록은 여전히 막습니다. 비밀 문자열 스캔과 키 형태 검사는 바뀌지 않습니다.
- 프롬프트를 바꾼 뒤에는 재녹화합니다. 해당 녹화 디렉터리를 지우고 `CORA_RECORD_MODE=record`로 다시 실행합니다(재녹화).
- 한계: 같은 요청을 다시 녹화하면 마지막 응답만 남습니다. 에이전트 루프 밖의 계획기(planner)와 결정기(decider) 호출은 작업 공간 경로를 정규화하지 않아 홈 경로와 타임스탬프만 정규화되며, `dir`의 상대 경로는 현재 디렉터리를 기준으로 풉니다.

### 결정기 (`/decider`)

- `cora.toml`의 `[decider]`는 기본값이 `kind = "heuristic"`, `model = "cheap"`, `timeout_s = 5`, `max_cost_per_decision = 0.001`, `min_confidence = 0.7`입니다. 사용처 `tier_routing`, `toolgroup`, `sensor_hint`는 모두 `false`입니다. 각 키의 뜻은 `cora.toml`의 주석과 같습니다.
- 모든 사용처는 기본적으로 꺼져 있습니다. `heuristic`은 키워드 규칙을 그대로 쓰므로 비용이 없습니다.
- 우선순위는 `/model pin`으로 고정한 모델, 재시도 때 강제되는 strong, 신뢰할 만한 결정기 답, 휴리스틱 순입니다. tripwire의 한 번 에스컬레이션은 그대로 유지됩니다.
- 신뢰도가 `min_confidence`보다 낮은 답이나 실패(시간 초과, 예산, `max_cost_per_decision` 초과, JSON 오류, 스키마 위반, 빈 응답, 제공자 오류)가 나면 휴리스틱 답으로 대신합니다.
- 센서 힌트(`sensor_hint`)는 이벤트 기록만 남기며, 검사, 게이트, tripwire 결과를 바꾸지 않습니다.
- `kind = "llm"`이면 호출은 기존 OpenRouter 제공자를 거치며, 용도 `decide`로 계량되고 비용에 포함됩니다.
- `cora run`의 요약에는 `decider:` 줄이 나타납니다.
- `/decider`는 종류, 모델, 사용처 상태와 최근 결정을 보여줍니다. 입력 원문은 보여주지 않습니다.

## 벤치

- `cora bench`(`--live` 없이)는 내장 작업 3개를 설정된 제공자(provider)를 통해 실행합니다. 기본 `cora.toml`을 쓰면 OpenRouter에 실제 유료 호출이 발생하므로 오프라인 실행이 아닙니다. 결과는 표로 출력됩니다.
- `cora bench --live`는 실제 OpenRouter 호출로 모델과 프로토콜을 조합해 작업을 돌립니다. 비용이 듭니다.
  - `OPENROUTER_API_KEY` 환경 변수가 필요합니다.
  - 전체 상한은 기본 USD 0.30이고, `--max-cost`로 바꿔도 USD 0.50을 넘을 수 없습니다.
  - 작업 하나의 상한은 기본적으로 전체 상한의 10분의 1입니다.
  - 보고서는 `report.json`과 `report.md`로 `--out` 디렉터리에 저장됩니다.
  - 첫 셀 전에 사전 점검(preflight)을 합니다. 실행에 쓰이는 모델들의 제공자(provider)마다 계정 상태를 한 번씩 조회합니다(제공자가 선택적으로 구현하는 `account_status` 기능). 이 기능이 없는 제공자는 `preflight: account check not available for <provider>: skipped` 한 줄을 출력하고 계속합니다. 검사가 빠졌다는 것을 알 수 있도록 이 줄은 항상 보입니다. 실행에 쓰이지 않는 제공자는 조회하지도 출력하지도 않습니다. 조회가 실패하거나 40초 안에 끝나지 않으면 `preflight: account check for <provider> failed (...)` 또는 `timed out` 알림만 출력하고 계속합니다. 어느 제공자든 키가 만료되었거나, 키 한도(`limit_remaining`)가 이번 실행의 `--max-cost`보다 작거나, 조회가 HTTP 401, 402, 403으로 거절되면 실행을 시작하지 않고 종료 코드 2로 끝납니다. 거절 안내는 그 제공자가 등록한 문구를 쓰고, 안내를 등록하지 않은 제공자는 제공자 이름과 HTTP 상태만 담은 일반 문구를 씁니다. 잔액이 0 이하이면 경고만 출력하고 계속합니다.
  - OpenRouter 제공자는 `https://openrouter.ai/api/v1/auth/key`로 키 상태를 조회합니다. 한도가 없거나 확인할 수 없으면 알림만 출력하고 계속합니다. 계정 잔액은 `https://openrouter.ai/api/v1/credits`로 조회해 `total_credits - total_usage`로 계산해 보여 줍니다. 잔액이 0 이하이면 유료 모델 요청이 HTTP 402로 거절될 수 있다는 `WARNING` 경고와 크레딧 URL(`https://openrouter.ai/settings/credits`), 크레딧 구매 또는 auto top-up 안내를 출력하지만 실행은 막지 않습니다(`--ab` 포함). 잔액 조회가 실패하면(시간 초과, 네트워크 오류, 비정상 상태, 해석할 수 없는 응답, 필드 누락) 경고 없이 계속합니다. 키 한도(`limit_remaining`)는 키에 걸린 지출 상한일 뿐 계정 잔액이 아니므로 잔액 판단에 쓰지 않습니다.
  - 실행 중 제공자가 HTTP 401, 402, 403을 응답하면 그 뒤의 호출을 멈추고 실행을 중단합니다. 남은 셀은 `not_run` 상태로 보고서에 남습니다. 부분 보고서를 저장한 뒤 종료 코드 3으로 끝나며, `report.json`의 `aborted`와 `cells`, `report.md`의 `aborted:`와 `cells:` 줄에서 확인할 수 있습니다. 중단 메시지에는 위의 계정 오류 안내가 함께 출력됩니다.
  - 중단이 일어나면 이미 진행 중이던 병렬 explore 호출은 끝까지 기다리고, 그 뒤의 새 호출은 위임 하위 에이전트의 호출까지 모두 막습니다.
  - 셀의 `latency_s`는 그 셀 전체의 벽시계 시간입니다. 재시도, 백오프 대기, 사전 점검, 컴퓨터가 잠들어 있던 시간을 모두 포함합니다. `wall_s`는 실행 전체의 벽시계 시간이며 셀 지연의 합보다 작지 않습니다.
  - 보고서에는 호출별 지연 시간 표(`### Call latency`)가 들어갑니다. 구성별과 셀별로 호출 수, p50, max를 적습니다. `[bench] stall_threshold_s`(기본 60초)보다 오래 걸린 호출은 `stalled_calls`로 세고, 그 셀은 `STALL`로 표시합니다.
  - API 키는 표준 출력, 표준 오류, 보고서, 오류 메시지 어디에도 출력되지 않습니다.
- 기준선 파일(예: `baseline.toml`)은 `--baseline`으로 넘깁니다. 형식은 `--live` 여부에 따라 다릅니다.

`--live` 없이 쓰는 형식은 `[baseline]` 테이블에 작업 이름과 USD 값을 적습니다.

```toml
[baseline]
fix_add = 0.05
```

`--live`와 함께 쓰는 형식은 선택 사항인 `[meta] source`와 작업별 `[tasks.<task_id>]` 테이블을 씁니다. 각 테이블에는 `cost_usd`(0 이상의 숫자)와 `success`(참 또는 거짓)가 필요합니다.

```toml
[meta]
source = "기준선을 얻은 방법에 대한 설명"

[tasks.fix_add]
cost_usd = 0.04
success = true
```

### A/B 비교와 티어 (`--ab`)

- `cora bench --live --ab`는 모델 하나와 프로토콜 하나로 구성(arm)들을 같은 작업에 비교합니다. 구성은 `deleg-off`(위임 끔, cheap 모델 고정), `deleg-on-par-off`(위임 켬, explore 병렬 끔), `deleg-on-par-on`(위임 켬, explore 병렬 켬), `strong-only`(strong 티어 모델 고정), `auto-routed`(라우팅, 벤치 모델이 cheap 티어가 되도록 카탈로그 순서를 맞춤)입니다. 위임과 모델을 섞은 조합은 실행하지 않습니다.
- `--ab`의 기본 작업은 다중 파일 과제 6개입니다. `query_client_timeout`, `query_total_backoff`, `query_env_override`(질의 3개)와 `multi_edit_delay_cap`, `multi_edit_rename_cents`, `multi_edit_region`(편집 3개)이며 `--tasks`로 고를 수 있습니다. `--ab`를 쓰지 않는 `--live` 실행의 기본 작업은 바뀌지 않습니다.
- 보고서(`report.md`)에는 구성별 표가 나옵니다. 시도, 해결, 비용, 해결당 비용, `resolved_per_dollar`(해결 수 ÷ 총 비용), 벽시계 시간과 위임 호출 통계가 들어갑니다. 작업을 난이도 구간(easy 2분 이하, medium 10분 이하, hard 10분 초과, 작성자 추정)별로 나눈 표와 작업별 모델 티어 표(cheap-only, strong-only, auto-routed, 자동 라우팅 티어와 플래그)도 나옵니다.
- `avoided_tokens_est`는 추정치입니다. 위임 하위 에이전트의 도구 결과 토큰에서 메인 에이전트로 돌아온 요약 토큰을 뺀 값이며 실제 절감량이 아닙니다. 각 구성은 작업당 한 번만 시도하므로 결과는 방향성만 보여 줍니다.

### 검증 재시도 (`--verify-attempts`)

- 뜻: 이 옵션을 주면 실행마다 `auto_check = true`이고 `max_attempts = N`입니다. 최종 답 뒤에 workspace의 공개 검사를 돌리고, 실패하면 `reflection`(반성) 1건을 남긴 뒤 같은 workspace에서 교훈을 가지고 새 시도를 시작합니다. 검사가 처음 통과하면 `solved`로 멈추고, N번째 시도까지 실패하면 `check_failed`로 멈춥니다.
- 범위와 제한: 2~5의 정수만 받습니다. `--live --suite e2e`에서만 쓸 수 있고(아니면 종료 코드 2), `--sensor`와 함께 쓸 수 없습니다(종료 코드 2). 설정 파일에서 `[agent] ladder = true`이면 종료 코드 2로 거절합니다. ladder가 켜지면 실행이 센서 경로로 바뀌어 재시도 경로 대신 센서 게이트를 쓰기 때문입니다(A/B의 arm b는 `ladder = false`).
- 숨김 채점기(채점기)는 시도 중에 workspace에 없습니다. 채점은 실행이 끝난 뒤에만 합니다. 공개 검사는 workspace의 것을 그대로 씁니다. 공개 검사 파일도 시도 중에 바꿀 수 있습니다(`tamper_guard`는 기본으로 꺼져 있습니다). 숨김 채점은 영향을 받지 않습니다.
- 검사를 자동으로 찾지 못하는 과제(예: `e2e_hx1`)는 재시도 없이 한 번만 실행합니다.
- 비용과 시간: 비용은 모든 시도의 합입니다. 과제별 비용 상한과 `wall_s`는 모든 시도에 걸쳐 적용됩니다. `max_iterations`는 시도마다 셉니다. 최종 답 게이트는 실행당 한 번만 거절합니다.
- 모델: `--models`로 고정한 모델은 재시도마다 같습니다. `--ab auto-routed`에서는 재시도가 `[router] escalate_on_retry`를 따르므로 strong 티어로 바뀔 수 있습니다.
- 보고서에는 `settings.verify_attempts`가 기록됩니다. 이 옵션을 주지 않으면 아무것도 바뀌지 않습니다.

### 반복 측정과 통계

- `--repeats N`이면 셀마다 N번 실행합니다. 실행 id는 `arm|model|protocol|task|rN` 형식이며(arm이 없으면 `-`), 반복 번호 N은 0부터 셉니다. 실행 시드는 `--seed`(기본값 0)에 반복 번호를 더한 값이고 보고서의 `seed`에 기록합니다. 시드는 제공자에게 전달하지 않으므로 모델의 응답을 고정하지 않습니다.
- 집계 단위는 (arm, 모델, 프로토콜, 작업)입니다. 단위마다 `k/n`(해결 수/실행 수), 해결률의 Wilson 95% 구간(z=1.96), 비용·토큰·벽시계 시간의 평균, 중앙값, 표준편차를 냅니다. 실행이 1개면 표준편차는 null입니다.
- 해결당 비용(`cost_per_solved_usd`)은 bootstrap 95% 백분위 구간(재표집 2000회, 시드 0)을 함께 냅니다. 해결이 하나도 없으면 값과 구간은 null이고 note는 `unsolved`입니다.
- `solved-per-dollar`(해결 수 ÷ 총 비용)는 총 비용이 0이면 null입니다.
- 실행이 5개 미만인 단위는 `low_n`으로 표시하고, `report.md`에 `WARNING: low_n` 줄을 씁니다. 구간이 넓어 비교가 의미 없다는 뜻입니다.
- 구성끼리의 비교는 문장으로 나옵니다. 해결률은 `difference not significant (n=…)`(구간이 겹침) 또는 `A higher than B (intervals do not overlap, n=…)`입니다. 비용은 `cost difference not significant (n=…)` 또는 `A cheaper than B (bootstrap 95% interval of the mean cost difference excludes 0, n=…)`입니다. 실행이 5개 미만이면 해결률과 비용 모두 `insufficient data (n=…)`입니다.
- 숫자는 유효숫자 2~3자리로 줄여 씁니다.
- 구간은 실행끼리 독립이라고 가정합니다. 같은 작업을 반복한 실행은 독립이 아닐 수 있으므로 구간이 실제보다 좁게 나올 수 있습니다. 보고서의 `note`에 이 내용이 나옵니다.
- 라이브 비교에는 `--repeats`를 3에서 5 이상으로 주는 것을 권장합니다.

### 예산 사전 추정, 부분 보고서, 이어하기

- 사전 추정은 실행을 시작하기 전에 계산하며 호출하지 않습니다. 남은 실행 수마다 단가를 곱해 더합니다. 단가는 `--resume`으로 이어 받은 완료 실행의 평균 비용이고, 완료 실행이 없으면 가격 기준 상한입니다.
- 가격 기준 상한은 작업마다 `--max-iterations`회 반복에 입력 16000 토큰과 출력 1024 토큰을 곱한 `cora.toml` 가격 계산값이며, 작업 상한(`--max-task-cost`)을 넘지 않습니다. 이 가정은 상한이지 보장이 아닙니다.
- 사전 추정이 `--max-cost`를 넘을 때의 동작은 다음과 같습니다. `--repeats`, `--trim-to-budget`, `--resume` 중 하나를 명시했으면 호출 없이 종료 코드 2로 거부합니다. `--trim-to-budget`을 주면 맞는 반복 수까지 줄여 실행하고 `trimmed` 기록을 남깁니다. 셋 다 없으면 `[bench] note:` 줄만 출력하고 실행하며, 예산 상한에 닿으면 남은 실행을 건너뜁니다(기존 동작).
- 보고서의 `partial`과 `partial_reason`은 실행이 끝까지 가지 못했는지 알려 줍니다. 사유는 `budget cap reached (--max-cost)`, `aborted: …`, `in progress: …` 중 하나입니다. `runs_planned`는 계획된 실행 수이고 `runs_completed`는 끝난 실행 수입니다.
- `report.json`은 실행 하나가 끝날 때마다 임시 파일에 쓴 뒤 교체하는 방식으로 갱신합니다. 중간에 끊겨도 마지막으로 끝난 실행까지는 남습니다.
- 예산 상한에 닿아 `partial: true`가 되어도 종료 코드는 0입니다. 제공자 계정 오류(HTTP 401, 402, 403)로 중단하면 종료 코드 3입니다.
- `--resume DIR`은 DIR의 `report.json`에서 끝난 실행을 읽고 그 실행은 호출 없이 건너뜁니다. 원본은 `report.resume-backup.json`으로 백업합니다. `--seed`가 원래 보고서와 같아야 하며, 다르면 종료 코드 2입니다. `--max-cost` 상한은 이번 실행에서 새로 쓰는 금액에만 적용되며, 이전 실행의 비용은 상한에 더하지 않습니다.
- `cora bench plan`의 출력은 구성마다 한 줄씩 나오는 표이고, 마지막에 `total_max_usd:`와 `suggested --repeats:` 줄을 냅니다. 보고서의 `budget_plan`에도 같은 값이 들어갑니다. 출력 끝에는 추정이 상한이라는 `PLAN_NOTE` 문구와, 라이브 예산은 마일스톤마다 charter의 프로젝트 하드 캡에 맞춰 정하며 이 명령은 이미 쓴 금액을 추적하지 않는다는 reminder가 나옵니다.

### 기준선 비교와 baseline.toml 스키마

`cora bench compare --baseline FILE`이 읽는 기준선 파일입니다. 이 형식은 `cora bench --baseline`(`--live` 없이 쓰는 `[baseline]` 형식)이나 `cora bench --live --baseline`(`success` 형식)과 다릅니다. 두 기존 형식은 바뀌지 않습니다.

| 위치 | 필드 | 필수 | 설명 |
|---|---|---|---|
| `[meta]` | `tool` | 필수 | 기준선을 낸 도구 이름입니다(비어 있지 않은 문자열). |
| `[meta]` | `model` | 필수 | 기준선을 낸 모델 이름입니다(비어 있지 않은 문자열). |
| `[meta]` | `date` | 필수 | 측정 날짜입니다(문자열 또는 TOML 날짜). |
| `[meta]` | `source` | 필수 | 측정 방법에 대한 설명입니다(비어 있지 않은 문자열). |
| `[meta]` | `synthetic` | 필수 | `true` 또는 `false`입니다. `true`이면 SYNTHETIC 배너를 붙입니다. |
| `[tasks.<task_id>]` | `solved` | 필수 | `true`/`false`, 또는 0부터 1 사이의 비율입니다. `true`는 1, `false`는 0으로 취급합니다. |
| `[tasks.<task_id>]` | `cost_usd` | 필수 | 실행 한 번당 평균 USD입니다(0 이상의 숫자). |
| `[tasks.<task_id>]` | `wall_s` | 필수 | 실행 한 번당 평균 초입니다(0 이상의 숫자). |
| `[tasks.<task_id>]` | `n` | 선택 | 반복 수입니다(1 이상의 정수, 기본값 1). |
| `[tasks.<task_id>]` | `note` | 선택 | 문자열 메모입니다. |

```toml
# SYNTHETIC / EXAMPLE - 실제 측정값 아님 (NOT MEASURED).
[meta]
tool = "example-tool"
model = "example-model"
date = "2026-01-01"
source = "SYNTHETIC / EXAMPLE - 실제 측정값 아님"
synthetic = true

[tasks.fix_off_by_one]
solved = true
cost_usd = 0.01
wall_s = 10.0
n = 1
```

- 오류: 필수 필드가 없거나 타입이 틀리면 `meta.tool`이나 `tasks.<task_id>.cost_usd`처럼 필드 이름을 담은 메시지를 내고 종료 코드 2로 끝납니다. 알 수 없는 최상위 키나 알 수 없는 작업 필드도 오류입니다. 오류 메시지에는 기준선 파일 이름만 나오고 전체 경로는 나오지 않습니다.
- 경고: 작업 ID가 CORA 벤치 작업이 아니면 경고를 내고 그 작업은 기준선에 그대로 둡니다. 보고서와 맞춰지지 않으면 `baseline only`로 나옵니다.
- 조인: 보고서의 작업 ID와 기준선의 작업 ID가 같은 것끼리 맞춥니다. 보고서에만 있으면 `CORA only`, 기준선에만 있으면 `baseline only`로 따로 적습니다.
- 열과 비율: CORA의 solved-per-dollar는 해결 수 ÷ 총 비용입니다. 기준선의 solved-per-dollar는 solved ÷ (cost_usd × n)입니다. 비율은 CORA ÷ 기준선이며, 1보다 크면 CORA가 유리합니다. 기준선의 solved-per-dollar가 0보다 클 때만 비율을 구하고, 그 밖의 경우(기준선 해결 수가 0이거나 비용이 0)에는 null입니다.
- 판정: 해결률만 비교합니다. 규칙은 벤치 섹션의 반복 측정 규칙과 같습니다. 실행이 5개 미만이면 `insufficient data (n=…)`, 두 Wilson 95% 구간이 겹치면 `difference not significant (n=…)`, 겹치지 않으면 `A higher than B (intervals do not overlap, n=…)`입니다. 기준선의 `n`이 1이면 `baseline n=1, 비교 불확실 (comparison uncertain)`을 판정에 붙입니다. 비용 차이는 판정하지 않습니다.
- 기준선이 없을 때: `--baseline`을 주지 않았거나 파일이 없으면 `baseline 없음: 비교 생략 (no baseline: comparison skipped)` 문구와 CORA의 절대 수치만 출력하고 종료 코드 0으로 끝납니다. 이는 오류가 아닙니다.
- SYNTHETIC 규칙: 배포물에는 `src/cora/data/baseline.example.toml` 하나만 들어 있으며, 이 파일은 합성 예시이고 실제 측정값이 아닙니다. 실제 측정 기준선은 직접 만들어 `--baseline`으로 넘깁니다. `synthetic = true`인 기준선으로 비교하면 출력 첫 줄에 SYNTHETIC 배너가 항상 붙습니다.

### e2e 프로젝트 태스크 (`--suite e2e`)

- `cora bench --live --suite e2e`는 요구사항 문서를 읽고 작은 프로젝트를 끝까지 만드는 과제를 실행합니다. `--suite e2e`는 `--live` 전용이며, `--tasks`로 과제를 고릅니다(기본값은 전체). `cora bench plan --suite e2e`는 호출 없이 과제별 최대 지출을 추정합니다.
- 스모크 세트는 샘플 과제 5개이며 난이도 순서입니다. `e2e_todo_cli`(easy, CLI 할 일 목록), `e2e_text_stats`(easy, 텍스트 통계 라이브러리와 테스트 명세), `e2e_rest_notes`(medium, `http.server` 기반 메모 REST 핸들러), `e2e_md_to_html`(medium, 마크다운을 HTML로 변환), `e2e_refactor_inventory`(hard, 단일 모듈을 패키지로 리팩터링)입니다. 과제 id는 `e2e_`로 시작하므로 기존 단일 파일 작업 id와 겹치지 않습니다.
- 하드 세트(M18, M19 측정용, 하네스 튜닝에 쓰지 않습니다)는 `e2e_h01`부터 `e2e_h06`까지의 실패 유형 과제와 `e2e_hx1`, `e2e_hx2`의 X 과제입니다. 각 id의 설명은 다음과 같습니다.
  - `e2e_h01`: CSV 열 통계 리포트 패키지(실패 유형 과제, 템플릿에 `python -m pytest -q`로 도는 부분 공개 테스트가 있고 숨김 채점이 그 상위 집합입니다).
  - `e2e_h02`: 원장 잔액과 월별 보고서(실패 유형 과제, 명세 테스트 `tests/test_ledger.py`는 수정하지 않습니다).
  - `e2e_h03`: 셸·JSON·Windows 경로 이스케이프 헬퍼와 HTML 숫자 엔티티 해제(실패 유형 과제, 큰 파일을 고칩니다).
  - `e2e_h04`: 수식 계산기(토큰화, 우선순위, 오류 메시지; 실패 유형 과제).
  - `e2e_h05`: 작업 추적기에 우선순위 추가(여러 모듈에 걸친 수정; 실패 유형 과제).
  - `e2e_h06`: 회의실 예약 시간창(자정을 넘는 예약, 빈 시간 계산; 실패 유형 과제).
  - `e2e_hx1`: 저장소 질문 과제. 읽기 전용으로 탐색해 다섯 질문의 답을 `ANSWERS.json`에 씁니다. 공개 검사는 없습니다.
  - `e2e_hx2`: 폐기 예정 헬퍼 `round_money`를 여러 모듈에서 `quantize`로 교체하는 과제입니다.
- X 과제의 채점 디렉터리에는 오프라인 테스트 전용 `exploration.json`(`{"sources": [...]}`)이 있습니다.
- 하드 과제의 한도는 `max_iterations` 25-30, `wall_s` 2400, `cost_usd` = max(0.05, 보정 실행 비용 x 3)입니다.
- (2026-10-22, M19e2) 새 과제 세트 `e2e_n01`..`e2e_n14`(디렉터리 `2NN_nNN_*`): 직접 작성한 혼합 과제입니다. 저자 의도 난이도는 `tests/fixtures/m19e2/manifest.toml`에 있고 에이전트 프롬프트와 채점에는 쓰이지 않습니다. 보정 결과는 `.docs/bench-results.md` M19e2 절에 있습니다.
- 과제 디렉터리는 `src/cora/bench/e2e_tasks/<디렉터리>/` 아래에 있습니다. 소스 체크아웃에만 있으며 독립 설치(wheel)에는 들어가지 않습니다. 파일은 다음과 같습니다.
  - `task.toml`: 과제 설정입니다.
  - `REQUIREMENTS.md`: 에이전트에게 주는 요구사항 문서입니다.
  - `template/`: 에이전트 작업 공간의 시작 파일입니다.
  - `grader/`: 채점 스크립트입니다. 기본값은 숨김(`hidden`)입니다.
  - `reference/`: 정답 구현입니다. 테스트 전용이며 실행 중에는 쓰이지 않습니다.

`task.toml`의 필드는 다음과 같습니다.

| 필드 | 필수 | 설명 |
|---|---|---|
| `id` | 필수 | `e2e_`로 시작하는 문자열입니다. 과제 사이에서 중복되면 안 됩니다. |
| `title` | 필수 | 비어 있지 않은 문자열입니다. |
| `difficulty` | 필수 | `easy`, `medium`, `hard` 중 하나입니다. |
| `requirements` | 필수 | 요구사항 파일의 상대 경로입니다(보통 `REQUIREMENTS.md`). |
| `template` | 필수 | 시작 파일 디렉터리의 상대 경로입니다. |
| `required_files` | 필수 | 완성되어야 하는 파일 목록입니다. 비어 있거나 절대 경로, `..`가 있으면 안 됩니다. |
| `limits.wall_s` | 필수 | 벽시계 시간 한도(초)입니다. 0보다 커야 합니다. |
| `limits.cost_usd` | 필수 | 과제 비용 한도(USD)입니다. 0보다 커야 합니다. |
| `limits.max_iterations` | 필수 | 반복 횟수 한도입니다. 0보다 큰 정수여야 합니다. |
| `grader.dir` | 필수 | 채점 스크립트 디렉터리의 상대 경로입니다. |
| `grader.entry` | 필수 | 채점 디렉터리 안의 진입 스크립트입니다(예: `grade.py`). |
| `grader.timeout_s` | 필수 | 채점 시간 한도(초)입니다. 0보다 커야 하며 상한은 120초입니다. |
| `grader.visibility` | 선택 | `hidden`(기본값) 또는 `visible`입니다. |
| `reference.dir` | 필수 | 정답 구현 디렉터리의 상대 경로입니다. 템플릿 안에 있으면 안 됩니다. |
| `reference.delete` | 선택 | 정답을 적용한 뒤 지울 파일 목록입니다(기본값은 빈 목록). |

- 로더는 과제를 읽을 때 다음 오류를 냅니다(과제 id 또는 디렉터리 이름과 함께 표시합니다). 필수 필드가 없으면 `missing required field '<필드>'`, `id`가 `e2e_`로 시작하지 않으면 `id must start with 'e2e_'`, 난이도가 틀리면 `difficulty must be one of easy, medium, hard`입니다. 한도가 0 이하이면 `limits.wall_s must be > 0`처럼 씁니다. 같은 id가 두 디렉터리에 있으면 `duplicate e2e task id`, 템플릿이나 채점 디렉터리, 진입 스크립트, 정답 디렉터리가 없으면 `template directory not found`, `grader directory not found`, `grader entry not found`, `reference directory not found`입니다. 정답이 템플릿 안에 있으면 `reference solution is inside the agent template`, 템플릿에 `REQUIREMENTS.md`나 `.cora_grader`가 있으면 `template must not contain REQUIREMENTS.md or .cora_grader`입니다. 경로가 과제 디렉터리를 벗어나면 `path escapes the task directory`입니다. 오류가 하나라도 있으면 실행을 시작하지 않고 종료 코드 2로 끝납니다.
- 작업 공간에는 템플릿과 `REQUIREMENTS.md`만 복사됩니다. 정답 구현과 채점 스크립트는 에이전트가 도는 동안 작업 공간에 없습니다. 에이전트가 끝나면(완료, 반복 한도, 시간 한도, 중단 무관) 채점 디렉터리를 작업 공간의 `.cora_grader`로 복사한 뒤 진입 스크립트를 실행합니다.
- 채점 프로토콜: 채점 스크립트는 마지막 비어 있지 않은 stdout 줄에 한 줄짜리 JSON을 씁니다. 형식은 `{"checks": [{"name": "...", "passed": true, "detail": "..."}]}`입니다. `score`는 통과한 check 수를 전체 check 수로 나눈 값이고, `full_pass`는 모든 check가 통과했는지입니다. 해결(solved)은 `full_pass`입니다.
- `grader_error`: 채점이 시간을 넘기거나, 0이 아닌 코드로 끝나거나, 올바른 JSON이 아니면 점수는 0이고 `full_pass`는 거짓입니다. 사유는 `grader_error`로 기록하고 하네스는 멈추지 않습니다.
- 샌드박스: 채점은 subprocess로 실행합니다. 작업 디렉터리는 작업 공간이고, 하드 타임아웃은 최대 120초입니다. 시간을 넘기면 프로세스 그룹을 종료합니다(killpg). 환경 변수는 화이트리스트(`PATH`, `LANG`, `LC_ALL`, `LC_CTYPE`, `TMPDIR`, `SYSTEMROOT`)만 전달하고 `HOME`은 작업 공간으로 바꿉니다. `PYTHONHASHSEED`는 `0`으로 고정합니다. stdout과 stderr는 각각 마지막 64 KiB까지만 읽습니다. API 키 환경 변수는 채점 프로세스에 전달되지 않습니다.
- 알려진 한계: OS 수준의 네트워크 차단이나 파일 격리는 없습니다. 채점 코드가 네트워크를 쓰지 않는다는 것은 검사 테스트로 확인합니다. 에이전트의 `run_shell`은 기본 설정에서 경로 제한이 없습니다. e2e strict 프로파일은 정적 검사로 채점과 정답 경로를 막지만, 남는 우회는 자율 승인 정책 섹션의 한계 목록을 보세요. 채점은 프로세스 그룹 기능을 쓰므로 Windows에서는 `--suite e2e`를 지원하지 않습니다.
- `--suite e2e`는 사용자 정책과 무관하게 내장 strict 프로파일로 실행합니다(보고서의 `policy_profile`이 `strict`). 실행마다 `policy_denies`(정책 거부 수)와 `policy_asks`(묻기로 판정된 수)를 기록하고, `e2e` 요약에 `policy_deny_total`과 `policy_ask_total`을 씁니다. 이 값들은 `human_interventions`와 따로 셉니다. `report.md`에는 `policy (strict e2e profile, separate from human_interventions):` 줄이 나옵니다. strict 프로파일은 macOS에서 `sandbox-exec`를 자동으로 켜며, 쓸 수 없으면 경고를 냅니다.
- `human_interventions`는 항상 0으로 기록합니다. 러너는 사람에게 질문하거나 승인을 요청하지 않습니다. 승인 요청이 생기면 자동으로 승인하고 그 횟수를 셉니다. 0이 아니면 보고서에 `WARNING: human_interventions > 0` 줄이 나옵니다.
- 종료 사유(`end_reason`)는 여섯 가지입니다. `final_answer`(에이전트가 최종 답변을 냄), `max_iterations`(반복 한도), `cost_limit`(비용 한도), `time_limit`(벽시계 시간 한도), `aborted`(제공자 계정 오류로 중단), `error`(그 밖의 오류)입니다.
- 반복 한도(`max_iterations`) 등 어떤 사유로 멈춘 e2e 실행도 채점합니다. `full_pass`이면 solved이고, 멈춘 사유는 `end_reason`/`stop_reason`에 그대로 남습니다. 내장 단일 파일 작업(`--suite` 기본)은 `final_answer`가 아닌 종료를 채점 없이 실패로 셉니다.
- 한도 조합: 반복 한도는 `--max-iterations`와 `limits.max_iterations` 중 작은 값입니다. 작업 비용 한도는 `--max-task-cost`와 `limits.cost_usd` 중 작은 값입니다. `--max-iterations`를 주지 않으면 선택한 과제의 반복 한도 중 최댓값을 씁니다. `--max-task-cost`를 주지 않으면 `[bench] max_task_cost_usd`가 있으면 그 값을, 없으면 `--max-cost`와 선택한 과제 비용 한도 중 작은 값을 씁니다. e2e 과제는 `--e2e-task-cost USD`를 주면 `limits.cost_usd` 대신 그 값을 과제 비용 한도로 씁니다(`--suite e2e` 전용, 0보다 크고 `--max-cost` 이하). 이 옵션을 주지 않으면 task.toml 값이 그대로 적용됩니다.
- 보고서는 기존 `report.json`과 `report.md` 구조를 따릅니다. 각 실행에 `score`, `full_pass`, `end_reason`, `human_interventions`, `grader` 상세(check별 이름, 통과 여부, 사유)가 들어갑니다. `report.md`에는 `### E2E tasks (solved = full_pass)` 표와 `#### checks:` 목록이 나옵니다. `e2e` 요약은 완료 실행 수, `full_pass` 수, 평균 부분 점수(`mean_score`), 사람 개입 합계, 채점 오류 수를 씁니다. `--repeats`와 반복 측정 통계(`solved = full_pass`)도 같은 방식으로 적용됩니다.

```text
cora bench --live --suite e2e --tasks e2e_todo_cli --repeats 3 --models <모델> --protocols react
```

## 결정기 평가 (`cora decider eval`)

- 케이스 파일은 JSONL입니다. 한 줄에 케이스 하나를 쓰고 빈 줄은 건너뜁니다. 예:

```jsonl
{"id": "a", "expected": "cheap", "prompt": "What is 2+2?", "tokens": {"input": 20000, "output": 2000}}
{"id": "b", "expected": "strong", "features": {"chars": 500, "code_keywords": true, "code_reference": true, "multi_step": false}, "replay": {"label": "strong", "confidence": 0.9}}
```

- `id`: 케이스 이름입니다. 생략하면 `line<줄 번호>`가 됩니다.
- `expected`: 정답 티어(`cheap` 또는 `strong`)입니다. 다른 값은 오류입니다.
- `prompt`: 과제 원문입니다. 있으면 휴리스틱이 원문을 그대로 봅니다.
- `features`: 과제의 요약입니다. `chars`(0 이상의 정수)와 `code_keywords`, `code_reference`, `multi_step`(참 또는 거짓)을 쓸 수 있습니다. 주어지면 `prompt`에서 계산한 값 대신 이 값을 씁니다. `prompt`가 없으면 필수입니다.
- `tokens`: 비용 추정에 쓸 입력(`input`)과 출력(`output`) 토큰 수입니다. 기본값은 입력 20000, 출력 2000입니다.
- `replay`: `replay` 결정기가 이 케이스에서 내는 답입니다(`label`, `confidence`, `fail`, `cost_usd`). 없으면 답이 없는 것으로 보고 휴리스틱 답으로 대신합니다.
- 케이스 형식을 벤치 결과에서 만드는 규칙: `cora bench --live --ab`의 `report.json`에 있는 `ab.per_task_tiers`에서 cheap만 해결한 과제는 `"expected": "cheap"`, strong만 해결한 과제는 `"expected": "strong"`으로 옮깁니다. 나머지 과제는 제외합니다.
- 출력은 다음 줄로 나옵니다.
  - `agreement`: 예측이 정답 티어와 맞은 수와 비율입니다.
  - `confusion (expected->predicted)`: 정답과 예측의 2×2 표입니다.
  - `misroutes`: `cheap->strong`은 싼 과제를 강한 모델로 보낸 것이고, `strong->cheap`은 어려운 과제를 싼 모델로 보낸 것입니다.
  - `fallbacks`와 `low_confidence`: 휴리스틱 답으로 대신한 수와 신뢰도가 `min_confidence`보다 낮아 무시한 수입니다.
  - `decision_cost_usd`: 결정 호출에 든 비용입니다. `heuristic`과 `replay`는 0입니다.
  - `expected_model_cost_usd`: 예측한 티어의 모델을 가격표와 토큰 추정으로 계산한 비용입니다. 괄호 안은 정답 티어를 모두 맞혔을 때의 비용입니다.
  - `expected_total_cost_usd`: 결정 비용과 모델 비용의 합입니다.
  - 가격을 모르는 모델은 `unpriced_models`로 세고 $0으로 계산합니다.
- `heuristic`과 `replay`는 네트워크 호출을 하지 않습니다.
- `llm`은 `--live`가 없으면 호출하지 않고 안내만 출력한 뒤 종료 코드 2로 끝납니다. `--live`를 주면 결정 호출 전에 사전 점검(preflight)을 하고,(`cora bench --live`와 같은 점검으로, 잔액이 0 이하이면 경고만 출력하고 계속합니다) `--max-cost`(기본 0.05 USD, 최대 0.50 USD)로 예산 가드를 겁니다. `--json`은 같은 보고서를 JSON으로 출력합니다.
- 승격 규칙: LLMDecider는 오프라인 평가와 이후 라이브 평가에서 휴리스틱보다 resolved-per-dollar가 좋다고 측정될 때만 기본값 후보가 되며, 기본값 변경은 오케스트레이터가 결정합니다. 이번 버전의 기본값은 `kind = "heuristic"`, 사용처 전부 꺼짐입니다.
- Jev: TypeSafe AI의 Jev는 나중에 같은 `Decider` 인터페이스 뒤에 붙일 수 있는 선택지입니다. 원시 `Choice`/`Score`/`Noul` API가 OpenRouter에서 제공되는지는 아직 확인되지 않았습니다. 확인되면 `Decider`를 구현하는 어댑터를 만들고 `[decider] kind`로 연결합니다. 지금은 구현이 없습니다.
- `typesafe/jev-router`는 결정기 코드 없이 기존 벤치의 일반 모델 항목으로 측정할 수 있습니다: `cora bench --live --models typesafe/jev-router`.

## SALE-lite 라우팅 (`cora sale eval`)

- 상태: 실험적 라이브러리, 런타임 미연결. 구현된 라우팅 기능이 아닙니다. '실패하면 더 높은 티어로' 아이디어는 계획된 escalation cascade(M16)로 다룹니다.
- 개요: SALE 논문의 아이디어를 줄인 라우팅 평가입니다. 작업의 plan 특징으로 tier마다 bid(`estimated_cost`, `expected_success`, `value`)를 계산하고, 예산 상한 안에서 `value`가 최대인 tier를 고릅니다. 논문의 entropy 추정, peer-scoring, 경매 메모리는 구현하지 않습니다. 기본으로 꺼져 있고, 네트워크와 API 키 없이 결정적으로 실행됩니다.
- 표식: 내장 tier 표 `src/cora/data/sale_tiers.toml`은 M15 측정 사이클 0의 실측값입니다(`placeholder = false`, 출처는 파일 머리말에 적혀 있습니다). 예시 케이스 `src/cora/data/sale_cases.synthetic.jsonl`은 합성(SYNTHETIC / PLACEHOLDER) 값이며, 이 파일의 표식 문구는 `SYNTHETIC / PLACEHOLDER, 실측 아님`입니다. tier 표에 `placeholder = true`가 있으면 `cora sale eval` 출력 앞뒤에 `WARNING: SYNTHETIC / PLACEHOLDER tier table, 실측 아님 (not measured).` 경고가 나옵니다. 표의 숫자는 자신의 live bench 결과로 바꿔야 합니다. 이 문서와 출력은 측정된 효과를 주장하지 않습니다.

### `[sale]` 설정

```toml
[sale]
enabled = false
bids = "heuristic"
reward = 20.0
budget_cap = 20.0
max_escalations = 1
tiers_file = ""
```

- `enabled`: `true`이면 `bids = "llm"`일 때 LLM bid 생성기를 쓸 수 있습니다. 기본값은 `false`입니다. 에이전트 루프에는 아직 연결되어 있지 않으므로 런타임 동작은 바뀌지 않습니다. 잘못된 값(true/false가 아님)이면 설정 오류입니다.
- `bids`: bid 생성기 종류입니다. `heuristic`(기본값, 결정적이며 호출 없음)이나 `llm`입니다. 다른 값이면 설정 오류입니다.
- `reward`: 작업 보상입니다. 0보다 큰 수이며 기본값은 20.0입니다.
- `budget_cap`: 작업당 비용 상한입니다. 0보다 큰 수이며 기본값은 20.0입니다.
- `max_escalations`: escalation 최대 횟수입니다. 0 이상의 정수이며 기본값은 1입니다.
- `tiers_file`: tier 표 TOML 경로입니다. 빈 문자열이면 내장 표를 씁니다. 상대 경로는 현재 디렉터리 기준으로 읽습니다.
- 기본 `cora.toml`에는 `[sale]` 섹션이 없고, 없으면 `enabled = false`로 꺼져 동작합니다. 알 수 없는 키나 잘못된 값은 설정 오류(종료 코드 2)입니다.

### tier 표 형식

tier 표는 TOML 파일입니다. 내장 파일 `src/cora/data/sale_tiers.toml`의 내용은 다음과 같습니다.

```toml
# MEASURED tier table - M15 measurement cycle 0 (실측).
# Source: .docs/bench-results.md "## M15 측정 사이클 0" (reports .cora/bench/m15/merged, date 2026-10-16).
# cheap = google/gemini-2.5-flash-lite (arm A), strong = deepseek/deepseek-v3.2 (arm C); cost = mean USD per task run, solve_rate = k/n over reported cells.
placeholder = false
unit = "usd per task run"

[[tiers]]
name = "cheap"
cost = 0.006590
solve_rate = 0.4545

[[tiers]]
name = "strong"
cost = 0.01570
solve_rate = 0.5152
```

- `placeholder`: 기본값은 `true`입니다. 내장 표는 M15 실측값이라 `false`입니다. 자신의 표를 쓸 때는 모든 값을 측정한 뒤에만 `false`로 바꾸세요.
- `unit`: 비용 단위 이름입니다. 기본값은 `arbitrary cost units`입니다. 내장 표의 단위는 `usd per task run`입니다.
- `[[tiers]]`: 항목마다 `name`, `cost`, `solve_rate` 세 키만 있어야 합니다. 다른 키는 오류입니다.
- 규칙: tier는 2개 이상이며, 저렴한 순서에서 강한 순서로 나열하고 `cost`는 엄격히 증가해야 합니다. `solve_rate`는 0부터 1 사이입니다. `name`은 서로 달라야 합니다.

### JSONL 케이스 형식

케이스 파일은 한 줄에 JSON 객체 하나입니다. 예시(`sale_cases.synthetic.jsonl`의 두 줄):

```json
{"id": "syn-01", "task": "Fix a typo in README.md", "plan": {"steps": 1, "files": 1, "tool_risk": 0.0, "uncertainty": 0.0}, "note": "SYNTHETIC / PLACEHOLDER, 실측 아님"}
{"id": "syn-08", "task": "Add caching to the API layer", "plan": {"steps": 9, "files": 4, "tool_risk": 0.5, "uncertainty": 0.5}, "outcomes": {"cheap": {"success": false, "cost": 1.5}, "strong": {"success": true, "cost": 12.0}}, "note": "SYNTHETIC / PLACEHOLDER, 실측 아님"}
```

- `id` (필수): 비어 있지 않은 문자열입니다. 파일 안에서 중복되면 안 됩니다.
- `task`: 작업 설명입니다. 기본값은 빈 문자열입니다.
- `plan`: 객체입니다. `steps`, `files`, `tool_risk`, `uncertainty` 네 키를 모두 써야 합니다. `tool_risk`와 `uncertainty`는 0부터 1 사이입니다.
- `plan_text`: plan 텍스트입니다. 아래 규칙으로 특징을 뽑습니다.
- `outcomes`: tier 이름마다 `success`(true/false)와 `cost`(0 이상)를 적은 객체입니다. 기록된 값이 있으면 기대값 대신 기록된 값을 씁니다.
- `note`: 메모 문자열입니다. 계산에 쓰지 않습니다.
- 규칙: 알 수 없는 키는 오류입니다. `plan`과 `plan_text`가 둘 다 있으면 `plan`을 씁니다. 빈 줄은 건너뜁니다. 오류는 `파일:줄 번호`와 함께 나오고 종료 코드는 2입니다.

### `plan_text` 추출 규칙

- steps: 비어 있지 않은 줄의 수입니다.
- files: 중복을 뺀 파일 경로의 수입니다.
- tool_risk: edit, write, delete, run 같은 쓰기·실행 계열 낱말(한국어 수정, 삭제, 실행, 설치, 이동 포함)이 든 줄의 비율입니다.
- uncertainty: maybe, investigate, 물음표(`?`) 같은 모호 낱말이 든 줄의 비율입니다.

### 공식

- `d = min(1, 0.05×steps + 0.1×files + 0.25×tool_risk + 0.25×uncertainty)`
- `size = 1 + 0.05×steps`
- `estimated_cost = cost × size`
- `expected_success = clamp(solve_rate − 1.5×d×(1 − solve_rate), 0, 1)`
- `value = expected_success × reward − estimated_cost`

라우터 규칙: `estimated_cost`가 `budget_cap` 이하인 tier 중 `value`가 최대인 tier를 고릅니다. 동점이면 더 싼 tier를 고릅니다. 모든 tier가 상한을 넘으면 가장 싼 tier를 고르고 `over_budget`을 표시합니다.

### escalation 규칙

escalation은 라이브러리 상태기계로만 구현되어 있습니다. sensor(테스트 등)가 실패하면 다음 상위 tier로 한 단계 올립니다. `max_escalations` 횟수를 넘으면 멈춥니다. 누적 비용에 다음 tier의 `estimated_cost`를 더한 값이 `budget_cap`을 넘으면 멈춥니다. 최상위 tier에서 실패하면 실패로 끝납니다. sensor가 통과하면 즉시 끝납니다. 이전 시도의 비용은 누적합니다. 종료 사유는 `sensor_passed`, `top_tier_failed`, `max_escalations`, `budget_cap` 중 하나입니다. 이 절은 `[escalation]`(M16 캐스케이드)과 별개입니다.

### bid 생성기

- `heuristic`: 기본값입니다. plan 특징에서 결정적으로 계산하며 어떤 호출도 하지 않습니다.
- `llm`: `enabled = true`와 `bids = "llm"`을 둘 다 켰을 때만 쓰입니다. plan을 만드는 planner 어댑터가 필요하지만 이 버전에는 연결된 어댑터가 없어서 planner가 없으면 오류입니다. 테스트는 replay 응답으로만 합니다.

### 정책 비교

`cora sale eval`은 네 정책을 같은 케이스에서 비교합니다.

- `always-cheap`: 항상 가장 싼 tier를 고릅니다.
- `always-strong`: 항상 가장 강한 tier를 고릅니다.
- `heuristic-router`: 기존 작업 설명 휴리스틱 점수(`prompt_features`와 `score_from_features`)가 `[router] threshold` 이상이면 가장 강한 tier, 아니면 가장 싼 tier를 고릅니다. plan은 보지 않습니다.
- `sale-lite`: heuristic bid와 위 라우터 규칙을 씁니다.

출력 열은 다음과 같습니다.

- `total_cost`: 기대 비용의 합입니다.
- `mean_cost`: 기대 비용의 평균입니다.
- `solve_rate`: 기대 solve-rate의 평균입니다.
- `strong_share`: 가장 강한 tier를 고른 케이스의 비율입니다.
- `over_budget`: 고른 tier의 `estimated_cost`가 `budget_cap`보다 큰 케이스 수입니다.
- `recorded`: 기록된 `outcomes`로 값을 대신한 횟수입니다.

예시 출력은 합성 데이터에서 나온 숫자이며 측정된 효과가 아닙니다.

```
policy             total_cost  mean_cost solve_rate strong_share over_budget recorded
always-cheap          12.3000     1.3667     0.2100       0.0000           0        1
always-strong        120.0000    13.3333     0.8303       1.0000           1        1
heuristic-router      24.9000     2.7667     0.2933       0.1111           0        1
sale-lite             61.5000     6.8333     0.5711       0.4444           0        1
```

`--json`을 주면 같은 보고서를 JSON으로 출력합니다.

### 한계

- 에이전트 루프에 연결되어 있지 않으므로 `enabled`는 지금 런타임 동작에 영향이 없습니다.
- 평가는 escalation을 시뮬레이션하지 않습니다.
- 계수(0.05, 0.1, 0.25, 1.5 등)는 고정 상수입니다.
- 비용 자동 환산, 학습, 온라인 보정은 없습니다.
- 완전히 결정적이며 네트워크, API 키, 환경 변수가 필요 없습니다.

## MCP 서버

MCP(Model Context Protocol) stdio 서버의 도구를 CORA 에이전트가 일반 도구처럼 호출할 수 있습니다. 서버는 `cora.toml`에 `[mcp.servers.<name>]` 테이블로 등록합니다. 기본 설정에는 서버가 없으며, 서버가 없으면 CORA는 MCP 프로세스를 하나도 시작하지 않습니다.

```toml
[mcp.servers.files]
command = "npx"
args = ["-y", "@modelcontextprotocol/server-filesystem", "."]
env = { EXAMPLE_TOKEN = "..." }
enabled = true
timeout_s = 30
```

| 키 | 기본값 | 설명 |
|---|---|---|
| `command` | 없음(필수) | 실행할 프로그램입니다. 셸을 거치지 않고 argv로 실행하며 PATH에서 찾습니다. 공백으로 나누지 않으므로 인자는 `args`에 씁니다. |
| `args` | `[]` | 문자열 목록입니다. 셸 메타문자(`;`, `&&`, `$(...)` 등)도 그대로 리터럴로 전달됩니다. |
| `env` | `{}` | 서버에 전달할 환경 변수 표입니다. 값은 문자열이어야 합니다. 여기 적은 변수만 허용 목록과 함께 전달됩니다. |
| `enabled` | `true` | `false`면 서버를 시작하지 않고 도구도 노출하지 않습니다. `/mcp`에는 `disabled`로 보입니다. |
| `timeout_s` | `30` | 시작(initialize), `tools/list`의 각 페이지, 각 `tools/call`에 적용되는 시간 제한(초)입니다. 0보다 커야 합니다. |

서버 이름(`<name>`)은 1~32자이며 영문, 숫자, `-`와 가운데의 `_`만 쓸 수 있습니다. 앞뒤나 연속된 `_`는 안 됩니다. 예: `files`, `my-server`, `my_server`.

잘못된 설정(`command` 누락, 타입 오류, `timeout_s`가 0 이하, 잘못된 이름, 알 수 없는 키)은 그 서버만 비활성화합니다. 다른 서버와 CORA 시작은 영향을 받지 않습니다. 시작할 때 `warning:` 줄이 나오고, `/mcp`에는 `failed`와 오류가 표시됩니다. `[mcp]`나 `[mcp.servers]` 자체가 표 형식이 아니면 MCP 전체가 꺼집니다.

`cora mcp serve`가 읽는 `[mcp]` 최상위 키(`max_cost_usd`, `max_iterations` 등, 아래 `MCP 서버로 실행` 섹션)는 엄격하게 검사합니다. 잘못된 값이면 `[mcp.servers.<name>]`처럼 그 항목만 끄지 않고 설정 오류로 종료 코드 2가 됩니다.

도구는 `mcp__<server>__<tool>` 이름으로 노출됩니다. 허용되지 않는 문자는 `_`로 바꿉니다. 이름이 64자를 넘으면 앞부분을 줄이고 원래 도구 이름의 sha1 해시 8자를 붙입니다. 같은 이름으로 충돌하면 서버가 준 목록에서 먼저 나온 도구를 쓰고, 나머지는 건너뛰며 `/mcp`에 메모로 표시됩니다. 내장 도구 이름은 MCP 도구가 덮어쓸 수 없습니다.

도구 설명(description)과 입력 스키마(inputSchema)는 그대로 모델에 전달됩니다. 스키마가 객체 형식이 아니면 빈 객체 스키마로 대체합니다. 텍스트가 아닌 내용(이미지 등)은 `[non-text content omitted: <type>]`로 바꿉니다. 도구 출력은 16000자로 자르며, 잘리면 표시가 붙습니다.

수명주기는 다음과 같습니다.

- 지연 시작: CORA 시작 때는 서버를 띄우지 않습니다. 그룹이 켜져 있으면 모델을 호출하기 직전에 처음 시작하고, `tools/list` 결과를 세션 동안 캐시합니다. 그룹이 꺼져 있으면 시작하지 않습니다. `tools/list_changed` 알림은 무시합니다. 설정을 바꾸면 CORA를 다시 시작해야 합니다.
- 작업 디렉터리: 서버는 `--workdir`(기본값은 현재 디렉터리)에서 실행됩니다.
- 크래시: 서버가 죽거나, EOF가 오거나, JSON이 잘못되거나, 너무 큰 메시지가 오면 `crashed`가 됩니다. 진행 중인 호출은 오류를 반환하고 에이전트는 계속 진행합니다. 다음 호출에서 한 번 다시 시작합니다. 연속으로 두 번 실패하면 `failed`가 되며 이번 세션에서는 다시 시작하지 않습니다. 성공한 호출이 있으면 실패 횟수가 0으로 돌아갑니다.
- 응답 없음: 같은 서버의 호출이 두 번 연속 시간 초과되면 응답 불능으로 보고 종료한 뒤 크래시로 셉니다.
- 종료: CORA가 끝날 때(정상 종료, Ctrl-C, 오류 포함) stdin을 닫고 1초 기다린 뒤 프로세스 그룹에 SIGTERM을, 다시 1초 뒤 SIGKILL을 보냅니다.

`/mcp`는 서버별 이름, 상태(`disabled`, `not started`, `running`, `crashed`, `failed`), 도구 수와 이름, 그룹이 꺼져 있는지, 재시작 횟수, 오류 요약을 보여줍니다. 서버를 시작하지 않습니다. 인자를 받지 않으며(`/mcp x`는 사용법 오류), 서버가 없으면 설정 방법을 안내합니다.

보안은 다음과 같습니다.

- 모든 MCP 도구는 읽기 전용이 아닌 것으로 취급합니다. 그래서 `approval = "ask"`일 때는 매번 묻고, 승인 요청에 서버 이름, 도구 이름, 인자를 보여줍니다. 거부하면 서버에 호출이 전달되지 않습니다. 서버가 주는 `readOnlyHint`는 신뢰하지 않습니다. `auto`, `deny`, 항상 허용은 다른 도구와 같이 동작합니다. MCP 도구는 계획 모드(`/plan`)에서 실행되지 않습니다.
- 환경 변수: 자식 프로세스에는 `PATH`, `HOME`, `USER`, `LOGNAME`, `SHELL`, `LANG`, `LANGUAGE`, `TERM`, `TMPDIR`, `TZ`, `LC_*` 변수와 서버의 `env`만 전달합니다. `OPENROUTER_API_KEY`는 `env`에 직접 적지 않는 한 전달되지 않습니다. 환경 변수 값은 어디에도 출력하지 않으며, 오류 요약에서는 `[REDACTED]`로 바꿉니다.
- stderr는 마지막 8KB만 보관하며 터미널에 출력하지 않습니다. 진단(`/mcp`의 오류 요약)에만 씁니다.
- OS 수준 샌드박스는 없습니다. 보호는 환경 변수 허용 목록과 승인 절차에 의존합니다.

### 알려진 제한

- stdio 전송만 지원합니다. HTTP, SSE, OAuth는 없고 resources, prompts, sampling도 지원하지 않습니다.
- `tools/list_changed` 알림은 무시합니다. 설정 변경은 CORA를 다시 시작해야 반영됩니다.
- `/delegate`로 띄운 하위 에이전트와 `cora bench`는 MCP 도구를 쓰지 않습니다.
- MCP 호출은 병렬로 실행되지 않습니다.
- Ctrl-C로 턴을 끊어도 진행 중인 서버 호출은 `timeout_s`까지 계속 기다릴 수 있습니다. 그 동안 같은 서버의 다음 호출은 대기합니다.
- 서버가 stdout에 JSON이 아닌 글을 출력하면 크래시로 봅니다. 로그는 stderr로 보내야 합니다.
- POSIX(macOS, Linux)에서만 동작합니다.

## 프로젝트 실행 (`cora project`)

`cora project run PLAN.toml`은 목표를 여러 마일스톤으로 나눈 계획 파일을 순서대로 실행합니다. 마일스톤마다 체크포인트를 저장하므로, 중간에 멈춰도 `cora project resume RUN_ID`로 끝난 마일스톤 다음부터 이어 갈 수 있습니다. 마일스톤마다 새 세션을 쓰며, 마일스톤 사이에 대화 문맥은 넘기지 않습니다.

### 계획 파일 형식

계획 파일은 TOML입니다. 최상위 `goal`과 `[[milestones]]` 테이블 목록이 있습니다.

```toml
goal = "작은 계산기 모듈을 만든다"

[[milestones]]
id = "design"
title = "설계"
task = "계산기의 공개 함수 목록을 정하고 설계 메모를 작업 디렉터리에 씁니다."

[[milestones]]
id = "impl"
title = "구현"
task = "설계 메모를 따라 calc.py를 구현합니다."
check = "uv run pytest tests/test_calc.py"

[[milestones]]
id = "docs"
title = "문서"
task = "calc.py의 사용법을 README.md에 적습니다."
```

- `goal`은 필수 문자열입니다.
- `[[milestones]]`는 하나 이상 있어야 하며, 적힌 순서대로 실행합니다.
- `id`는 필수이고 비어 있지 않은 문자열이어야 합니다. 앞뒤 공백은 지우며, 계획 안에서 유일해야 합니다.
- `title`은 필수 문자열입니다. 진행 표시에 쓰입니다.
- `task`는 필수이고 비어 있지 않은 문자열입니다. 그 마일스톤의 작업 지시입니다.
- `check`는 선택 항목입니다. 있으면 마일스톤의 최종 답을 받아들이기 전에 센서 게이트로 실행합니다. 실패하면 같은 세션에서 고쳐 다시 시도하며, 재시도 횟수는 `[agent] sensor_max_retries`를 따릅니다(기본값이면 검사는 최대 4회입니다). 센서 게이트에서는 tripwire도 켜집니다.
- 알 수 없는 키가 있으면 종료 코드 2로 끝납니다. 계획 오류가 나면 체크포인트를 만들지 않습니다.
- `conditions`는 선택 항목입니다. 마일스톤의 최종 답 뒤에 실행할 완료 조건 목록이며, 자세한 내용은 아래 완료 조건 섹션을 보세요.

### 완료 조건 (conditions)과 게이트

마일스톤에 `conditions`를 주면, 최종 답 뒤에 조건을 순서대로 확인하고 모두 통과해야 마일스톤이 `completed`가 됩니다. 조건은 두 종류입니다.

- `kind = "command"`와 `cmd`: 셸 명령을 실행하고, 종료 코드 0이면 통과합니다.
- `kind = "file_exists"`와 `path`: 파일이 있으면 통과합니다. `path`는 작업 디렉터리 기준 상대 경로여야 하며, 절대 경로와 `..`은 허용하지 않습니다.

```toml
[[milestones]]
id = "impl"
title = "구현"
task = "calc.py를 구현하고 테스트를 통과시킵니다."
conditions = [ { kind = "command", cmd = "uv run pytest -q" }, { kind = "file_exists", path = "calc.py" } ]
```

- 조건은 최종 답(`check`가 있으면 그 통과) 뒤에 순서대로 실행하며, 첫 실패에서 멈춥니다.
- 조건 명령은 센서 게이트와 같은 정책 검사와 셸 경로를 거칩니다. 정책이 거부한 명령은 실행하지 않고 실패로 칩니다.
- 조건마다 `[project] condition_timeout_s`초의 시간 제한이 있습니다. 실패한 출력은 끝부분 `condition_output_chars`자만 남깁니다.
- 실패하면 새 세션으로 원래 작업에 실패한 조건과 출력 끝부분을 덧붙여 다시 실행합니다. 재시도 횟수는 `[project] gate_retries`(기본 1, 0이면 재시도 없음)입니다.
- 재시도까지 실패하면 `stop_reason`이 `gate_failed`가 되고 종료 코드 1로 끝납니다. 해당 마일스톤은 `failed`, 뒤의 마일스톤은 `pending`으로 남습니다. 체크포인트의 `gate` 기록에 `failed_condition`이 남습니다.
- 조건 실행 하나는 도구 호출 1회로 셉니다. 재시도도 같은 프로젝트 예산을 씁니다.
- `resume`은 `gate_failed` 마일스톤을 새 재시도 한도로 다시 시작하며, 이전 실패 기록은 지웁니다.
- 실행 중 강제 종료 후 재개하면 이미 쓴 시도 횟수(`gate.attempts`)는 유지됩니다. 진행 중이던 시도는 저장된 실패 내용과 함께 다시 실행합니다.
- `check` 실패는 재시도 없이 종료 코드 1로 끝나며, 기존 마일스톤 동작과 같습니다.

### 계획 생성 (cora project plan, --goal)

- 모델 응답은 JSON 객체 하나여야 합니다. `{"goal": "...", "milestones": [{"id", "title", "task", "check"?, "conditions"?}]}` 형식이며, ```` ```json ```` 울타리로 감싼 응답도 받습니다.
- 마일스톤은 1개 이상이고 `[project] max_milestones`(기본 8)를 넘을 수 없습니다.
- 응답이 형식에 맞지 않으면 오류 내용을 담아 한 번만 다시 요청합니다. 그래도 맞지 않으면 종료 코드 2입니다.
- 엄격 파싱이 실패하면 계획 JSON은 먼저 복구 단계 `strip_fences`, `extract_object`, `trailing_commas`, `single_quotes`를 시도합니다. 이 복구는 `[agent] lenient_parse = true`(기본값)일 때만 실행됩니다. 모델 복구 호출은 이 단계들이 모두 실패한 경우에만 일어납니다. 그래도 형식이 맞지 않는 응답은 종료 코드 2로 끝납니다.
- 계획 호출 비용은 결과의 `cost_usd`와 `budget.used`에 포함되며, 호출 전에 비용 상한을 확인합니다.
- `cora project run --goal GOAL`은 계획을 만든 뒤 `<workdir>/.cora/projects/<run_id>/plan.toml`에 저장하고 바로 실행합니다. `-o`를 주면 같은 계획을 그 파일에도 씁니다.
- 계획 프롬프트에는 이 실행의 셸 정책 규칙(`render_policy_rules`)이 들어갑니다. 모델이 정책으로 거부될 검사 명령(`check`)이나 `command` 조건을 쓰지 않도록 알려 주기 위해서입니다.
- 정책으로 거부된 `check`/`command` 조건은 `policy_repairs` 횟수만큼 수정 요청을 받습니다. 그래도 거부되는 항목은 버리고 기록합니다(계획 문서의 `plan_policy`, 그리고 `policy_dropped` 목록).
- 검사가 모두 버려진 마일스톤은 `ungated = true`로 표시됩니다. 경고를 출력하고 결과의 `ungated_milestones`에 나옵니다. 이것은 오류가 아니며 종료 코드를 바꾸지 않습니다.
- `cora project plan --approval`이 있습니다. 헤드리스 실행에 쓸 계획은 `--approval policy`로 만들어야 합니다.
- `policy_repairs`(0–3, 기본값 1)는 `[project]` 설정입니다. 배포되는 `cora.toml`에는 이 키가 적혀 있지 않습니다. 기본값은 코드에서 오므로 M20 사전 등록이 해시로 고정한 파일이 그대로 남습니다. 바꾸려면 `[project]` 아래에 `policy_repairs = N`을 직접 씁니다. 0이면 모델을 다시 부르지 않고 거부된 검사를 바로 버립니다.

### 체크포인트와 재개

- 체크포인트는 `<workdir>/.cora/projects/<run_id>/checkpoint.json`에 저장합니다. 같은 디렉터리의 `events.jsonl`에 이벤트 기록이 쌓입니다.
- 쓰기는 임시 파일에 쓰고 fsync한 뒤 원자적으로 바꿉니다. 쓰기 도중 실패해도 이전 체크포인트는 그대로 남습니다.
- 저장 시점은 마일스톤을 시작할 때와 끝날 때(완료, 실패, 중단)입니다.
- 체크포인트에는 계획(goal과 마일스톤), 완료된 마일스톤 id 목록, 현재 마일스톤, 마일스톤마다의 상태와 세션 id, 비용, 토큰, 모델, 도구 호출 수, 최종 답, 누적 예산 사용량, 마지막 정지 사유가 들어 있습니다.
- run id는 `YYYYmmdd-HHMMSS-xxxxxx` 형식(시각과 16진수 6자리)입니다. 실행이 시작되면 stderr에 `project run id: <run_id>`로 나옵니다. 이 값은 경로로 쓰이므로 이 형식만 받습니다.
- SIGKILL처럼 강제로 끝나면 체크포인트에는 완료된 마일스톤만 남습니다. 진행 중이던 마일스톤은 `resume`할 때 새 세션으로 처음부터 다시 실행합니다.
- `cora project resume RUN_ID`는 완료된 마일스톤을 호출 없이 건너뜁니다. 체크포인트에 저장된 계획을 쓰므로 계획 파일을 다시 줄 필요가 없습니다.
- 모든 마일스톤이 이미 완료된 실행을 재개하면 모델이나 도구를 호출하지 않고 종료 코드 0으로 끝납니다.
- 한 번의 실행 안에서 실패한 마일스톤을 자동으로 다시 시도하지 않습니다(`conditions` 게이트 재시도는 예외). 다시 하려면 `resume`을 실행합니다.
- 같은 run id를 두 프로세스가 동시에 재개하는 것은 지원하지 않습니다.

### 프로젝트 예산

- 프로젝트 전체에 예산 거버너가 하나 있습니다. 비용, 반복 횟수, 벽시계 시간, 도구 호출 수를 모든 마일스톤에 걸쳐 누적해서 셉니다.
- 재개할 때는 이전 실행까지의 누적값에서 이어서 셉니다. 그래서 긴 계획은 상한을 충분히 크게 줘야 합니다.
- 헤드리스 기본값(벽시계 900초, 도구 호출 200회)과 `[agent] max_iterations`(기본 30)도 프로젝트 전체에 적용됩니다.
- 상한에 닿으면 종료 코드 4로 끝나며 `stop_reason`은 `budget_exceeded`입니다. `budget.tripped`에 상한 이름이 나옵니다. 상한을 올린 뒤 `cora project resume`으로 이어 갈 수 있습니다.

### 프로젝트 JSON 결과

`--json`을 주면 결과 문서 한 줄을 stdout에 씁니다. 키는 헤드리스 결과와 같은 15개이며 값은 프로젝트 전체를 합산한 것입니다. `session_id`는 마지막으로 실행된 마일스톤의 세션입니다. 여기에 두 키가 더 있습니다.

- `run_id`: 체크포인트의 run id입니다. 계획 오류 때문에 체크포인트가 만들어지기 전에 끝났으면 null입니다.
- `milestones`: 계획 순서대로 `{"id", "status", "session_id", "cost_usd"}` 객체의 목록입니다. `status`는 `completed`, `failed`, `interrupted`, `pending` 중 하나입니다. 실행 중에 멈춰서 `running`으로 남은 마일스톤은 `interrupted`로 보입니다.
- `milestones`에서 `conditions`가 있는 마일스톤에는 `gate` 값이 붙습니다. `{"attempts", "passed", "failed_condition"}` 형식이며, 아직 도달하지 않았으면 null입니다. `conditions`가 없는 마일스톤에는 `gate` 키가 없습니다.
- `project run`의 오류 결과의 `cost_usd`는 오류까지 실행된 마일스톤 비용과 계획 비용의 합입니다. 완료된 마일스톤은 `status`가 `completed`인 것만 셉니다.
- `stop_reason`은 `gate_failed`가 될 수 있습니다(완료 조건이 재시도 뒤에도 통과하지 못함).
- `cora project plan --json` 문서의 키는 헤드리스 결과 키(profile 제외)에 `path`, `goal`, `milestone_count`, `plan_policy`를 더한 것입니다. 오류도 같은 키이며 종료 코드 2입니다(예산 초과는 4).

### 프로젝트 종료 코드

| 코드 | 의미 |
|---|---|
| 0 | 모든 마일스톤이 완료되었습니다. |
| 1 | 최종 답 없이 멈췄습니다. 검사 실패나 마일스톤 실패가 여기에 해당합니다. 완료 조건 게이트가 재시도 뒤에도 통과하지 못한 `gate_failed`도 여기에 해당합니다. |
| 2 | 계획 파일, 설정, 체크포인트 오류입니다. 알 수 없는 run id와 읽을 수 없는 체크포인트도 여기에 해당합니다. 계획 생성 실패(잘못된 응답 두 번, 제공자·계정 오류)와 잘못된 `conditions`도 여기에 해당합니다. |
| 4 | 예산 상한에 닿았습니다(`budget_exceeded`). |
| 5 | 정책 거부로 멈췄습니다(`policy_blocked`). |
| 130 | SIGINT로 중단했습니다(`interrupted`). |
| 143 | SIGTERM으로 중단했습니다(`interrupted`). |

### `[project]` 설정

| 키 | 기본값 | 뜻 |
|---|---|---|
| `gate_retries` | 1 | 완료 조건이 실패한 마일스톤을 새 세션으로 다시 실행하는 횟수입니다. 0이면 재시도하지 않습니다. |
| `max_milestones` | 8 | 계획 생성이 만들 수 있는 마일스톤 수의 상한입니다. |
| `condition_timeout_s` | 60 | 조건 명령 하나의 시간 제한(초)입니다. |
| `condition_output_chars` | 2000 | 실패한 조건 출력의 끝부분 중 재시도 피드백으로 남기는 글자 수입니다. |
| `policy_repairs` | 1 | 계획의 `check`/`command` 조건이 정책으로 거부되었을 때 수정을 요청하는 횟수입니다(0–3). 배포되는 `cora.toml`에는 적혀 있지 않으며 코드 기본값을 씁니다. 바꾸려면 `[project]` 아래에 `policy_repairs = N`을 씁니다. |

## MCP 서버로 실행 (`cora mcp serve`)

`cora mcp serve`는 CORA를 MCP 서버로 실행합니다. 클라이언트는 CORA 에이전트에게 작업을 맡기고 결과를 JSON으로 받습니다. 이 섹션은 서버 쪽 동작만 다룹니다. 클라이언트 설정 예시는 아래 `클라이언트 설정 예시`에 있습니다.

### 전송과 기본 동작

- 전송은 stdio만 지원합니다. 프로토콜 버전은 `2025-06-18`이며, 클라이언트가 다른 버전을 보내면 `2025-06-18`로 응답합니다.
- stdout에는 JSON-RPC 메시지만 나갑니다. 로그와 진단은 모두 stderr로 나갑니다.
- 표준 입력이 닫히면(EOF) 진행 중인 실행을 저장하고 종료 코드 0으로 끝납니다. 설정이 잘못되면(`[mcp]` 값이 범위를 벗어나거나 `approval`이 `ask` 또는 `auto`) 아무 응답 없이 종료 코드 2로 끝납니다.
- 지원하는 요청은 `initialize`, `ping`, `tools/list`, `tools/call`입니다. 알림은 `notifications/cancelled`만 처리하고 나머지는 무시합니다.
- 승인 모드는 `[mcp]`의 `approval` 키로만 정합니다. 명령행이나 도구 인자로는 바꿀 수 없습니다.

### 도구

`run_task` 인자입니다.

| 인자 | 타입 | 설명 |
|---|---|---|
| `task` | 문자열 | 필수입니다. 공백만 있으면 안 됩니다. |
| `max_cost_usd` | 숫자 | 이번 호출의 비용 상한(USD)입니다. 0이거나 없으면 서버 상한을 씁니다. |
| `max_iterations` | 정수 | 반복 횟수 상한입니다. 규칙은 같습니다. |
| `max_wall_s` | 숫자 | 벽시계 시간 상한(초)입니다. 규칙은 같습니다. |
| `max_tool_calls` | 정수 | 도구 호출 수 상한입니다. 규칙은 같습니다. |

`resume_session` 인자입니다.

| 인자 | 타입 | 설명 |
|---|---|---|
| `session_id` | 문자열 | 필수입니다. `list_sessions`가 준 세션 id입니다. |
| `task` | 문자열 | 선택입니다. 있으면 후속 작업으로 실행하고, 없으면 세션을 이어서 실행합니다. |
| 예산 키 | | `run_task`와 같은 네 가지 키(`max_cost_usd`, `max_iterations`, `max_wall_s`, `max_tool_calls`)를 받습니다. |

`list_sessions` 인자입니다.

| 인자 | 타입 | 설명 |
|---|---|---|
| `limit` | 정수 | 가져올 세션 수입니다. 기본값은 20이고 최대는 100입니다. 1 이상이어야 합니다. |

알 수 없는 인자나 잘못된 타입은 JSON-RPC 오류 -32602로 거부합니다.

도구 결과는 텍스트 블록 하나에 JSON 문서가 들어 있습니다. `run_task`와 `resume_session`의 문서 키는 `ok`, `stop_reason`, `final_answer`, `session_id`, `cost_usd`, `iterations`, `tokens`, `wall_s`, `budget`, `policy`, `warnings`, `truncated`입니다. 실패하면 `errors`에 사유가 들어가며, `isError`는 `ok`가 false일 때 true입니다. 정지 사유는 `final_answer`, `budget_exceeded`, `policy_blocked`, `interrupted`, `busy`, `depth_exceeded` 등입니다. `list_sessions`의 문서 키는 `sessions`, `count`, `total`, `cost_usd`, `truncated`입니다. `list_sessions`는 모델을 호출하지 않으므로 `cost_usd`는 0입니다.

### JSON-RPC 오류 코드

| 코드 | 뜻 |
|---|---|
| -32700 | 파싱 오류입니다. 줄이 JSON이 아닙니다. |
| -32600 | 잘못된 요청입니다. 배열(배치)이거나 `jsonrpc`가 `2.0`이 아니거나, 메시지가 너무 큽니다. |
| -32601 | 지원하지 않는 메서드입니다. |
| -32602 | 잘못된 인자이거나 알 수 없는 도구입니다. |

### `[mcp]` 설정

| 키 | 기본값 | 허용 범위 | 설명 |
|---|---|---|---|
| `max_cost_usd` | 0.5 | 0보다 큰 숫자 | 호출 하나의 비용 상한(USD)입니다. `resume_session`에서는 세션의 이전 누적 비용에 더해 셉니다. |
| `max_iterations` | 30 | 1 이상의 정수 | 반복 횟수 상한입니다. |
| `max_wall_s` | 600 | 0보다 큰 숫자 | 호출 하나의 벽시계 시간 상한(초)입니다. 클라이언트의 도구 시간 제한보다 작게 두세요. |
| `max_tool_calls` | 200 | 1 이상의 정수 | 도구 호출 수 상한입니다. |
| `max_depth` | 1 | 1 이상의 정수 | 재귀 가드 한도입니다(아래 재귀 가드 항목 참고). |
| `max_output_chars` | 20000 | 1000 이상 49999 이하 | 도구 결과 문서 하나의 글자 수 상한입니다. |
| `approval` | "policy" | `policy` 또는 `deny` | 승인 방식입니다. `ask`와 `auto`는 시작할 때 거부됩니다. |

서버 상한은 무제한이 될 수 없습니다. 0이나 음수는 설정 오류입니다.

### 예산 clamp

요청 인자의 예산 값은 서버 상한을 넘을 수 없습니다. 요청 값이 0이거나 없으면 서버 상한을 쓰고, 서버 상한보다 크면 서버 상한으로 줄입니다. 요청으로는 상한을 낮출 수만 있고 올릴 수는 없습니다. 상한에 닿으면 `budget_exceeded`로 끝나며 세션은 저장됩니다.

### 승인

승인은 `policy`(정책이 판정하고 묻지 않음)나 `deny`(모든 도구 호출 거부) 둘 중 하나입니다. 서버는 사람에게 묻지 않으므로 정책이 `ask`로 판정한 호출은 묻지 않고 거부합니다. 자동 승인(`auto`)은 서버에 없습니다. 정책 판정과 셸 제한은 자율 승인 정책 섹션과 같습니다.

### 재귀 가드

서버는 시작할 때 `CORA_MCP_DEPTH`를 읽어 깊이를 정합니다(없으면 0). 그리고 자기 환경의 값을 1 늘려 둡니다. 셸 명령과 MCP 자식 프로세스는 이 값을 그대로 받습니다. 깊이가 `max_depth` 이상이면 `run_task`와 `resume_session`을 거부하고 `stop_reason`이 `depth_exceeded`인 오류를 냅니다. `CORA_MCP_DEPTH`가 음이 아닌 정수가 아니면 같은 방식으로 거부합니다. `list_sessions`는 영향을 받지 않습니다. 서버가 끝나면 환경 변수는 원래 값으로 돌아갑니다.

### 한 번에 한 실행

실행은 한 번에 하나만 허용합니다. 실행 중에 다른 `run_task`나 `resume_session`이 오면 `busy` 오류로 즉시 거부합니다(`stop_reason`은 `busy`). `ping`, `tools/list`, `list_sessions`는 실행 중에도 바로 답합니다.

### 결과 길이 상한과 잘림

결과 문서의 텍스트가 `max_output_chars`를 넘으면 `final_answer`를 잘라 뒤에 `...[truncated: N more chars; full answer stored in session <id>]` 표시를 붙이고, `truncated`를 true로 둡니다. 정책 판정 목록은 `decisions_omitted` 개수로 대체하고, 경고와 오류는 10개까지만 각 300자씩 남깁니다. 전체 답은 `.cora/sessions/<id>/session.json`의 `final_answer`에 그대로 남습니다.

### 취소와 진행 알림

- 취소: 클라이언트가 `notifications/cancelled`를 보내고 `requestId`가 진행 중인 요청의 id와 같으면, 현재 도구 호출이 끝난 뒤 실행을 멈춥니다. 세션은 `interrupted`로 저장되며, 그 요청에는 응답을 보내지 않습니다. 다른 id의 취소 알림은 무시합니다.
- 진행: `tools/call`의 `_meta`에 `progressToken`이 있으면 실행 중 `notifications/progress`를 보냅니다. `progress`는 증가하는 정수이고, `message`에는 반복 횟수와 비용이 들어갑니다. 알림은 최대 1초에 한 번 나갑니다.

### 클라이언트 설정 예시

아래는 `.mcp.json` 예시입니다. API 키는 파일에 적지 말고 클라이언트의 환경 변수(`OPENROUTER_API_KEY`)로 넘기세요.

```json
{"mcpServers": {"cora": {"command": "cora", "args": ["mcp", "serve", "-w", "."]}}}
```

### 시간 제한 주의

- Claude Code: 도구 호출의 벽시계 제한은 약 28시간으로 알려져 있습니다(확인되지 않음). stdio 유휴 타이머는 30분이며 진행 알림으로 초기화됩니다.
- Claude Desktop: 도구 호출 제한이 약 60초라는 보고가 있습니다(확인되지 않음).
- 그래서 `max_wall_s`는 작게 두고, 긴 작업은 `resume_session`으로 나눠 실행하세요.

## 자율 승인 정책 (policy)

`--approval policy`나 REPL의 `/approval policy`로 켭니다. 이 모드에서는 정책이 도구 호출마다 허용(allow) 또는 거부(deny)를 정합니다. 사람에게 묻지 않으며, `ask` 규칙이 걸린 호출은 묻지 않고 거부로 처리합니다. 이 보호는 정책 수준의 confinement입니다. 인자 파싱, 경로 검사, 깨끗한 환경으로 막으며 OS 샌드박스가 아닙니다. 아래 한계 목록의 우회가 남습니다.

정책 모드가 아니더라도 `list_files`, `search`, `read_file`의 기본 동작이 바뀌었습니다. 이 변경은 모든 승인 모드(`ask`, `auto`, `deny`, `policy`)에 적용됩니다. `list_files`와 `search`는 이제 자격 증명 파일 이름(`.env`, `*.pem`, `id_rsa*` 등), 보호 경로, 워크스페이스 밖을 가리키는 심볼릭 링크를 결과에 넣지 않고 읽지도 않습니다. `read_file`로 이런 파일을 직접 지정하면 `denied: credential file: .env` 같은 오류로 거부합니다. `.env.example`, `.env.sample`, `.env.template`은 읽을 수 있습니다. 재귀 탐색은 셸의 `grep -r`나 `ls -R` 대신 이 도구를 쓰세요. 셸에서는 이런 재귀 옵션이 거부됩니다.

### 정책 파일 형식

정책은 `.cora/policy.toml`에서 읽습니다. 이 파일이 있으면 `cora.toml`의 `[policy]` 섹션을 대신하며, 두 곳을 합치지 않습니다. 파일의 최상위 키는 다음과 같습니다.

```toml
shell_confinement = true
sandbox = false
env_passthrough = []

[[rules]]
id = "allow-api-curl"
decision = "allow"
command = "curl https://api.example.com/*"
```

- `rules`: 규칙 목록입니다(`[[rules]]` 표). 규칙마다 `id`, `decision`, `tool`, `group`, `command` 중 하나 이상을 씁니다. `id`는 고유해야 하며 `default`, `floor:`, `confine:`, `strict:`로 시작할 수 없습니다. `decision`은 `allow`, `ask`, `deny` 중 하나입니다. `tool`, `group`, `command`는 문자열이나 문자열 목록이고 `*`, `?`, `[...]` 글롭을 씁니다.
- `command`는 셸 명령을 나눈 각 구간(세그먼트)에 맞춥니다. 공백은 한 칸으로 줄여서 비교합니다. 예를 들어 `"curl https://api.example.com/*"`은 그 주소로 가는 `curl` 구간에만 맞습니다.
- `shell_confinement`: `true`면 `run_shell` 명령을 정적 검사로 확인합니다. 기본값은 `false`입니다. policy 모드와 e2e strict 프로파일에서는 항상 켜집니다.
- `sandbox`: `true`면 macOS에서 `sandbox-exec`로 셸 명령을 감쌉니다. 기본값은 `false`입니다.
- `env_passthrough`: 셸 명령 환경에 넘길 변수 이름 목록입니다. `API_KEY`, `TOKEN`, `SECRET`, `PASSWORD`처럼 자격 증명으로 보이는 이름은 오류가 납니다.

정책이 거부한 도구 호출은 모델에게 `denied by policy (...)` 관찰 메시지와 그 아래 `Hint:` 한 줄로 돌아갑니다. 힌트 문구는 계획 단계가 쓰는 것과 같은 `RULE_HINTS` 표에서 가져옵니다. 판정(허용/거부)과 거부 횟수 집계는 바뀌지 않습니다. 힌트는 도구 호출의 거부에만 붙습니다. 샌드박스 검사(`check`)와 마일스톤 완료 조건의 거부는 기존 메시지를 그대로 씁니다. `deny` 모드에서 사용자가 거부한 `denied by user: approval required for ...`에는 힌트가 붙지 않습니다.

- `[policy] prompt_rules`: 기본값은 `false`입니다. `cora.toml`의 `[policy]` 표에서만 읽으며 `.cora/policy.toml`에서는 알 수 없는 키로 거부합니다. `true`이고 정책 게이트가 활성일 때만 셸 정책 규칙(`render_policy_rules`)을 주 에이전트와 하위 에이전트 시스템 프롬프트 끝에 `Shell policy for run_shell:` 제목으로 덧붙입니다. 유료 근거가 생기기 전까지 `false`로 둡니다. 값이 bool이 아니거나 알 수 없는 키가 있으면 종료 코드 2로 끝납니다.

잘못된 정책 파일이나 규칙은 조용히 허용하지 않습니다. 알 수 없는 키, 잘못된 `decision`, 중복된 `id`, 비어 있는 패턴이 있으면 CLI는 종료 코드 2로 끝나며 모델을 호출하지 않습니다.

### 판정 순서와 구체성

1. 하한(hard) 검사를 먼저 합니다. 여기에 걸리면 규칙이 있어도 거부하며 풀 수 없습니다.
2. 셸 명령의 소프트 항목은 사용자의 `allow` 규칙이 그 구간에 맞으면 통과합니다. strict 프로파일은 풀지 않습니다.
3. 규칙은 두 계층으로 봅니다. 사용자 규칙이 먼저이고 내장 기본 규칙이 나중입니다. 한 계층 안에서는 `deny`, `ask`, `allow` 순서로 보며, 같은 결정 안에서는 구체성이 높은 규칙이 이깁니다. 구체성은 `command`가 있는 규칙, 리터럴 글자가 많은 패턴, 정확한 도구 이름, `tool`이 있는 규칙, `group`이 있는 규칙 순서입니다. 구체성까지 같으면 설정 파일에서 먼저 쓴 규칙이 이깁니다.
4. 맞는 규칙이 없으면 거부합니다(`default`).
5. 셸 명령은 구간마다 판정하고, 가장 엄한 결과를 그 명령의 결과로 씁니다.

### 내장 기본 정책

| 도구 | 기본 판정 | 규칙 id |
|---|---|---|
| `list_files`, `read_file`, `search`, `git_status`, `git_diff`, `git_log`, `todo_write`, `submit_plan`, `delegate` | 허용 | `default:read-tools` |
| `edit_file` | 허용(경로 검사를 거침) | `default:edit` |
| `write_file` | 허용(경로 검사를 거침) | `default:edit` |
| `delete_file` | 승인 필요(ask) | `default:delete` |
| `git_add`, `git_commit`, `git_branch` | 묻기(policy 모드에서는 거부) | `default:git-write` |
| `web_fetch` | 묻기(policy 모드에서는 거부) | `default:web` |
| `mcp__*` | 묻기(policy 모드에서는 거부) | `default:mcp` |
| `run_shell` | 허용 목록에 맞는 명령만 허용 | `default:shell` |
| 그 밖의 도구 | 거부 | `default` |

`run_shell`의 허용 목록은 다음과 같습니다. `pytest`, `python -m pytest`, `python3 -m pytest`, `python -m unittest`, `python3 -m unittest`, `uv run pytest`, `uv run ruff`, `ruff`, `python -m ruff`, `python3 -m ruff`, git의 조회 하위 명령(`status`, `diff`, `log`, `show`, `branch`의 조회 형태), `ls`, `cat`, `grep`, `head`, `tail`, `wc`, `pwd`, `echo`, 그리고 워크스페이스 안의 `.py` 스크립트를 `python` 또는 `python3`로 실행하는 형태입니다. 위 목록에 없는 명령은 거부합니다.

### write_file과 delete_file

- `write_file`은 파일을 새로 만들거나 덮어씁니다. `append = true`이면 파일 끝에 내용을 덧붙이고, 디렉터리가 없으면 만듭니다. 큰 파일은 나눠서 씁니다. 첫 조각은 `write_file`로 쓰고, 나머지 조각은 `append = true`로 이어 씁니다.
- `delete_file`은 워크스페이스 안의 일반 파일 하나만 지웁니다. 디렉터리는 지우지 않습니다.
- 두 도구는 `edit_file`과 같은 경로 검사를 거칩니다. 보호 경로와 자격 증명 파일은 쓰거나 지울 수 없습니다.
- 대화형 승인에서는 두 도구 모두 diff를 보여 줍니다.
- e2e strict 프로파일은 `write_file`과 `delete_file`을 모두 허용합니다. 셸 허용 목록은 바뀌지 않았습니다.

### 하한과 풀 수 있는 항목

풀 수 없는 하한(hard)은 다음과 같습니다.

- 워크스페이스 밖 경로, 심볼릭 링크로 밖을 가리키는 경로, 절대경로 탈출
- 보호 경로: `~/.config/cora`, `~/.ssh`, `~/.aws`, `~/.gnupg`, `~/.netrc`, `~/.git-credentials`, `~/.pypirc`, `~/.npmrc`, `~/.docker`, `~/.kube`, `.git/config`, 설치된 패키지 데이터(`src/cora/data`와 e2e 과제의 채점 디렉터리, 정답 디렉터리 포함)
- 자격 증명 파일 이름: `.env`, `.env.*`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `id_rsa*`, `id_ed25519*`, `.netrc`, `.git-credentials`, `.pypirc`, `.npmrc`, `credentials.json` 등
- 쓰기 보호: `.git`, `.cora` 디렉터리, `cora.toml`, `.envrc`
- 셸 치환(`$(...)`, 백틱, `<(...)`), here-doc, `~`, 허용되지 않은 환경 변수 대입, 파이프로 실행 파일에 넘기는 형태

풀 수 있는 소프트 항목은 사용자의 `allow` 규칙으로 허용할 수 있습니다(strict 프로파일은 제외). 인라인 코드 실행(`python -c`, `awk` 프로그램 등, `confine:one-liner`), 옵션 표 밖의 옵션, 금지 옵션, 재귀 옵션, `git`의 외부 프로그램 실행, 네트워크 명령이 여기에 듭니다. 예를 들어 `curl`은 기본 정책에 없으므로 기본적으로 거부됩니다. 아래처럼 `allow` 규칙을 쓰면 그 주소로 가는 호출만 허용됩니다.

```toml
[[rules]]
id = "allow-api-curl"
decision = "allow"
command = "curl https://api.example.com/*"
```

풀기로 한 항목은 사용자가 받아들인 능력입니다. 소프트 항목을 풀면 그 명령이 옵션이나 재귀 같은 능력을 얻습니다.

### 셸 confinement

- 명령은 `&&`, `||`, `;`, `|` 등으로 구간을 나누고 구간마다 판정합니다.
- 허용 목록의 프로그램(`ls`, `cat`, `grep`, `egrep`, `fgrep`, `head`, `tail`, `wc`, `pwd`, `echo`, `pytest`, `ruff`)은 프로그램별 옵션 표로 파싱합니다. 옵션 표에 없는 옵션, 금지 옵션, 값을 받지 않는 옵션에 값이 붙은 형태는 모두 거부합니다(fail-closed). 긴 옵션의 줄임 형태도 표에 있는 것만 받습니다.
- 금지 구문: `$(...)`, 백틱, `<(...)`, `eval`, `source`, `sh -c`, `python -c`, `xargs`, `find -exec`, `tar -C`, `git -C`, `cd`, `$HOME`, `~`, here-doc입니다. 위에서 말한 대로 구문마다 풀 수 있는지가 다릅니다.
- `python -m`은 `pytest`, `ruff`, `unittest` 모듈만 허용합니다. 그 뒤의 인자는 같은 `pytest`나 `ruff` 옵션 표로 다시 검사합니다(`uv run`도 `pytest`와 `ruff`만 허용합니다). `python script.py`는 워크스페이스 안 스크립트에 한해 허용합니다. 스크립트 안의 동작은 검사하지 않습니다.
- 재귀 금지: `grep -r`, `grep -R`, `ls -R`처럼 하위 디렉터리로 내려가는 옵션은 거부합니다. `search`나 `list_files`를 쓰세요.
- `git grep`의 페이저 옵션(`-O`와 그 줄임 형태)은 거부합니다. `git`은 하위 명령 허용 목록을 따릅니다.
- 파이프 뒤쪽(싱크)은 `head`, `tail`, `wc`만 허용합니다.
- `echo`도 금지 구문과 경로 검사를 그대로 받습니다.
- 환경 변수 대입(`NAME=값`)은 `PYTHONHASHSEED`, `PYTHONDONTWRITEBYTECODE`, `PYTHONUTF8`, `TZ`, `LANG`, `LC_*`, `TERM`, `NO_COLOR`, `PY_COLORS`, `FORCE_COLOR`, `COLUMNS`, `LINES`만 허용하고, 값에 `/`나 `..`, 글롭이 들어가면 안 됩니다. 나머지는 거부합니다.
- `[policy] shell_confinement = true`로 `ask`와 `auto`에서도 셸 confinement를 켤 수 있습니다. 이때 허용 목록 밖의 프로그램은 일반 경로 검사만 받습니다. 옵션 표가 있는 프로그램은 모든 모드에서 표로 검사합니다.
- `/check`로 실행하는 검사 명령도 같은 규칙을 받습니다.

### 환경 정리와 sandbox-exec

셸 명령은 깨끗한 환경에서 실행합니다. 넘기는 변수는 `PATH`, `LANG`, `LANGUAGE`, `LC_*`, `TERM`, `TZ`, `TMPDIR`, `USER`, `LOGNAME`, `SHELL`, `VIRTUAL_ENV`, `NO_COLOR`, `PYTHONIOENCODING`과 `env_passthrough`뿐입니다. 자격 증명으로 보이는 이름은 넘기지 않습니다. `HOME`은 `.cora/home`으로 바꾸며, 작업 디렉터리는 워크스페이스입니다.

`[policy] sandbox = true`이면 macOS에서 `sandbox-exec`로 셸 명령을 감쌉니다. 기본값은 꺼짐입니다. e2e strict 프로파일은 `sandbox-exec`를 쓸 수 있으면 자동으로 켭니다. 쓸 수 없으면 경고를 내고 정책 계층만 적용합니다. macOS가 아닌 시스템에는 OS 샌드박스가 없고 인자 파싱 계층만 쓰기를 막습니다.

### 기록과 요약

- `policy_decision`: 판정마다 한 번 기록합니다. 도구, 인자 요약, 판정(`allow`, `ask`, `deny`), 규칙 id, 이유, 모드, 최종 결과(`allow`, `deny`, `approval`)를 담습니다.
- `policy_summary`: 세션이 끝날 때 한 번 기록합니다. 키는 `mode`, `source`, `allow`, `ask`, `deny`, `ask_resolved_deny`, `decisions`, `decisions_dropped`입니다. `decisions`는 최대 200건이고 넘친 건수는 `decisions_dropped`에 셉니다.
- `policy_warning`: sandbox-exec를 쓸 수 없을 때의 경고 문장입니다.
- `cora run`과 `cora -p`는 끝날 때 stderr에 `policy: mode=... allow=... ask=... deny=...` 줄을 한 번 씁니다.
- e2e 보고서의 `policy_denies`, `policy_asks`, `policy`는 `human_interventions`와 별도입니다.

### 한계와 남는 우회

이 정책은 정적 검사이며 OS 샌드박스가 아닙니다. 다음 우회가 남습니다.

- 허용된 `python script.py`는 워크스페이스 안 스크립트라면 임의의 파일을 읽고 쓸 수 있습니다. 스크립트 내용은 검사하지 않습니다.
- 허용된 테스트 실행기(`pytest`, `python -m unittest`, `uv run pytest`)는 테스트 코드를 통해 임의의 코드를 실행할 수 있습니다. `python -m unittest <모듈>`은 워크스페이스 심볼릭 링크를 거쳐 이미 밖을 가리키는 모듈을 읽을 수 있습니다. 기본 정책은 `ln -s`를 거부하지만, 이미 있는 링크는 막지 않습니다.
- 워크스페이스 안에 스크립트나 실행 파일을 만들어 실행하는 것을 막지 않습니다.
- 실행 중에 만들어지는 경로(변수, 계산된 문자열, 다른 파일이 가리키는 경로)는 정적 검사로 보이지 않습니다.
- TOCTOU: 검사하는 시점과 실행하는 시점 사이에 파일 시스템이 바뀔 수 있습니다.
- 네트워크를 막지 않습니다. OS 방화벽이 없으므로 허용된 명령과 `allow` 규칙으로 허용된 명령은 네트워크에 접근할 수 있습니다.
- 워크스페이스 안의 재귀 읽기는 `list_files`와 `search`로 할 수 있습니다. 보호 경로와 자격 증명 파일 이름만 제외됩니다.
- 사용자가 `allow` 규칙으로 소프트 항목(옵션, 재귀, 인라인 코드, 네트워크 등)을 풀면 그 능력을 받아들인 것입니다.
- `git diff`, `git log -p`, `git show`는 경로 인자 없이 쓰면 추적 중인 파일의 내용을 출력합니다. 자격 증명 파일이 추적되고 있다면 그 내용도 나옵니다.
- macOS가 아니면 OS 샌드박스가 없습니다. 인자 파싱 계층이 유일한 쓰기 장벽입니다.
- cora 체크아웃에서 작업할 때는 `src/cora/data`가 보호 대상입니다.

## 설정

설정 파일은 다음 순서로 찾습니다. 먼저 맞는 것을 씁니다.

1. `--config`로 지정한 파일
2. 현재 디렉터리의 `./cora.toml`
3. `~/.config/cora/cora.toml`
4. 내장 기본값 `src/cora/data/cora.toml`

주요 섹션은 다음과 같습니다.

- `[providers.openrouter]`: `api_key_env`에 키를 읽을 환경 변수 이름을 씁니다. 기본값은 `OPENROUTER_API_KEY`입니다.
  - `timeout_s`(기본 120): 응답을 기다리는 읽기 시간입니다.
  - `request_deadline_s`(기본 90): HTTP 시도 하나의 전체 시간 상한입니다. 본문 바이트가 계속 와도 이 시간이 지나면 끊습니다. 네트워크 오류와 같은 규칙으로 재시도하며, 최대 2번까지 1초와 2초를 기다린 뒤 다시 보냅니다. 그래도 실패하면 오류로 끝납니다.
  - `stream_stall_timeout_s`(기본 30): 스트리밍에서 데이터 조각이 이 시간 동안 오지 않으면 그 시도를 끊습니다. 재시도 규칙은 같습니다. 답변 일부가 이미 출력된 뒤에는 중복 출력을 막기 위해 재시도하지 않습니다.
  - `provider_sort`(선택): `throughput`, `latency`, `price` 중 하나이며 요청의 `provider.sort`로 보냅니다. 설정하지 않으면 아무것도 보내지 않습니다. 다른 값이면 설정을 읽을 때 오류로 끝납니다.
  - `require_parameters`(선택): `true` 또는 `false`입니다. `true`로 설정하면 요청의 `provider.require_parameters`로 보내고, 요청의 파라미터를 모두 지원하는 엔드포인트로만 라우팅합니다. 미설정이면 요청이 바뀌지 않습니다(기본 동작 그대로). 이 설정은 제공자 전체에 적용되며 모델별로 나뉘지 않습니다. 다른 값이면 설정을 읽을 때 오류로 끝납니다.
  - `provider_ignore`(선택): OpenRouter 제공자 슬러그 목록입니다 (예: `["amazon-bedrock"]`). 설정하면 요청의 `provider.ignore`로 보내고, OpenRouter는 그 제공자의 엔드포인트로 라우팅하지 않습니다. 슬러그는 OpenRouter 모델 엔드포인트 목록(`api/v1/models/<모델>/endpoints`)의 `tag` 앞부분입니다 (예: `amazon-bedrock/us-west-2` → `amazon-bedrock`). 미설정이면 요청이 바뀌지 않습니다. 제공자 전체, 즉 같은 실행의 모든 OpenRouter 모델에 적용됩니다. 빈 목록, 중복, 소문자 슬러그가 아닌 값이면 설정을 읽을 때 오류로 끝납니다.
- `[[models]]`: 사용할 모델 목록입니다. `id`, `tier`, 가격, `context_tokens`, `supports_tools`를 적습니다. 모델별 `tool_protocol`도 줄 수 있습니다.
  - 기본 cheap 모델은 첫 cheap 항목인 `google/gemini-2.5-flash-lite`(입력 USD 0.10, 출력 USD 0.40, 100만 토큰당, 컨텍스트 1,048,576 토큰)입니다. strong 모델은 OpenRouter의 `deepseek/deepseek-v3.2`입니다. qwen, mistral, deepseek 모델 ID는 카탈로그에 그대로 남아 있습니다.
  - strong 모델 가격은 100만 토큰당 입력 USD 0.28, 출력 USD 0.42, 캐시 읽기 USD 0.028입니다(OpenRouter 모델 목록, 2026-10-18). 이전 값은 0.26 / 0.38 / 0.14였고, 이 값은 `.ensemble/research/strong-tier-model.md`의 C5 범위(입력 0.21~0.28, 출력 0.31~0.42, 캐시 읽기 0.02~0.14) 안에 있습니다. 모델 ID와 가격은 목록으로 확인했고, 완료 호출로 실측한 것은 아닙니다.
  - `moonshotai/kimi-k2-0905`는 더 이상 strong이 아닙니다. 기존 핀과 과거 기록용으로 `tier = "cheap"` 항목에 남아 있고, 첫 cheap 항목이 아니므로 기본 cheap 모델은 바뀌지 않습니다.
  - 기본 모델(cheap과 strong)은 모두 OpenRouter를 쓰므로 `OPENROUTER_API_KEY`가 필요합니다. 키가 없으면 `cora run`은 종료 코드 2로 끝나고 오류 메시지에 `OPENROUTER_API_KEY`를 씁니다.
  - Gemini 무료 티어 모델은 `[router] pin`이나 `/model`로 고를 수 있지만 기본 모델이 되지 않습니다.
  - 근거는 단일 파일 과제 11개, react, 과제당 1회 시도입니다. gemini-2.5-flash-lite는 11/11이었고 해결당 $0.00144, 과제당 약 10초였습니다. gpt-4o-mini는 7/11, gpt-4.1-nano는 3/11이었습니다. qwen3-coder-30b는 10~11/11이었고 과제당 약 35~62초였습니다. OpenRouter 통계에서 gemini-2.5-flash-lite는 제공자 5곳에서 약 150~190 tok/s, qwen3-coder-30b는 제공자 1곳에서 약 19 tok/s로 보였습니다. 이것은 방향성 증거이며 추후 재검증할 예정입니다. 자세한 내용은 `.docs/bench-results.md`를 보세요.
- `[router]`와 `[router.grades]`: 요청 등급(simple, medium, complex)을 티어 이름 또는 모델 ID에 연결합니다.
  - 라우팅 동작:
    - 신호는 네 가지입니다: 400자 이상, 코드 작업 키워드, 파일/코드 참조, 여러 단계. 신호마다 1점입니다.
    - `threshold = 3`이므로 `complex`는 4개 신호 중 3개 이상이 있어야 합니다. `medium_threshold = 1`입니다.
    - simple과 medium은 cheap, complex는 strong으로 갑니다. 기본 경로는 cheap입니다.
    - 파일 하나를 고치는 보통 작업(ordinary)은 cheap으로 갑니다.
    - 라벨이 붙은 프롬프트 집합은 `tests/data/router_prompts.toml`이고, 이전과 새 점수의 표는 `.docs/bench-results.md`에 있습니다.
- `[agent]`: `approval`(`ask`, `auto`, `deny`, `policy`), `max_iterations`, `max_cost_usd`, `max_wall_s`, `max_tool_calls`, `budget_warn_fraction`, `tool_protocol`(`react`, `native`, `auto`), `sensor_max_retries`, `tripwire`, `lenient_parse`, `auto_check`, `tamper_guard`, `selftest`, `ladder`를 설정합니다. 예산 상한의 뜻은 예산 상한 섹션을 보세요.
  - `lenient_parse`(기본값 `true`): 엄격한 ReAct 파싱이 실패했을 때만 복구를 시도합니다. 엄격 파싱이 성공한 응답은 바뀌지 않습니다. 복구 순서는 코드 펜스 제거(`strip_fences`), 산문 제거(`strip_prose`), 작은따옴표를 큰따옴표로(`single_quotes`), 끝 쉼표 제거(`trailing_commas`), 문자열 입력을 첫 인자로 감싸기(`wrap_string_input`), 중괄호 블록 추출(`extract_braces`)입니다. `wrap_string_input`의 인자 이름은 도구의 첫 필수 인자이며, 필수 인자가 없으면 첫 속성입니다. 속성이 없는 도구는 건너뜁니다. 계획 생성(`cora project plan`, `project run --goal`)의 JSON에도 적용됩니다.
  - 복구가 일어나면 `parse_repaired` 이벤트(`repairs` 목록 포함)가, 복구도 실패하면 `parse_error` 이벤트가 남습니다.
  - `repeat_breaker`가 켜져 있으면 반복을 감지할 때 `repeat_detected` 이벤트(`iteration`, `kind`, `count`)가 남습니다.
  - `false`면 엄격 파싱만 씁니다. 잘못된 값(true/false가 아닌 값)이면 설정 오류로 종료 코드 2입니다.
  - 위임 하위 에이전트는 `lenient_parse`와 상관없이 항상 엄격 파싱을 씁니다.
  - `react_max_tokens`(기본값 `4096`): ReAct 모델 호출 한 번의 출력 토큰 상한입니다. 256~32768 범위의 정수여야 하며, 아니면 종료 코드 2입니다. 응답이 상한에서 잘리고 도구 호출 형식이 맞지 않으면 도구는 실행하지 않고 "잘렸다"는 관측 메시지를 모델에 돌려줍니다. 이때 `reply_truncated` 이벤트(`iteration`, `output_tokens`, `max_tokens`)가 남습니다.
- `[headless]`: `cora run --headless`와 `--json` 실행의 벽시계 시간(`max_wall_s`, 기본 900)과 도구 호출 수(`max_tool_calls`, 기본 200) 상한입니다. 비용과 반복 횟수는 `[agent]`를 따릅니다.
- `[policy]`: 자율 승인 정책입니다. 자세한 내용은 자율 승인 정책 섹션을 보세요. `.cora/policy.toml`이 있으면 이 섹션 대신 그 파일을 씁니다.
- `[memory]`: 대화 컨텍스트의 예산과 보존 기준을 설정합니다.
  - `ledger`(기본값 `false`): true면 고정된 작업 상태 원장(ledger)을 씁니다. 원장은 편집한 파일(경로, 편집 횟수, 마지막 반복), 실행한 검사(명령, 통과/실패, 반복, 결과 끝부분 짧게), 결정(게이트, 반성, 에스컬레이션, `tests_modified`, 잘림/파싱 거부)을 기록합니다. 모델 호출은 하지 않으며 축출되지 않습니다. 보호 경로는 `<protected>`로, 비밀 값은 `<redacted>`로 표시됩니다.
  - `ledger_max_chars`(기본값 1500, 범위 200-20000): 원장의 글자 수 상한입니다. 오래된 통과 검사와 편집 횟수부터 압축하며, 가장 최근 검사와 편집한 파일 경로는 남깁니다.
  - `summarize`: `"off"` 또는 `"llm"`, 기본값 `"off"`. `"llm"`이면 메시지가 축출될 때만 저비용 모델을 부르며, 축출 한 번당 최대 한 번입니다. 입력은 상한이 있고 파일 내용은 제외합니다. 이 호출은 계측되고 예산 상한의 통제를 받으며, 실패하면 결정론적 원장으로 대체합니다. `ledger = false`여도 허용되며, 이때는 요약 한 줄만 남깁니다.
  - 잘못된 값이거나 `[memory]`에 알 수 없는 키가 있으면 종료 코드 2입니다.
  - 이벤트: `ledger_update`, `ledger_evict_note`, `summary_call`.
- `[context]`: 저장소 규모 컨텍스트(저장소 맵, 중복 읽기 제거)를 설정합니다. 모두 기본값 꺼짐(false)입니다.
- `[cache]`: 프롬프트 비용 스위치(프롬프트 캐시 표시, 짧은 도구 설명, 관찰 압축)를 설정합니다. 모두 기본값 꺼짐입니다. 자세한 내용은 프롬프트 비용 스위치 섹션을 보세요.
- `[delegation]`: 실험적 기능인 하위 에이전트 위임입니다. 기본값은 꺼짐이며 `enabled = true` 또는 `--delegate`로 켭니다. 병렬 explore 키(`parallel_explore`, `explore_concurrency`, `explore_max_calls`, `max_total_tokens`, `max_total_cost_usd`, `summary_max_chars`)도 여기서 설정합니다. 자세한 내용은 위임 섹션을 보세요.
- `[tools]`: `@` 멘션, git 도구, web 도구의 출력 상한을 설정합니다.
- `[tool_groups]`: 꺼 둘 도구 그룹(`disabled`)과 `auto_simple`을 설정합니다.
- `[decider]`: 라우팅, 도구 그룹, 센서 힌트에 쓰는 결정기를 설정합니다. 기본값은 휴리스틱이며 사용처는 모두 꺼져 있습니다. 자세한 내용은 결정기 섹션을 보세요.
- `[sale]`: 실험적 기능인 SALE-lite 라우팅(plan 기반 bid)입니다. 기본 설정 파일에는 없으며 없으면 꺼짐(`enabled = false`)으로 동작합니다. 자세한 내용은 SALE-lite 라우팅 섹션을 보세요.
- `[ui]`: 터미널 화면 표시를 설정합니다. `theme`(기본 `default`; `default`, `dark`, `light`, `mono`. `mono`는 색 없이 글리프만 씁니다), `ascii`(기본 false; true면 `●` 같은 글리프 대신 `*`, `|_`, `[x]` 같은 ASCII 문자를 씁니다. 출력 인코딩이 UTF가 아니면 자동으로 ASCII를 씁니다), `color`(기본 `auto`; `auto`는 터미널일 때만 색, `never`는 색 없음, `always`는 터미널이 색 지원을 알리지 않아도 색을 씁니다). `NO_COLOR` 환경 변수가 있으면 `color`와 상관없이 색을 쓰지 않습니다. 파이프 출력과 `cora -p`는 `color = "always"`여도 평문입니다. 잘못된 값이면 설정을 읽을 때 오류로 끝납니다(종료 코드 2). `mono`는 CORA가 칠하는 색만 끄므로 답변 마크다운의 색까지 끄려면 `NO_COLOR` 또는 `color = "never"`를 쓰세요. TUI 관련 키는 다음과 같습니다. `tui`(기본 true; false면 클래식 인라인 REPL), `mouse`(기본 true; TUI 시작 때 마우스 캡처를 켜서 휠이 대화 영역을 스크롤함. false면 터미널 기본 선택을 쓰지만 휠이 입력 기록을 움직일 수 있음), `exit_summary`(기본 true; false면 TUI 종료 뒤 요약을 출력하지 않음), `scrollback_blocks`(기본 5000; TUI 대화 블록의 상한이며 100 이상이어야 하고, 넘으면 오래된 것부터 버림).
- `[bench]`: `cora bench --live`의 기본 모델, 프로토콜, 상한을 설정합니다. `models` 목록은 `google/gemini-2.5-flash-lite`로 시작하며, `--ab`도 이 목록의 첫 모델을 씁니다. `stall_threshold_s`(기본 60)로 지연 호출을 표시하는 기준(초, 0보다 커야 함)을 정합니다.
- `[mcp.servers.<name>]`: MCP stdio 서버입니다. 기본 설정에는 없습니다. 자세한 내용은 MCP 서버 섹션을 보세요.

`.cora/`에는 실행 중 생기는 파일이 들어갑니다. 이 디렉터리는 `.gitignore`에 들어 있습니다.

- `models.toml`: `/model`로 저장한 티어 모델 설정입니다.
- `history`: REPL 입력 기록입니다.
- `sessions/`: 저장된 세션입니다. `/sessions`와 `/resume`이 여기를 읽습니다.
- `policy.toml`: 자율 승인 정책 파일입니다. 있으면 `cora.toml`의 `[policy]`를 대신하며 두 곳을 합치지 않습니다.
- `home/`: 셸 명령의 `HOME`으로 쓰는 디렉터리입니다. 정책 모드와 e2e strict 프로파일에서 만듭니다.
- `index/repomap.json`: 저장소 맵의 캐시입니다. `[context].repo_map`이 켜져 있을 때만 씁니다.

### 저장소 규모 컨텍스트 (`[context]`)

이 기능은 `cora.toml`의 `[context]` 섹션에서만 설정합니다. 이 기능을 위한 CLI 옵션은 없습니다. 모든 키의 기본값은 꺼짐이므로, 설정하지 않으면 프롬프트와 작업 메모리는 이 기능이 생기기 전과 같습니다.

- `repo_map`(기본값 false): 시스템 프롬프트에 작업 공간의 간략한 맵을 넣습니다. 맵은 파일마다 한 줄이며, 작업 공간 기준 상대 경로, 바이트 크기, 최상위 Python 함수와 클래스 이름을 보여 줍니다. 실행(`run`)이나 이어하기(`resume`)마다 한 번만 만들고, 반성 재시도에서는 같은 맵을 다시 씁니다.
- `repo_map_max_chars`(기본값 4000): 맵 텍스트의 글자 수 상한입니다. 넘으면 앞쪽 줄부터 남기고 `[repo map truncated]` 표시를 붙입니다. 같은 입력이면 항상 같은 결과가 나옵니다. 0보다 큰 정수여야 합니다.
- `max_files`(기본값 500): 맵에 넣을 파일 수의 상한입니다. 상한에 닿으면 그 뒤의 파일은 맵에 들어가지 않습니다. 0보다 큰 정수여야 합니다.
- `dedupe_reads`(기본값 false): 같은 파일을 `read_file`로 다시 읽으면 이전 읽기 결과를 `[superseded: <path> read again later]` 표시로 바꿉니다. 가장 최근 읽기 결과는 그대로 남습니다. 파일 하나의 결과를 담은 단일 관찰에만 적용합니다. 한 메시지에 여러 도구 결과가 묶인 다중 행동 관찰과 이미 요약으로 밀려난 줄은 바꾸지 않습니다.

맵에는 `PathGuard`가 막는 파일(자격 증명과 보호 경로 포함)이 들어가지 않습니다. `.git`과 `.cora` 디렉터리도 건너뜁니다. 맵은 파일 내용을 넣지 않고, Python 파일만 구문 분석해 심볼 이름을 얻습니다. 구문 분석에 실패하거나 바이너리인 파일은 경로와 크기만 나옵니다.

캐시는 `.cora/index/repomap.json`에 저장합니다. 캐시 항목은 경로, mtime, 크기를 키로 삼으며, 바뀌었거나 새로 생긴 파일만 다시 구문 분석합니다. 삭제된 파일은 캐시에서도 빠집니다. 캐시 파일을 읽거나 해석하지 못하거나 버전이 다르면 빈 캐시로 시작합니다. `.cora/`는 `.gitignore`에 들어 있습니다.

하위 에이전트(위임)와 이어하기한 세션도 같은 `[context]` 설정을 따릅니다. 토큰 절감 효과는 오프라인에서만 측정했습니다. `tests/test_context_agent.py`가 `tests/repo_fixture.py`로 만든 저장소에서 OFF, 맵, 중복 제거, 둘 다 켠 경우의 요청 토큰 합을 비교하며, 네 경우 모두 최종 답은 같습니다. 실제 모델 호출로는 검증하지 않았으며, 기본값은 꺼짐으로 둡니다.

### 프롬프트 비용 스위치 (`[cache]`)

이 기능은 `cora.toml`의 `[cache]` 섹션과 `[[models]]` 항목에서만 설정합니다. 이 기능을 위한 CLI 옵션은 없습니다. 모든 스위치의 기본값은 꺼짐이므로, 설정하지 않으면 요청 본문, 도구 설명, 작업 메모리는 이 기능이 생기기 전과 같습니다.

- `prompt_cache`(기본값 false): 시스템 프롬프트에 캐시 표시를 붙입니다. `cache = true`인 모델에만 적용됩니다.
- `tool_descriptions`(`"full"`/`"terse"`, 기본값 `"full"`): `terse`이면 내장 도구 설명을 60자 이하의 짧은 문장으로 바꿉니다. 네이티브 도구 스키마의 설명은 이 짧은 문장만 담고, react 프롬프트는 짧은 문장 뒤에 인자 설명(`Args:`)을 붙입니다.
- `compress_observations`(기본값 false): `[memory].keep_last_messages`보다 오래된 관찰을 앞뒤만 남기고 줄입니다.
- `compress_chars`(기본값 800, 0보다 큰 정수): 줄인 관찰마다 앞뒤로 남기는 글자 수입니다.

모델별 키는 `[[models]]` 항목에 씁니다.

- `cache = true`(기본값 false): 명시적 캐시 표시를 쓰는 모델(Anthropic, Qwen 계열)에 켭니다. 자동으로 캐시하는 모델은 켤 필요가 없습니다. 기본 카탈로그에는 이 키가 없습니다.
- `cache_read_usd_per_mtok`(선택): 캐시 읽기 단가(100만 토큰당 달러)입니다. 없으면 캐시 토큰도 입력 단가로 계산하며 새 금액을 추정하지 않습니다.

와이어 형식: `prompt_cache`가 켜져 있고 모델이 `cache = true`이면 첫 시스템 메시지를 `cache_control`이 붙은 블록 배열(`[{"type":"text","text":..., "cache_control":{"type":"ephemeral"}}]`)로 보냅니다. 다른 메시지는 바뀌지 않습니다. 제공자가 이 형식을 거부하면 `prompt_cache`를 끄세요. 자동 재시도는 없습니다.

계측: 응답의 `prompt_tokens_details.cached_tokens`를 `cached` 토큰으로 기록합니다. 값이 0보다 클 때만 요약(`cached=N`)과 결과의 `tokens`에 표시합니다.

비용: 캐시 읽기 단가를 알 때만 캐시 토큰을 그 단가로 계산합니다. 단가를 모르면 비용은 바뀌지 않습니다. 제공자가 비용을 보고하면 그 값을 씁니다. 캐시 쓰기 할증은 가격 계산에 넣지 않는 한계가 있습니다.

압축 표시: 줄인 관찰에는 `[compressed: N chars omitted]` 표시가 들어갑니다. 다음 메시지는 줄이지 않습니다: 가장 최근 관찰, 같은 파일의 가장 최근 읽기, 관찰이 아닌 메시지(사용자 작업, 시스템 프롬프트 등).

범위: 하위 에이전트(위임)와 이어하기한 세션도 같은 `[cache]` 설정을 따릅니다. 효과는 오프라인에서만 측정했습니다(`tests/test_cache_agent.py`, `tests/test_cache_terse.py`). 실제 모델 호출로는 검증하지 않았으며, 기본값은 꺼짐으로 둡니다.

## 개발

- 테스트: `uv run pytest`
- 실제 호출을 하는 테스트: `uv run pytest --run-live`입니다. 실제 호출이 일어나고 비용이 들며 `OPENROUTER_API_KEY`가 필요합니다.
- 린트: `uv run ruff check src tests`

`src/cora/core/prerouter.py`는 실험용 사전 라우터이며 미연결 상태입니다. 설정 키가 없고 기본 동작을 바꾸지 않습니다. 결과는 `.docs/bench-results.md`의 M19e 절에 있습니다.
