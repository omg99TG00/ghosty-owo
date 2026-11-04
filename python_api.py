# python_api.py
import threading
import asyncio
from datetime import datetime
from typing import Dict, Optional

from flask import Flask, jsonify, request
from flask_cors import CORS

from core.heart import WorkerState, WorkerManager, _run_farming_loop, PseudoCtx
from core.ui import log_info, log_warn

api = Flask(__name__)
CORS(api)

manager = WorkerManager()
_users: Dict[str, dict] = {}
_users_lock = threading.Lock()

class UserWorkerRef:
    def __init__(self, worker_num: int, token: str, channel_id: int):
        self.worker_num = worker_num
        self.token = token
        self.channel_id = channel_id
        self.username = None
        self.running = False
        self.valid = True
        self.bot = None
        self.ws: Optional[WorkerState] = None

def _get_or_create_user(user_id: str, username: str = "unknown") -> dict:
    with _users_lock:
        if user_id not in _users:
            _users[user_id] = {
                "user_id": user_id, "username": username, "workers": {},
                "next_num": 1, "created_at": datetime.now().isoformat(),
            }
        elif username and username != "unknown":
            _users[user_id]["username"] = username
        return _users[user_id]

def _run_worker_thread(user_id: str, ref: UserWorkerRef):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    label = f"[U{user_id}] [W#{ref.worker_num}]"
    try:
        from core.utils import create_bot
        bot = create_bot(ref.worker_num)
        ref.bot = bot

        ws = WorkerState(ref.worker_num)
        ws.bot = bot
        ws.auto_start_channel_id = ref.channel_id
        ws.current_speed_mode = "efficient"
        ws.huntbot_enabled = True
        ref.ws = ws

        manager.register_worker(ws)
        from core.heart import register_commands
        register_commands(bot, ws)

        @bot.event
        async def on_ready():
            ref.username = str(bot.user)
            ref.running = True
            log_info(f"{label} Ready as {bot.user}")
            if not ref.channel_id: return
            ok, blocking = manager.try_claim_channel(ref.channel_id, ref.worker_num)
            if not ok:
                log_warn(f"{label} Channel locked by W#{blocking}")
                return
            target = bot.get_channel(ref.channel_id) or await bot.fetch_channel(ref.channel_id)
            if not target: return
            ctx = PseudoCtx(target, bot)
            asyncio.create_task(_run_farming_loop(ctx, ws, bot))

        bot.run(ref.token, log_handler=None)
    except Exception as e:
        import traceback
        traceback.print_exc()
        ref.valid = False
        ref.running = False
        log_warn(f"{label} Worker died: {e}")

@api.route("/api/user/<user_id>/ensure", methods=["GET"])
def ensure_user(user_id: str):
    _get_or_create_user(user_id, request.args.get("username", "unknown"))
    return jsonify({"success": True})

@api.route("/api/user/<user_id>/status", methods=["GET"])
def user_status(user_id: str):
    with _users_lock:
        u = _users.get(user_id)
        if not u: return jsonify({"success": True, "workers": []})
        workers = [{"worker_num": r.worker_num, "username": r.username, "channel_id": r.channel_id, "valid": r.valid, "running": r.running, "state": r.ws.to_dict() if r.ws else None} for r in u["workers"].values()]
        return jsonify({"success": True, "workers": workers})

@api.route("/api/user/<user_id>/add_worker", methods=["POST"])
def add_worker(user_id: str):
    body = request.get_json(force=True, silent=True) or {}
    token = (body.get("token") or "").strip()
    channel_id = body.get("channel_id")
    if not token or not channel_id: return jsonify({"success": False, "error": "missing data"}), 400
    u = _get_or_create_user(user_id, body.get("username", "unknown"))
    with _users_lock:
        num = u["next_num"]
        u["next_num"] += 1
        ref = UserWorkerRef(num, token, int(channel_id))
        ref.username = body.get("username", "unknown")
        u["workers"][num] = ref
    threading.Thread(target=_run_worker_thread, args=(user_id, ref), daemon=True).start()
    return jsonify({"success": True, "worker_num": num})

def start_api(host="0.0.0.0", port=5000):
    log_info(f"[API] Bridge on http://{host}:{port}")
    try:
        from waitress import serve
        serve(api, host=host, port=port)
    except ImportError:
        api.run(host=host, port=port, debug=False, use_reloader=False)
