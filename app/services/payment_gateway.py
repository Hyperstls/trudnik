"""Abstract interface for payment providers (Фаза 5 — Task 5.1).

No-op implementation. Used while monetization is disabled.
Do NOT delete app/services/payment_service.py (dead code; tests depend on it).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PaymentRequest:
    amount: float
    currency: str = 'RUB'
    description: str = ''
    return_url: str = ''
    metadata: dict = field(default_factory=dict)


@dataclass
class PaymentResult:
    payment_id: str
    confirmation_url: str
    status: str
    provider: str


@dataclass
class WebhookPayload:
    payment_id: str
    status: str
    raw_data: bytes
    signature: str


class PaymentGateway(ABC):
    """Abstract interface for payment providers.

    Implementations (future, NOT in this sprint):
    - YooKassaPaymentGateway
    - CloudPaymentsPaymentGateway
    - MockPaymentGateway (for tests)
    """

    @abstractmethod
    def create_payment(self, request: PaymentRequest) -> PaymentResult:
        raise NotImplementedError

    @abstractmethod
    def verify_webhook(self, payload: WebhookPayload) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_payment_status(self, payment_id: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def refund(self, payment_id: str, amount: Optional[float] = None) -> bool:
        raise NotImplementedError


class NullPaymentGateway(PaymentGateway):
    """No-op implementation. Used while monetization is disabled.

    All methods either return mock values or raise NotImplementedError.
    This is the default gateway injected by the DI container.
    """

    def create_payment(self, request: PaymentRequest) -> PaymentResult:
        raise NotImplementedError(
            'Monetization is disabled; payment gateway not configured')

    def verify_webhook(self, payload: WebhookPayload) -> bool:
        return False  # always reject — no webhooks expected

    def get_payment_status(self, payment_id: str) -> str:
        return 'disabled'

    def refund(self, payment_id: str, amount: Optional[float] = None) -> bool:
        raise NotImplementedError('Monetization is disabled')
