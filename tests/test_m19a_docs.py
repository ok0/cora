import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / ".docs" / "bench-results.md"
MIRROR = ROOT / "tests" / "fixtures" / "m19" / "preregistration.md"
PART1_RE = r"^## M19 사전 등록 \(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\)$"
PART2_RE = r"^## M19 사전 등록 2부 \(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\)$"
TITLES_1 = [
    "판정 기준",
    "분류와 indeterminate 규칙",
    "비용 우위 규칙",
    "최선 구성 (best configuration)",
    "상보성 (oracle / union)",
    "팔 레시피",
    "팔 b 한도 의미 (ADR-33)",
    "같은 한도 해석",
    "P1 결정 규칙",
    "하네스 (ADR-32)",
    "절단 순서와 실행 규칙",
    "중단 규칙",
    "수정 규칙",
]


def _section(text: str, heading_regex: str) -> str:
    match = re.search(heading_regex, text, re.M)
    assert match is not None
    rest = text[match.start():]
    nxt = re.search(r"^## ", rest[1:], re.M)
    end = len(rest) if nxt is None else nxt.start() + 1
    return rest[:end].rstrip("\n")


def test_prereg_part1_heading():
    mirror = MIRROR.read_text(encoding="utf-8")
    bench = BENCH.read_text(encoding="utf-8")
    assert len(re.findall(PART1_RE, mirror, re.M)) == 1
    assert len(re.findall(PART1_RE, bench, re.M)) == 1


def test_prereg_part1_items():
    section = _section(MIRROR.read_text(encoding="utf-8"), PART1_RE)
    for token in [
        "0.70",
        "0.40",
        "2.0",
        "N = 3",
        "indeterminate",
        "oracle",
        "union",
        "W_lo",
        "S_cc",
        "claude-code-m19.toml",
        "--verify-attempts 3",
        "ladder = false",
        "1.5",
        "not measured (budget)",
        "A20",
        "tests/fixtures/m19/preregistration.md",
    ]:
        assert token in section, token
    for title in TITLES_1:
        assert f"### {title}" in section, title


def test_prereg_part1_no_tbd():
    section = _section(MIRROR.read_text(encoding="utf-8"), PART1_RE)
    for word in ["TBD", "미정", "to be decided", "결정 예정"]:
        assert word not in section, word


def test_prereg_part1_mirror_identical():
    assert _section(MIRROR.read_text(encoding="utf-8"), PART1_RE) == _section(
        BENCH.read_text(encoding="utf-8"), PART1_RE
    )


def test_no_key_material():
    for path in (BENCH, MIRROR):
        assert re.search(r"sk-or-[A-Za-z0-9_-]{8,}", path.read_text(encoding="utf-8")) is None


def test_mirror_tracked():
    result = subprocess.run(
        ["git", "check-ignore", "-q", str(MIRROR)], cwd=ROOT, check=False
    )
    assert result.returncode == 1


def test_q7_record():
    bench = BENCH.read_text(encoding="utf-8")
    part1 = re.search(PART1_RE, bench, re.M)
    assert part1 is not None
    q7_heading = "## M19a Q7 모델 목록 확인 ("
    q7_index = bench.find(q7_heading)
    assert q7_index > part1.start()
    section = _section(bench, r"^## M19a Q7 모델 목록 확인 \(")
    for model_id in [
        "google/gemini-2.5-flash-lite",
        "deepseek/deepseek-v3.2",
        "qwen/qwen3-coder-30b-a3b-instruct",
        "mistralai/mistral-small-3.2-24b-instruct",
        "openai/gpt-4o-mini",
    ]:
        assert model_id in section, model_id
    assert "https://openrouter.ai/api/v1/models" in section


def test_prereg_part2():
    mirror = MIRROR.read_text(encoding="utf-8")
    matches = list(re.finditer(PART2_RE, mirror, re.M))
    assert len(matches) == 1
    part1 = re.search(PART1_RE, mirror, re.M)
    assert matches[0].start() > part1.start()
    section = _section(mirror, PART2_RE)
    for title in [
        "패널",
        "팔 설정 차이",
        "호출 목록",
        "예상 비용과 절단선",
        "Claude Code 일정",
        "사용자 확인 기록",
        "M19 유료 호출 목록 (R19 일괄 확인용)",
        "M19a 종료 기준",
    ]:
        assert f"### {title}" in section, title
    assert "not measured (budget)" in section
    assert "402" in section
    assert "checkpoint 2" in section or "체크포인트 2" in section


def test_prereg_part2_mirror_identical():
    assert _section(MIRROR.read_text(encoding="utf-8"), PART2_RE) == _section(
        BENCH.read_text(encoding="utf-8"), PART2_RE
    )


def test_mirror_amendments_identical():
    mirror = MIRROR.read_text(encoding="utf-8")
    bench = BENCH.read_text(encoding="utf-8")
    for match in re.finditer(r"^## M19 사전 등록 수정 \(", mirror, re.M):
        heading = mirror[match.start():].split("\n", 1)[0]
        pattern = r"^" + re.escape(heading) + r"$"
        assert _section(mirror, pattern) == _section(bench, pattern), heading


def test_cost_plan():
    bench = BENCH.read_text(encoding="utf-8")
    assert re.search(r"^## M19a 비용 계획 \(", bench, re.M) is not None
    section = _section(bench, r"^## M19a 비용 계획 \(")
    assert "bench plan" in section
    assert "2026-10-22 09:11" in section


def test_probe_confirmations_recorded():
    section = _section(BENCH.read_text(encoding="utf-8"), r"^## M19a 탐침 \(probe\) \(")
    assert "실행 (Recommended)" in section
    assert "m3 넣으세요" in section
    assert "원문은 편집자 입력에 없습니다" not in section
    assert "열린 항목으로 두고" not in section


def test_arm_first_cut_list():
    section = _section(BENCH.read_text(encoding="utf-8"), r"^## M19a 비용 계획 \(")
    assert "3b. strict arm-first" in section
    assert "6.5678" in section
    assert "c_cc(m1→m2)" in section


def test_amendment_items():
    section = _section(
        MIRROR.read_text(encoding="utf-8"),
        r"^## M19 사전 등록 수정 \(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\)$",
    )
    for token in ["R17", "n = 3", "55496cf", "claude-code-m19.toml", "2026-10-18T08:03:40Z"]:
        assert token in section, token

