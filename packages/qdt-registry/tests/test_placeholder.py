import importlib
import pathlib


def test_package_imports():
    name = pathlib.Path(__file__).resolve().parents[1].name.replace("-", "_")
    assert importlib.import_module(name).__version__
