"""Регрессия: работодатель может оценить нескольких исполнителей одного задания.

Баг: UPSERT в POST /api/ratings искал существующую оценку по паре
(rater_user_id, job_id) — вторая оценка другому исполнителю того же
задания перезаписывала первую. Правильный ключ уникальности:
(rater_user_id, job_id, rated_user_id) — см. миграцию 145.

Тесты эмулируют PostgREST-хранилище, фильтрующее по eq-параметрам из URL,
поэтому на старом коде (lookup без rated_user_id) падают: вторая оценка
«находила» бы чужую запись и уходила в PATCH вместо INSERT.
"""
import re
from unittest.mock import patch, MagicMock

import pytest

EMPLOYER_ID = '11111111-1111-1111-1111-111111111111'
WORKER_A_ID = '22222222-2222-2222-2222-222222222222'
WORKER_B_ID = '33333333-3333-3333-3333-333333333333'
JOB_ID = '44444444-4444-4444-4444-444444444444'


@pytest.fixture
def client(app_client):
    """Flask test client с сессией работодателя — владельца задания."""
    with app_client.session_transaction() as sess:
        sess['user_id'] = EMPLOYER_ID
        sess['role'] = 'employer'
        from app.utils.auth import generate_jwt
        sess['access_token'] = generate_jwt(EMPLOYER_ID, 'employer')
    return app_client


def _resp(payload, ok=True):
    m = MagicMock()
    m.ok = ok
    m.json = lambda: payload
    m.status_code = 200 if ok else 400
    m.text = '' if ok else 'error'
    return m


class _FakeRatingsDb:
    """In-memory эмуляция PostgREST для сценариев POST /api/ratings.

    Фильтрует ratings по eq-параметрам, реально присутствующим в URL, —
    именно это ловит регрессию lookup'а по неполному ключу.
    """

    def __init__(self):
        self.ratings = []
        self.posts = []
        self.patches = []
        self._seq = 0

    @staticmethod
    def _filters(endpoint):
        return dict(re.findall(r'([a-z_]+)=eq\.([^&]+)', endpoint))

    def __call__(self, method, endpoint, **kwargs):
        if endpoint.startswith('jobs?'):
            return _resp([{'id': JOB_ID, 'status': 'completed', 'employer_id': EMPLOYER_ID}])
        if endpoint.startswith('applications?'):
            # accepted-отклик оцениваемого работника на задание
            return _resp([{'id': 'app-1'}])
        if method == 'GET' and endpoint.startswith('ratings?'):
            flt = self._filters(endpoint)
            found = [
                {'id': r['id']} for r in self.ratings
                if all(r.get(k) == v for k, v in flt.items())
            ]
            return _resp(found)
        if method == 'POST' and endpoint == 'ratings':
            self._seq += 1
            row = dict(kwargs['json'])
            row['id'] = f'rating-{self._seq}'
            self.ratings.append(row)
            self.posts.append(row)
            return _resp([row])
        if method == 'PATCH' and endpoint.startswith('ratings?id=eq.'):
            rating_id = endpoint.split('ratings?id=eq.', 1)[1].split('&', 1)[0]
            for r in self.ratings:
                if r['id'] == rating_id:
                    r.update(kwargs['json'])
            self.patches.append((rating_id, kwargs['json']))
            return _resp([{}])
        raise AssertionError(f'unexpected call: {method} {endpoint}')


def _post_rating(client, rated_user_id, rating):
    return client.post('/api/ratings', json={
        'job_id': JOB_ID,
        'rated_user_id': rated_user_id,
        'rating': rating,
        'comment': '',
        'target_type': 'worker',
    })


class TestEmployerRatesMultipleWorkers:
    """Один работодатель — несколько исполнителей одного задания."""

    def test_two_workers_get_two_separate_ratings(self, client):
        """Оценки двум разным исполнителям одного задания — обе сохраняются (2 INSERT)."""
        db = _FakeRatingsDb()
        with patch('app.blueprints.ratings.postgrest_admin_request', side_effect=db):
            resp_a = _post_rating(client, WORKER_A_ID, 5)
            resp_b = _post_rating(client, WORKER_B_ID, 4)

        assert resp_a.status_code == 200 and resp_a.get_json()['success'] is True
        assert resp_b.status_code == 200 and resp_b.get_json()['success'] is True
        assert resp_a.get_json()['is_new'] is True
        assert resp_b.get_json()['is_new'] is True

        # Обе оценки вставлены как новые строки, ни одного UPDATE
        assert len(db.posts) == 2
        assert db.patches == []
        saved = {(r['rater_user_id'], r['job_id'], r['rated_user_id']) for r in db.ratings}
        assert saved == {
            (EMPLOYER_ID, JOB_ID, WORKER_A_ID),
            (EMPLOYER_ID, JOB_ID, WORKER_B_ID),
        }

    def test_repeat_rating_same_worker_updates(self, client):
        """Повторная оценка тому же исполнителю — UPDATE существующей записи."""
        db = _FakeRatingsDb()
        with patch('app.blueprints.ratings.postgrest_admin_request', side_effect=db):
            _post_rating(client, WORKER_A_ID, 5)
            resp_repeat = _post_rating(client, WORKER_A_ID, 3)

        assert resp_repeat.status_code == 200
        assert resp_repeat.get_json()['success'] is True
        assert resp_repeat.get_json()['is_new'] is False

        # Одна запись в «БД»: первая вставлена, вторая обновила её же
        assert len(db.posts) == 1
        assert len(db.patches) == 1
        assert len(db.ratings) == 1
        assert db.ratings[0]['rating'] == 3
        assert db.ratings[0]['rated_user_id'] == WORKER_A_ID
