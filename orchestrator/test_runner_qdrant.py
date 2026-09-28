from orchestrator import runner


def test_healthcheck():
    state = {"topic":"t","domain":"d"}
    res = runner.ROUTER.get("qdrant-healthcheck")(state)
    assert isinstance(res, dict)
    print("healthcheck returned state type OK")


if __name__ == "__main__":
    test_healthcheck()
