"""Original two-mode styling and speech instructions."""

REVIEW_SCHEMA = """{
  "overall_score": 0,
  "verdict": "",
  "suits_user": false,
  "fit_score": 0,
  "proportion_score": 0,
  "color_harmony_score": 0,
  "style_score": 0,
  "quality_cues_score": 0,
  "occasion_guess": "",
  "key_strengths": [],
  "key_issues": [],
  "quick_improvements": [],
  "reasoning_long": "",
  "reasoning_short": ""
}"""

# ----------------------------
# Prompts
# ----------------------------
def build_image_to_text_decide_prompt(output_schema: str) -> str:
    """
    Decide prompt: user is wearing ONE new item (or a clearly highlighted main item).
    Output: JSON only, purchase recommendation based solely on the photo.
    """
    return f"""
You are a fashion assistant. The user provided ONE photo of themselves wearing a clothing item they are considering buying.

TASK:
- Analyze ONLY what is visible in the photo (no web browsing, no guessing about the user's preferences, wardrobe, budget, or brand unless clearly visible).
- Evaluate whether the user should buy the item based on: fit, proportions, how flattering it is on their body, color harmony with their visible features (skin/hair), style impact, versatility inferred from the item itself, and visible quality cues.
- Output ONLY valid JSON that matches this exact schema (same keys, no extra keys): {output_schema}

OUTPUT RULES:
- JSON only (no markdown, no commentary).
- Integers only for all *_score fields and overall_score.
- Score ranges:
  - overall_score: 0 to 100
  - all *_score: 1 to 10
- Arrays: max 4 items each, concise phrases.
- verdict must be exactly one of: "buy", "maybe", "skip"
- suits_user must be true/false based on the photo (fit + harmony + overall effect).
- reasoning_long: max 240 characters, one paragraph, practical and direct.
- reasoning_short: max 60 characters.

SCORING GUIDANCE (use the photo):
- fit_score: how well the garment fits (too tight/loose, pulling, bunching, shoulder seams, waist placement).
- proportion_score: whether it balances the user's silhouette (length, rise/waist position, sleeve/hem placement).
- color_harmony_score: how the color works with the user's visible coloring (contrast, washing out, clashes).
- style_score: how strong/coherent the style looks on the user (modern, intentional, cohesive).
- quality_cues_score: visible fabric/structure cues (sheen, drape, wrinkles, puckering seams, cheap-looking hardware, lining).

VERDICT LOGIC:
- "buy" if overall_score >= 78 and key_issues are minor/fixable.
- "maybe" if overall_score between 60-77 or needs tailoring/styling to shine.
- "skip" if overall_score < 60 or major fit/flattery issues.

Return ONLY the JSON object.
""".strip()


def build_image_to_text_outfit_prompt(output_schema: str) -> str:
    """
    Rate prompt: user is wearing an outfit (multiple pieces).
    Output: JSON only, score + review, does it suit them.
    Same schema keys as decide for consistent downstream handling.
    """
    return f"""
You are a fashion assistant. The user provided ONE photo of themselves wearing an outfit.

TASK:
- Analyze ONLY what is visible in the photo (no web browsing, no guessing about the user's preferences, wardrobe, or brand unless clearly visible).
- Evaluate how well the outfit suits the user: fit, proportions, color harmony, style cohesion, and visible quality/finish.
- Output ONLY valid JSON that matches this exact schema (same keys, no extra keys): {output_schema}

OUTPUT RULES:
- JSON only (no markdown, no commentary).
- Integers only for all *_score fields and overall_score.
- Score ranges:
  - overall_score: 0 to 100
  - all *_score: 1 to 10
- Arrays: max 4 items each, concise phrases.
- verdict must be exactly one of: "wear", "tweak", "avoid"
- suits_user must be true/false based on the photo.
- reasoning_long: max 240 characters, one paragraph, practical and direct.
- reasoning_short: max 60 characters.

SCORING GUIDANCE (use the photo):
- fit_score: fit across the outfit (shoulders, waist, hems, bunching/pulling).
- proportion_score: balance of top/bottom volumes, lengths, waist placement, leg line.
- color_harmony_score: whether colors work with each other AND the user’s visible coloring.
- style_score: cohesion/intentionality (do pieces look like they belong together).
- quality_cues_score: visible construction/finish (drape, wrinkles, shine, footwear condition, obvious cheap cues).

VERDICT LOGIC:
- "wear" if overall_score >= 78.
- "tweak" if overall_score between 60-77 (good base, needs styling fixes).
- "avoid" if overall_score < 60.

Return ONLY the JSON object.
""".strip()


def build_text_to_audio_prompt() -> str:
    """
    Instructions for TTS: we are NOT asking for analysis here.
    We want a clear spoken delivery of the already-produced review.
    """
    return """
You are a voice stylist reading a fashion verdict to the user.
Speak clearly and naturally. Sound helpful, confident, and concise.
Avoid reading raw JSON. Do not mention scores as “underscore”.
Keep it under ~20 seconds when possible.
""".strip()


