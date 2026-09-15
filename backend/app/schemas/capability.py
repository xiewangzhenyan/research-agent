"""Bounded browser contracts. Secret replacement is explicit and write-only."""

import json
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AssetWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int | None = Field(default=None, ge=1)
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1200)
    scope: Literal["personal", "project", "system"] = "personal"
    tags: list[str] = Field(default_factory=list, max_length=10)
    enabled: bool = False
    config: dict = Field(default_factory=dict)
    secrets: dict[str, str] | None = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def bounded(self):
        if not self.name.strip() or any(not t.strip() or len(t) > 30 for t in self.tags):
            raise ValueError("名称与标签不能为空或过长")
        if len(json.dumps(self.config)) > 300000 or len(json.dumps(self.secrets)) > 20000:
            raise ValueError("配置内容过长")
        return self


class RevisionAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)


class RestoreAction(RevisionAction):
    version: int = Field(ge=1)


class SkillFileWrite(RevisionAction):
    path: str = Field(max_length=240)
    content: str = Field(max_length=100000)


class ToggleAction(RevisionAction):
    enabled: bool


class BindingsWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_ids: list[UUID] = Field(max_length=12)
    revision: str = Field(max_length=64)


class MCPConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transport: Literal["streamable-http", "sse", "stdio"] = "streamable-http"
    url: str = Field(default="", max_length=2048)
    command: str = Field(default="", max_length=200)
    args: list[str] = Field(default_factory=list, max_length=30)
    enabled_tools: list[str] = Field(default_factory=list, max_length=30)
    auto_approved_tools: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def valid(self):
        if self.transport == "stdio":
            if not self.command.strip() or any(len(a) > 1000 for a in self.args):
                raise ValueError("请填写启动命令；参数最多 1000 字")
        elif not self.url.strip():
            raise ValueError("请填写 MCP 服务地址")
        if any(not re.fullmatch(r"[\w.:-]{1,128}", n) for n in self.enabled_tools):
            raise ValueError("工具名称无效")
        if not set(self.auto_approved_tools) <= set(self.enabled_tools):
            raise ValueError("免逐次确认的工具必须先启用")
        return self
