"""X4: delete_job must use delete_job_cascade RPC instead of manual cascade."""
import inspect


def test_delete_job_uses_rpc_cascade():
    """X4: delete_job must use postgrest_rpc('delete_job_cascade', ...)."""
    from app.blueprints import jobs
    
    source = inspect.getsource(jobs.delete_job)
    
    # Проверить, что используется RPC
    assert "postgrest_rpc('delete_job_cascade'" in source or 'postgrest_rpc("delete_job_cascade"' in source, \
        "delete_job must use postgrest_rpc('delete_job_cascade', ...)"
    
    # Проверить, что manual cascade удалён
    assert 'cascade_tables' not in source, \
        "delete_job must not use manual cascade_tables loop"
    
    # Проверить, что есть проверка resp.ok
    assert 'resp.ok' in source or 'rpc_result.ok' in source, \
        "delete_job must check RPC response ok status"
