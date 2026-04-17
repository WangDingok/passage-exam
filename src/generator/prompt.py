import json
from typing import Optional

from ..parser import ParsedSourceDocument
from .state import QuizGenerationState

GROUPS_SYSTEM_PROMPT = """You generate passage-based exam content in strict JSON.
Rules:
- Output valid JSON only.
- Output must match this schema:
  {
    "groups": [
      {
        "order": integer,
        "passage": string,
        "questions": [
          {
            "order": integer,
            "question": string,
            "choices": [
              {"content": string}
            ]
          }
        ]
      }
    ]
  }
- Each question must contain exactly 4 unique choices (each choice MUST NOT have True/False in content).
- Do not mark correct answers.
- Do not output HTML.
- Use the source only as style guidance and produce new classroom-ready questions (each question MUST NOT have True/False in content).
- Do not add markdown fences or commentary.
"""

ANSWER_SYSTEM_PROMPT = """You solve draft passage-based exams in strict JSON.
Rules:
- Output valid JSON only.
- Output must match this schema:
  {
    "answers": [
      {
        "group_order": integer,
        "question_order": integer,
        "correct_choice_order": integer
      }
    ]
  }
- Only answer the provided draft questions.
- Each correct_choice_order must be an integer from 1 to 4.
- Do not rewrite the passage, questions, or choices.
- Do not add markdown fences or commentary.
"""


def build_groups_prompt(
    source: ParsedSourceDocument,
    title: str,
    description: str,
    questions_per_group: Optional[int],
) -> str:
    question_count_instruction = (
        f"Generate exactly {questions_per_group} questions for each passage group."
        if questions_per_group else
        "Infer an appropriate number of questions per passage group from the source sample."
    )

    return f"""Create a new passage-based exam using the source sample below.

Requirements:
- Title: {title}
- Description: {description or f"Generated from source file {source.title}"}
- {question_count_instruction}
- Group related questions under the passage they depend on.
- If the source contains existing sample questions, use them only as style guidance and produce new questions.
- Keep the output concise, classroom-ready, and internally consistent.

Source title: {source.title}
Source content:
{source.text}
"""


def build_answer_prompt(state: QuizGenerationState) -> str:
    if hasattr(state, "model_dump"):
        dumped = state.model_dump()
    else:
        dumped = state.dict()
    state_json = json.dumps(dumped, ensure_ascii=False, indent=2)
    return f"""Read the passage and solve the quiz below.

Return only the answer key JSON.

Quiz state:
{state_json}
"""
