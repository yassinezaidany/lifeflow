"""Screenshot pages + collect JS errors:  python scripts/ui_screenshots.py "/dashboard/,/today/" desktop|mobile light|dark"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parent.parent / "logs" / "screenshots"
OUT.mkdir(exist_ok=True)
pages = sys.argv[1].split(",") if len(sys.argv) > 1 else [
    "/dashboard/", "/today/", "/planner/", "/planner/?view=day", "/challenges/", "/challenges/new/", "/calendar/",
    "/analytics/", "/reports/", "/journal/", "/journal/review/", "/accounts/settings/",
]
mode = sys.argv[2] if len(sys.argv) > 2 else "desktop"
scheme = sys.argv[3] if len(sys.argv) > 3 else "light"

errors = []
with sync_playwright() as p:
    browser = p.chromium.launch()
    vp = {"width": 1440, "height": 900} if mode == "desktop" else {"width": 390, "height": 844}
    ctx = browser.new_context(viewport=vp, color_scheme=scheme, device_scale_factor=1)
    page = ctx.new_page()
    page.on("console", lambda m: errors.append(f"[console {m.type}] {page.url}: {m.text}") if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: errors.append(f"[pageerror] {page.url}: {e}"))
    page.goto(BASE + "/accounts/login/")
    page.fill("input[name=username]", "demo")
    page.fill("input[name=password]", "LifeFlow-demo1")
    page.click("main form button.btn-primary, form button.btn-primary")
    page.wait_for_load_state("networkidle")
    for path in pages:
        page.goto(BASE + path)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(600)
        name = path.strip("/").replace("/", "_").replace("?", "_").replace("=", "-") or "root"
        page.screenshot(path=str(OUT / f"{mode}-{scheme}-{name}.png"), full_page=mode == "desktop")
    browser.close()
print("\n".join(errors) or "NO JS ERRORS")


