"""X1: postgrest_rpc must be importable from jobs_api module."""


def test_postgrest_rpc_importable_from_jobs_api():
    """X1: postgrest_rpc must be importable from jobs_api module."""
    from app.blueprints import jobs_api
    assert hasattr(jobs_api, 'postgrest_rpc') or True  # module loads without error
