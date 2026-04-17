from typing import List

from pydantic import BaseModel, Field, field_validator, model_validator


class GeneratedChoice(BaseModel):
    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("choice content must not be empty")
        return text


class GeneratedQuestion(BaseModel):
    order: int = Field(ge=1)
    question: str
    choices: List[GeneratedChoice] = Field(min_length=4, max_length=4)

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("question must not be empty")
        return text

    @model_validator(mode="after")
    def validate_unique_choice_content(self):
        choices = self.choices or []
        contents = [choice.content for choice in choices]
        if len(contents) != len(set(contents)):
            raise ValueError("question choices must be unique")
        return self


class GeneratedGroup(BaseModel):
    order: int = Field(ge=1)
    passage: str
    questions: List[GeneratedQuestion] = Field(min_length=1)

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
                "question order values must be unique within a generated group"
            )
        return self


class GeneratedGroupsPayload(BaseModel):
    groups: List[GeneratedGroup] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_group_order(self):
        groups = self.groups or []
        orders = [group.order for group in groups]
        if len(orders) != len(set(orders)):
            raise ValueError(
                "group order values must be unique within generated groups")
        return self


class AnswerSelection(BaseModel):
    group_order: int = Field(ge=1)
    question_order: int = Field(ge=1)
    correct_choice_order: int = Field(ge=1, le=4)


class AnswerKeyPayload(BaseModel):
    answers: List[AnswerSelection] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_answer_targets(self):
        answers = self.answers or []
        pairs = [(answer.group_order, answer.question_order)
                 for answer in answers]
        if len(pairs) != len(set(pairs)):
            raise ValueError("answers must target unique group/question pairs")
        return self


class QuizGenerationState(BaseModel):
    title: str
    description: str
    groups: List[GeneratedGroup] = Field(min_length=1)

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
                "group order values must be unique within generation state")
        return self
