"""Abstract interface for subscription/quota management (Фаза 5 — Task 5.2).

No-op implementation. All users are on free tier with unlimited quota.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class Subscription:
    user_id: str
    plan: str  # 'free', 'basic', 'pro', 'business' (future)
    jobs_remaining: int  # -1 = unlimited
    expires_at: Optional[datetime]
    features: dict


class SubscriptionService(ABC):
    """Abstract interface for subscription/quota management.

    Implementations (future, NOT in this sprint):
    - DbSubscriptionService (queries employer_subscriptions table)
    - MockSubscriptionService (for tests)

    The DI container injects FreeTierSubscriptionService which always
    returns unlimited quota — preserving current behavior.
    """

    @abstractmethod
    def get_subscription(self, user_id: str) -> Subscription:
        raise NotImplementedError

    @abstractmethod
    def check_quota(self, user_id: str, action: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def consume_quota(self, user_id: str, action: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def upgrade(self, user_id: str, plan: str, payment_id: str) -> Subscription:
        raise NotImplementedError


class FreeTierSubscriptionService(SubscriptionService):
    """No-op implementation. All users are on free tier.

    Returns unlimited quota for all actions to preserve existing behavior.
    """

    def get_subscription(self, user_id: str) -> Subscription:
        return Subscription(
            user_id=user_id,
            plan='free',
            jobs_remaining=-1,  # unlimited
            expires_at=None,
            features={'all': True},
        )

    def check_quota(self, user_id: str, action: str) -> bool:
        return True  # always allowed

    def consume_quota(self, user_id: str, action: str) -> None:
        pass  # no-op

    def upgrade(self, user_id: str, plan: str, payment_id: str) -> Subscription:
        raise NotImplementedError('Monetization is disabled')
