"""Jinja var templates."""

import pytest

from supershelf.errors import VarCandidateError, VarConfigError
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


def test_a_namespace_without_a_field_fails_the_candidate() -> None:
    environment = VarEnvironment()
    with pytest.raises(VarCandidateError, match="namespace needs a field"):
        environment.render("{{ __file__ }}", {"__file__": {"name": "a.txt"}})


def test_date_fields_follow_the_stored_format() -> None:
    environment = VarEnvironment()
    scope = {"__date__": DateScope("2026-04-25")}
    assert environment.render("{{ __date__ }}", scope) == "2026-04-25"
    assert environment.render("{{ __date__.Y }}-{{ __date__.m }}/{{ __date__.d }}", scope) == (
        "2026-04/25"
    )


def test_source_is_compiled_once() -> None:
    environment = VarEnvironment()
    assert environment.render("{{ name }}", {"name": "a"}) == "a"
    assert environment.render("{{ name }}", {"name": "b"}) == "b"
    assert len(environment._compiled) == 1
