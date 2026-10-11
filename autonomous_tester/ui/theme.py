"""Löb theme system — Dusk (dark) and Linen (light).

Dusk/Linen structure with a warm palette and Löb's own peach-coral
accent (#e8907a).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Theme:
    """Color token set for one theme variant."""

    name: str

    # Backgrounds
    bg_base: str
    bg_surface: str
    bg_deep: str
    bg_hover: str

    # Primary accent
    primary: str

    # Text
    text_primary: str
    text_secondary: str
    text_muted: str

    # Borders
    border: str
    border_subtle: str

    # Status
    success: str
    error: str
    warning: str

    # Thinking accent
    thinking: str

    # Dim levels (for section headers, separators)
    dim_dark: str
    dim_mid: str
    dim_light: str

    # Tool category colors
    category_colors: dict[str, str] = field(default_factory=dict)

    # Category markers (same across themes)
    category_markers: dict[str, str] = field(default_factory=dict)


_MARKERS = {
    "git": "◇",
    "svc": "□",
    "brw": "◉",
    "aud": "∿",
    "api": "⊙",
    "out": "△",
}

DUSK = Theme(
    name="dusk",
    bg_base="#0e0718",
    bg_surface="#180f24",
    bg_deep="#07030e",
    bg_hover="#20152c",
    primary="#e8907a",
    text_primary="#dde0c8",
    text_secondary="#b8b6a0",
    text_muted="#9a9878",
    border="#3a2e42",
    border_subtle="#1a1a2e",
    success="#22c55e",
    error="#ef4444",
    warning="#ffaa00",
    thinking="#a78bfa",
    dim_dark="#5a4e66",
    dim_mid="#7a6e88",
    dim_light="#9a9878",
    category_colors={
        "git": "#22c55e",
        "svc": "#93a4f4",
        "brw": "#e8907a",
        "aud": "#a78bfa",
        "api": "#ffaa00",
        "out": "#c4786a",
    },
    category_markers=_MARKERS,
)

LINEN = Theme(
    name="linen",
    bg_base="#ffffff",
    bg_surface="#fafafa",
    bg_deep="#f5f5f5",
    bg_hover="#f0f0f2",
    primary="#e8907a",
    text_primary="#1e1d26",
    text_secondary="#2e2d3a",
    text_muted="#5e5d74",
    border="#e2e2e8",
    border_subtle="#d4d4da",
    success="#16a34a",
    error="#dc2626",
    warning="#cc7700",
    thinking="#8b5cf6",
    dim_dark="#c8c8d0",
    dim_mid="#9898a8",
    dim_light="#5e5d74",
    category_colors={
        "git": "#16a34a",
        "svc": "#4f6cf7",
        "brw": "#d4705a",
        "aud": "#8b5cf6",
        "api": "#cc7700",
        "out": "#a85e4e",
    },
    category_markers=_MARKERS,
)

THEMES: dict[str, Theme] = {"dusk": DUSK, "linen": LINEN}
