#!/usr/bin/env python3
"""Evaluation harness (build step 4): runs every question in test_questions.json
through the live agent and checks the answer against ground-truth-derived
assertions, then reports a pass/fail table and overall pass rate.

Usage:
  python3 eval/run_eval.py                          # run everything
  python3 eval/run_eval.py --ids scenario_02,edge_01_legitimate_empty_result
  python3 eval/run_eval.py --sleep 5                 # gentler pacing on rate limits

This does NOT replace manual scenario verification (used to build the checks
below) - it's a regression net: run it after any prompt/schema/graph change to
catch answers that silently got worse.
"""
import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.graph import ask  # noqa: E402

ROOT = Path(__file__).resolve().parent
QUESTIONS_PATH = ROOT / "test_questions.json"
RESULTS_DIR = ROOT / "results"


def _contains(text: str, item: str) -> bool:
    """Word-boundary, case-insensitive containment check. Plain substring matching
    would false-positive on our ID scheme (e.g. 'RM1' is a substring of 'RM10',
    'C1' is a substring of 'C10'), so every check must respect token boundaries."""
    return re.search(r"\b" + re.escape(item) + r"\b", text, re.IGNORECASE) is not None


def check_answer(answer: str, confidence: str | None, checks: dict) -> list[str]:
    """Returns a list of human-readable failure reasons; empty list means pass."""
    failures = []
    answer = answer or ""

    if "confidence_in" in checks and confidence not in checks["confidence_in"]:
        failures.append(f"confidence={confidence!r} not in {checks['confidence_in']}")

    for item in checks.get("must_include_all", []):
        if not _contains(answer, item):
            failures.append(f"missing required text: {item!r}")

    for key in ("must_include_any", "must_include_any_2"):
        options = checks.get(key)
        if options and not any(_contains(answer, opt) for opt in options):
            failures.append(f"none of {options} found (needed at least one)")

    for item in checks.get("must_exclude", []):
        if _contains(answer, item):
            failures.append(f"forbidden text present: {item!r}")

    return failures


def run(test_cases: list[dict], sleep_seconds: float) -> list[dict]:
    results = []
    for i, case in enumerate(test_cases):
        t0 = time.monotonic()
        try:
            state = ask(case["question"])
            answer = state.get("answer") or ""
            confidence = state.get("confidence")
            reasoning_log = state.get("reasoning_log", [])
            error = None
        except Exception as exc:  # noqa: BLE001 - a crash is itself a failure to record, not to raise
            answer, confidence, reasoning_log, error = "", None, [], str(exc)
        latency_s = round(time.monotonic() - t0, 1)

        failures = [f"agent raised an exception: {error}"] if error else check_answer(answer, confidence, case["checks"])
        passed = not failures

        results.append({
            "id": case["id"],
            "scenario": case["scenario"],
            "question": case["question"],
            "passed": passed,
            "confidence": confidence,
            "latency_s": latency_s,
            "answer": answer,
            "failures": failures,
            # kept for post-hoc debugging of a failure without needing to re-run the
            # question (each entry has node/engine_used/model/latency_ms + node-specific
            # detail like cypher_query/sql_query/valid/reason)
            "reasoning_log": reasoning_log,
        })

        icon = "PASS" if passed else "FAIL"
        print(f"[{i+1}/{len(test_cases)}] {icon}  {case['id']}  ({latency_s}s, confidence={confidence})")
        if not passed:
            for f in failures:
                print(f"         - {f}")

        if i < len(test_cases) - 1:
            time.sleep(sleep_seconds)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", help="comma-separated list of test ids to run (default: all)")
    parser.add_argument("--sleep", type=float, default=3.0, help="seconds to sleep between questions (default 3)")
    args = parser.parse_args()

    test_cases = json.loads(QUESTIONS_PATH.read_text())
    if args.ids:
        wanted = set(args.ids.split(","))
        test_cases = [c for c in test_cases if c["id"] in wanted]
        missing = wanted - {c["id"] for c in test_cases}
        if missing:
            print(f"Warning: unknown test ids ignored: {missing}")

    if not test_cases:
        print("No test cases selected.")
        sys.exit(1)

    print(f"Running {len(test_cases)} evaluation questions...\n")
    results = run(test_cases, args.sleep)

    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    print(f"\n{'=' * 60}")
    print(f"RESULT: {passed}/{total} passed ({100 * passed / total:.0f}%)")
    if passed < total:
        print("Failed:", ", ".join(r["id"] for r in results if not r["passed"]))

    RESULTS_DIR.mkdir(exist_ok=True)
    out_path = RESULTS_DIR / f"eval_run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps({
        "run_at": datetime.now(timezone.utc).isoformat(),
        "pass_count": passed,
        "total_count": total,
        "results": results,
    }, indent=2))
    print(f"Full report written to {out_path.relative_to(ROOT.parent)}")


if __name__ == "__main__":
    main()
