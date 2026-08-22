"""Юнит-тесты check_stop_words (app/blueprints/jobs.py).

Стоп-слова ТК РФ ст.15 — блокировка переквалификации в трудовые отношения:
    ставка, зарплата, штат, трудовая, график, постоянная работа, вахта

⚠️ ДОКУМЕНТИРУЕТ ГРАНИЦУ РЕАЛИЗАЦИИ: подстрочный match через lower(), БЕЗ
лемматизации. Следовательно: «зарплата» ловится, «зарплату» — НЕТ;
«ЗАРПЛАТА» ловится (lower), «з а р п л а т а» — НЕТ. Эти кейсы фиксируют
фактическое поведение; усиление проверки — отдельная задача (см.
docs/QA_TEST_CASES.md, категория «сильные границы»).
"""

import pytest

from app.blueprints.jobs import STOP_WORDS, check_stop_words


class TestStopWordsPositive:
    @pytest.mark.parametrize('word', STOP_WORDS)
    def test_each_stop_word_detected(self, word):
        """Каждое слово из списка — в title → найдено."""
        assert word in check_stop_words(f'Требуется сотрудник, {word} высокая')

    def test_uppercase_detected(self):
        """Регистр не спасает: lower() перед сравнением."""
        assert 'зарплата' in check_stop_words('ЗАРПЛАТА ДВОЙНАЯ')

    def test_mixed_case_detected(self):
        assert 'график' in check_stop_words('ГраФик 2/2')

    def test_word_with_punctuation(self):
        """«ставка!» — подстрока внутри текста → найдено."""
        assert 'ставка' in check_stop_words('Часовая ставка!')

    def test_phrase_detected(self):
        assert 'постоянная работа' in check_stop_words('Ищем постоянная работа в офис')


class TestStopWordsNegative:
    def test_clean_text(self):
        assert check_stop_words('Разовый демонтаж конструкций, оплата за смену') == []

    def test_inflected_form_not_detected(self):
        """ГРАНИЦА: «зарплату» (вин. падеж) НЕ ловится — лемматизации нет."""
        assert check_stop_words('Выдаём зарплату ежедневно') == []

    def test_spaced_out_letters_not_detected(self):
        """ГРАНИЦА: «з а р п л а т а» — обход разделителями."""
        assert check_stop_words('з а р п л а т а деньгами') == []

    def test_word_boundary_false_positive(self):
        """«подставка» содержит «ставка» как подстроку → ЛОВИТСЯ (false positive).
        Документированное поведение подстрочного поиска."""
        assert 'ставка' in check_stop_words('Нужна подставка для цветов')


class TestStopWordsReturnShape:
    def test_returns_list_of_found(self):
        found = check_stop_words('ставка и график работы')
        assert sorted(found) == ['график', 'ставка']

    def test_empty_string(self):
        assert check_stop_words('') == []

    def test_word_list_content(self):
        """Контракт: ровно 7 стоп-слов, включая составное."""
        assert len(STOP_WORDS) == 7
        assert 'постоянная работа' in STOP_WORDS
