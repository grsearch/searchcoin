from app.cluster import normalize_server_role, role_enabled


def test_normalize_server_role():
    assert normalize_server_role("scanner") == "scanner"
    assert normalize_server_role("bad") == "all"


def test_role_enabled():
    assert role_enabled("all", "scanner")
    assert role_enabled("strategy", "strategy")
    assert not role_enabled("trader", "scanner")
