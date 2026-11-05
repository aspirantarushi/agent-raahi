"""Screenshots of every screen, in English and Hindi, at laptop (1280px) and phone (390px) width.

    .venv/bin/python scripts/screenshots_all.py        # saves docs/screenshots/screens/*.png

Uses the installed Google Chrome (Playwright "chrome" channel). Practice data only.
"""

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from screenshots import ROOT, URL, WIDTHS, wait_for_app  # noqa: E402

OUT = ROOT / "docs" / "screenshots" / "screens"
LABELS = {
    "en": {"menu": "Menu", "Home": "Home", "New case": "New case", "My cases": "My cases", "Learn": "Learn",
           "Evaluation": "Evaluation (practice)", "Supervisor": "Supervisor", "undertrial": "Section 479 aid (undertrial)",
           "sign_in": "Sign in"},
    "hi": {"menu": "मेन्यू", "Home": "Home", "New case": "नया केस", "My cases": "Case tracker", "Learn": "Learn",
           "Evaluation": "Evaluation (अभ्यास)", "Supervisor": "Supervisor", "undertrial": "धारा 479 सहायक (विचाराधीन क़ैदी)",
           "sign_in": "साइन इन करें"},
}
NAV_KEYS = {"New case": "nav-new", "My cases": "nav-tracker", "Learn": "nav-learn", "Evaluation": "nav-evaluation",
            "Supervisor": "nav-supervisor"}
TALL = {"laptop": 3600, "phone": 6400}  # Streamlit scrolls inside its own frame: use a tall window
SCREENS = ["Home", "New case", "Undertrial", "My cases", "Learn", "Evaluation", "Supervisor"]


def password() -> str:
    for line in (ROOT / ".streamlit" / "secrets.toml").read_text(encoding="utf-8").splitlines():
        if line.startswith("SUPERVISOR_PASSWORD"):
            return line.split("=", 1)[1].strip().strip('"')
    return os.environ.get("SUPERVISOR_PASSWORD", "")


def open_screen(page, screen, code):
    labels = LABELS[code]
    target = "New case" if screen == "Undertrial" else screen
    if target != "Home":  # the top navigation buttons
        page.locator(f".st-key-{NAV_KEYS[target]} button").first.click()
        wait_for_app(page)
    if screen == "Undertrial":
        page.get_by_text(labels["undertrial"]).first.click()
        wait_for_app(page)
    if screen == "Supervisor":
        page.get_by_label("Supervisor password" if code == "en" else "Supervisor पासवर्ड").first.fill(password())
        page.keyboard.press("Tab")
        page.get_by_role("button", name=labels["sign_in"]).click()
        wait_for_app(page)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    saved = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        for code in ("en", "hi"):
            for label, (w, h) in WIDTHS.items():
                for screen in SCREENS:
                    page = browser.new_page(viewport={"width": w, "height": TALL[label]})
                    page.goto(URL)
                    wait_for_app(page)
                    if code == "hi":
                        page.locator(".st-key-ui_lang label").filter(has_text="हिंदी").first.click()
                        wait_for_app(page)
                    open_screen(page, screen, code)
                    path = OUT / f"{screen.lower().replace(' ', '-')}-{code}-{label}.png"
                    page.screenshot(path=str(path), full_page=True)
                    saved.append(path)
                    page.close()
        browser.close()
    for path in saved:
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
