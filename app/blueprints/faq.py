"""FAQ blueprint: статическая страница «Вопросы и ответы».

Доступна всем (включая гостей). Контент — статичный HTML-аккордеон
(details/summary, без JS — соответствует CSP strict-dynamic).
"""

from flask import Blueprint, render_template

faq_bp = Blueprint('faq', __name__)


@faq_bp.route('/faq')
def faq():
    """Страница «Вопросы и ответы»."""
    return render_template('faq.html', title='Вопросы и ответы')
