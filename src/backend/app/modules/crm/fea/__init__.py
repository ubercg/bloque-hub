"""FEA (Firma Electrónica Avanzada) integration: provider interface and mock."""

from app.modules.crm.fea.adapter import FEAProviderMock, IFEAProvider, SendForSignatureResult

__all__ = ["IFEAProvider", "FEAProviderMock", "SendForSignatureResult"]
