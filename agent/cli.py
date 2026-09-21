"""Manual one-shot runner: python3 -m agent.cli "your question here" [--jev]

Prints the plain-English answer plus a full reasoning trace (query_type, any
Cypher/SQL generated, simulation params, and which LLM engine/latency each
step used) — useful for manually validating the 12 required scenarios against
ground truth before the eval harness (build step 4) exists.

If the question triggers human_approval_gate (a disruption recommendation), this
auto-approves it (a CLI debug tool has no UI to click Approve/Reject) and says so.
"""
import json
import sys
import uuid

from langgraph.types import Command

from .graph import ask, get_graph


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--jev"]
    use_jev = "--jev" in sys.argv[1:]
    if not args:
        print('Usage: python3 -m agent.cli "your question here" [--jev]')
        sys.exit(1)

    question = " ".join(args)
    thread_id = str(uuid.uuid4())
    final_state = ask(question, thread_id=thread_id, use_jev=use_jev)

    if "__interrupt__" in final_state:
        rec = final_state["__interrupt__"][0].value
        print(f"\n🔔 Approval needed: {rec.get('description')}")
        print("(CLI auto-approves for demo purposes - use the Streamlit UI to actually decide)")
        run_config = {"configurable": {"thread_id": thread_id}}
        final_state = get_graph().invoke(Command(resume={"approved": True, "note": "CLI auto-approved"}), run_config)

    confidence_icon = {"high": "🟢", "estimated": "🟡", "low": "🔴"}.get(final_state.get("confidence"), "🔴")

    print(f"\nQ: {question}\n")
    print(f"{confidence_icon} {final_state.get('answer')}\n")
    print("--- reasoning trace ---")
    for entry in final_state.get("reasoning_log", []):
        print(json.dumps(entry, indent=2, default=str))


if __name__ == "__main__":
    main()
