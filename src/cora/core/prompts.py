from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

ACTION_RULE_SINGLE = "one action per response"
ACTION_RULE_PARALLEL = (
    "one action per response, except that independent read-only actions (such as list_files, "
    "read_file, search) may be batched by repeating the Action/Action Input pair; they run in "
    "parallel and you get numbered Observations in the same order"
)

SYSTEM_TEMPLATE = (
    """You are CORA, a cost-efficient coding and research agent working inside the """
    """directory: {workspace}.
Solve the task by interleaving short reasoning with tool use.

Available tools:
{tools}

Respond in EXACTLY one of these two formats.
To use a tool:
Thought: <brief reasoning>
Action: <tool name>
Action Input: <one JSON object with the tool arguments>

To finish:
Thought: <brief reasoning>
Final Answer: <answer for the user>

"""
    """Rules: {action_rule}; never write "Observation:" yourself; """
    """paths are relative to the workspace; """
    """keep thoughts short.{reflections}"""
)

NATIVE_SYSTEM_TEMPLATE = (
    """You are CORA, a cost-efficient coding and research agent working inside the """
    """directory: {workspace}.
Solve the task by calling the provided tools. {call_rule}
When the task is complete, reply with your final answer as plain text and no tool calls.
Rules: paths are relative to the workspace; keep reasoning short.{reflections}"""
)
NATIVE_CALL_SINGLE = "Call one tool per response."
NATIVE_CALL_PARALLEL = (
    "Independent read-only calls (list_files, read_file, search) may be made together in "
    "one response; they run in parallel."
)

PLAN_MODE_NOTE = (
    "\n\nPLAN MODE is on: only read-only tools run; edits, shell, git changes and "
    "web_fetch are refused. Investigate, then call submit_plan with a concise step-by-step plan, "
    "then give a one-line final answer."
)

SUBAGENT_NOTE = (
    "\n\nYou are a sub-agent handling one narrow subtask for another agent. Work only on that "
    "subtask, use as few steps as possible, and finish with a short Final Answer summarizing "
    "what you found (key file paths and facts). You cannot delegate."
)

EXPLORE_NOTE = (
    "\n\nYou are a read-only explore sub-agent answering one narrow question for another agent. "
    "Only the tools listed above exist (no edits, no shell, no delegation). "
    "Use as few steps as possible and finish with a Final Answer of at most {max_chars} "
    "characters: key file paths and facts only."
)

DELEGATE_NUDGE = (
    "\n\nIf the task needs information spread over many files that it does not name, send each "
    'independent lookup to `delegate` with mode "explore" (several in one response '
    "run in parallel); you get back short summaries and keep your own context small."
)

REFLECTIONS_BLOCK ="\n\nLessons from previous failed attempts (apply them):\n{items}"

REPO_MAP_BLOCK = (
    "\n\nRepository map (workspace-relative path (bytes): top-level Python symbols). "
    "Use it to choose which files to read; read a file before relying on its contents.\n{map}"
)

REFLECT_TEMPLATE = (
    """You attempted a task and failed.

Task:
{task}

Your last steps:
{trajectory}

Failure signal:
{failure}

"""
    """In at most 5 sentences, diagnose the cause of the failure and state a concrete plan """
    """for the next attempt. Do not restate the task."""
)


def build_system_prompt(
    workspace: Path,
    tools_description: str,
    reflections: Sequence[str],
    project_context: str = "",
    parallel: bool = False,
    protocol: str = "react",
    plan_mode: bool = False,
    repo_map: str = "",
    selftest: bool = False,
    nudge: bool = False,
) -> str:
    block = ""
    if reflections:
        items = "\n".join(f"- {r}" for r in reflections)
        block = REFLECTIONS_BLOCK.format(items=items)
    if plan_mode:
        block = block + PLAN_MODE_NOTE
    if selftest:
        block = block + SELFTEST_NOTE
    extra = project_context + (REPO_MAP_BLOCK.format(map=repo_map) if repo_map else "")
    tail = DELEGATE_NUDGE if nudge else ""
    if protocol == "native":
        return (
            NATIVE_SYSTEM_TEMPLATE.format(
                workspace=workspace,
                reflections=block,
                call_rule=NATIVE_CALL_PARALLEL if parallel else NATIVE_CALL_SINGLE,
            )
            + extra
            + tail
        )
    return (
        SYSTEM_TEMPLATE.format(
            workspace=workspace,
            tools=tools_description,
            reflections=block,
            action_rule=ACTION_RULE_PARALLEL if parallel else ACTION_RULE_SINGLE,
        )
        + extra
        + tail
    )


POLICY_RULES_HEADER = "\n\nShell policy for run_shell:\n"


def policy_rules_suffix(rules: str) -> str:
    return POLICY_RULES_HEADER + rules if rules else ""


SENSOR_FEEDBACK = (
    "Observation: the check command failed, so the task is not finished yet "
    "(check run {run} of at most {max_runs}).\nCheck: {command}\nOutput (last {chars} chars):\n"
    "{output}\nFix the cause, then give your final answer again."
)
TRIPWIRE_NOTE = (
    "Observation: the same {kind} error happened {count} times in a row. Do not "
    "repeat the same action; a stronger model now continues. Try a different approach."
)
ESCALATION_NOTE = (
    "Observation: this run moved to a stronger model ({trigger}). Earlier steps did not "
    "finish the task. Check the current files, then continue with a different approach."
)
TRIPWIRE_STOP = (
    "tripwire: the same {kind} error ({name}) repeated {count} times {why}; stopped "
    "to avoid a loop. Last error: {head}"
)
SELFTEST_NOTE = (
    "\n\nNo check command is configured for this task. Before your final answer, write a few "
    "focused pytest tests for your change under .cora/selftest/ (for example "
    ".cora/selftest/test_task.py, created with edit_file and an empty old). Never put these "
    "tests in the workspace's own test locations. They are run with: "
    "python -m pytest -q .cora/selftest; failures are reported back as feedback."
)
SELFTEST_FEEDBACK = (
    "Observation: your self-test under .cora/selftest failed (soft feedback; your final answer "
    "was kept).\nCommand: {command}\nOutput (last {chars} chars):\n{output}"
)
TESTS_MODIFIED = (
    "tests_modified: pre-existing test files were changed or deleted: {files}. Restore them; "
    "do not edit existing tests to make the check pass."
)

REPEAT_WHAT = {
    "same_reply": "you sent the same reply twice in a row",
    "parse_error": "your reply could not be parsed twice in a row",
    "edit_mismatch": "edit_file could not find 'old' in the same file twice in a row",
}
REPEAT_FEEDBACK = (
    "Repetition detected: {what}; sending it again will fail the same way. "
    "Change the approach: {alternatives}."
)
REPEAT_ALT_RAW = (
    "put the file text in a raw block (<<<CONTENT ... CONTENT>>>, or <<<OLD ... OLD>>> and "
    "<<<NEW ... NEW>>>) instead of a JSON string"
)
REPEAT_ALTS = (
    "make a smaller edit_file that changes only a few lines",
    "re-read the file with read_file and copy the exact lines",
    "write a large file in parts (write_file, then write_file with append=true)",
)


def repeat_feedback(kind: str, raw_blocks: bool) -> str:
    alts = ((REPEAT_ALT_RAW,) if raw_blocks else ()) + REPEAT_ALTS
    return REPEAT_FEEDBACK.format(what=REPEAT_WHAT[kind], alternatives="; ".join(alts))
