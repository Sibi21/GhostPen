"""
scripts/capture_sidebar_screenshot.py
-------------------------------------
Captures high-resolution screenshot of Streamlit sidebar via Chrome DevTools Protocol.
"""

import asyncio
import base64
import json
import os
import subprocess
import time
import urllib.request
import websockets

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_FILE = os.path.join(REPO_ROOT, "artifacts", "sidebar_screenshot.png")
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


async def capture():
    # Start Chrome with remote debugging on port 9222
    user_data_dir = os.path.join(REPO_ROOT, ".chrome_temp")
    proc = subprocess.Popen([
        CHROME_PATH,
        "--headless=new",
        "--disable-gpu",
        "--remote-debugging-port=9222",
        f"--user-data-dir={user_data_dir}",
        "--window-size=1300,1050",
        "http://localhost:8501",
    ])

    try:
        # Wait for debugging endpoint
        ws_url = None
        for _ in range(20):
            try:
                tabs = json.loads(urllib.request.urlopen("http://localhost:9222/json").read())
                for t in tabs:
                    if "8501" in t.get("url", ""):
                        ws_url = t["webSocketDebuggerUrl"]
                        break
                if ws_url:
                    break
            except Exception:
                pass
            await asyncio.sleep(0.5)

        if not ws_url:
            raise RuntimeError("Could not connect to Chrome debugging target on localhost:8501")

        print("Connected to Chrome target:", ws_url)

        async with websockets.connect(ws_url) as ws:
            # Enable Runtime and DOM
            await ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
            await ws.recv()

            # Wait for Streamlit sidebar to render
            print("Waiting for Streamlit to render...")
            await asyncio.sleep(6.0)

            # Evaluate script to get sidebar clip if desired, or capture full page
            eval_req = {
                "id": 2,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": """
                    (() => {
                        const sb = document.querySelector('section[data-testid="stSidebar"]');
                        if (!sb) return null;
                        const rect = sb.getBoundingClientRect();
                        return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
                    })()
                    """,
                    "returnByValue": True,
                },
            }
            await ws.send(json.dumps(eval_req))
            resp = json.loads(await ws.recv())
            clip_data = resp.get("result", {}).get("result", {}).get("value")
            print("Sidebar clip:", clip_data)

            # Capture screenshot
            params = {}
            if clip_data and clip_data.get("width", 0) > 0:
                params["clip"] = {
                    "x": max(0, clip_data["x"]),
                    "y": max(0, clip_data["y"]),
                    "width": clip_data["width"] + 20,
                    "height": min(1000, max(600, clip_data["height"])),
                    "scale": 1,
                }

            snap_req = {
                "id": 3,
                "method": "Page.captureScreenshot",
                "params": params,
            }
            await ws.send(json.dumps(snap_req))
            snap_resp = json.loads(await ws.recv())

            img_base64 = snap_resp["result"]["data"]
            img_bytes = base64.b64decode(img_base64)

            os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
            with open(OUT_FILE, "wb") as f:
                f.write(img_bytes)

            print(f"[OK] Saved sidebar screenshot to: {OUT_FILE} ({len(img_bytes)} bytes)")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    asyncio.run(capture())
