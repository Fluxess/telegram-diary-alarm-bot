import os
import logging
from aiohttp import web
import database as db

logger = logging.getLogger(__name__)

async def handle_index(request):
    html_path = os.path.join(os.path.dirname(__file__), "webapp", "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return web.Response(text=f.read(), content_type="text/html")

async def handle_get_data(request):
    user_id = request.query.get("user_id")
    if not user_id:
        return web.json_response({"error": "user_id required"}, status=400)
    
    user_id = int(user_id)
    tasks = db.get_user_tasks(user_id, completed=None)
    diary = db.get_user_diary_entries(user_id, limit=20)
    return web.json_response({
        "tasks": tasks,
        "diary": diary
    })

async def handle_complete_task(request):
    task_id = request.query.get("task_id")
    if task_id:
        db.complete_task(int(task_id))
    return web.json_response({"status": "ok"})

def create_webapp():
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/user_data", handle_get_data)
    app.router.add_post("/api/complete_task", handle_complete_task)
    return app
