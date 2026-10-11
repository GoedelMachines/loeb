"""Tests for the Löb theme system."""

from autonomous_tester.ui.theme import DUSK, LINEN


def test_dusk_is_dark():
    assert DUSK.name == "dusk"
    assert DUSK.bg_base == "#0e0718"
    assert DUSK.primary == "#e8907a"


def test_linen_is_light():
    assert LINEN.name == "linen"
    assert LINEN.bg_base == "#ffffff"
    assert LINEN.primary == "#e8907a"


def test_primary_accent_shared():
    assert DUSK.primary == LINEN.primary


def test_category_colors_exist():
    for theme in (DUSK, LINEN):
        assert "git" in theme.category_colors
        assert "svc" in theme.category_colors
        assert "brw" in theme.category_colors
        assert "aud" in theme.category_colors
        assert "api" in theme.category_colors
        assert "out" in theme.category_colors


def test_theme_is_frozen():
    import dataclasses

    import pytest

    assert dataclasses.is_dataclass(DUSK)
    with pytest.raises(dataclasses.FrozenInstanceError):
        DUSK.name = "modified"
