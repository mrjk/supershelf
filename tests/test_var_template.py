"""Jinja var templates."""

from pathlib import Path

import pytest

from supershelf.errors import VarCandidateError, VarConfigError
from supershelf.var_commands import FileBinding
from supershelf.var_template import VarEnvironment


def _binding() -> FileBinding:
    return FileBinding(Path("a.txt"), "abc", "c", "m")


def test_literal_is_not_compiled() -> None:
    environment = VarEnvironment()
    assert environment.render("Bank2000", {}, _binding(), {}) == "Bank2000"
    assert environment._compiled == {}


def test_syntax_error_is_a_config_error() -> None:
    environment = VarEnvironment()
    with pytest.raises(VarConfigError, match="Invalid var template"):
        environment.compile_source("{{")


def test_unknown_name_fails_the_candidate() -> None:
    environment = VarEnvironment()
    with pytest.raises(VarCandidateError):
        environment.render("{{ missing }}", {}, _binding(), {})


def test_source_is_compiled_once() -> None:
    environment = VarEnvironment()
    binding = _binding()
    assert environment.render("{{ name }}", {"name": "a"}, binding, {}) == "a"
    assert environment.render("{{ name }}", {"name": "b"}, binding, {}) == "b"
    assert len(environment._compiled) == 1
