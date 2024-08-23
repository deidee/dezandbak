from playwright.sync_api import sync_playwright

def run(playwright):
    # launch the browser
    browser = playwright.chromium.launch()
    # opens a new browser page
    page = browser.new_page()
    # navigate to the website
    page.goto('https://galeriehelder.nl')
    # take a full-page screenshot
    page.screenshot(path='example.png', full_page=True)
    # always close the browser
    browser.close()

with sync_playwright() as playwright:
    run(playwright)
