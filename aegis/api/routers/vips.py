"""VIP configuration endpoints (authenticated and VIP-scoped)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from aegis.api import schemas
from aegis.api.dependencies import (
    ensure_vip_access,
    get_current_user,
    require_role,
    scoped_vip_ids,
)
from aegis.api.services.fingerprints import FingerprintService
from aegis.api.services.vips import VipService
from aegis.common.db import get_session
from aegis.common.models.enums import AliasKind, ReferenceMediaKind, UserRole
from aegis.common.models.ops import User
from aegis.common.storage import ObjectStorage, get_object_storage

router = APIRouter(prefix="/vips", tags=["vips"])

MAX_REFERENCE_MEDIA_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}

AdminOrLead = Depends(require_role(UserRole.ADMIN, UserRole.LEAD))


def get_vip_service(session: Session = Depends(get_session)) -> VipService:
    return VipService(session)


def get_fingerprint_service(session: Session = Depends(get_session)) -> FingerprintService:
    return FingerprintService(session)


@router.post(
    "",
    response_model=schemas.VipRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[AdminOrLead],
)
def create_vip(
    payload: schemas.VipCreate,
    service: VipService = Depends(get_vip_service),
) -> schemas.VipRead:
    return schemas.VipRead.model_validate(service.create_vip(payload))


@router.get("", response_model=list[schemas.VipRead])
def list_vips(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    service: VipService = Depends(get_vip_service),
) -> list[schemas.VipRead]:
    vips = service.list_vips()
    scopes = scoped_vip_ids(session, user)
    if scopes is not None:
        vips = [vip for vip in vips if vip.id in scopes]
    return [schemas.VipRead.model_validate(vip) for vip in vips]


@router.get("/{vip_id}", response_model=schemas.VipRead)
def get_vip(
    vip_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    service: VipService = Depends(get_vip_service),
) -> schemas.VipRead:
    ensure_vip_access(session, user, vip_id)
    return schemas.VipRead.model_validate(service.get_vip(vip_id))


@router.patch(
    "/{vip_id}",
    response_model=schemas.VipRead,
    dependencies=[AdminOrLead],
)
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
    dependencies=[AdminOrLead],
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
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    service: VipService = Depends(get_vip_service),
) -> list[schemas.AliasRead]:
    ensure_vip_access(session, user, vip_id)
    return [schemas.AliasRead.model_validate(row) for row in service.list_aliases(vip_id)]


@router.delete(
    "/{vip_id}/aliases/{kind}/{alias}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[AdminOrLead],
)
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
    dependencies=[AdminOrLead],
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
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    service: VipService = Depends(get_vip_service),
) -> list[schemas.ContextKeywordRead]:
    ensure_vip_access(session, user, vip_id)
    return [schemas.ContextKeywordRead.model_validate(row) for row in service.list_context_keywords(vip_id)]


@router.delete(
    "/{vip_id}/context-keywords/{keyword}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[AdminOrLead],
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
    dependencies=[AdminOrLead],
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
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    service: VipService = Depends(get_vip_service),
) -> list[schemas.OfficialAccountRead]:
    ensure_vip_access(session, user, vip_id)
    return [schemas.OfficialAccountRead.model_validate(row) for row in service.list_official_accounts(vip_id)]


@router.delete(
    "/{vip_id}/official-accounts/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[AdminOrLead],
)
def remove_official_account(
    vip_id: uuid.UUID,
    account_id: uuid.UUID,
    service: VipService = Depends(get_vip_service),
) -> None:
    service.remove_official_account(vip_id, account_id)


@router.post(
    "/{vip_id}/reference-media",
    response_model=schemas.ReferenceMediaRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[AdminOrLead],
)
async def upload_reference_media(
    vip_id: uuid.UUID,
    file: UploadFile = File(...),
    kind: ReferenceMediaKind = Form(ReferenceMediaKind.PORTRAIT),
    service: VipService = Depends(get_vip_service),
    storage: ObjectStorage = Depends(get_object_storage),
) -> schemas.ReferenceMediaRead:
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=415, detail="unsupported image type")
    data = await file.read(MAX_REFERENCE_MEDIA_BYTES + 1)
    if len(data) > MAX_REFERENCE_MEDIA_BYTES:
        raise HTTPException(status_code=413, detail="image too large")
    media = service.add_reference_media(
        vip_id,
        data=data,
        kind=kind,
        content_type=file.content_type,
        storage=storage,
    )
    return schemas.ReferenceMediaRead.model_validate(media)


@router.get("/{vip_id}/reference-media", response_model=list[schemas.ReferenceMediaRead])
def list_reference_media(
    vip_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    service: VipService = Depends(get_vip_service),
) -> list[schemas.ReferenceMediaRead]:
    ensure_vip_access(session, user, vip_id)
    return [schemas.ReferenceMediaRead.model_validate(row) for row in service.list_reference_media(vip_id)]


@router.delete(
    "/{vip_id}/reference-media/{media_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[AdminOrLead],
)
def remove_reference_media(
    vip_id: uuid.UUID,
    media_id: uuid.UUID,
    service: VipService = Depends(get_vip_service),
) -> None:
    service.remove_reference_media(vip_id, media_id)


@router.post(
    "/{vip_id}/sensitive-fingerprints",
    response_model=schemas.FingerprintRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[AdminOrLead],
)
def register_fingerprint(
    vip_id: uuid.UUID,
    payload: schemas.FingerprintCreate,
    service: FingerprintService = Depends(get_fingerprint_service),
) -> schemas.FingerprintRead:
    return schemas.FingerprintRead.model_validate(service.register(vip_id, payload))


@router.get(
    "/{vip_id}/sensitive-fingerprints",
    response_model=list[schemas.FingerprintRead],
)
def list_fingerprints(
    vip_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    service: FingerprintService = Depends(get_fingerprint_service),
) -> list[schemas.FingerprintRead]:
    ensure_vip_access(session, user, vip_id)
    return [schemas.FingerprintRead.model_validate(row) for row in service.list(vip_id)]


@router.delete(
    "/{vip_id}/sensitive-fingerprints/{fingerprint_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[AdminOrLead],
)
def remove_fingerprint(
    vip_id: uuid.UUID,
    fingerprint_id: uuid.UUID,
    service: FingerprintService = Depends(get_fingerprint_service),
) -> None:
    service.remove(vip_id, fingerprint_id)
