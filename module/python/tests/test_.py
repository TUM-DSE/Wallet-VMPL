import wallet as w


def test_ext():
    assert w._w.__version__ == "0.0.1"
