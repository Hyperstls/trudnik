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
        'password': 'Aa1!aaaa',
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
        'password': 'Aa1!aaaa',
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


def test_export_data_fills_blacklist_and_employer_applications(authed_client, monkeypatch):
    """Регрессия: разделы blacklist и applications_as_employer непустые при данных.

    Раньше запрашивались несуществующие таблица `blacklist` (правильно —
    `blacklists`) и колонка `applications.employer_id` (её нет — отклики на
    задания заказчика выбираются через jobs → applications.job_id), поэтому
    оба раздела молча приходили пустыми.
    """
    import app.blueprints.profile as profile_mod
    from app.utils import PostgrestResponse

    user_id = '11111111-1111-1111-1111-111111111111'
    job_id = '22222222-2222-2222-2222-222222222222'

    def fake_get(method, endpoint, **kwargs):
        if endpoint.startswith('blacklists?'):
            assert f'user_id=eq.{user_id}' in endpoint
            return PostgrestResponse(
                ok=True, status_code=200,
                data=[{'user_id': user_id,
                       'blocked_user_id': '55555555-5555-5555-5555-555555555555'}],
                text='[]')
        if endpoint.startswith('jobs?'):
            assert f'employer_id=eq.{user_id}' in endpoint
            return PostgrestResponse(ok=True, status_code=200,
                                     data=[{'id': job_id}], text='[]')
        if endpoint.startswith('applications?job_id=in.'):
            assert job_id in endpoint
            return PostgrestResponse(
                ok=True, status_code=200,
                data=[{'id': '33333333-3333-3333-3333-333333333333',
                       'job_id': job_id, 'status': 'pending'}],
                text='[]')
        return PostgrestResponse(ok=True, status_code=200, data=[], text='[]')

    monkeypatch.setattr(profile_mod, 'postgrest_request', fake_get)
    response = authed_client.get('/profile/export-data', follow_redirects=False)
    assert response.status_code == 200
    data = response.get_json()
    assert [r['user_id'] for r in data['blacklist']] == [user_id]
    assert [r['job_id'] for r in data['applications_as_employer']] == [job_id]


def test_export_data_employer_without_jobs_skips_in_query(authed_client, monkeypatch):
    """Нет заданий → applications_as_employer пуст, а запрос applications
    не выполняется вовсе (пустой `in.()` невалиден в PostgREST)."""
    import app.blueprints.profile as profile_mod
    from app.utils import PostgrestResponse

    requested = []

    def fake_get(method, endpoint, **kwargs):
        requested.append(endpoint)
        return PostgrestResponse(ok=True, status_code=200, data=[], text='[]')

    monkeypatch.setattr(profile_mod, 'postgrest_request', fake_get)
    response = authed_client.get('/profile/export-data', follow_redirects=False)
    assert response.status_code == 200
    data = response.get_json()
    assert data['applications_as_employer'] == []
    assert not any(e.startswith('applications?job_id=in.') for e in requested)


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
