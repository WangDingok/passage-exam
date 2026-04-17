from typing import Any, Dict, List, Optional

from .client import HasuraGraphQLClient

GET_DRAFT_QUERY = """
query GetPassageExamDraft($id: uuid!, $eventsWhere: passage_exam_passage_exam_events_bool_exp!) {
  passage_exam_passage_exam_drafts_by_pk(id: $id) {
    id
    title
    description
    status
    source_filename
    source_extension
    source_text
    normalized_document_json
    generation_params_json
    publish_result_json
    error_message
    created_by
    updated_by
    created_at
    updated_at
    published_at
  }
  passage_exam_passage_exam_events(where: $eventsWhere, order_by: {created_at: desc}) {
    id
    draft_id
    event_type
    payload_json
    actor_id
    created_at
  }
}
"""

LIST_DRAFTS_QUERY = """
query ListPassageExamDrafts(
  $where: passage_exam_passage_exam_drafts_bool_exp!
  $limit: Int!
  $offset: Int!
) {
  passage_exam_passage_exam_drafts(
    where: $where
    limit: $limit
    offset: $offset
    order_by: [{updated_at: desc}, {created_at: desc}]
  ) {
    id
    title
    description
    status
    source_filename
    source_extension
    created_by
    updated_by
    created_at
    updated_at
    published_at
    error_message
    publish_result_json
  }
}
"""

CREATE_DRAFT_MUTATION = """
mutation CreatePassageExamDraft($object: passage_exam_passage_exam_drafts_insert_input!) {
  insert_passage_exam_passage_exam_drafts_one(object: $object) {
    id
    title
    description
    status
    source_filename
    source_extension
    source_text
    normalized_document_json
    generation_params_json
    publish_result_json
    error_message
    created_by
    updated_by
    created_at
    updated_at
    published_at
  }
}
"""

UPDATE_DRAFT_MUTATION = """
mutation UpdatePassageExamDraft($id: uuid!, $set: passage_exam_passage_exam_drafts_set_input!) {
  update_passage_exam_passage_exam_drafts_by_pk(pk_columns: {id: $id}, _set: $set) {
    id
    title
    description
    status
    source_filename
    source_extension
    source_text
    normalized_document_json
    generation_params_json
    publish_result_json
    error_message
    created_by
    updated_by
    created_at
    updated_at
    published_at
  }
}
"""

CREATE_EVENT_MUTATION = """
mutation CreatePassageExamEvent($object: passage_exam_passage_exam_events_insert_input!) {
  insert_passage_exam_passage_exam_events_one(object: $object) {
    id
    draft_id
    event_type
    payload_json
    actor_id
    created_at
  }
}
"""


class PassageExamWorkflowOperations:

    def __init__(self, client: HasuraGraphQLClient):
        self.client = client

    async def get_draft(self, draft_id: str) -> Dict[str, Any]:
        result = await self.client.execute(
            query=GET_DRAFT_QUERY,
            operation_name="GetPassageExamDraft",
            variables={
                "id": draft_id,
                "eventsWhere": {
                    "draft_id": {
                        "_eq": draft_id
                    }
                },
            },
        )
        return {
            "draft": result.get("passage_exam_passage_exam_drafts_by_pk"),
            "events": result.get("passage_exam_passage_exam_events", []),
        }

    async def list_drafts(self, *, where: Dict[str, Any], limit: int,
                          offset: int) -> List[Dict[str, Any]]:
        result = await self.client.execute(
            query=LIST_DRAFTS_QUERY,
            operation_name="ListPassageExamDrafts",
            variables={
                "where": where,
                "limit": limit,
                "offset": offset
            },
        )
        return result.get("passage_exam_passage_exam_drafts", [])

    async def create_draft(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        result = await self.client.execute(
            query=CREATE_DRAFT_MUTATION,
            operation_name="CreatePassageExamDraft",
            variables={"object": payload},
        )
        return result.get("insert_passage_exam_passage_exam_drafts_one", {})

    async def update_draft(
            self, draft_id: str,
            payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        result = await self.client.execute(
            query=UPDATE_DRAFT_MUTATION,
            operation_name="UpdatePassageExamDraft",
            variables={
                "id": draft_id,
                "set": payload
            },
        )
        return result.get("update_passage_exam_passage_exam_drafts_by_pk")

    async def create_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        result = await self.client.execute(
            query=CREATE_EVENT_MUTATION,
            operation_name="CreatePassageExamEvent",
            variables={"object": payload},
        )
        return result.get("insert_passage_exam_passage_exam_events_one", {})
