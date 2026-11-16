"""Checks that the pill and category colors are the approved ones and readable."""

import re
from pathlib import Path

import pytest
from django.template import Context, Template, TemplateDoesNotExist
from django.template.loader import get_template

from apps.platforms.categories import Category
from apps.ui.templatetags.trac_ui import stage_step

CSS_DIR = Path(__file__).resolve().parents[3] / "static" / "css"
CSS = (CSS_DIR / "trac.css").read_text()
LIFECYCLE_CSS = (CSS_DIR / "topics.css").read_text()
AA = 4.5

# The owner's "Slate blue" palette. Each token in trac.css must hold exactly this value.
PALETTE = {
    "--trac-canvas": "#e4eaf1", "--trac-paper": "#f6f8fb", "--trac-panel": "#edf1f6", "--trac-border": "#c9d3df",
    "--trac-ink": "#17212e", "--trac-ink-secondary": "#4a5869",
    "--trac-accent": "#2b5c8f", "--trac-on-accent": "#f6f8fb",
    "--trac-header": "#1d2b3c", "--trac-on-header": "#eef3f8", "--trac-header-muted": "#b4c2d1",
    "--trac-green-fill": "#cdebd8", "--trac-green-ink": "#0f5a30",
    "--trac-amber-fill": "#fbe5ae", "--trac-amber-ink": "#6b4b00",
    "--trac-red-fill": "#f6c6c2", "--trac-red-ink": "#8f1d16",
    "--trac-none-fill": "#dce3eb", "--trac-none-ink": "#4a5869",
    "--trac-elevated-fill": "#e6dff7", "--trac-elevated-ink": "#5b3fa8",
}
PAPER = PALETTE["--trac-paper"]


def render(source, **context):
    return Template("{% load trac_labels %}" + source).render(Context(context))


def luminance(color):
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def css_vars(selector, css=CSS):
    """The color variables set in one rule. A value written as var(--trac-x) is looked up in the palette."""
    block = re.search(re.escape(selector) + r" \{([^}]*)\}", css).group(1)
    found = dict(re.findall(r"(--[\w-]+): (#\w+|var\(--trac-[\w-]+\))", block))
    return {k: PALETTE.get(v[4:-1], v) if v.startswith("var(") else v for k, v in found.items()}


# The palette and the style rules

def test_palette_tokens_are_the_owners_values():
    root = css_vars(":root")
    for token, value in PALETTE.items():
        assert root[token] == value, token


def test_nothing_is_pure_white_and_cards_are_flat():
    """Rules 2 and 5: no white, no shadows, no gradients, in any stylesheet (focus rings are outlines)."""
    for path in sorted(CSS_DIR.glob("*.css")):
        css = re.sub(r"/\*.*?\*/", "", path.read_text(), flags=re.S)
        assert not re.search(r"#fff\b|#ffffff|(?<![\w-])white(?![\w-])|rgba?\(\s*255\s*,\s*255\s*,\s*255", css, re.I), path.name
        assert not re.search(r"gradient", css, re.I), path.name
        for value in re.findall(r"box-shadow:\s*([^;}]*)", css):
            assert value.strip() == "none", (path.name, value)
        for value in re.findall(r"(?<![\w-])--bs-[\w-]*shadow[\w-]*:\s*([^;}]*)", css):
            assert value.strip() in ("none", "transparent") or value.strip().startswith("var("), (path.name, value)


def test_lightest_color_is_the_surface():
    assert max(luminance(v) for v in PALETTE.values()) == luminance(PAPER)


def test_cards_have_the_12px_radius_and_text_is_inter_14px():
    root = re.search(r":root \{([^}]*)\}", CSS).group(1)
    assert "--trac-radius: 12px" in root
    assert '--bs-body-font-family: "Inter"' in root and "--bs-body-font-size: 0.875rem" in root


@pytest.mark.parametrize("ink,ground", [
    ("--trac-ink", "--trac-canvas"), ("--trac-ink", "--trac-paper"), ("--trac-ink", "--trac-panel"),
    ("--trac-ink-secondary", "--trac-canvas"), ("--trac-ink-secondary", "--trac-paper"), ("--trac-ink-secondary", "--trac-panel"),
    ("--trac-accent", "--trac-canvas"), ("--trac-accent", "--trac-paper"), ("--trac-accent", "--trac-panel"), ("--trac-accent", "--trac-none-fill"),
    ("--trac-on-accent", "--trac-accent"), ("--trac-on-header", "--trac-header"), ("--trac-header-muted", "--trac-header"),
    ("--trac-green-ink", "--trac-green-fill"), ("--trac-amber-ink", "--trac-amber-fill"), ("--trac-red-ink", "--trac-red-fill"),
    ("--trac-none-ink", "--trac-none-fill"), ("--trac-elevated-ink", "--trac-elevated-fill"),
    ("--trac-green-ink", "--trac-paper"), ("--trac-amber-ink", "--trac-paper"), ("--trac-red-ink", "--trac-paper"),
    ("--trac-elevated-ink", "--trac-paper"), ("--trac-on-accent", "--trac-red-ink"),
])
def test_palette_pairs_are_readable(ink, ground):
    assert contrast(PALETTE[ink], PALETTE[ground]) >= AA, (ink, ground)


def test_selected_items_get_a_3px_ink_outline():
    """Rule 4: the selected chip, pill, answer, tab and calendar type chip each carry the outline."""
    selected = {
        "guidance.css": '.platform-toggle[aria-pressed="true"]', "pathfinder.css": ".my-system-chip input:checked + span",
        "topics.css": ".topic-chip-active", "library.css": ".library-section-active", "riskcal.css": ".riskcal-chip-on",
    }
    for name, selector in selected.items():
        rule = re.search(re.escape(selector) + r"[^{]*\{([^}]*)\}", (CSS_DIR / name).read_text()).group(1)
        assert "outline: 3px solid var(--trac-ink)" in rule, (name, selector)
    assert "outline: 3px solid var(--trac-ink)" in re.search(r"\.status-tab\.active \{([^}]*)\}", CSS).group(1)


# Type pills

def test_type_pill_names_the_type():
    assert render('{% type_pill "Control" %}') == '<span class="type-pill type-pill-control">Control</span>\n'
    assert 'type-pill-control">Control' in render('{% type_pill "Control" %}')


@pytest.mark.parametrize("key,bg,ink", [
    ("control", "#dce3eb", "#2b5c8f"), ("risk", "#f6c6c2", "#8f1d16"),
])
def test_type_pill_colors_are_the_approved_pairs_and_readable(key, bg, ink):
    colors = css_vars(f".type-pill-{key}")
    assert (colors["--pill-bg"], colors["--pill-ink"]) == (bg, ink)
    assert contrast(ink, bg) >= AA


# Category pills

def test_category_pill_links_to_the_category_page():
    html = render("{% category_pill key %}", key="jobs")
    assert 'class="category-pill category-jobs"' in html and 'href="/platforms/category/jobs/"' in html
    assert ">Jobs and interfaces</a>" in html


def test_category_pill_ignores_unknown_keys():
    assert render("{% category_pill key %}", key="mainframe").strip() == ""


APPROVED_EDGE_COLORS = {
    "application": "#5b3f8c", "database": "#2f5d8a", "operating_system": "#556677", "jobs": "#46489a",
    "network": "#2e7d5b", "identity": "#8c3f5b", "cloud": "#1f6e7e", "engineering_tools": "#a04a2f",
    "logging": "#5e6b1f",
}


@pytest.mark.parametrize("category", Category.values)
def test_category_colors_are_approved_and_readable(category):
    colors = css_vars(f".category-{category}")
    assert colors["--category"] == APPROVED_EDGE_COLORS[category]
    ink, tint = colors["--category-ink"], colors["--category-tint"]
    assert contrast(ink, tint) >= AA
    assert contrast(ink, PAPER) >= AA and contrast(ink, PALETTE["--trac-canvas"]) >= AA
    # The category band paints this color behind light text.
    assert contrast(PALETTE["--trac-on-accent"], colors["--category"]) >= AA


def test_every_category_has_colors():
    assert set(APPROVED_EDGE_COLORS) == set(Category.values)


# Stage steps

def test_stage_step_spreads_stages_across_the_four_steps():
    assert [stage_step(i, 1) for i in range(1)] == [1]
    assert [stage_step(i, 2) for i in range(2)] == [1, 4]
    assert [stage_step(i, 4) for i in range(4)] == [1, 2, 3, 4]
    for total in range(2, 9):
        steps = [stage_step(i, total) for i in range(total)]
        assert steps == sorted(steps) and steps[0] == 1 and steps[-1] == 4


@pytest.mark.parametrize("step", [1, 2, 3, 4])
def test_stage_step_colors_are_readable(step):
    colors = css_vars(f".lifecycle-step-{step}", LIFECYCLE_CSS)
    assert contrast(colors["--stage-ink"], colors["--stage-bg"]) >= AA


def test_stage_steps_run_from_light_to_deep_blue():
    backgrounds = [css_vars(f".lifecycle-step-{n}", LIFECYCLE_CSS)["--stage-bg"] for n in (1, 2, 3, 4)]
    assert backgrounds[0] == "#dce3eb" and backgrounds[-1] == "#2b5c8f"
    assert [luminance(c) for c in backgrounds] == sorted((luminance(c) for c in backgrounds), reverse=True)


# Count tiles

def test_count_tile_tones():
    assert "count-tile-control" in render('{% count_tile "Controls" 3 "control" %}')
    assert "count-tile-risk" in render('{% count_tile "Risks" 3 "risk" %}')
    assert "count-tile-alert" in render('{% count_tile "Unmapped risks" 2 "alert" %}')


def test_alert_tile_is_neutral_at_zero_and_unknown_tones_fall_back():
    assert "count-tile-neutral" in render('{% count_tile "Unmapped risks" 0 "alert" %}')
    assert "count-tile-neutral" in render('{% count_tile "Odd" 5 "purple" %}')


@pytest.mark.parametrize("tone,expected_bg", [("alert", "#8f1d16"), ("control", "#dce3eb"), ("risk", "#f6c6c2")])
def test_count_tile_colors_are_readable(tone, expected_bg):
    colors = css_vars(f".count-tile-{tone}")
    assert colors["--tile-bg"] == expected_bg
    assert contrast(colors["--tile-ink"], colors["--tile-bg"]) >= AA


# Shared form field

def test_field_form_is_a_shared_component():
    assert get_template("components/field_form.html")
    with pytest.raises(TemplateDoesNotExist):
        get_template("rcm/field_form.html")


# Tone pills and badges

def test_every_tone_pair_is_readable():
    tones = 0
    for selectors, block in re.findall(r"^((?:\.tone-\w+(?:, )?)+) \{([^}]*)\}", CSS, re.M):
        colors = dict(re.findall(r"(--[\w-]+): (#\w+|var\(--trac-[\w-]+\)|transparent)", block))
        colors = {k: PALETTE.get(v[4:-1], v) if v.startswith("var(") else v for k, v in colors.items()}
        if colors["--pill-bg"] == "transparent":
            colors["--pill-bg"] = PALETTE["--trac-paper"]
        assert contrast(colors["--pill-ink"], colors["--pill-bg"]) >= AA, selectors
        tones += selectors.count(".tone-")
    assert tones >= 19
