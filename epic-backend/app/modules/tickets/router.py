from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from ...core.rate_limit import limiter

from . import service
from .schemas import (
    TicketCreateIn, TicketAssignIn, StatusChangeIn, PriorityChangeIn, TicketTypeChangeIn,
    CommentCreateIn, TicketOut, TicketDetailOut, TicketCommentOut, TicketAttachmentOut,
)
from .state_machine import allowed_target_states_for
from ...database import get_db
from ...dependencies import get_current_user
from ...config import get_settings

router = APIRouter()


def _to_detail(t):
    out = TicketDetailOut.model_validate(t).model_dump()
    out["allowed_target_states"] = allowed_target_states_for(t.status)
    return out


@router.post("", response_model=TicketOut, status_code=201)
@limiter.limit("30/minute")
def create_ticket(request: Request, payload: TicketCreateIn, db: Session = Depends(get_db),
                  me=Depends(get_current_user)):
    try:
        payload = payload.normalized()
    except ValueError as e:
        raise HTTPException(400, str(e))
    t = service.create_ticket(db, creator=me, title=payload.title, description=payload.description,
                              ticket_type=payload.ticket_type, category=payload.category, priority=payload.priority,
                              requestor_id=payload.requestor_id, location_id=payload.location_id,
                              channel=payload.channel or "SELF_SERVICE",
                              device_name=payload.device_name, device_ip_address=payload.device_ip_address,
                              device_site_name=payload.device_site_name)
    return t


@router.get("", response_model=list[TicketOut])
def list_tickets(db: Session = Depends(get_db), me=Depends(get_current_user)):
    return service.list_for_user(db, me)


@router.get("/{ticket_id}", response_model=TicketDetailOut)
def get_ticket(ticket_id: str, db: Session = Depends(get_db), me=Depends(get_current_user)):
    t = service.fetch_detail(db, ticket_id, me)
    return _to_detail(t)


@router.post("/{ticket_id}/assign", response_model=TicketOut)
@limiter.limit("30/minute")
def assign(request: Request, ticket_id: str, payload: TicketAssignIn, db: Session = Depends(get_db),
           me=Depends(get_current_user)):
    return service.assign_ticket(db, ticket_id=ticket_id, assignee_id=payload.assignee_id, actor=me)


@router.post("/{ticket_id}/status", response_model=TicketOut)
@limiter.limit("30/minute")
def change_status(request: Request, ticket_id: str, payload: StatusChangeIn, db: Session = Depends(get_db),
                  me=Depends(get_current_user)):
    return service.change_status(db, ticket_id=ticket_id, target_status=payload.target_status.upper(), actor=me)


@router.post("/{ticket_id}/priority", response_model=TicketOut)
@limiter.limit("30/minute")
def change_priority(request: Request, ticket_id: str, payload: PriorityChangeIn, db: Session = Depends(get_db),
                    me=Depends(get_current_user)):
    return service.change_priority(db, ticket_id=ticket_id, priority=payload.priority.upper(), actor=me)


@router.post("/{ticket_id}/reclassify", response_model=TicketOut)
@limiter.limit("30/minute")
def reclassify(request: Request, ticket_id: str, payload: TicketTypeChangeIn, db: Session = Depends(get_db),
               me=Depends(get_current_user)):
    return service.reclassify_ticket(db, ticket_id=ticket_id, ticket_type=payload.ticket_type.upper(), actor=me)


@router.post("/{ticket_id}/cancel", response_model=TicketOut)
@limiter.limit("30/minute")
def cancel(request: Request, ticket_id: str, db: Session = Depends(get_db), me=Depends(get_current_user)):
    return service.cancel_ticket(db, ticket_id=ticket_id, actor=me)


@router.post("/{ticket_id}/comments", response_model=TicketCommentOut, status_code=201)
@limiter.limit("30/minute")
def add_comment(request: Request, ticket_id: str, payload: CommentCreateIn, db: Session = Depends(get_db),
                me=Depends(get_current_user)):
    c = service.add_comment(db, ticket_id=ticket_id, text=payload.text, actor=me)
    # Eagerly attach author for response shape.
    c.author = me
    return c


@router.post("/{ticket_id}/attachments", response_model=TicketAttachmentOut, status_code=201)
@limiter.limit("10/minute")
async def upload_attachment(request: Request, ticket_id: str, file: UploadFile = File(...),
                            db: Session = Depends(get_db), me=Depends(get_current_user)):
    max_bytes = get_settings().ATTACHMENT_MAX_BYTES
    chunks = []
    total = 0
    CHUNK = 1024 * 1024  # 1 MB
    while True:
        chunk = await file.read(CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            # Stop reading immediately — never buffer more than max_bytes + one chunk.
            raise HTTPException(413, f"Attachment exceeds {max_bytes} bytes")
        chunks.append(chunk)
    data = b"".join(chunks)

    att = service.add_attachment(db, ticket_id=ticket_id, file_name=file.filename,
                                 content_type=file.content_type, data=data, actor=me)
    return att


@router.get("/{ticket_id}/attachments/{att_id}/download")
def download_attachment(ticket_id: str, att_id: str, db: Session = Depends(get_db),
                        me=Depends(get_current_user)):
    from .models import TicketAttachment
    t = service.fetch_detail(db, ticket_id, me)  # also enforces visibility
    att = next((a for a in t.attachments if a.id == att_id), None)
    if not att:
        raise HTTPException(404, "Attachment not found")
    from .storage import get_storage
    from .attachment_validation import safe_download_filename
    fh = get_storage().open(att.storage_uri)
    safe_name = safe_download_filename(att.file_name)
    # Always force a download rather than trusting the stored content_type for inline rendering —
    # this avoids a stored attachment being served in a way the browser tries to execute/render.
    return StreamingResponse(fh, media_type="application/octet-stream",
                             headers={"Content-Disposition": f'attachment; filename="{safe_name}"',
                                      "X-Content-Type-Options": "nosniff"})