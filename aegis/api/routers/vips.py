"""VIP configuration endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from aegis.api import schemas
from aegis.api.services.vips import VipService
from aegis.common.db import get_session
from aegis.common.models.enums import AliasKind

router = APIRouter(prefix="/vips", tags=["vips"])


def get_vip_service(session: Session = Depends(get_session)) -> VipService:
    return VipService(session)


@router.post("", response_model=schemas.VipRead, status_code=status.HTTP_201_CREATED)
def create_vip(
    payload: schemas.VipCreate,
    service: VipService = Depends(get_vip_service),
) -> schemas.VipRead:
    return schemas.VipRead.model_validate(service.create_vip(payload))


@router.get("", response_model=list[schemas.VipRead])
def list_vips(service: VipService = Depends(get_vip_service)) -> list[schemas.VipRead]:
    return [schemas.VipRead.model_validate(vip) for vip in service.list_vips()]


@router.get("/{vip_id}", response_model=schemas.VipRead)
def get_vip(
    vip_id: uuid.UUID,
    service: VipService = Depends(get_vip_service),
) -> schemas.VipRead:
    return schemas.VipRead.model_validate(service.get_vip(vip_id))


@router.patch("/{vip_id}", response_model=schemas.VipRead)
def update_vip(
    vip_id: uuid.UUID,
    payload: schemas.VipUpdate,
    service: VipService = Depends(get_vip_service),
) -> schemas.VipRead:
    return schemas.VipRead.model_validate(service.update_vip(vip_id, payload))


@router.post(
    "/{vip_id}/aliases",
    response_model=schemas.AliasRead,
    status_code=status.HTTP_201_CREATED,
)
def add_alias(
    vip_id: uuid.UUID,
    payload: schemas.AliasCreate,
    service: VipService = Depends(get_vip_service),
) -> schemas.AliasRead:
    return schemas.AliasRead.model_validate(service.add_alias(vip_id, payload))


@router.get("/{vip_id}/aliases", response_model=list[schemas.AliasRead])
def list_aliases(
    vip_id: uuid.UUID,
    service: VipService = Depends(get_vip_service),
) -> list[schemas.AliasRead]:
    return [schemas.AliasRead.model_validate(row) for row in service.list_aliases(vip_id)]


@router.delete("/{vip_id}/aliases/{kind}/{alias}", status_code=status.HTTP_204_NO_CONTENT)
def remove_alias(
    vip_id: uuid.UUID,
    kind: AliasKind,
    alias: str,
    service: VipService = Depends(get_vip_service),
) -> None:
    service.remove_alias(vip_id, alias, kind)


@router.post(
    "/{vip_id}/context-keywords",
    response_model=schemas.ContextKeywordRead,
    status_code=status.HTTP_201_CREATED,
)
def add_context_keyword(
    vip_id: uuid.UUID,
    payload: schemas.ContextKeywordCreate,
    service: VipService = Depends(get_vip_service),
) -> schemas.ContextKeywordRead:
    return schemas.ContextKeywordRead.model_validate(service.add_context_keyword(vip_id, payload))


@router.get("/{vip_id}/context-keywords", response_model=list[schemas.ContextKeywordRead])
def list_context_keywords(
    vip_id: uuid.UUID,
    service: VipService = Depends(get_vip_service),
) -> list[schemas.ContextKeywordRead]:
    return [schemas.ContextKeywordRead.model_validate(row) for row in service.list_context_keywords(vip_id)]


@router.delete(
    "/{vip_id}/context-keywords/{keyword}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_context_keyword(
    vip_id: uuid.UUID,
    keyword: str,
    service: VipService = Depends(get_vip_service),
) -> None:
    service.remove_context_keyword(vip_id, keyword)


@router.post(
    "/{vip_id}/official-accounts",
    response_model=schemas.OfficialAccountRead,
    status_code=status.HTTP_201_CREATED,
)
def add_official_account(
    vip_id: uuid.UUID,
    payload: schemas.OfficialAccountCreate,
    service: VipService = Depends(get_vip_service),
) -> schemas.OfficialAccountRead:
    return schemas.OfficialAccountRead.model_validate(service.add_official_account(vip_id, payload))


@router.get("/{vip_id}/official-accounts", response_model=list[schemas.OfficialAccountRead])
def list_official_accounts(
    vip_id: uuid.UUID,
    service: VipService = Depends(get_vip_service),
) -> list[schemas.OfficialAccountRead]:
    return [schemas.OfficialAccountRead.model_validate(row) for row in service.list_official_accounts(vip_id)]


@router.delete(
    "/{vip_id}/official-accounts/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_official_account(
    vip_id: uuid.UUID,
    account_id: uuid.UUID,
    service: VipService = Depends(get_vip_service),
) -> None:
    service.remove_official_account(vip_id, account_id)
