import os
from typing import Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from dotenv import load_dotenv

from ..graphql.client import GraphQLError
from ..workflow import (
    DraftGenerateRequest,
    DraftNotFoundError,
    DraftStatus,
    DraftUpdateRequest,
    PassageExamWorkflowService,
    build_validation_issues,
    ValidationResponse,
)

load_dotenv()


def _get_default_actor_id() -> Optional[str]:
    return os.getenv("PASSAGE_EXAM_CREATED_BY")


def get_actor_id(x_user_id: Optional[str] = Header(default=None,
                                                   alias="X-User-Id")) -> str:
    actor_id = _get_default_actor_id() or x_user_id
    if not actor_id:
        raise HTTPException(status_code=401,
                            detail="PASSAGE_EXAM_CREATED_BY env or X-User-Id header is required")
    return actor_id


def get_publish_actor_id(x_user_id: Optional[str] = Header(
    default=None, alias="X-User-Id")) -> str:
    actor_id = _get_default_actor_id() or x_user_id
    if not actor_id:
        raise HTTPException(
            status_code=401,
            detail="PASSAGE_EXAM_CREATED_BY env or X-User-Id header is required")
    return actor_id


def get_workflow_service() -> PassageExamWorkflowService:
    return PassageExamWorkflowService()


def model_to_payload(model):
    return model.model_dump()


def create_app() -> FastAPI:
    app = FastAPI(title="Passage Exam Workflow API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def healthcheck() -> dict:
        return {"ok": True}

    @app.get("/drafts")
    async def list_drafts(
            status: Optional[DraftStatus] = Query(default=None),
            search: Optional[str] = Query(default=None),
            created_by: Optional[str] = Query(default=None),
            updated_after: Optional[str] = Query(default=None),
            updated_before: Optional[str] = Query(default=None),
            limit: int = Query(default=50, ge=1, le=200),
            offset: int = Query(default=0, ge=0),
            service: PassageExamWorkflowService = Depends(
                get_workflow_service),
    ):
        return await service.list_drafts(
            status=status,
            search=search,
            created_by=created_by,
            updated_after=updated_after,
            updated_before=updated_before,
            limit=limit,
            offset=offset,
        )

    @app.get("/drafts/{draft_id}")
    async def get_draft(
            draft_id: str,
            service: PassageExamWorkflowService = Depends(
                get_workflow_service),
    ):
        try:
            return await service.get_draft(draft_id)
        except DraftNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/drafts/upload")
    async def upload_draft_source(
            file: UploadFile = File(...),
            actor_id: str = Depends(get_actor_id),
            service: PassageExamWorkflowService = Depends(
                get_workflow_service),
    ):
        if not file.filename:
            raise HTTPException(status_code=400, detail="filename is required")
        try:
            return await service.upload_source(
                filename=file.filename,
                content=await file.read(),
                actor_id=actor_id,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/drafts/{draft_id}/generate")
    async def generate_draft(
            draft_id: str,
            request: DraftGenerateRequest,
            actor_id: str = Depends(get_actor_id),
            service: PassageExamWorkflowService = Depends(
                get_workflow_service),
    ):
        try:
            return await service.generate(draft_id, request, actor_id=actor_id)
        except DraftNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.patch("/drafts/{draft_id}")
    async def update_draft(
            draft_id: str,
            request: DraftUpdateRequest,
            actor_id: str = Depends(get_actor_id),
            service: PassageExamWorkflowService = Depends(
                get_workflow_service),
    ):
        try:
            return await service.update_draft(draft_id,
                                              request,
                                              actor_id=actor_id)
        except DraftNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValidationError as error:
            raise HTTPException(
                status_code=422,
                detail=model_to_payload(
                    ValidationResponse(valid=False,
                                       issues=build_validation_issues(error))),
            ) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/drafts/{draft_id}/validate")
    async def validate_draft(
            draft_id: str,
            service: PassageExamWorkflowService = Depends(
                get_workflow_service),
    ):
        try:
            return await service.validate_draft(draft_id)
        except DraftNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/drafts/{draft_id}/publish")
    async def publish_draft(
            draft_id: str,
            actor_id: str = Depends(get_publish_actor_id),
            service: PassageExamWorkflowService = Depends(
                get_workflow_service),
    ):
        try:
            return await service.publish(draft_id,
                                         actor_id=actor_id,
                                         idempotency="skip")
        except DraftNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except GraphQLError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    return app


app = create_app()
