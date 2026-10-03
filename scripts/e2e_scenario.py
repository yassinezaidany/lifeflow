"""Browser end-to-end scenario (spec section 109). Requires: dev server on :8000, demo data (seed_demo),
and pip install -r requirements-dev.txt; python -m playwright install chromium.

    python scripts/e2e_scenario.py
"""
import random
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parent.parent / "logs" / "e2e"
OUT.mkdir(exist_ok=True)
errors = []
uname = f"e2e{random.randint(1000, 9999)}"


def shot(page, name):
    page.screenshot(path=str(OUT / f"e2e-{name}.png"))


with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(f"[pageerror] {page.url}: {e}"))
    page.on("console", lambda m: errors.append(f"[console] {page.url}: {m.text}") if m.type == "error" else None)

    # 1. Register
    page.goto(BASE + "/accounts/register/")
    page.fill("input[name=first_name]", "Test")
    page.fill("input[name=username]", uname)
    page.fill("input[name=email]", f"{uname}@example.com")
    page.fill("input[name=password]", "Very-strong-pass-42")
    page.click("form button.btn-primary")
    page.wait_for_url("**/accounts/welcome/")
    print("1 register OK ->", page.url)
    shot(page, "01-onboarding")

    # 2. Onboarding: skip
    page.click("text=Skip setup")
    page.wait_for_url("**/dashboard/")
    print("2 onboarding skip OK")

    # 3. Wizard: create challenge (Pages, 2/day, every day, 30 days)
    page.goto(BASE + "/challenges/new/")
    page.fill("#w-name", "Read Qur'an pages")
    page.click("button:has-text('Continue')")
    page.click("button.tile:has-text('A number')")
    page.locator("input[placeholder^='Field name']").first.fill("Pages")
    page.click("button:has-text('Continue')")
    page.fill("#w-target", "2")
    shot(page, "03-wizard-goal")
    page.click("button:has-text('Continue')")
    page.click("button:has-text('Continue')")  # frequency: every day
    page.click("button:has-text('Continue')")  # period: 30 days
    shot(page, "03-wizard-review")
    page.click("button:has-text('Create challenge')")
    page.wait_for_url(__import__("re").compile(r".*/challenges/\d+/$"))
    challenge_url = page.url
    print("3 challenge created ->", challenge_url)

    # 4. Planner: create an activity linked to the challenge via click on grid
    page.goto(BASE + "/planner/?view=day")
    page.wait_for_load_state("networkidle")
    page.locator("main button.btn-primary:has-text('Add')").click()
    page.fill("#act-name", "Qur'an reading")
    page.fill("#act-start", "00:00")
    page.fill("#act-end", "00:30")
    page.select_option("#act-ch", label="Read Qur'an pages")
    page.locator("#act-name").press("Enter")
    page.wait_for_timeout(1200)
    shot(page, "04-planner-day")
    blocks = page.locator(".tl-block")
    print("4 activity created, blocks:", blocks.count())

    # 5. Complete the activity from Today â†’ propose recording entry â†’ confirm with prefill
    page.goto(BASE + "/today/")
    page.locator("li:has-text('Qur') button[aria-label='Mark as done']").click()
    page.wait_for_timeout(800)
    page.click("button:has-text('Review & record')")
    page.wait_for_timeout(800)
    page.locator("input[id^='f-']").first.fill("3")
    shot(page, "05-record-from-activity")
    page.click("#entry-title >> xpath=ancestor::form//button[@type='submit']")
    page.wait_for_timeout(1500)
    shot(page, "05-today-after")
    print("5 activity completed + entry recorded")

    # 6. Quick add: record another entry via global + menu
    page.goto(BASE + "/dashboard/")
    page.click("aside button:has-text('Quick add')")
    page.click("aside button:has-text('Record progress')")
    page.wait_for_timeout(800)
    page.locator("input[id^='f-']").first.fill("1")
    page.click("#entry-title >> xpath=ancestor::form//button[@type='submit']")
    page.wait_for_timeout(1500)
    shot(page, "06-dashboard")
    text = page.inner_text("main")
    assert "Read Qur'an pages" in text
    print("6 quick add OK")

    # 7. Challenge analytics
    page.goto(challenge_url)
    page.wait_for_load_state("networkidle")
    assert "4" in page.inner_text("main")
    shot(page, "07-challenge")
    print("7 challenge page OK")

    # 8. Calendar
    page.goto(BASE + "/calendar/")
    shot(page, "08-calendar")

    # 9. Report + PDF
    page.goto(BASE + "/reports/")
    page.click("form button:has-text('Generate report')")
    page.wait_for_url(__import__("re").compile(r".*/reports/\d+/$"))
    shot(page, "09-report")
    with page.expect_download() as dl:
        page.click("a:has-text('Download PDF')")
    pdf = dl.value.path()
    assert open(pdf, "rb").read(4) == b"%PDF"
    print("9 report + PDF OK")
    page.goto(BASE + "/reports/")
    assert page.locator("text=October 2026").count() >= 1
    print("10 report history OK")

    # 11. Logout
    page.click("aside form button[aria-label='Sign out']")
    page.wait_for_url("**/accounts/login/")
    print("11 logout OK")

    # 12. Isolation: login as demo, the new challenge must not appear
    page.fill("input[name=username]", "demo")
    page.fill("input[name=password]", "LifeFlow-demo1")
    page.click("form button.btn-primary")
    page.goto(BASE + "/challenges/?status=all")
    assert "Read Qur'an pages" not in page.inner_text("main")
    r = page.goto(challenge_url)
    print("12 isolation OK (foreign challenge status:", r.status, ")")
    browser.close()

print("\n".join(errors) or "NO JS ERRORS")




