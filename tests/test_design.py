"""Look and feel: WCAG AA contrast for the theme colours, phone rules, no web fonts or images."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.9 on this Mac: a tiny reader is enough for key = "value" lines
    tomllib = None


def config() -> dict:
    text = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    return dict(re.findall(r'^(\w+)\s*=\s*"([^"]*)"', text, re.M))


def luminance(hex_colour: str) -> float:
    rgb = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_text_and_buttons_meet_wcag_aa():
    c = config()
    assert contrast(c["textColor"], c["backgroundColor"]) >= 4.5           # body text
    assert contrast(c["textColor"], c["secondaryBackgroundColor"]) >= 4.5  # text in boxes
    assert contrast("#FFFFFF", c["primaryColor"]) >= 4.5                    # white text on main buttons
    assert contrast("#FFFFFF", c["redColor"]) >= 4.5                        # emergency banners
    assert contrast("#FFFFFF", "#13213B") >= 4.5                            # navy main buttons
    assert contrast("#4A5468", c["backgroundColor"]) >= 4.5                 # muted text
    assert contrast("#C7D2E5", "#13213B") >= 4.5                            # sources on the navy facts band
    assert contrast("#78350F", "#FEF3C7") >= 4.5                            # amber "needs attention" chip
    assert contrast("#FFFFFF", "#14213D") >= 4.5 and contrast("#FECACA", "#14213D") >= 4.5  # safety bar


def test_red_is_kept_for_emergencies():
    c = config()
    assert c["primaryColor"].upper() != c["redColor"].upper()


def test_phone_rules_and_speed():
    css = (ROOT / "assets" / "app.css").read_text(encoding="utf-8")
    assert "@media (max-width: 640px)" in css and "min-height: 44px" in css and "overflow-x: hidden" in css
    assert ":focus-visible" in css
    assert "@import" not in css and "url(" not in css      # no web fonts or images to download
    assert not re.search(r"animation\s*:|@keyframes|transition\s*:", css)
    assert "Noto Sans" in config()["font"]


def test_page_helplines_have_tappable_numbers_and_icons_like_home():
    import ui
    bar = ui.page_helplines("In danger? Call 112", "Free legal aid: 15100")
    assert 'href="tel:112"' in bar and 'href="tel:15100"' in bar
    assert '>call</span>' in bar and '>support_agent</span>' in bar  # phone icon, support icon
    home = ui.helpline("Free and open source.", "In danger? Call 112", "Free legal aid: 15100")
    assert ui.helpline_links("In danger? Call 112", "Free legal aid: 15100") in home and \
        ui.helpline_links("In danger? Call 112", "Free legal aid: 15100") in bar  # the very same links
