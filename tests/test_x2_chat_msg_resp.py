"""X2: chat.send_message must check msg_resp.ok before enqueue_notification."""
import inspect


def test_chat_send_message_checks_msg_resp_ok():
    """X2: send_message must check msg_resp.ok before enqueue_notification."""
    from app.blueprints import chat
    
    # Получить исходный код функции send_message
    source = inspect.getsource(chat.send_message)
    
    # Проверить, что есть проверка msg_resp.ok
    assert 'msg_resp.ok' in source, "send_message must check msg_resp.ok"
    
    # Проверить, что enqueue_notification вызывается ПОСЛЕ проверки
    lines = source.split('\n')
    msg_resp_check_line = None
    enqueue_line = None
    
    for i, line in enumerate(lines):
        if 'if not msg_resp.ok' in line:
            msg_resp_check_line = i
        if 'enqueue_notification' in line and msg_resp_check_line is not None:
            enqueue_line = i
            break
    
    assert msg_resp_check_line is not None, "msg_resp.ok check must exist"
    assert enqueue_line is not None, "enqueue_notification must be called after check"
    assert enqueue_line > msg_resp_check_line, "enqueue_notification must be after msg_resp.ok check"
