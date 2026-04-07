"""Yatagarasu - LLM-based relevance scorer. Profile-driven from config."""

import json
import os
import urllib.request
from models import FeedItem


ANTHROPIC_API = "https://api.anthropic.com/v1/messages"


def build_profile_prompt(config: dict) -> str:
    """Build scoring system prompt from config profile + domains."""
    profile = config.get("profile", {})
    description = profile.get("description", "a researcher")
    projects = profile.get("projects", [])
    noise = profile.get("noise_patterns", [])
    domains = config.get("domains", {})

    lines = [
        "You are a relevance scorer for a personal signal curation system.",
        f"The user is {description}, currently working on:",
    ]
    for i, proj in enumerate(projects, 1):
        lines.append(f"{i}. {proj}")

    lines.extend([
        "",
        "Score each item 1-5:",
        "5 = RED: directly actionable, deadline, competitor paper, or breaking change",
        "4 = ORANGE: changes mental model, worth reading in full",
        "3 = YELLOW: useful context, skim-worthy",
        "2 = noise with a kernel of signal",
        "1 = pure noise, skip entirely",
        "",
        "Domain keywords for calibration:",
    ])

    for name, cfg in domains.items():
        weight = cfg.get("weight", 1.0)
        kws = cfg.get("keywords", [])[:5]
        lines.append(f"  {name} (weight {weight}): {', '.join(kws)}")

    if noise:
        lines.append("")
        lines.append("NOISE PATTERNS (auto-score 1):")
        for pat in noise:
            lines.append(f"- {pat}")

    lines.extend([
        "",
        "Return a JSON array: [{\"idx\": 0, \"score\": 4, \"tier\": \"ORANGE\", \"why\": \"one sentence\"}]",
        "Be ruthless. Most items should score 1-2. Only exceptional items get 4-5.",
    ])
    return "\n".join(lines)


def score_items(items: list[FeedItem], config: dict) -> list[tuple[FeedItem, int, str, str]]:
    """Score items using Claude Haiku. Returns [(item, score, tier, reason)]."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("[scorer] ANTHROPIC_API_KEY not set, returning unscored items")
        return [(item, 3, "YELLOW", "unscored -- no API key") for item in items]

    model = config.get("scoring", {}).get("model", "claude-haiku-4-5-20251001")
    batch_size = config.get("scoring", {}).get("batch_size", 40)
    system_prompt = build_profile_prompt(config)

    scored = []

    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        items_text = "\n".join(
            f"{j}. [{item.domain}] {item.title} | {item.summary[:200]}"
            for j, item in enumerate(batch)
        )

        payload = json.dumps({
            "model": model,
            "max_tokens": 2048,
            "system": system_prompt,
            "messages": [{"role": "user", "content": f"Score these items:\n\n{items_text}"}],
        }).encode()

        try:
            req = urllib.request.Request(ANTHROPIC_API, data=payload, headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            })
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read())

            text = ""
            for block in result.get("content", []):
                if block.get("type") == "text":
                    text += block["text"]

            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                scores_data = json.loads(text[start:end])
                score_map = {s["idx"]: s for s in scores_data}

                for j, item in enumerate(batch):
                    if j in score_map:
                        s = score_map[j]
                        scored.append((item, s["score"], s.get("tier", "YELLOW"), s.get("why", "")))
                    else:
                        scored.append((item, 2, "YELLOW", "unscored"))
            else:
                print("[scorer] could not parse JSON from response")
                scored.extend((item, 2, "YELLOW", "parse error") for item in batch)

        except Exception as e:
            print(f"[scorer] API error: {e}")
            scored.extend((item, 2, "YELLOW", f"error: {e}") for item in batch)

    return scored
