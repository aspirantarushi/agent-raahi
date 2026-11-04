"""Take screenshots of the running app (http://localhost:8501) at laptop and phone width.

    .venv/bin/python scripts/screenshots.py before        # saves docs/screenshots/before/*.png

Uses the Google Chrome already installed (Playwright's "chrome" channel), so no browser download.
Only fictional practice data appears in screenshots.
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
URL = "http://localhost:8501"
WIDTHS = {"laptop": (1280, 1600), "phone": (390, 2400)}


def wait_for_app(page):
    page.wait_for_selector('[data-testid="stApp"]', timeout=30000)
    page.wait_for_timeout(1500)
    try:  # wait until Streamlit has finished running the script
        page.wait_for_selector('[data-testid="stStatusWidget"]', state="detached", timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(1000)


def shoot(folder: str, name: str, steps=None):
    out = ROOT / "docs" / "screenshots" / folder
    out.mkdir(parents=True, exist_ok=True)
    saved = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        for label, (w, h) in WIDTHS.items():
            page = browser.new_page(viewport={"width": w, "height": h})
            page.goto(URL)
            wait_for_app(page)
            for step in steps or []:
                step(page)
                wait_for_app(page)
            path = out / f"{name}-{label}.png"
            page.screenshot(path=str(path), full_page=True)
            saved.append(path)
            page.close()
        browser.close()
    return saved


def read_wages_story(page):
    """Fictional practice story -> read with the AI -> skip to the summary (steps 3 and 4)."""
    story = (ROOT / "practice_stories" / "unpaid_wages.txt").read_text(encoding="utf-8")
    page.get_by_label("The story, in the volunteer's words").fill(story)
    page.keyboard.press("Tab")
    page.wait_for_timeout(800)
    page.get_by_role("button", name="Read the story").click()
    try:  # questions may come first; if the AI found everything it needs, the summary comes straight away
        page.wait_for_selector("text=Skip the rest and see the summary", timeout=120000)
        page.get_by_role("button", name="Skip the rest and see the summary").click()
    except Exception:
        page.screenshot(path=str(ROOT / "docs" / "screenshots" / "debug-after-read.png"), full_page=True)
    page.wait_for_selector("text=I have checked this summary", timeout=120000)


if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else "before"
    for path in shoot(folder, "new-case-any-case"):
        print(path.relative_to(ROOT))
    if folder != "before":
        for path in shoot(folder, "new-case-any-case-summary", [read_wages_story]):
            print(path.relative_to(ROOT))
