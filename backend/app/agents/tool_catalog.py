"""Versioned declarations shared by registration, authorization and discovery."""

from dataclasses import dataclass

DATETIME_TOOL = "current_datetime"
ASK_USER_TOOL = "ask_user"
PYTHON_TOOL = "run_python"
CHAT_TOOL_NAMES = (DATETIME_TOOL, ASK_USER_TOOL)
TOOL_POLICY_VERSION = "tools-v1"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    label: str
    description: str
    execution: str
    timeout_seconds: int | None
    output_limit_bytes: int
    retry: str


TOOL_SPECS = {
    DATETIME_TOOL: ToolSpec(
        DATETIME_TOOL, "当前时间", "查询服务器日期与时间", "application", 2, 2048, "read_only"
    ),
    ASK_USER_TOOL: ToolSpec(
        ASK_USER_TOOL,
        "用户澄清",
        "缺少必要信息时暂停并询问",
        "interaction",
        None,
        100000,
        "durable_pause",
    ),
    PYTHON_TOOL: ToolSpec(
        PYTHON_TOOL,
        "Python 计算",
        "在独立、禁网的隔离环境中执行 Python；文件与数据分析能力由节点配置决定",
        "sandbox",
        30,
        32768,
        "same_code_reuses_result",
    ),
}
