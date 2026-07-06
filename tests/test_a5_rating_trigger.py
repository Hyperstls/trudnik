"""
A5: PostgreSQL trigger для атомарного пересчёта рейтинга

Тесты проверяют, что:
1. Миграция 101 существует и содержит триггер
2. Функция update_rating больше не выполняет read-modify-write
"""
import pytest
import os


class TestMigration101RatingTrigger:
    """Тесты для миграции с триггером пересчёта рейтинга."""

    def test_migration_file_exists(self):
        """A5: Миграция 101 должна существовать."""
        migration_path = 'migrations/101_recompute_profile_rating_trigger.sql'
        assert os.path.exists(migration_path), f"Миграция {migration_path} не найдена"

    def test_migration_contains_trigger(self):
        """A5: Миграция должна содержать триггер для таблицы ratings."""
        with open('migrations/101_recompute_profile_rating_trigger.sql', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Проверяем наличие ключевых элементов
        assert 'CREATE OR REPLACE FUNCTION recompute_profile_rating' in content
        assert 'CREATE TRIGGER' in content
        assert 'trg_recompute_rating' in content
        assert 'AFTER INSERT OR UPDATE OR DELETE ON public.ratings' in content
        assert 'SECURITY DEFINER' in content
        assert 'SET search_path' in content
        assert 'REVOKE EXECUTE' in content

    def test_migration_uses_avg_and_count(self):
        """A5: Триггер должен использовать AVG и COUNT для пересчёта."""
        with open('migrations/101_recompute_profile_rating_trigger.sql', 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert 'AVG(rating)' in content
        assert 'COUNT(*)' in content
        assert 'UPDATE public.profiles' in content


class TestUpdateRatingDeprecated:
    """Тесты для упрощённой функции update_rating."""

    def test_update_rating_does_not_modify_profile_directly(self):
        """A5: update_rating не должна напрямую обновлять profiles."""
        import inspect
        from app.services.ratings_service import update_rating
        
        source = inspect.getsource(update_rating)
        
        # Проверяем что функция не содержит PATCH запросов к profiles
        assert 'PATCH' not in source
        assert 'profiles?id=eq' not in source

    def test_update_rating_logs_call(self):
        """A5: update_rating должна логировать вызов."""
        from unittest.mock import patch, MagicMock
        from app.services.ratings_service import update_rating
        
        with patch('app.services.ratings_service.logger') as mock_logger:
            update_rating('test-user-id', 5.0)
            # Проверяем что logger был вызван
            assert mock_logger.debug.called or mock_logger.info.called
