from typing import Any, Dict, List, Optional

from .client import HasuraGraphQLClient

QUESTION_CATEGORIES_QUERY = """
query GetAllQuestionCategories($filter: question_categories_bool_exp!) {
  question_categories(where: {_and: [$filter, {is_deleted: {_eq: false}}]}) {
    id
    code
    name
    children {
      id
      code
      name
      children {
        id
        code
        name
        children {
          id
          code
          name
        }
      }
    }
  }
}
"""

MATERIAL_CATEGORIES_QUERY = """
query GetMaterialCategories($where: material_categories_bool_exp) {
  material_categories(where: $where) {
    id
    code
  }
}
"""

FIND_EXISTING_MATERIAL_QUERY = """
query FindExistingMaterial($title: String!, $descriptionPattern: String!) {
  materials(
    where: {
      title: {_eq: $title}
      description: {_ilike: $descriptionPattern}
      is_deleted: {_eq: false}
    }
    limit: 1
  ) {
    id
    title
    description
  }
}
"""

FIND_MATERIAL_BY_ID_QUERY = """
query FindMaterialById($id: uuid!) {
  materials_by_pk(id: $id) {
    id
    title
    description
  }
}
"""

CREATE_EXAM_MUTATION = """
mutation SaveExamWithMaterial($object: exams_insert_input!) {
  insert_exams_one(object: $object) {
    id
    description
    material_id
    materials {
      id
      title
      is_published
    }
    exam_questions {
      id
      question_id
      question {
        id
        sub_questions(order_by: {order_number: asc}) {
          id
        }
      }
    }
  }
}
"""


class PassageQuestionOperations:

    def __init__(self, client: HasuraGraphQLClient):
        self.client = client

    async def get_categories(self) -> List[Dict[str, Any]]:
        result = await self.client.execute(
            query=QUESTION_CATEGORIES_QUERY,
            operation_name="GetAllQuestionCategories",
            variables={"filter": {
                "parent_id": {
                    "_is_null": True
                }
            }},
        )
        return result.get("question_categories", [])


class ExamOperations:

    def __init__(self, client: HasuraGraphQLClient):
        self.client = client

    async def get_material_categories(self) -> List[Dict[str, Any]]:
        result = await self.client.execute(
            query=MATERIAL_CATEGORIES_QUERY,
            operation_name="GetMaterialCategories",
            variables={"where": {
                "is_deleted": {
                    "_eq": False
                }
            }},
        )
        return result.get("material_categories", [])

    async def find_existing_material(
            self, title: str, hash_marker: str) -> Optional[Dict[str, Any]]:
        result = await self.client.execute(
            query=FIND_EXISTING_MATERIAL_QUERY,
            operation_name="FindExistingMaterial",
            variables={
                "title": title,
                "descriptionPattern": f"%{hash_marker}%",
            },
        )
        materials = result.get("materials", [])
        return materials[0] if materials else None

    async def find_material_by_id(
            self, material_id: str) -> Optional[Dict[str, Any]]:
        result = await self.client.execute(
            query=FIND_MATERIAL_BY_ID_QUERY,
            operation_name="FindMaterialById",
            variables={"id": material_id},
        )
        return result.get("materials_by_pk")

    async def create_exam(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        result = await self.client.execute(
            query=CREATE_EXAM_MUTATION,
            operation_name="SaveExamWithMaterial",
            variables=payload,
        )
        return result.get("insert_exams_one", {})
