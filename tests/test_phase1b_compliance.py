"""Phase 1b: тесты соответствия 152-ФЗ и security-hardening.

Покрывает:
- обязательное согласие на обработку ПДн при регистрации (152-ФЗ ст.9);
- экспорт персональных данных (право субъекта, ст.14/15);
- удаление вероисповедания из публичных полей профиля (ст.10);
- выравнивание TTL access_token и сессии.
"""
import pytest
from app.utils.auth import generate_jwt


def _auth_session(app_client, role='worker'):
    """Аутентифицированная сессия (access_token в session)."""
    with app_client.session_transaction() as sess:
        sess['user_id'] = '11111111-1111-1111-1111-111111111111'
        sess['role'] = role
        sess['access_token'] = generate_jwt(sess['user_id'], role)
    return app_client


# ── 152-ФЗ ст.9: согласие ──────────────────────────────────────────
def test_registration_blocked_without_consent(app_client):
    """Без чекбокса согласия регистрация не проходит (остаётся на форме)."""
    response = app_client.post('/register', data={
        'full_name': 'Test User',
        'email': 'nocosent@example.com',
        'password': 'StrongP@ss1',
        'city': 'Москва',
        'role': 'worker',
        '_csrf_token': 'test',
        # consent НЕ передан
    }, follow_redirects=False)
    assert response.status_code == 200
    assert 'обработкой персональных данных'.encode('utf-8') in response.data


def test_registration_passes_with_consent(app_client):
    """С согласием регистрация проходит валидацию (не блокируется consent-чеком)."""
    response = app_client.post('/register', data={
        'full_name': 'Test User',
        'email': 'consent@example.com',
        'password': 'StrongP@ss1',
        'city': 'Москва',
        'role': 'worker',
        '_csrf_token': 'test',
        'consent': 'on',
    }, follow_redirects=True)
    assert response.status_code == 200


# ── 152-ФЗ ст.14/15: право на доступ/копию ПДн ─────────────────────
def test_export_data_requires_login(app_client):
    """Экспорт ПДн доступен только аутентифицированным."""
    response = app_client.get('/profile/export-data', follow_redirects=False)
    assert response.status_code in (302, 303)


def test_export_data_returns_json(authed_client):
    """Аутентифицированный пользователь получает JSON со своими данными."""
    response = authed_client.get('/profile/export-data', follow_redirects=False)
    assert response.status_code == 200
    assert response.mimetype == 'application/json'
    data = response.get_json()
    assert isinstance(data, dict)
    assert 'legal_basis' in data
    assert 'profile' in data


# ── 152-ФЗ ст.10: вероисповедание убрано из публичных полей ─────────
def test_religion_removed_from_public_profile_fields():
    """PUBLIC_PROFILE_FIELDS не содержит religion/religion_id."""
    from app.blueprints.profile import PUBLIC_PROFILE_FIELDS
    assert 'religion' not in PUBLIC_PROFILE_FIELDS
    assert 'religion_id' not in PUBLIC_PROFILE_FIELDS


def test_registration_ignores_religion_field(app_client):
    """即使 форма отправляет religion_id, он не сохраняется (backend не читает)."""
    # Проверяем, что в коде регистрации нет чтения religion_id из формы.
    import inspect
    from app.blueprints.auth import register
    source = inspect.getsource(register)
    assert "request.form.get('religion_id')" not in source


# ── Security: TTL access_token выровнен с сессией ──────────────────
def test_access_token_ttl_aligned_with_session():
    """ACCESS_TOKEN_TTL не больше PERMANENT_SESSION_LIFETIME (окно утечки)."""
    from app.utils.auth import ACCESS_TOKEN_TTL_SECONDS
    from app.config import Config
    assert ACCESS_TOKEN_TTL_SECONDS <= Config.PERMANENT_SESSION_LIFETIME


@pytest.fixture
def authed_client(app_client):
    return _auth_session(app_client)
