"""
scripts/capture_mailbox_screenshot.py
-------------------------------------
Captures high-resolution screenshot of the GhostPen mailbox table via Chrome DevTools Protocol.
"""

import asyncio
import base64
import json
import os
import shutil
import subprocess
import urllib.request
import websockets

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_FILE = os.path.join(REPO_ROOT, "artifacts", "mailbox_table_screenshot.png")
BRAIN_DIR = r"C:\Users\SIMI\.gemini\antigravity\brain\a7dcccad-fbdb-4892-b92d-5ff0efb4cec7"
BRAIN_OUT = os.path.join(BRAIN_DIR, "mailbox_table_screenshot.png")
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


async def capture():
    user_data_dir = os.path.join(REPO_ROOT, ".chrome_temp_mailbox")
    proc = subprocess.Popen([
        CHROME_PATH,
        "--headless=new",
        "--disable-gpu",
        "--remote-debugging-port=9223",
        f"--user-data-dir={user_data_dir}",
        "--window-size=1600,2200",
        "http://localhost:8501",
    ])

    try:
        ws_url = None
        for _ in range(25):
            try:
                tabs = json.loads(urllib.request.urlopen("http://localhost:9223/json").read())
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
            await ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
            await ws.recv()

            print("Waiting for Streamlit mailbox table to render...")
            await asyncio.sleep(7.0)

            # Scroll table into view and get its bounding rect
            eval_req = {
                "id": 2,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": """
                    (() => {
                        const table = document.querySelector('.mailbox-table-container');
                        if (!table) return null;
                        table.scrollIntoView({ block: 'start', behavior: 'instant' });
                        const rect = table.getBoundingClientRect();
                        return { x: rect.x, y: window.scrollY + rect.y, width: rect.width, height: rect.height };
                    })()
                    """,
                    "returnByValue": True,
                },
            }
            await ws.send(json.dumps(eval_req))
            resp = json.loads(await ws.recv())
            clip_data = resp.get("result", {}).get("result", {}).get("value")
            print("Mailbox clip:", clip_data)

            await asyncio.sleep(1.0)

            # Capture screenshot
            params = {}
            if clip_data and clip_data.get("width", 0) > 0:
                params["clip"] = {
                    "x": max(0, clip_data["x"] - 15),
                    "y": 0,  # after scrollIntoView, table is at the top of the viewport
                    "width": clip_data["width"] + 30,
                    "height": min(1200, clip_data["height"] + 40),
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
            print(f"[OK] Saved screenshot to: {OUT_FILE} ({len(img_bytes)} bytes)")

            if os.path.exists(BRAIN_DIR):
                with open(BRAIN_OUT, "wb") as f:
                    f.write(img_bytes)
                print(f"[OK] Saved copy to brain artifacts: {BRAIN_OUT}")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    asyncio.run(capture())
