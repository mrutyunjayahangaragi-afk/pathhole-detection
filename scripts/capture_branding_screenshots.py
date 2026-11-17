"""Script to capture headless Chrome screenshots of CivicLens branding across desktop and mobile."""

import subprocess
import os
import time

CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
ARTIFACT_DIR = "/Users/mrutyunjayaashokhangaragi/.gemini/antigravity/brain/a3a57b00-f03b-45eb-98ca-69a9dd6b2059"
os.makedirs(ARTIFACT_DIR, exist_ok=True)

PAGES_TO_CAPTURE = [
    {
        "name": "screenshot_desktop_homepage.png",
        "url": "http://localhost:5055/",
        "window_size": "1440,900",
        "desc": "Desktop Homepage (Hero & Fixed Sidebar)",
    },
    {
        "name": "screenshot_desktop_sidebar.png",
        "url": "http://localhost:5055/citizen-dashboard.html",
        "window_size": "1280,850",
        "desc": "Citizen Dashboard with Fixed Sidebar Brand Header",
    },
    {
        "name": "screenshot_mobile_homepage.png",
        "url": "http://localhost:5055/",
        "window_size": "390,844",
        "desc": "Mobile Homepage (390px - Compact Emblem & Responsive Layout)",
    },
    {
        "name": "screenshot_mobile_report.png",
        "url": "http://localhost:5055/citizen-report.html",
        "window_size": "390,844",
        "desc": "Mobile Citizen Report (390px - Header Emblem)",
    },
    {
        "name": "screenshot_gateway.png",
        "url": "http://localhost:5055/login.html",
        "window_size": "1280,800",
        "desc": "Authentication Gateway with Official Logo",
    },
    {
        "name": "screenshot_citizen_login.png",
        "url": "http://localhost:5055/citizen-login.html",
        "window_size": "1280,800",
        "desc": "Citizen Sign In & Registration with Official Logo",
    },
    {
        "name": "screenshot_municipal_login.png",
        "url": "http://localhost:5055/municipal/login.html",
        "window_size": "1280,800",
        "desc": "Municipal Official Login with Official Logo",
    },
    {
        "name": "screenshot_live_monitor.png",
        "url": "http://localhost:5055/dashboard/dashboard.html",
        "window_size": "1440,900",
        "desc": "Live Sensor & Telemetry Operations Console with Official Logo",
    },
]


def capture():
    print(f"Starting screenshot capture to {ARTIFACT_DIR}...")
    for item in PAGES_TO_CAPTURE:
        out_path = os.path.join(ARTIFACT_DIR, item["name"])
        cmd = [
            CHROME_BIN,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            f"--window-size={item['window_size']}",
            f"--screenshot={out_path}",
            item["url"],
        ]
        print(f"Capturing {item['desc']} -> {item['name']} ({item['window_size']})...")
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                print(f"  [OK] {item['name']} ({os.path.getsize(out_path)} bytes)")
            else:
                print(f"  [FAIL] {item['name']}: {res.stderr}")
        except Exception as e:
            print(f"  [ERROR] {item['name']}: {e}")

    print("Capture complete.")


if __name__ == "__main__":
    capture()
