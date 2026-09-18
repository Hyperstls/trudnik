"""Тесты фильтра навыков на странице /my-applications.

tab=received — фильтр по навыкам ОТКЛИКНУВШЕГОСЯ (user_skills → worker_id IN ...).
tab=sent — фильтр по навыкам ЗАДАНИЯ (job_skills → job_id IN ...).

Раньше фильтр был пустышкой: при выбранных навыках грузились все заявки
(limit=500) и отдавались без фильтрации (TODO в applications.py).

В pytest-окружении in-memory mock PostgREST не активен (см. app/utils/__init__.py:
гейт _allow_mock_import), поэтому postgrest_request патчится в неймспейсе
блюпринта мини-реализацией, выполняющей eq/in-фильтры из query string.
"""
import pytest

EMPLOYER_ID = '00000000-0000-0000-0000-000000000002'
WORKER_ID = '00000000-0000-0000-0000-000000000003'
WORKER2_ID = '00000000-0000-0000-0000-0000000000a2'
JOB1_ID = '00000000-0000-0000-0000-000000000010'
JOB2_ID = '00000000-0000-0000-0000-000000000011'
APP1_ID = '00000000-0000-0000-0000-0000000000a1'
APP2_ID = '00000000-0000-0000-0000-0000000000b1'

SKILLS = [
    {'id': 'skill-1', 'name': 'Уборка'},
    {'id': 'skill-2', 'name': 'Курьер'},
]


class _FakeResponse:
    def __init__(self, data):
        self.ok = True
        self.status_code = 200
        self._data = data
        self.headers = {}
        self.text = ''

    def json(self):
        return self._data


def _make_fake_postgrest(tables):
    """Мини-PostgREST: выполняет eq./in.() фильтры query string по таблицам."""
    def _fake(method, url, **kwargs):
        table, _, qs = url.partition('?')
        rows = list(tables.get(table, []))
        for part in qs.split('&'):
            if '=' not in part:
                continue
            k, v = part.split('=', 1)
            if v.startswith('eq.'):
                rows = [r for r in rows if str(r.get(k, '')) == v[3:]]
            elif v.startswith('in.('):
                vals = [x.strip() for x in v[3:].strip('()').split(',') if x.strip()]
                rows = [r for r in rows if str(r.get(k, '')) in vals]
        return _FakeResponse(rows)
    return _fake


def _patch_postgrest(mocker, tables):
    mocker.patch('app.blueprints.applications.postgrest_request',
                 new=_make_fake_postgrest(tables))


def _login(client, user_id, role):
    """Авторизовать сессию валидным JWT (как в test_b5)."""
    from app.utils.auth import generate_jwt
    token = generate_jwt(user_id, role)
    with client.session_transaction() as sess:
        sess['user_id'] = user_id
        sess['role'] = role
        sess['access_token'] = token


def _received_apps():
    """Два отклика разных трудников на задание работодателя.

    Ключ 'job.employer_id' — эмуляция PostgREST-фильтра по вложенному ресурсу.
    worker/job — как embedded-ресурсы реального PostgREST (шаблон их требует).
    """
    job = {'id': JOB1_ID, 'organization_name': 'ООО Тест', 'date_time': '2026-07-01T09:00:00',
           'payment_amount': 1500, 'status': 'open', 'current_workers': 0, 'max_workers': 2}
    return [
        {'id': APP1_ID, 'job_id': JOB1_ID, 'worker_id': WORKER_ID,
         'status': 'pending', 'created_at': '2025-06-02T10:00:00+00:00',
         'job.employer_id': EMPLOYER_ID,
         'worker': {'id': WORKER_ID, 'full_name': 'Трудник Один', 'photo_url': '',
                    'rating': 4.8, 'desired_payment': 1000, 'email_public': 'w1@test.ru'},
         'job': dict(job)},
        {'id': APP2_ID, 'job_id': JOB1_ID, 'worker_id': WORKER2_ID,
         'status': 'pending', 'created_at': '2025-06-03T10:00:00+00:00',
         'job.employer_id': EMPLOYER_ID,
         'worker': {'id': WORKER2_ID, 'full_name': 'Трудник Два', 'photo_url': '',
                    'rating': 4.2, 'desired_payment': 900, 'email_public': 'w2@test.ru'},
         'job': dict(job)},
    ]


def test_received_filter_by_worker_skills(app_client, mocker):
    """received + ?skills=Уборка: остаётся только отклик трудника с этим навыком."""
    _patch_postgrest(mocker, {
        'skills': SKILLS,
        'user_skills': [{'user_id': WORKER_ID, 'skill_id': 'skill-1'}],  # Уборка
        'applications': _received_apps(),
    })
    _login(app_client, EMPLOYER_ID, 'employer')

    resp = app_client.get('/my-applications',
                          query_string={'tab': 'received', 'skills': 'Уборка'})

    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert f'data-app-id="{APP1_ID}"' in html
    assert f'data-app-id="{APP2_ID}"' not in html


def test_received_without_filter_returns_all(app_client, mocker):
    """received без навыков: оба отклика видны (регрессия на пустой фильтр)."""
    _patch_postgrest(mocker, {
        'skills': SKILLS,
        'user_skills': [],
        'applications': _received_apps(),
    })
    _login(app_client, EMPLOYER_ID, 'employer')

    resp = app_client.get('/my-applications', query_string={'tab': 'received'})

    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert f'data-app-id="{APP1_ID}"' in html
    assert f'data-app-id="{APP2_ID}"' in html


def test_received_filter_no_matching_workers(app_client, mocker):
    """received: навыку не соответствует ни один трудник → честный пустой список."""
    _patch_postgrest(mocker, {
        'skills': SKILLS,
        'user_skills': [],
        'applications': _received_apps(),
    })
    _login(app_client, EMPLOYER_ID, 'employer')

    resp = app_client.get('/my-applications',
                          query_string={'tab': 'received', 'skills': 'Уборка'})

    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert f'data-app-id="{APP1_ID}"' not in html
    assert f'data-app-id="{APP2_ID}"' not in html


def test_sent_filter_by_job_skills(app_client, mocker):
    """sent + ?skills=Курьер: остаётся только отклик на задание с этим навыком."""
    _patch_postgrest(mocker, {
        'skills': SKILLS,
        'job_skills': [{'job_id': JOB1_ID, 'skill_id': 'skill-2'}],  # Курьер
        'applications': [
            {'id': APP1_ID, 'job_id': JOB1_ID, 'worker_id': WORKER_ID,
             'status': 'pending', 'created_at': '2025-06-02T10:00:00+00:00'},
            {'id': APP2_ID, 'job_id': JOB2_ID, 'worker_id': WORKER_ID,
             'status': 'accepted', 'created_at': '2025-07-02T10:00:00+00:00'},
        ],
    })
    _login(app_client, WORKER_ID, 'worker')

    resp = app_client.get('/my-applications',
                          query_string={'tab': 'sent', 'skills': 'Курьер'})

    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert f'/jobs/{JOB1_ID}' in html
    assert f'/jobs/{JOB2_ID}' not in html


def test_sent_filter_no_matching_jobs(app_client, mocker):
    """sent: ни одно задание не имеет навыка → пустой список, а не все отклики."""
    _patch_postgrest(mocker, {
        'skills': SKILLS,
        'job_skills': [],
        'applications': [
            {'id': APP1_ID, 'job_id': JOB1_ID, 'worker_id': WORKER_ID,
             'status': 'pending', 'created_at': '2025-06-02T10:00:00+00:00'},
        ],
    })
    _login(app_client, WORKER_ID, 'worker')

    resp = app_client.get('/my-applications',
                          query_string={'tab': 'sent', 'skills': 'Курьер'})

    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert f'/jobs/{JOB1_ID}' not in html
    assert f'/jobs/{JOB2_ID}' not in html
