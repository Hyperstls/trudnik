"""
F18: Проверка наличия семантических HTML5 тегов.

Требования:
- Все страницы должны иметь <header>, <main>, <footer>
- Карточки вакансий должны быть обёрнуты в <article>
"""
import os
import re
from pathlib import Path


def test_base_template_has_semantic_tags():
    """Проверяет, что base.html содержит header, main и footer."""
    base_path = Path(__file__).parent.parent / 'templates' / 'base.html'
    
    with open(base_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Проверяем наличие <header>
    assert '<header' in content, "base.html должен содержать тег <header>"
    
    # Проверяем наличие <main>
    assert '<main' in content, "base.html должен содержать тег <main>"
    
    # Проверяем наличие <footer>
    assert '<footer' in content, "base.html должен содержать тег <footer>"


def test_job_cards_use_article_tag():
    """Проверяет, что карточки вакансий используют <article> вместо <div>."""
    templates_dir = Path(__file__).parent.parent / 'templates'
    
    # Проверяем index.html (список вакансий)
    index_path = templates_dir / 'index.html'
    with open(index_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Ищем карточки вакансий (они имеют класс 'card' или 'job-card')
    # Проверяем, что они обёрнуты в <article>
    article_pattern = r'<article[^>]*class="[^"]*card[^"]*"'
    matches = re.findall(article_pattern, content)
    
    assert len(matches) > 0, "Карточки вакансий в index.html должны быть обёрнуты в <article>"


def test_all_templates_extend_base():
    """Проверяет, что все шаблоны наследуются от base.html."""
    templates_dir = Path(__file__).parent.parent / 'templates'
    
    # Список шаблонов, которые должны наследоваться от base.html
    required_templates = [
        'index.html',
        'login.html',
        'register.html',
        'profile.html',
        'job_detail.html',
        'my_jobs.html',
        'my_applications.html',
        'notifications.html',
    ]
    
    for template_name in required_templates:
        template_path = templates_dir / template_name
        if template_path.exists():
            with open(template_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Проверяем, что шаблон наследуется от base.html
            assert '{% extends "base.html" %}' in content or "{% extends 'base.html' %}" in content, \
                f"{template_name} должен наследоваться от base.html"
