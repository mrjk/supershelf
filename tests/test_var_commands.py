"""Built-in var commands."""

import pytest

from supershelf.errors import VarCandidateError
from supershelf.template.environment import VarEnvironment


def test_regex_time_var_tries_formats_in_order() -> None:
    environment = VarEnvironment()
    rendered = environment.render(
        '{{ regex_time_var(value, "%H:%M:%S", "%Y%m%d") }}',
        {"value": "20211231"},
    )
    assert rendered == "2021-12-31"


def test_regex_replace_miss_fails_the_candidate() -> None:
    environment = VarEnvironment()
    with pytest.raises(VarCandidateError, match="did not match"):
        environment.render(
            '{{ regex_replace(value, "[0-9]", "x") }}',
            {"value": "ab"},
        )
