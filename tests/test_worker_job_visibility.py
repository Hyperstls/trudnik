"""Логика отображения заданий для трудника: проверка opt-in гео-поиска.

Требования:
- по умолчанию нет автоматической фильтрации по расстоянию (гео — opt-in);
- радиус-поиск присутствует и без верхнего предела («Любое расстояние»);
- радиус-путь не крашит и не бланкует страницу.

(Видимость конкретных заданий проверяется на проде; мок здесь покрывает лишь
корректность маршрута и наличие UI.)
"""
WORKER_ID = '00000000-0000-0000-0000-000000000003'


def _login_worker(client):
    with client.session_transaction() as sess:
        sess['user_id'] = WORKER_ID
        sess['role'] = 'worker'


def test_index_has_optin_geo_search(app_client):
    """На главной есть опциональный гео-поиск с радиусом без верхнего предела."""
    _login_worker(app_client)
    r = app_client.get('/')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'geo-nearby-btn' in body           # кнопка «Рядом со мной»
    assert 'Рядом со мной' in body
    assert 'Любое расстояние' in body         # радиус без ограничения


def test_index_radius_path_ok(app_client):
    """Явный радиус + локация не крашат маршрут (200, не 500)."""
    _login_worker(app_client)
    r = app_client.get('/?lat=55.75&lng=37.61&radius=0.001&sort=distance')
    assert r.status_code == 200


def test_index_location_without_radius_ok(app_client):
    """Локация без радиуса — только сортировка по расстоянию, без фильтрации (200)."""
    _login_worker(app_client)
    r = app_client.get('/?lat=55.75&lng=37.61&sort=distance')
    assert r.status_code == 200


def test_index_default_has_no_radius_in_query(app_client):
    """По умолчанию radius не задаётся (нет авто-ограничения) — рендер 200."""
    r = app_client.get('/')
    assert r.status_code == 200
