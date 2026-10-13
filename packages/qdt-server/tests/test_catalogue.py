"""Every curated method's spec matches its function: same keyword parameters, same defaults."""

import inspect

import pytest

from qdt_server.catalogue import METHODS, run_method, specs


@pytest.mark.parametrize("name", sorted(METHODS))
def test_spec_matches_the_function_signature(name):
    spec, method = METHODS[name]
    params = {
        p.name: p.default
        for p in inspect.signature(method).parameters.values()
        if p.kind is inspect.Parameter.KEYWORD_ONLY
    }
    assert {p.name for p in spec.parameters} == set(params)
    for p in spec.parameters:
        assert p.default == params[p.name], p.name
    assert spec.resolve({}) == params
    assert spec.name == name


def test_specs_are_the_catalogue():
    assert [s.name for s in specs()] == list(METHODS)


def test_unknown_method_is_a_key_error():
    with pytest.raises(KeyError, match="no method"):
        run_method("nope", None, None, {})
