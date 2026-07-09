from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8055"

def dump(page, label):
    print(f"\n===== {label} | url={page.url} =====")
    for b in page.query_selector_all("button, a, [role='button']"):
        txt = (b.inner_text() or "").strip().replace("\n", " ")
        if txt:
            print(f"  BTN: {txt[:60]!r} id={b.get_attribute('id')}")

def login(page, email, password):
    page.goto(BASE + "/dashboard/", wait_until="load")
    page.wait_for_selector("#society-dropdown .Select-input input", timeout=30000, state="attached")
    page.wait_for_timeout(800)
    # open menu
    page.click("#society-dropdown .Select-control", timeout=15000)
    page.wait_for_selector(".Select-option", timeout=8000)
    opts = [o.inner_text() for o in page.query_selector_all(".Select-option")]
    print("  society options:", opts)
    page.click(".Select-option:has-text('Sunrise Residency')", timeout=10000)
    page.wait_for_timeout(500)
    sel = ""
    try:
        sel = page.locator("#society-dropdown .Select-value-label").inner_text()
    except Exception:
        pass
    print("  selected society:", sel)
    page.click("#society-select-btn", timeout=15000)
    try:
        page.wait_for_selector("#login-email", timeout=20000)
    except Exception as e:
        print("  !! login-email did not appear. stage2 dump:")
        s2 = page.query_selector("#login-stage-2")
        if s2:
            print("   stage2 style:", s2.get_attribute("style"))
            print("   stage2 html:", s2.inner_html()[:500])
        raise
    page.fill("#login-email", email, force=True)
    page.fill("#login-password", password, force=True)
    page.click("#login-btn")
    page.wait_for_timeout(4000)
    print("  logged in, url:", page.url)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.on("console", lambda m: print("  [console]", m.text[:180]))
        login(page, "admin@sunriseresidency.com", "Admin@2024")
        page.goto(BASE + "/dashboard/admin-portal", wait_until="load")
        page.wait_for_timeout(3000)
        dump(page, "ADMIN PORTAL")
        clicked = False
        for el in page.query_selector_all("*"):
            t = (el.inner_text() or "").strip()
            if t in ("Upcoming Events", "Events"):
                try:
                    el.click()
                    clicked = True
                    print("Clicked card:", t)
                    break
                except Exception as e:
                    print("click fail", e)
        page.wait_for_timeout(3000)
        dump(page, "AFTER EVENTS CARD CLICK")
        dc = page.query_selector("#drill-content")
        if dc:
            h = dc.inner_html()
            print("DRILL-CONTENT length:", len(h))
            print(h[:4000])
        browser.close()

if __name__ == "__main__":
    main()
