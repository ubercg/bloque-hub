"""Adapter para proveedor PAC (CFDI 4.0). Mock para desarrollo."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass
class CfdiTimbradoResult:
    uuid: uuid.UUID
    xml_url: str
    pdf_url: str


class ICfdiProvider(Protocol):
    def timbrar(
        self,
        *,
        emisor_rfc: str,
        emisor_nombre: str,
        emisor_regimen: str,
        receptor_rfc: str,
        receptor_nombre: str,
        receptor_regimen: str,
        receptor_uso_cfdi: str,
        forma_pago: str,
        monto: float,
        iva_monto: float,
        lugar_expedicion: str,
        descripcion: str,
    ) -> CfdiTimbradoResult:
        ...


class CfdiProviderMock:
    """Mock: devuelve UUID y URLs falsas sin llamar al SAT."""

    def timbrar(
        self,
        *,
        emisor_rfc: str,
        emisor_nombre: str,
        emisor_regimen: str,
        receptor_rfc: str,
        receptor_nombre: str,
        receptor_regimen: str,
        receptor_uso_cfdi: str,
        forma_pago: str,
        monto: float,
        iva_monto: float,
        lugar_expedicion: str,
        descripcion: str,
    ) -> CfdiTimbradoResult:
        u = uuid.uuid4()
        return CfdiTimbradoResult(
            uuid=u,
            xml_url=f"https://mock-pac.example/cfdi/{u}.xml",
            pdf_url=f"https://mock-pac.example/cfdi/{u}.pdf",
        )
