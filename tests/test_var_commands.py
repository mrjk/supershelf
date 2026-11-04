"""Built-in var commands."""

import pytest

from supershelf.errors import VarCandidateError
from supershelf.template.environment import VarEnvironment


def test_parse_date_tries_formats_in_order() -> None:
    environment = VarEnvironment()
    rendered = environment.render(
        '{{ value | parse_date("%H:%M:%S", "%Y%m%d") }}',
        {"value": "20211231"},
    )
    assert rendered == "2021-12-31"


def test_parse_date_miss_fails_the_candidate() -> None:
    environment = VarEnvironment()
    with pytest.raises(VarCandidateError, match="No format matched"):
        environment.render(
            '{{ value | parse_date("%H:%M:%S") }}',
            {"value": "20211231"},
        )
    with pytest.raises(VarCandidateError, match="needs a string and a format"):
        environment.render("{{ value | parse_date }}", {"value": "20211231"})


def test_parse_date_output_overrides_the_profile_format() -> None:
    environment = VarEnvironment()
    rendered = environment.render(
        '{{ value | parse_date("%Y%m%d", output="%Y-%m") }}',
        {"value": "20211231", "__config__": {"date_format": "%d/%m/%Y"}},
    )
    assert rendered == "2021-12"


def test_parse_date_uses_the_profile_format() -> None:
    environment = VarEnvironment()
    rendered = environment.render(
        '{{ value | parse_date("%Y%m%d") }}',
        {"value": "20211231", "__config__": {"date_format": "%d/%m/%Y"}},
    )
    assert rendered == "31/12/2021"


def test_parse_date_falls_back_when_the_profile_format_is_missing() -> None:
    environment = VarEnvironment()
    rendered = environment.render(
        '{{ value | parse_date("%Y%m%d") }}',
        {"value": "20211231"},
    )
    blank = environment.render(
        '{{ value | parse_date("%Y%m%d") }}',
        {"value": "20211231", "__config__": {"date_format": "   "}},
    )
    assert rendered == "2021-12-31"
    assert blank == "2021-12-31"


def test_regex_replace_miss_fails_the_candidate() -> None:
    environment = VarEnvironment()
    with pytest.raises(VarCandidateError, match="did not match"):
        environment.render(
            '{{ regex_replace(value, "[0-9]", "x") }}',
            {"value": "ab"},
        )
