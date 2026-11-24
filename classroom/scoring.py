"""Rubric scoring of student contributions with Claude.

The whole discussion goes in, in order, with the instructor's prompts and unidentified
speakers kept as context, because whether a comment "builds on others" depends on what
came before it. Only identified student contributions are scored.

These scores are suggestions for the instructor, not grades. The prompt tells the
model to judge substance and ignore fluency, accent, grammar and transcription errors,
and not to reward length.
"""
from __future__ import annotations

import json

import anthropic

from .config import Config
from .contribution import Contribution

SYSTEM = """You help a business-school instructor review class discussion. You get a \
transcript of one session, split into numbered contributions with the speaker's role. \
Score each STUDENT contribution on the rubric, 1 (absent) to 5 (excellent), from what \
was said.

Rules:
- Judge substance only. Ignore fluency, accent, grammar, filler words and speech-to-text \
errors; the transcript is automatic and will contain mistakes.
- Do not reward length. A short, sharp point can score 5; a long one can score 1.
- "builds_on_others" needs a link to something an earlier speaker said.
- One plain sentence of summary and one of rationale per contribution. No praise words \
like "great" or "excellent" in the text.
- Score every student contribution id you are given, and no others."""


def _dims(cfg: Config) -> list[str]:
    return [r.split(":", 1)[0].strip() for r in cfg.rubric]


def _schema(dims: list[str]) -> dict:
    item_props = {"id": {"type": "string"}, "summary": {"type": "string"},
                  "rationale": {"type": "string"}}
    item_props.update({d: {"type": "integer"} for d in dims})
    return {
        "type": "object",
        "properties": {
            "contributions": {"type": "array", "items": {
                "type": "object", "properties": item_props,
                "required": list(item_props), "additionalProperties": False}},
            "session_themes": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["contributions", "session_themes"],
        "additionalProperties": False,
    }


def _transcript(contribs: list[Contribution], course_context: str) -> str:
    lines = []
    if course_context:
        lines += [f"Course and session context: {course_context}", ""]
    for c in contribs:
        if c.kind == "short":
            continue
        role = {"student": "STUDENT", "instructor": "INSTRUCTOR"}.get(c.kind, "UNIDENTIFIED")
        tag = f"[{c.id}] {role}" + (f" ({c.speaker_name})" if c.kind == "student" else "")
        lines.append(f"{tag}: {c.text}")
    return "\n".join(lines)


def score(contribs: list[Contribution], cfg: Config, course_context: str = "",
          client: anthropic.Anthropic | None = None) -> dict:
    """Returns {"scores": {contribution_id: {...}}, "session_themes": [...], "model": str}."""
    student_ids = [c.id for c in contribs if c.kind == "student"]
    if not student_ids:
        return {"scores": {}, "session_themes": [], "model": None}
    client = client or anthropic.Anthropic()
    dims = _dims(cfg)
    rubric = "\n".join(f"- {r}" for r in cfg.rubric)
    user = (f"Rubric:\n{rubric}\n\nScore these student contribution ids: "
            f"{', '.join(student_ids)}\n\nTranscript:\n{_transcript(contribs, course_context)}")

    with client.beta.messages.stream(
        model=cfg.claude_model,
        max_tokens=64000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=SYSTEM,
        output_config={"effort": cfg.claude_effort,
                       "format": {"type": "json_schema", "schema": _schema(dims)}},
        messages=[{"role": "user", "content": user}],
    ) as stream:
        msg = stream.get_final_message()

    if msg.stop_reason == "refusal":
        raise RuntimeError("scoring was declined by the model; the session report is still "
                           "written without scores")
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("scoring output was cut off; split the session and retry")
    text = "".join(b.text for b in msg.content if b.type == "text")
    data = json.loads(text)

    wanted = set(student_ids)
    scores = {}
    for item in data["contributions"]:
        if item["id"] not in wanted:
            continue
        for d in dims:
            item[d] = max(1, min(5, int(item[d])))
        item["mean"] = round(sum(item[d] for d in dims) / len(dims), 2)
        scores[item["id"]] = item
    return {"scores": scores, "session_themes": data.get("session_themes", []),
            "model": msg.model, "dims": dims}
