"""Data shapes shared by the generator, renderer and publishers."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field


class Page(BaseModel):
    """One printable page inside the product PDF."""

    heading: str
    intro: str = Field(description="One or two sentences telling the buyer how to use this page.")
    layout: Literal["checklist", "lined", "table"] = Field(
        description="checklist: tick-box items. lined: prompts each followed by writing lines. "
        "table: a grid with the given column headers and blank rows to fill in."
    )
    items: list[str] = Field(
        description="checklist: 8-20 checklist items. lined: 3-6 prompts. table: 2-6 column headers."
    )


class ProductSpec(BaseModel):
    """Everything needed to render and list one digital product."""

    title: str = Field(description="Marketplace listing title, keyword-rich, at most 140 characters.")
    cover_title: str = Field(description="Short title for the cover image, at most 6 words.")
    cover_subtitle: str = Field(description="Short benefit line for the cover image, at most 10 words.")
    niche: str
    target_buyer: str
    description: str = Field(
        description="Listing description in plain text with short paragraphs and a bulleted "
        "'What's included' list. No markdown headings."
    )
    tags: list[str] = Field(description="Exactly 13 search tags, each at most 20 characters, lowercase.")
    price_usd: float = Field(description="Retail price between 3 and 15 USD.")
    accent_color: str = Field(description="Hex colour like #3B6E8F used on the cover and headings.")
    pages: list[Page] = Field(description="4 to 10 pages.")

    def cleaned(self) -> "ProductSpec":
        """Enforce marketplace limits the model may overshoot (Etsy: 140-char title, 13 tags of 20 chars)."""
        tags: list[str] = []
        for tag in self.tags:
            t = re.sub(r"[^a-z0-9 '\-]", "", tag.lower()).strip()[:20].strip()
            if t and t not in tags:
                tags.append(t)
        color = self.accent_color if re.fullmatch(r"#[0-9a-fA-F]{6}", self.accent_color) else "#3B6E8F"
        return self.model_copy(
            update={
                "title": self.title.strip()[:140],
                "tags": tags[:13],
                "price_usd": round(min(max(self.price_usd, 1.0), 50.0), 2),
                "accent_color": color,
            }
        )

    @property
    def slug(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.cover_title.lower()).strip("-")[:60] or "product"
