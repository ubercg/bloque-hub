"""FEA provider interface and mock implementation."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class SignerInfo:
    """Firmante para el proceso de firma."""

    email: str
    name: str


@dataclass
class SendForSignatureResult:
    """Resultado de enviar documento a firma."""

    provider_document_id: str
    status: str  # e.g. "sent"


class IFEAProvider(ABC):
    """Interfaz para proveedor FEA (mock o real)."""

    @abstractmethod
    def send_for_signature(
        self,
        pdf_bytes: bytes,
        signers: list[SignerInfo],
        title: str,
        callback_url: str,
        **kwargs: Any,
    ) -> SendForSignatureResult:
        """Sube el PDF y crea el proceso de firma. Retorna provider_document_id y estado."""
        ...


class FEAProviderMock(IFEAProvider):
    """
    Mock que simula respuestas de la API FEA.
    Devuelve un provider_document_id ficticio (UUID).
    Opcionalmente puede invocar callback_url con payload simulado para probar el webhook.
    """

    def send_for_signature(
        self,
        pdf_bytes: bytes,
        signers: list[SignerInfo],
        title: str,
        callback_url: str,
        **kwargs: Any,
    ) -> SendForSignatureResult:
        doc_id = str(uuid.uuid4())
        return SendForSignatureResult(
            provider_document_id=doc_id,
            status="sent",
        )
