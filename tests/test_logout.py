"""T19 — logout реализован POST-формой (раньше был GET-ссылкой на POST-only маршрут -> 405).

В режиме TESTING CSRF отключён (middleware.csrf_check), поэтому проверяем
метод+поведение, а не отказ по CSRF.
"""


def test_logout_get_method_not_allowed(app_client):
    """GET /logout -> 405 (маршрут принимает только POST)."""
    resp = app_client.get('/logout')
    assert resp.status_code == 405


def test_logout_post_redirects_and_clears(app_client):
    """POST /logout без @login_required -> 302 + сессия очищена."""
    with app_client.session_transaction() as sess:
        sess['user_id'] = 'someone'
        sess['access_token'] = 'x'
    resp = app_client.post('/logout')
    assert resp.status_code == 302
    with app_client.session_transaction() as sess:
        assert not sess.get('user_id'), 'сессия должна быть очищена после logout'
