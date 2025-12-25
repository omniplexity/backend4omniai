from __future__ import annotations

from typing import Any, Dict, Literal, Type

from pydantic import BaseModel, Field

from services.tooling import web_search


class ToolInput(BaseModel):
    pass


class WebSearchInput(BaseModel):
    query: str = Field(..., description="Search query")
    max_results: int = Field(5, ge=1, le=10, description="Maximum number of results")


class ToolBase:
    name: str = ""
    description: str = ""
    input_model: Type[BaseModel] = ToolInput
    execution: Literal["in_process", "mcp_docker"] = "in_process"
    default_enabled: bool = True

    async def invoke(self, data: BaseModel) -> Dict[str, Any]:
        raise NotImplementedError

    def input_schema(self) -> Dict[str, Any]:
        model = self.input_model
        if hasattr(model, "model_json_schema"):
            return model.model_json_schema()
        return model.schema()


class WebSearchTool(ToolBase):
    name = "web_search"
    description = "Search the web (DuckDuckGo lite) and return title/snippet results."
    input_model = WebSearchInput
    execution = "in_process"
    default_enabled = True

    async def invoke(self, data: WebSearchInput) -> Dict[str, Any]:
        results = await web_search(data.query, max_results=data.max_results)
        return {"results": results}


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolBase] = {}

    def register(self, tool: ToolBase) -> ToolBase:
        self._tools[tool.name] = tool
        return tool

    def list_tools(self) -> list[ToolBase]:
        return list(self._tools.values())

    def get(self, name: str) -> ToolBase | None:
        return self._tools.get(name)


TOOL_REGISTRY = ToolRegistry()
TOOL_REGISTRY.register(WebSearchTool())
