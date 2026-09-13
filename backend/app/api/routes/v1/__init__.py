"""API v1 router aggregation."""
# ruff: noqa: I001 - Imports structured for Jinja2 template conditionals

from fastapi import APIRouter

from app.api.routes.v1 import health
from app.api.routes.v1 import admin_users, auth, users
from app.api.routes.v1 import admin_ratings
from app.api.routes.v1 import conversations, public_demos
from app.api.routes.v1 import admin_conversations
from app.api.routes.v1 import agent
from app.api.routes.v1 import files
from app.api.routes.v1 import me_slash_commands
from app.api.routes.v1 import admin_stats

v1_router = APIRouter()

v1_router.include_router(health.router, tags=["health"])

v1_router.include_router(auth.router, prefix="/auth", tags=["auth"])
v1_router.include_router(users.router, prefix="/users", tags=["users"])

v1_router.include_router(admin_ratings.router, prefix="/admin/ratings", tags=["admin:ratings"])

v1_router.include_router(conversations.router, prefix="/conversations", tags=["conversations"])
v1_router.include_router(public_demos.router, prefix="/demos", tags=["demos"])

v1_router.include_router(agent.router, tags=["agent"])

v1_router.include_router(files.router, tags=["files"])

v1_router.include_router(
    admin_conversations.router, prefix="/admin/conversations", tags=["admin-conversations"]
)

v1_router.include_router(admin_users.router, prefix="/admin/users", tags=["admin:users"])
v1_router.include_router(
    me_slash_commands.router, prefix="/me/slash-commands", tags=["me:slash-commands"]
)
v1_router.include_router(admin_stats.router, prefix="/admin", tags=["admin:stats"])

from app.api.routes.v1 import knowledge

v1_router.include_router(knowledge.router, tags=["knowledge"])

from app.api.routes.v1 import agent_runs

v1_router.include_router(agent_runs.router)

from app.api.routes.v1 import projects

v1_router.include_router(projects.router)

from app.api.routes.v1 import memory

v1_router.include_router(memory.router)

from app.api.routes.v1 import chat_turns

v1_router.include_router(chat_turns.router)
