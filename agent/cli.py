"""Manual one-shot runner: python3 -m agent.cli "your question here"

Prints the plain-English answer plus a full reasoning trace (query_type, any
Cypher/SQL generated, simulation params, and which LLM engine/latency each
step used) — useful for manually validating the 12 required scenarios against
ground truth before the eval harness (build step 4) exists.
"""
import json
import sys

from .graph import ask


def main() -> None:
    if len(sys.argv) < 2:
        print('Usage: python3 -m agent.cli "your question here"')
        sys.exit(1)

    question = " ".join(sys.argv[1:])
    final_state = ask(question)

    confidence_icon = {"high": "🟢", "estimated": "🟡", "low": "🔴"}.get(final_state.get("confidence"), "🔴")

    print(f"\nQ: {question}\n")
    print(f"{confidence_icon} {final_state.get('answer')}\n")
    print("--- reasoning trace ---")
    for entry in final_state.get("reasoning_log", []):
        print(json.dumps(entry, indent=2, default=str))


if __name__ == "__main__":
    main()
