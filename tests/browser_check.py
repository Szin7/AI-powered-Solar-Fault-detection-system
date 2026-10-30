import argparse
import json
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://127.0.0.1:8000")
parser.add_argument("--executable")
parser.add_argument("--integration-check", action="store_true")
args = parser.parse_args()
root = Path(os.getenv("SOLARSENSE_HOME", "."))
credentials = json.loads((root / "var/credentials.json").read_text())
screenshots = root / "var" / "browser-check"
screenshots.mkdir(parents=True, exist_ok=True)
errors = []
with sync_playwright() as p:
    options = {"headless": True}
    if args.executable:
        options.update(executable_path=args.executable, args=["--no-sandbox", "--disable-dev-shm-usage"])
    browser = p.chromium.launch(**options)
    desktop = browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
    page = desktop.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.goto(args.url)
    expect(page.get_by_role("heading", name="Solar Panel Monitor", exact=True)).to_be_visible()
    page.locator("#token").fill(credentials["operator"])
    page.locator("#login button").click()
    expect(page.locator("#model-version")).to_contain_text("Release", timeout=30000)
    expect(page.locator("#connection")).to_have_text("Live subscription")
    assert page.locator("#apply").is_enabled()
    page.locator("#freeze").click()
    timestamp = page.locator("#clock").inner_text()
    page.wait_for_timeout(2300)
    assert timestamp == page.locator("#clock").inner_text()
    page.locator("#freeze").click()
    page.get_by_role("button", name="Station 2", exact=True).click()
    expect(page.get_by_text("West roof ·", exact=False).first).to_be_visible()
    page.get_by_role("button", name="Station 1", exact=True).click()
    page.get_by_text("Voltage (V)", exact=True).click()
    expect(page.get_by_role("heading", name="Voltage (V) - Detailed Analysis")).to_be_visible()
    page.get_by_role("button", name="Close Detailed View").click()
    page.get_by_role("button", name="manual", exact=True).click()
    page.get_by_label("Voltage", exact=True).fill("33.7")
    page.get_by_role("button", name="Apply Values").click()
    expect(page.get_by_role("status")).to_contain_text("Condition requested")
    page.wait_for_timeout(3000)
    fleet = page.request.get(
        args.url + "/api/v1/stations", headers={"Authorization": "Bearer " + credentials["operator"]}
    ).json()
    station = next(s for s in fleet["stations"] if s["id"] == "roof-east")
    assert station["scenario"]["manual"]["voltage_v"] == 33.7
    assert station["reading"]["voltage_v"] == 33.7
    page.locator("#relay-off").click()
    expect(page.locator("#command-status")).to_contain_text("confirmed OFF", timeout=15000)
    page.locator("#relay-on").click()
    expect(page.locator("#command-status")).to_contain_text("confirmed ON", timeout=15000)
    page.get_by_role("button", name="Resume scheduled scenario").click()
    with page.expect_download() as download:
        page.get_by_role("button", name="Download CSV", exact=True).click()
    assert download.value.suggested_filename == "roof-east-simulated.csv"
    page.get_by_role("button", name="preset", exact=True).click()
    page.get_by_role("button", name="missing", exact=True).click()
    page.get_by_role("button", name="Apply condition", exact=True).click()
    expect(page.get_by_role("heading", name="data quality", exact=True)).to_be_visible(timeout=15000)
    page.get_by_text("Current (A)", exact=True).click()
    expect(page.get_by_role("heading", name="Current (A) - Detailed Analysis")).to_be_visible()
    page.get_by_role("button", name="Close Detailed View").click()
    page.get_by_role("button", name="Resume scheduled scenario").click()
    page.get_by_role("button", name="Stop Monitoring", exact=True).click()
    expect(page.get_by_text("Display monitoring stopped.", exact=False)).to_be_visible()
    page.get_by_role("button", name="Start Monitoring", exact=True).click()
    expect(page.locator("#connection")).to_have_text("Live subscription")
    if args.integration_check:
        page.get_by_label("Technician name", exact=True).fill("Demo technician")
        page.get_by_label("Technician phone", exact=True).fill("+12025550123")
        page.get_by_label("Enable automatic alerts", exact=True).check()
        page.get_by_role("button", name="Save technician", exact=True).click()
        expect(page.get_by_test_id("integration-status")).to_contain_text("Technician saved")
        page.get_by_test_id("source-hardware").click()
        expect(page.get_by_text("HARDWARE DATA", exact=True)).to_be_visible()
        headers = {"X-Gateway-Key": os.environ["SOLARSENSE_GATEWAY_KEY"]}
        for i in range(6):
            payload = {
                "senderId": 1,
                "ldrValue": 3500,
                "dhtTemp": 30,
                "humidity": 50,
                "thermistorTemp": 40,
                "voltage": 20 + i * 0.01,
                "current": 0.001,
                "relayStatus": False,
                "valid": True,
                "gateway_timestamp_ms": int(__import__("time").time() * 1000) + i,
            }
            response = page.request.post(args.url + "/api/gateway-data", data=[payload], headers=headers)
            assert response.status == 200, response.text()
        expect(page.locator("#model-version")).to_contain_text("Hardware release hw-", timeout=15000)
        expect(page.get_by_role("heading", name="Open Circuit", exact=True)).to_be_visible(timeout=15000)
        expect(page.get_by_role("heading", name="Measured DC Power", exact=False)).to_be_visible()
        page.get_by_role("button", name="Preview message", exact=True).click()
        expect(page.get_by_test_id("alert-preview")).to_contain_text("HARDWARE")
        expect(page.get_by_test_id("alert-preview")).to_contain_text("open circuit")
        with page.expect_download() as hardware_download:
            page.get_by_role("button", name="Download CSV", exact=True).click()
        assert hardware_download.value.suggested_filename == "roof-east-hardware.csv"
        page.screenshot(path=str(screenshots / "hardware.png"), full_page=True)
        page.get_by_test_id("source-simulated").click()
        expect(page.locator("#model-version")).to_contain_text("Release", timeout=15000)
        page.get_by_role("button", name="Resume scheduled scenario").click()
    page.evaluate("window.scrollTo(0, 0)")
    page.screenshot(path=str(screenshots / "desktop.png"))
    mobile = browser.new_context(viewport={"width": 390, "height": 844})
    small = mobile.new_page()
    small.on("pageerror", lambda error: errors.append(str(error)))
    small.goto(args.url)
    small.locator("#token").fill(credentials["viewer"])
    small.locator("#login button").click()
    expect(small.locator("#model-version")).to_contain_text("Release", timeout=30000)
    assert small.locator("#apply").is_disabled()
    assert small.locator("#relay-off").is_disabled()
    assert not small.evaluate("document.documentElement.scrollWidth > window.innerWidth")
    small.screenshot(path=str(screenshots / "mobile.png"), full_page=True)
    assert not errors, errors
    report = {
        "browser": browser.version,
        "dashboard": "restored original React dashboard",
        "desktop": "1440x1000",
        "mobile": "390x844",
        "viewer_controls_disabled": True,
        "freeze_keeps_timestamp": True,
        "station_switching": True,
        "expanded_chart": True,
        "manual_values_reach_simulator": True,
        "relay_confirmations": True,
        "csv_download": True,
        "missing_current_chart": True,
        "stop_start_monitoring": True,
        "csp_bypassed": False,
        "hardware_fixture_ui": args.integration_check,
        "technician_contact_and_preview": args.integration_check,
        "physical_hardware_tested": False,
        "js_errors": errors,
        "horizontal_overflow": False,
    }
    (root / "reports").mkdir(exist_ok=True)
    (root / "reports/browser.json").write_text(json.dumps(report, indent=2) + "\n")
    browser.close()
print(json.dumps(report, indent=2))
