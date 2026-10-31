"""Тесты для demo/calc.py: положительные, отрицательные, ноль."""

from calc import add


def test_add_positive():
    assert add(2, 3) == 5


def test_add_negative():
    assert add(-2, -3) == -5


def test_add_zero():
    assert add(0, 0) == 0


def test_add_floats():
    assert add(0.5, 0.25) == 0.75


def test_add_mixed_sign():
    assert add(-0.5, 1) == 0.5
