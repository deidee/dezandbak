from playwright.sync_api import sync_playwright
from urllib.parse import urlparse

def run(playwright):
    url = 'https://www.anbi-collectief.nl/aanmelden'
    o = urlparse(url)

    # launch the browser
    browser = playwright.chromium.launch()
    # opens a new browser page
    page = browser.new_page()
    page.set_viewport_size({"width": 1280, "height": 768})

    # navigate to the website
    page.goto(url)
    # take a full-page screenshot
    page.screenshot(path=o.hostname + '.png', full_page=False)
    # always close the browser
    browser.close()

with sync_playwright() as playwright:
    run(playwright)
