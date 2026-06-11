import importlib


def test_import_kaizen():
    mod = importlib.import_module("kaizen")
    assert hasattr(mod, "__version__")
