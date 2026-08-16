import rules_engine


def test_package_imports():
    assert rules_engine.__name__ == "rules_engine"
