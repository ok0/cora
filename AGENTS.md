# CORA 작업 규칙
- 세션 시작 시 .docs/paper-digest.md만 읽는다. .reference/ 와 논문을 다시 전체 색인하지 않는다(재색인 금지 규칙 참조).
- 아키텍처: .docs/architecture.md, 환경: .docs/environment.md.
- 코어(src/cora/core)는 cora.cli / cora.bench / typer 를 import 하지 않는다.
- API 키는 환경변수로만. 커밋 금지.
- 테스트: 빠른 실행 `uv run pytest` / 전체 실행 `uv run pytest --full` (커밋 전 필수, 검증자는 --full 한 번). 작업 중에는 관련 테스트만 (`uv run pytest tests/test_x.py -k ...`).
