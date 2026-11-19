"""Structured source-grounded answers shared by generation and evaluation."""

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    index: int = Field(ge=1, le=10)
    quote: str = Field(min_length=2, max_length=450)


class GroundedClaim(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    evidence: list[Evidence] = Field(min_length=1, max_length=4)


class GroundedAnswer(BaseModel):
    sufficient: bool
    claims: list[GroundedClaim] = Field(default_factory=list, max_length=10)
