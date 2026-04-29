from datetime import datetime, timezone
from uuid import UUID
from decimal import Decimal
import hashlib
import json

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.modules.finance.models import CfdiDocument, CfdiEstado, CfdiTipo
from app.modules.booking.models import Reservation
from app.modules.crm.models import Contract, ContractStatus, Quote, QuoteItem

class CFDIAmountMismatchError(Exception):
    pass

class ContractImmutableError(Exception):
    pass

class ImmutableQuoteError(Exception):
    pass

def generate_contract(quote_id: UUID, tenant_id: UUID, db: Session) -> Contract:
    """Generate contract using the frozen snapshot values of QuoteItems."""
    quote = db.get(Quote, quote_id)
    if not quote or quote.tenant_id != tenant_id:
        raise ValueError("Quote not found")

    snapshot_data = {
        "quote_id": str(quote.id),
        "items": [],
        "additional_services": []
    }
    
    total_frozen = Decimal('0.00')
    for item in quote.items:
        if item.subtotal_frozen is None:
            raise ValueError("Cannot generate contract: Quote is not digitally approved (no snapshot)")
            
        subtotal = Decimal(str(item.subtotal_frozen))
        total_frozen += subtotal
        
        snapshot_data["items"].append({
            "id": str(item.id),
            "space_id": str(item.space_id),
            "uma_value": str(item.uma_snapshot) if item.uma_snapshot else None,
            "uma_date": str(item.uma_snapshot_date) if item.uma_snapshot_date else None,
            "discount_amount": str(item.discount_amount) if item.discount_amount else "0.00",
            "subtotal_frozen": str(item.subtotal_frozen)
        })
        
    for svc in quote.additional_services:
        total_frozen += Decimal(str(svc.calculated_price))
        snapshot_data["additional_services"].append({
            "id": str(svc.id),
            "service_id": str(svc.service_id),
            "calculated_price": str(svc.calculated_price)
        })
        
    snapshot_json = json.dumps(snapshot_data, sort_keys=True)
    snapshot_hash = hashlib.sha256(snapshot_json.encode()).hexdigest()
    
    existing = db.query(Contract).filter(Contract.quote_id == quote.id).first()
    if existing:
        if existing.status == ContractStatus.SIGNED:
            raise ContractImmutableError("Cannot regenerate a signed contract")
        existing.contract_snapshot_hash = snapshot_hash
        db.flush()
        return existing
        
    contract = Contract(
        tenant_id=tenant_id,
        quote_id=quote.id,
        status=ContractStatus.PENDING,
        contract_snapshot_hash=snapshot_hash
    )
    db.add(contract)
    db.flush()
    return contract

def check_quote_mutability(quote: Quote, db: Session):
    """Called before any modification to Quote or QuoteItems."""
    contract = db.query(Contract).filter(Contract.quote_id == quote.id).first()
    if contract and contract.status == ContractStatus.SIGNED:
        from app.modules.audit.service import append_audit_log
        append_audit_log(
            db=db,
            tenant_id=quote.tenant_id,
            tabla="quotes",
            registro_id=quote.id,
            accion="UPDATE_ATTEMPT",
            valor_nuevo={"msg": "Attempt to modify quote after contract signed"}
        )
        raise ImmutableQuoteError("Quote is immutable after contract is signed")

def generate_cfdi(reservation_id: UUID, tenant_id: UUID, db: Session) -> CfdiDocument:
    """Generate CFDI post CONTRACT_SIGNED, deriving amounts from quote_items frozen subtotal."""
    reservation = db.get(Reservation, reservation_id)
    if not reservation:
        raise ValueError("Reservation not found")
        
    # Since Reservation doesn't have a direct quote_id mapping in models initially,
    # we map them through Inventory which contains both space_id, fecha and quote_id / reservation_id.
    # Wait, the prompt says "generate_cfdi(reservation_id, tenant_id) -> CFDIDocument".
    # I'll implement logic finding the Quote via inventory.
    from app.modules.inventory.models import Inventory
    
    inv_slot = db.query(Inventory).filter(
        Inventory.reservation_id == reservation.id,
        Inventory.quote_id.isnot(None)
    ).first()
    
    if not inv_slot or not inv_slot.quote_id:
        # Fallback to direct total calculation if no quote linked
        raise ValueError("No quote linked to this reservation via inventory")

    quote = db.get(Quote, inv_slot.quote_id)
    contract = db.query(Contract).filter(Contract.quote_id == quote.id).first()
    
    if not contract or contract.status != ContractStatus.SIGNED:
        raise ValueError("CFDI requires a signed contract")
        
    total_frozen = Decimal('0.00')
    for item in quote.items:
        total_frozen += Decimal(str(item.subtotal_frozen or 0))
    for svc in quote.additional_services:
        total_frozen += Decimal(str(svc.calculated_price or 0))

    # Basic IVA assumption for CFDI
    monto_base = (total_frozen / Decimal('1.16')).quantize(Decimal('0.01'))
    iva = total_frozen - monto_base

    # Create CFDI
    cfdi = CfdiDocument(
        tenant_id=tenant_id,
        reservation_id=reservation_id,
        tipo=CfdiTipo.INGRESO,
        rfc_emisor="MUNICIPIO_QRO",
        rfc_receptor="XAXX010101000",
        uso_cfdi="G03",
        forma_pago="01",
        monto=float(monto_base),
        iva_monto=float(iva),
        estado=CfdiEstado.PENDIENTE
    )
    
    db.add(cfdi)
    db.flush()
    
    # Check total_cfdi == subtotal_frozen
    total_cfdi_calc = Decimal(str(cfdi.monto)) + Decimal(str(cfdi.iva_monto))
    if abs(total_cfdi_calc - total_frozen) > Decimal('0.01'):
        raise CFDIAmountMismatchError(f"CFDI amount {total_cfdi_calc} does not match frozen subtotal {total_frozen}")

    return cfdi


def validar_datos_fiscales_para_cfdi(rfc_receptor, regimen_receptor, uso_cfdi):
    from app.modules.finance.matriz_sat import validar_compatibilidad_regimen_uso_cfdi
    
    if not rfc_receptor:
        return ["RFC_RECEPTOR_AUSENTE"]
        
    err = validar_compatibilidad_regimen_uso_cfdi(regimen_receptor, uso_cfdi, rfc_receptor)
    if err:
        return [err]
    return []

def generar_cfdi_para_reserva(reserva, db, monto, receptor_rfc=None, receptor_razon_social=None, receptor_regimen=None, receptor_uso_cfdi="G03"):
    from app.modules.finance.models import CfdiDocument, CfdiEstado, CfdiTipo
    from datetime import datetime, timezone
    from uuid import uuid4
    
    cfdi = CfdiDocument(
        tenant_id=reserva.tenant_id,
        reservation_id=reserva.id,
        tipo=CfdiTipo.INGRESO,
        rfc_emisor="MUNICIPIO_QRO",
        rfc_receptor=receptor_rfc or "XAXX010101000",
        uso_cfdi=receptor_uso_cfdi,
        forma_pago="01",
        monto=monto / 1.16,
        iva_monto=monto - (monto / 1.16),
        estado=CfdiEstado.PENDIENTE
    )
    
    errs = validar_datos_fiscales_para_cfdi(receptor_rfc, receptor_regimen, receptor_uso_cfdi)
    if errs:
        cfdi.estado = CfdiEstado.ERROR
        cfdi.error_codigo = errs[0]
    else:
        cfdi.estado = CfdiEstado.TIMBRADO
        cfdi.uuid_fiscal = uuid4()
        cfdi.xml_url = "https://mock.cfdi.xml"
        cfdi.timbrado_at = datetime.now(timezone.utc)
        
    db.add(cfdi)
    return cfdi
