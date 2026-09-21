"""Small shared helpers for parsing LLM output."""
import json
import re


def strip_code_fence(text: str) -> str:
    text = text.strip()
    match = re.match(r"^```(?:\w+)?\n(.*)\n```$", text, re.DOTALL)
    return match.group(1).strip() if match else text


def extract_json(text: str) -> dict:
    """Extracts the first {...} JSON object from an LLM response, tolerating
    surrounding prose or code fences."""
    text = strip_code_fence(text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"No JSON object found in: {text!r}")
    return json.loads(text[start : end + 1])
