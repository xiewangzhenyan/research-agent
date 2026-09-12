"""Server-owned policy: task choices may reduce permission, never expand it."""

from app.agents.tool_catalog import CHAT_TOOL_NAMES, PYTHON_TOOL, TOOL_POLICY_VERSION, TOOL_SPECS
from app.core.config import settings
from app.core.exceptions import AuthorizationError, BadRequestError
from app.services import sandbox_client


async def tool_catalog(user):
    sandbox = await sandbox_client.health()
    eligible = bool(user and (user.is_app_admin or settings.SANDBOX_ALLOW_PUBLIC))
    items = []
    for name, spec in TOOL_SPECS.items():
        available = name in CHAT_TOOL_NAMES or (eligible and sandbox["status"] == "ready")
        items.append(
            {
                "id": name,
                "label": spec.label,
                "description": spec.description,
                "version": TOOL_POLICY_VERSION,
                "execution": spec.execution,
                "available": available,
                "default_enabled": name in CHAT_TOOL_NAMES,
                "timeout_seconds": spec.timeout_seconds,
                "output_limit_bytes": spec.output_limit_bytes,
                "retry": spec.retry,
                "reason": None
                if available
                else "独立沙箱尚未就绪"
                if sandbox["status"] != "ready"
                else "当前仅开放管理员验证",
            }
        )
    return {"version": TOOL_POLICY_VERSION, "items": items, "sandbox": sandbox}


async def resolve_tools(user, requested):
    names = list(dict.fromkeys(CHAT_TOOL_NAMES if requested is None else requested))
    if any(name not in TOOL_SPECS for name in names):
        raise BadRequestError(message="任务包含未注册工具")
    if PYTHON_TOOL in names:
        catalog = await tool_catalog(user)
        if not next(i["available"] for i in catalog["items"] if i["id"] == PYTHON_TOOL):
            raise AuthorizationError(message="当前账号的隔离代码执行尚未就绪")
    return names
