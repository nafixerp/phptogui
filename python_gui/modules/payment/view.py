"""Payment voucher window (reuses the Receipt form layout; no discount line)."""

from __future__ import annotations

from ...core.posting import PostingEngine
from ..receipt.view import ReceiptView
from .service import PaymentService


class PaymentView(ReceiptView):
    TITLE = "Payment"
    _DISCOUNT = False

    def _make_service(self, database, session):
        return PaymentService(PostingEngine(database), session)
