"""Jinja var templates."""

import pytest

from supershelf.errors import VarCandidateError, VarConfigError
from supershelf.template import ScopeObject
from supershelf.var_template import VarEnvironment
from supershelf.vars import DateScope


def test_literal_is_not_compiled() -> None:
    environment = VarEnvironment()
    assert environment.render("Bank2000", {}) == "Bank2000"
    assert environment._compiled == {}


def test_syntax_error_is_a_config_error() -> None:
    environment = VarEnvironment()
    with pytest.raises(VarConfigError, match="Invalid var template"):
        environment.compile_source("{{")


def test_unknown_name_fails_the_candidate() -> None:
    environment = VarEnvironment()
    with pytest.raises(VarCandidateError):
        environment.render("{{ missing }}", {})
    with pytest.raises(VarCandidateError):
        environment.render("{{ __file_name__ }}", {})


def test_a_namespace_prints_its_text() -> None:
    environment = VarEnvironment()
    rendered = environment.render(
        "{{ __file__ }}",
        {"__file__": ScopeObject({"name": "acme.pdf", "path": "bills/acme.pdf"}, "name")},
    )
    assert rendered == "acme.pdf"
    with pytest.raises(VarCandidateError, match="namespace needs a field"):
        environment.render("{{ __profile__.document }}", {"__profile__": {"document": {}}})


def test_date_fields_follow_the_stored_format() -> None:
    environment = VarEnvironment()
    scope = {"__date__": DateScope("2026-04-25")}
    assert environment.render("{{ __date__ }}", scope) == "2026-04-25"
    assert environment.render("{{ __date__.Y }}-{{ __date__.m }}/{{ __date__.d }}", scope) == (
        "2026-04/25"
    )
    shown = {"__date__": DateScope("2026-04-25", "%d/%m/%Y")}
    assert environment.render("{{ __date__ }}", shown) == "25/04/2026"
    assert environment.render("{{ __date__.strftime('%Y-%m') }}", shown) == "2026-04"
    with pytest.raises(VarCandidateError, match="non-empty"):
        environment.render("{{ __date__.strftime('') }}", shown)


def test_source_is_compiled_once() -> None:
    environment = VarEnvironment()
    assert environment.render("{{ name }}", {"name": "a"}) == "a"
    assert environment.render("{{ name }}", {"name": "b"}) == "b"
    assert len(environment._compiled) == 1
