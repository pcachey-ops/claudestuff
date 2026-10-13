"""Ask Claude to design one new printable product."""

from __future__ import annotations

import anthropic

from .models import ProductSpec

MODEL = "claude-opus-5-5"

SYSTEM = """You design printable digital products (planners, trackers, checklists, worksheets) \
sold as instant-download PDFs on Etsy and Shopify.

Make something a real buyer would pay for: specific to one buyer and one job, practical on paper, \
and clearly better than a free blank template. Prefer narrow niches with steady search demand \
over broad ones (e.g. "sourdough starter feeding log" beats "kitchen planner").

Rules:
- Original content only. No trademarks, brand names, characters or copyrighted material.
- No medical, legal or financial claims beyond general organisation.
- Write the title for marketplace search: lead with the main keyword phrase, then use-cases, \
then "Printable PDF".
- The description must state this is a digital download and nothing physical ships.
- Tags: 13 distinct buyer search phrases, lowercase, 20 characters or fewer each."""


class GenerationError(RuntimeError):
    pass


def generate_spec(
    client: anthropic.Anthropic,
    niches: list[str],
    existing_titles: list[str],
) -> ProductSpec:
    avoid = "\n".join(f"- {t}" for t in existing_titles[-200:]) or "(none yet)"
    prompt = (
        f"Pick ONE product within these niches: {', '.join(niches)}.\n\n"
        f"Already in the catalog, so do not repeat or closely overlap these:\n{avoid}\n\n"
        "Design the full product: listing copy and the content of every page."
    )

    response = client.beta.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        output_format=ProductSpec,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )

    if response.stop_reason == "refusal":
        raise GenerationError(f"Model declined the request: {response.stop_details}")
    if response.stop_reason == "max_tokens":
        raise GenerationError("Response hit max_tokens before the product was complete")
    if response.parsed_output is None:
        raise GenerationError("Model returned no parseable product spec")
    return response.parsed_output.cleaned()
