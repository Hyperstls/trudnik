"""X3: mutation routes must be POST only."""
import inspect


def test_apply_job_post_only():
    """X3: apply_job must be POST only."""
    from app.blueprints import applications
    
    # Получить исходный код маршрута
    source = inspect.getsource(applications.apply_job)
    
    # Проверить, что маршрут использует только POST
    assert "methods=['POST']" in source or 'methods=["POST"]' in source, \
        "apply_job must use methods=['POST'] only"


def test_cancel_job_post_only():
    """X3: cancel_job must be POST only."""
    from app.blueprints import jobs
    
    source = inspect.getsource(jobs.cancel_job)
    assert "methods=['POST']" in source or 'methods=["POST"]' in source, \
        "cancel_job must use methods=['POST'] only"


def test_restore_job_post_only():
    """X3: restore_job must be POST only."""
    from app.blueprints import jobs
    
    source = inspect.getsource(jobs.restore_job)
    assert "methods=['POST']" in source or 'methods=["POST"]' in source, \
        "restore_job must use methods=['POST'] only"


def test_delete_job_post_only():
    """X3: delete_job must be POST only."""
    from app.blueprints import jobs
    
    source = inspect.getsource(jobs.delete_job)
    assert "methods=['POST']" in source or 'methods=["POST"]' in source, \
        "delete_job must use methods=['POST'] only"
