from typing import List, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class QuestionChoice(BaseModel):
    content: str = Field(...,
                         description="Choice content rendered as safe HTML.")
    is_correct: bool = False

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("choice content must not be empty")
        return text


class PassageQuestion(BaseModel):
    order: int = Field(ge=1)
    type: Literal["multiple_choice"] = "multiple_choice"
    question: str
    choices: List[QuestionChoice] = Field(min_length=4, max_length=4)

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("question must not be empty")
        return text

    @model_validator(mode="after")
    def validate_single_choice(self):
        choices = self.choices or []
        correct_count = sum(1 for choice in choices if choice.is_correct)
        if correct_count != 1:
            raise ValueError(
                "multiple_choice questions must contain exactly one correct answer"
            )
        return self


class PassageGroup(BaseModel):
    order: int = Field(ge=1)
    passage: str
    questions: List[PassageQuestion] = Field(min_length=1)

    @field_validator("passage")
    @classmethod
    def validate_passage(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("passage must not be empty")
        return text

    @model_validator(mode="after")
    def validate_unique_question_order(self):
        questions = self.questions or []
        orders = [question.order for question in questions]
        if len(orders) != len(set(orders)):
            raise ValueError(
                "question order values must be unique within a passage group")
        return self


class PassageExamDocument(BaseModel):
    title: str
    description: str = ""
    groups: List[PassageGroup] = Field(min_length=1)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("title must not be empty")
        return text

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: str) -> str:
        return (value or "").strip()

    @model_validator(mode="after")
    def validate_unique_group_order(self):
        groups = self.groups or []
        orders = [group.order for group in groups]
        if len(orders) != len(set(orders)):
            raise ValueError(
                "group order values must be unique within a document")
        return self

    def sorted_copy(self) -> "PassageExamDocument":
        sorted_groups = []
        for group in sorted(self.groups, key=lambda item: item.order):
            sorted_questions = sorted(group.questions,
                                      key=lambda item: item.order)
            sorted_groups.append(
                PassageGroup(
                    order=group.order,
                    passage=group.passage,
                    questions=sorted_questions,
                ))
        return PassageExamDocument(
            title=self.title,
            description=self.description,
            groups=sorted_groups,
        )
