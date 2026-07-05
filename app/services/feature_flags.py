"""Abstract interface for feature flags (Фаза 5 — Task 5.3).

All billing-related flags are False by default.
"""

from abc import ABC, abstractmethod


class FeatureFlags(ABC):
    """Abstract interface for feature flags.

    Implementations:
    - RedisFeatureFlags (production, with admin UI to toggle) — future
    - EnvFeatureFlags (per-deployment) — future
    - StaticFeatureFlags (hardcoded — current sprint)
    """

    @abstractmethod
    def is_enabled(self, flag_name: str, user_id: str = None) -> bool:
        raise NotImplementedError

    @abstractmethod
    def enable(self, flag_name: str, user_id: str = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def disable(self, flag_name: str, user_id: str = None) -> None:
        raise NotImplementedError


class StaticFeatureFlags(FeatureFlags):
    """Static flags from env/config. Used in current sprint.

    All billing-related flags are False by default.
    """

    DEFAULT_FLAGS = {
        'free_tier_active': True,   # приложение работает в бесплатном режиме
        'billing_enabled': False,   # монетизация выключена
        'kkt_enabled': False,       # 54-ФЗ выключен
        'paid_search_boost': False,
        'promoted_jobs': False,
    }

    def __init__(self, overrides: dict = None):
        self._flags = {**self.DEFAULT_FLAGS, **(overrides or {})}

    def is_enabled(self, flag_name: str, user_id: str = None) -> bool:
        return self._flags.get(flag_name, False)

    def enable(self, flag_name: str, user_id: str = None) -> None:
        raise NotImplementedError('StaticFeatureFlags is read-only')

    def disable(self, flag_name: str, user_id: str = None) -> None:
        raise NotImplementedError('StaticFeatureFlags is read-only')
