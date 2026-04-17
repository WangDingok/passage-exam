import json
import os
from typing import Any, Dict, Optional

import httpx
from loguru import logger


class GraphQLError(Exception):
    """Raised when a GraphQL operation fails."""

    def __init__(self, errors: Any):
        self.errors = errors if isinstance(errors, list) else [errors]
        message = json.dumps(self.errors, ensure_ascii=False, indent=2)
        super().__init__(message)


class HasuraGraphQLClient:

    def __init__(self,
                 api_url: Optional[str] = None,
                 admin_secret: Optional[str] = None):
        api_url = api_url or os.getenv("GRAPHQL_URL")
        admin_secret = admin_secret or os.getenv("HASURA_ADMIN_SECRET")

        if not api_url:
            raise ValueError("GRAPHQL_URL not configured")
        if not admin_secret:
            raise ValueError("HASURA_ADMIN_SECRET not configured")
            
        self.api_url: str = api_url
        self.admin_secret: str = admin_secret

        self.headers = {
            "Content-Type": "application/json",
            "X-Hasura-Admin-Secret": self.admin_secret,
        }
        self._http_client = httpx.AsyncClient(timeout=30.0, headers=self.headers)

    async def execute(
        self,
        *,
        query: str,
        operation_name: Optional[str] = None,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"query": query}
        if operation_name:
            payload["operationName"] = operation_name
        if variables is not None:
            payload["variables"] = variables

        logger.debug("Executing Hasura operation {}", operation_name
                     or "unnamed")
                     
        response = await self._http_client.post(self.api_url, json=payload)
        response.raise_for_status()
        result = response.json()

        if "errors" in result:
            raise GraphQLError(result["errors"])
        return result.get("data", {})
        
    async def close(self):
        await self._http_client.aclose()
