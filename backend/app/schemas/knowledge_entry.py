"""Bounded, plain-text authoring contracts; source type cannot change on edit."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EntryText(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="after")
    @classmethod
    def validate_text(cls, value):
        if isinstance(value, str):
            if not value.strip() or "\x00" in value:
                raise ValueError("内容不能为空或包含空字符")
            return value.strip()
        return value


class ManualCreate(EntryText):
    kind: Literal["manual"]
    title: str = Field(min_length=1, max_length=150)
    content: str = Field(min_length=1, max_length=20000)


class FAQCreate(EntryText):
    kind: Literal["faq"]
    question: str = Field(min_length=1, max_length=150)
    answer: str = Field(min_length=1, max_length=10000)
    alternative_questions: list[Annotated[str, Field(min_length=1, max_length=150)]] = Field(
        default_factory=list, max_length=5
    )

    @model_validator(mode="after")
    def normalize_alternatives(self):
        seen = {self.question.casefold()}
        unique = []
        for question in self.alternative_questions:
            question = question.strip()
            if not question or "\x00" in question:
                raise ValueError("相似问法不能为空或包含空字符")
            if question.casefold() not in seen:
                unique.append(question)
                seen.add(question.casefold())
        self.alternative_questions = unique
        return self


class ManualUpdate(ManualCreate):
    revision: int = Field(ge=1, strict=True)


class FAQUpdate(FAQCreate):
    revision: int = Field(ge=1, strict=True)


EntryCreate = Annotated[ManualCreate | FAQCreate, Field(discriminator="kind")]
EntryUpdate = Annotated[ManualUpdate | FAQUpdate, Field(discriminator="kind")]


class EntryRead(BaseModel):
    document_id: UUID
    revision: int
    entry: EntryCreate
