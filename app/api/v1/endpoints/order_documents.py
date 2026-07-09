from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session, joinedload

from app.core.permissions import ORDERS_READ, ORDERS_WRITE
from app.db.models.pdf_document import PDFDocument
from app.db.models.service_order import ServiceOrder
from app.db.models.user import User
from app.db.session import get_db
from app.dependencies import RequirePermission, ensure_not_viewer_for_mutation
from app.schemas.order_document import OrderDocumentGenerate, OrderDocumentResponse
from app.services.order_document_registry import (
    create_order_document,
    load_order_for_documents,
    read_document_bytes,
)

router = APIRouter(prefix="/orders", tags=["order-documents"])


def _doc_response(doc: PDFDocument) -> OrderDocumentResponse:
    name = doc.generated_by.full_name if doc.generated_by else None
    return OrderDocumentResponse(
        id=doc.id,
        company_id=doc.company_id,
        service_order_id=doc.service_order_id,
        document_type=doc.document_type,
        document_format=doc.document_format,
        file_url=doc.file_url,
        generated_at=doc.generated_at,
        generated_by_id=doc.generated_by_id,
        generated_by_name=name,
    )


@router.get("/by-tracking/{tracking_code}", response_model=dict)
def get_order_by_tracking(
    tracking_code: str,
    current_user: User = Depends(RequirePermission(ORDERS_READ)),
    db: Session = Depends(get_db),
) -> dict:
    order = (
        db.query(ServiceOrder)
        .filter(
            ServiceOrder.company_id == current_user.company_id,
            ServiceOrder.tracking_code == tracking_code.strip().upper(),
        )
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    return {"id": str(order.id), "order_number": order.order_number, "tracking_code": order.tracking_code}


@router.get("/{order_id}/documents", response_model=list[OrderDocumentResponse])
def list_documents(
    order_id: UUID,
    current_user: User = Depends(RequirePermission(ORDERS_READ)),
    db: Session = Depends(get_db),
) -> list[OrderDocumentResponse]:
    order = load_order_for_documents(db, company_id=current_user.company_id, order_id=order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    docs = (
        db.query(PDFDocument)
        .options(joinedload(PDFDocument.generated_by))
        .filter(PDFDocument.service_order_id == order_id)
        .order_by(PDFDocument.generated_at.desc())
        .all()
    )
    return [_doc_response(d) for d in docs]


@router.post(
    "/{order_id}/documents",
    response_model=OrderDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_document(
    order_id: UUID,
    payload: OrderDocumentGenerate,
    current_user: User = Depends(RequirePermission(ORDERS_WRITE)),
    db: Session = Depends(get_db),
) -> OrderDocumentResponse:
    ensure_not_viewer_for_mutation(current_user)
    order = load_order_for_documents(db, company_id=current_user.company_id, order_id=order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    try:
        doc = create_order_document(
            db,
            order=order,
            document_type=payload.document_type,
            document_format=payload.format,
            generated_by=current_user,
        )
        db.commit()
        db.refresh(doc)
        db.refresh(doc, attribute_names=["generated_by"])
        return _doc_response(doc)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _get_doc(
    db: Session, *, company_id: UUID, order_id: UUID, doc_id: UUID
) -> PDFDocument | None:
    return (
        db.query(PDFDocument)
        .filter(
            PDFDocument.id == doc_id,
            PDFDocument.service_order_id == order_id,
            PDFDocument.company_id == company_id,
        )
        .first()
    )


@router.get("/{order_id}/documents/{doc_id}")
def download_document(
    order_id: UUID,
    doc_id: UUID,
    current_user: User = Depends(RequirePermission(ORDERS_READ)),
    db: Session = Depends(get_db),
) -> Response:
    doc = _get_doc(db, company_id=current_user.company_id, order_id=order_id, doc_id=doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    try:
        pdf_bytes = read_document_bytes(doc)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail="Archivo PDF no encontrado") from e
    filename = f"{doc.document_type}-{doc.document_format}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{order_id}/documents/{doc_id}/preview")
def preview_document(
    order_id: UUID,
    doc_id: UUID,
    current_user: User = Depends(RequirePermission(ORDERS_READ)),
    db: Session = Depends(get_db),
) -> Response:
    doc = _get_doc(db, company_id=current_user.company_id, order_id=order_id, doc_id=doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    try:
        pdf_bytes = read_document_bytes(doc)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail="Archivo PDF no encontrado") from e
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline"},
    )
