import inspect
import json
import os
from typing import Any, Awaitable, Callable, Dict, Optional, Type, TypeVar

from dotenv import load_dotenv
from loguru import logger
from openai import AsyncAzureOpenAI
from pydantic import BaseModel

from ..contracts import PassageExamDocument, PassageGroup, PassageQuestion, QuestionChoice
from ..parser import ParsedSourceDocument
from ..utils import ensure_html_paragraphs, load_json_document
from .prompt import (
    ANSWER_SYSTEM_PROMPT,
    GROUPS_SYSTEM_PROMPT,
    build_answer_prompt,
    build_groups_prompt,
)
from .state import AnswerKeyPayload, GeneratedGroupsPayload, QuizGenerationState

load_dotenv()

T = TypeVar("T", bound=BaseModel)
ProgressCallback = Callable[[str, Dict[str, Any]], Optional[Awaitable[None]]]


def _validate_model(model_class: Type[T],
                    payload: Dict[str, Any]) -> T:
    return model_class.model_validate(payload)


async def _emit_progress(
    progress_callback: Optional[ProgressCallback],
    stage: str,
    **payload: Any,
) -> None:
    if progress_callback is None:
        return
    result = progress_callback(stage, payload)
    if inspect.isawaitable(result):
        await result


def build_generation_state(
    *,
    title: str,
    description: str,
    groups_payload: GeneratedGroupsPayload,
) -> QuizGenerationState:
    return QuizGenerationState(
        title=title,
        description=description,
        groups=groups_payload.groups,
    )


def build_document_from_state(
    *,
    state: QuizGenerationState,
    answer_key: AnswerKeyPayload,
) -> PassageExamDocument:
    answer_map = {
        (answer.group_order, answer.question_order):
        answer.correct_choice_order
        for answer in answer_key.answers
    }
    expected_pairs = {(group.order, question.order)
                      for group in state.groups
                      for question in group.questions}
    answer_pairs = set(answer_map)

    if expected_pairs != answer_pairs:
        raise ValueError("answer key does not match generated quiz state")

    final_groups = []
    for group in sorted(state.groups, key=lambda item: item.order):
        final_questions = []
        for question in sorted(group.questions, key=lambda item: item.order):
            correct_choice_order = answer_map[(group.order, question.order)]
            final_questions.append(
                PassageQuestion(
                    order=question.order,
                    type="multiple_choice",
                    question=ensure_html_paragraphs(question.question),
                    choices=[
                        QuestionChoice(
                            content=ensure_html_paragraphs(choice.content),
                            is_correct=index == correct_choice_order,
                        ) for index, choice in enumerate(question.choices,
                                                         start=1)
                    ],
                ))

        final_groups.append(
            PassageGroup(
                order=group.order,
                passage=ensure_html_paragraphs(group.passage),
                questions=final_questions,
            ))

    return PassageExamDocument(
        title=state.title,
        description=state.description,
        groups=final_groups,
    )


class AzureOpenAIPassageClient:

    def __init__(self) -> None:
        self.api_key = os.getenv("AZURE_OPENAI_API_KEY")
        self.azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        self.api_version = os.getenv("AZURE_OPENAI_API_VERSION")
        self.deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME",
                                         "gpt-4o")

        if not self.api_key or not self.azure_endpoint or not self.api_version:
            raise ValueError(
                "Azure OpenAI credentials are required: AZURE_OPENAI_API_KEY, "
                "AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_VERSION")

        self.client = AsyncAzureOpenAI(
            api_key=self.api_key,
            azure_endpoint=self.azure_endpoint,
            api_version=self.api_version,
        )

    async def _create_json_completion(self, *, system_prompt: str,
                                      user_prompt: str) -> Dict[str, Any]:
        logger.info(
            "Sending request to Azure OpenAI (deployment: {}). Waiting for response...",
            self.deployment_name)
        response = await self.client.chat.completions.create(
            model=self.deployment_name,
            temperature=0.0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_prompt
                },
            ],
        )
        logger.info("Received response from Azure OpenAI.")
        message = response.choices[0].message.content or "{}"
        return load_json_document(message)

    async def generate_groups(
        self,
        *,
        source: ParsedSourceDocument,
        title: str,
        description: str,
        questions_per_group: Optional[int],
    ) -> Dict[str, Any]:
        logger.debug("Generating quiz groups for {}", source.path)
        return await self._create_json_completion(
            system_prompt=GROUPS_SYSTEM_PROMPT,
            user_prompt=build_groups_prompt(
                source=source,
                title=title,
                description=description,
                questions_per_group=questions_per_group,
            ),
        )

    async def answer_quiz(
        self,
        *,
        state: QuizGenerationState,
    ) -> Dict[str, Any]:
        logger.debug("Answering quiz state '{}'", state.title)
        return await self._create_json_completion(
            system_prompt=ANSWER_SYSTEM_PROMPT,
            user_prompt=build_answer_prompt(state),
        )


class PassageExamGenerator:

    def __init__(self, client: Optional[Any] = None) -> None:
        self.client = client or AzureOpenAIPassageClient()

    async def generate(
        self,
        *,
        source: ParsedSourceDocument,
        title: Optional[str] = None,
        description: str = "",
        questions_per_group: Optional[int] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> PassageExamDocument:
        resolved_title = title or source.title
        resolved_description = description or f"Generated from source file {source.title}"

        logger.info(
            "Starting exam generation for '{}'. Questions per group: {}",
            resolved_title,
            questions_per_group or "Auto",
        )

        await _emit_progress(
            progress_callback,
            "starting",
            title=resolved_title,
            source_title=source.title,
            questions_per_group=questions_per_group,
            message="Preparing generation request.",
        )
        logger.info("Step 1/2: Requesting group generation from OpenAI...")
        await _emit_progress(
            progress_callback,
            "requesting_groups",
            title=resolved_title,
            message="Generating passage groups from the source document.",
        )
        groups_payload = _validate_model(
            GeneratedGroupsPayload,
            await self.client.generate_groups(
                source=source,
                title=resolved_title,
                description=resolved_description,
                questions_per_group=questions_per_group,
            ),
        )

        total_questions = sum(
            len(group.questions) for group in groups_payload.groups)
        logger.info(
            "Generated {} passage groups with a total of {} questions. Proceeding to answer generation.",
            len(groups_payload.groups),
            total_questions,
        )
        await _emit_progress(
            progress_callback,
            "groups_generated",
            title=resolved_title,
            groups_count=len(groups_payload.groups),
            questions_count=total_questions,
            message=(
                f"Generated {len(groups_payload.groups)} passage groups and "
                f"{total_questions} questions. Solving answer key next."
            ),
        )

        state = build_generation_state(
            title=resolved_title,
            description=resolved_description,
            groups_payload=groups_payload,
        )

        logger.info("Step 2/2: Requesting answer generation from OpenAI...")
        await _emit_progress(
            progress_callback,
            "requesting_answers",
            title=resolved_title,
            groups_count=len(groups_payload.groups),
            questions_count=total_questions,
            message="Generating answer key for the draft questions.",
        )
        answer_key = _validate_model(
            AnswerKeyPayload,
            await self.client.answer_quiz(state=state),
        )

        logger.info(
            "Answer key successfully generated. Building final document.")
        await _emit_progress(
            progress_callback,
            "answers_generated",
            title=resolved_title,
            groups_count=len(groups_payload.groups),
            questions_count=total_questions,
            message="Answer key generated. Building normalized document.",
        )

        document = build_document_from_state(
            state=state,
            answer_key=answer_key,
        )
        logger.info(
            "Completed generation of normalized exam '{}' with {} passage groups and {} total questions",
            document.title, len(document.groups),
            sum(len(group.questions) for group in document.groups))
        await _emit_progress(
            progress_callback,
            "completed",
            title=document.title,
            groups_count=len(document.groups),
            questions_count=sum(len(group.questions) for group in document.groups),
            message="Generation completed successfully.",
        )
        return document


def dump_document_json(document: PassageExamDocument) -> str:
    if hasattr(document, "model_dump"):
        dumped = document.model_dump()
    else:
        dumped = document.dict()
    return json.dumps(dumped, ensure_ascii=False, indent=2)
