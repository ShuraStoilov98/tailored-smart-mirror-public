"""Validate model output and convert a verified review to a spoken script."""
import json

from .errors import InvalidReview
from .prompts import REVIEW_SCHEMA

REVIEW_FIELDS = json.loads(REVIEW_SCHEMA)


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidReview("Duplicate review fields.")
        result[key] = value
    return result


def validate_review(text: str, mode: str) -> dict:
    """Reject malformed/provider-invented fields before rendering or speaking."""
    if mode not in {"rate", "decide"}:
        raise InvalidReview("Unknown review mode.")
    try:
        review = json.loads(text, object_pairs_hook=_unique_fields)
    except (json.JSONDecodeError, TypeError) as exc:
        raise InvalidReview("Invalid review JSON.") from exc
    schema = REVIEW_FIELDS
    if not isinstance(review, dict) or set(review) != set(schema):
        raise InvalidReview("Unexpected review fields.")
    for key in schema:
        value = review[key]
        if key.endswith("_score"):
            minimum, maximum = (0, 100) if key == "overall_score" else (1, 10)
            if type(value) is not int or not minimum <= value <= maximum:
                raise InvalidReview("Invalid review score.")
        elif key == "suits_user":
            if type(value) is not bool:
                raise InvalidReview("Invalid suitability value.")
        elif isinstance(schema[key], list):
            if not isinstance(value, list) or len(value) > 4 or any(
                not isinstance(item, str) or len(item) > 160 for item in value
            ):
                raise InvalidReview("Invalid review list.")
        else:
            maximum = {"reasoning_long": 240, "reasoning_short": 60}.get(key, 160)
            if not isinstance(value, str) or len(value) > maximum:
                raise InvalidReview("Invalid review text.")
    verdicts = {"buy", "maybe", "skip"} if mode == "decide" else {"wear", "tweak", "avoid"}
    if review["verdict"] not in verdicts:
        raise InvalidReview("Invalid verdict.")
    return review


def review_json_to_spoken_text(review: dict, mode: str) -> str:
    """
    Converts the JSON review into a short spoken script for TTS.
    """
    # Fallback defaults
    overall = review.get("overall_score")
    verdict = review.get("verdict", "")
    suits = review.get("suits_user")
    short = review.get("reasoning_short", "")
    strengths = review.get("key_strengths") or []
    issues = review.get("key_issues") or []
    fixes = review.get("quick_improvements") or []

    # Keep it brief and friendly for audio
    if mode == "decide":
        verdict_line = {
            "buy": "My verdict: buy it.",
            "maybe": "My verdict: maybe—close, but not perfect.",
            "skip": "My verdict: skip it.",
        }.get(verdict, f"My verdict is: {verdict}.")
    else:
        verdict_line = {
            "wear": "This outfit is a strong wear.",
            "tweak": "This outfit is good, but needs a tweak.",
            "avoid": "I’d avoid this outfit as-is.",
        }.get(verdict, f"My verdict is: {verdict}.")

    suit_line = ""
    if isinstance(suits, bool):
        suit_line = "It suits you well." if suits else "It doesn’t flatter you as much as it could."

    # Compact bullet-like speech without sounding robotic
    parts = []
    if isinstance(overall, int):
        parts.append(f"Score: {overall} out of 100.")
    parts.append(verdict_line)
    if suit_line:
        parts.append(suit_line)

    if short:
        parts.append(short)

    if strengths:
        parts.append(f"Best part: {strengths[0]}.")
    if issues:
        parts.append(f"Main issue: {issues[0]}.")
    if fixes:
        parts.append(f"Quick fix: {fixes[0]}.")

    # Final cleanup
    script = " ".join([p.strip() for p in parts if str(p).strip()])
    return script.strip()


