from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.data.operators import OPERATOR_PROFILES


class MissionInput(BaseModel):
    map: str
    squadSize: int = Field(ge=1, le=3)
    gameMode: Literal["normal", "confidential", "top_secret"] = "normal"
    tactic: Literal["稳健搜打", "高风险速撤", "潜行避战"]
    operators: list[str] = Field(min_length=1, max_length=3)
    weight: float = Field(gt=0, le=60)

    @field_validator("operators")
    @classmethod
    def normalize_operators(cls, operators: list[str]) -> list[str]:
        normalized = [name.strip() for name in operators if name.strip()]
        if not normalized:
            raise ValueError("at least one operator is required")
        if len(set(normalized)) != len(normalized):
            raise ValueError("operators must be unique")
        unknown = [name for name in normalized if name not in OPERATOR_PROFILES]
        if unknown:
            raise ValueError(f"unknown operators: {', '.join(unknown)}")
        return normalized


class AgentRequest(BaseModel):
    input: MissionInput
    round: int = Field(ge=1, le=4)
    context: dict[str, Any] = Field(default_factory=dict)
    phase: Literal["draft", "refine"] | None = None
    peers: dict[str, Any] = Field(default_factory=dict)


class CreateRunRequest(BaseModel):
    input: MissionInput
    maxRounds: int = Field(default=4, ge=1, le=4)
    workflowKey: str = "extraction-default"


class AgentVersionCreate(BaseModel):
    prompt: str = Field(min_length=20, max_length=20000)
    capabilities: list[str] = Field(min_length=1)
    tools: list[str] = Field(default_factory=list)
    priority: int = Field(default=50, ge=0, le=100)
    enabled: bool = True


class WorkflowVersionCreate(BaseModel):
    definition: dict[str, Any]
    enabled: bool = True


class ToolInvokeRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    provider: Literal["llm", "mock"]
    model: str | None
    fallback_to_mock: bool
