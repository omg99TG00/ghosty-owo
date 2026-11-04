"""
GhoSty OwO V4 - Python Worker Process
Selfbot workers (discord.py-self) + Flask bridge + web dashboard.
Controller (discord.js) runs in bot/index.js on a separate process.
"""

import os
import sys
import threading
import subprocess
import shutil

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from core.ui import log_info, log_success, log_warn

web_dashboard_enabled = os.environ.get(
    "WEB_DASHBOARD", "true"
).strip().lower() not in ("0", "false", "no", "off")

print("""
+================================================================+
|   GhoSty OwO V4 - Python Worker Process                        |
|                                                                |
|   Controller:  Node.js discord.js (separate process)           |
|   Workers:     discord.py-self (this process)                  |
|   Bridge API:  Flask on :5000                                  |
|   Dashboard:   Flask on :8765                                  |
+================================================================+
""")

from core.utils import create_bot
from core.heart import (
    WorkerState, WorkerManager, register_commands,
    _run_farming_loop, PseudoCtx
)

global_manager = WorkerManager()
global_manager.set_has_channels_config(True)


def ensure_node():
    """Download portable Node.js if not installed in the container."""
    if shutil.which("node"):
        return True

    node_dir = os.path.abspath("node-v18.20.2-linux-x64")
    node_bin = os.path.join(node_dir, "bin")

    if not os.path.exists(os.path.join(node_bin, "node")):
        log_info("Node.js not found. Downloading portable Node.js...")
        tar_url = "https://nodejs.org/dist/v18.20.2/node-v18.20.2-linux-x64.tar.xz"
        tar_file = "node.tar.xz"

        try:
            if shutil.which("curl"):
                subprocess.run(["curl", "-sLO", tar_url], check=True)
            elif shutil.which("wget"):
                subprocess.run(["wget", "-q", tar_url], check=True)
            else:
                import urllib.request
                urllib.request.urlretrieve(tar_url, tar_file)

            subprocess.run(["tar", "-xf", tar_file], check=True)
            os.remove(tar_file)
            log_success("Node.js downloaded and extracted.")
        except Exception as e:
            log_warn(f"Failed to download Node.js: {e}")
            return False

    os.environ["PATH"] = node_bin + os.pathsep + os.environ.get("PATH", "")
    return shutil.which("node") is not None


def _run_standalone_worker(token: str, channel_id: int, worker_num: int = 999):
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        bot = create_bot(worker_num)
        ws = WorkerState(worker_num)
        ws.bot = bot
        ws.auto_start_channel_id = channel_id
        ws.current_speed_mode = "efficient"
        ws.huntbot_enabled = True
        global_manager.register_worker(ws)
        register_commands(bot, ws)

        @bot.event
        async def on_ready():
            log_info(f"[STANDALONE] {bot.user} ready")
            if channel_id:
                ok, _ = global_manager.try_claim_channel(channel_id, worker_num)
                if ok:
                    ch = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
                    if ch:
                        await ch.send(f"Worker #{worker_num} online.")
                        asyncio.create_task(
                            _run_farming_loop(PseudoCtx(ch, bot), ws, bot)
                        )

        bot.run(token, log_handler=None)
    except Exception:
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    threads = []

    # 1. Flask bridge
    try:
        from python_api import start_api
        api_t = threading.Thread(target=start_api, daemon=True, name="PythonAPI")
        api_t.start()
        threads.append(api_t)
        log_success("Python API bridge started on :5000")
    except Exception as e:
        log_warn(f"API bridge failed: {e}")

    # 2. Dashboard
    if web_dashboard_enabled:
        try:
            from dashboard.app import start_server
            dash_t = threading.Thread(target=start_server, daemon=True, name="Dashboard")
            dash_t.start()
            threads.append(dash_t)
            log_success("Dashboard started on :8765")
        except Exception as e:
            log_warn(f"Dashboard: {e}")

    # 3. Optional standalone selfbot
    st = os.environ.get("SELFBOT_TOKEN", "").strip()
    sc = os.environ.get("SELFBOT_CHANNEL_ID", "").strip()
    if st and sc.isdigit():
        t = threading.Thread(
            target=_run_standalone_worker,
            args=(st, int(sc), 999),
            daemon=True, name="StandaloneWorker"
        )
        t.start()
        threads.append(t)
        log_success("Standalone worker started")

    # 4. Spawn Node.js controller automatically
    if os.path.exists("bot/index.js"):
        if ensure_node():
            try:
                if not os.path.exists("node_modules"):
                    log_info("Installing Node.js dependencies...")
                    subprocess.run(["npm", "install", "--quiet", "--no-audit", "--no-fund"], check=True)
                
                log_info("Starting Node.js controller...")
                node_proc = subprocess.Popen(["node", "bot/index.js"])
            except Exception as e:
                log_warn(f"Failed to start Node controller: {e}")
        else:
            log_warn("Could not find or install Node.js. Controller will not run.")
    else:
        log_warn("bot/index.js not found. Controller will not run.")

    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        log_info("Shutdown")
        sys.exit(0)
