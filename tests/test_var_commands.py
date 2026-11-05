"""Built-in var commands."""

import pytest

from supershelf.errors import VarCandidateError
from supershelf.template.environment import VarEnvironment
from supershelf.template.filters.parse_boolean import parse_boolean
from supershelf.template.filters.parse_float import parse_float
from supershelf.template.filters.parse_int import parse_int


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


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("39,45", "39.45"),
        ("12.50", "12.50"),
        ("1.234,56", "1234.56"),
        ("1,234.56", "1234.56"),
        ("1 234,56", "1234.56"),
        ("CAD 39,45", "39.45"),
        ("EUR12.50", "12.50"),
        ("1,234", "1.234"),
        ("$39.45", "39.45"),
        ("1'234,56", "1234.56"),
    ],
)
def test_parse_float_spellings(value: str, expected: str) -> None:
    environment = VarEnvironment()
    rendered = environment.render("{{ value | parse_float }}", {"value": value})
    assert rendered == expected


def test_parse_float_rejects_a_broken_group() -> None:
    environment = VarEnvironment()
    with pytest.raises(VarCandidateError, match="not a float"):
        environment.render("{{ value | parse_float }}", {"value": "1,2,34"})


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("12,0", "12"),
        ("12.0", "12"),
        ("1,234.00", "1234"),
        ("1,234", "1234"),
        ("1.234", "1234"),
        ("+007", "7"),
    ],
)
def test_parse_int_spellings(value: str, expected: str) -> None:
    environment = VarEnvironment()
    rendered = environment.render("{{ value | parse_int }}", {"value": value})
    assert rendered == expected


def test_parse_int_rejects_a_nonzero_fraction() -> None:
    environment = VarEnvironment()
    with pytest.raises(VarCandidateError, match="not an int"):
        environment.render("{{ value | parse_int }}", {"value": "12,5"})


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("YES", "true"),
        ("on", "true"),
        ("OFF", "false"),
        ("no", "false"),
    ],
)
def test_parse_boolean_spellings(value: str, expected: str) -> None:
    environment = VarEnvironment()
    rendered = environment.render("{{ value | parse_boolean }}", {"value": value})
    assert rendered == expected


def test_parse_boolean_rejects_an_unknown_word() -> None:
    environment = VarEnvironment()
    with pytest.raises(VarCandidateError, match="not a bool"):
        environment.render("{{ value | parse_boolean }}", {"value": "maybe"})


def test_parse_filters_need_a_string() -> None:
    with pytest.raises(VarCandidateError, match="parse_float needs a string"):
        parse_float(12)
    with pytest.raises(VarCandidateError, match="parse_int needs a string"):
        parse_int(12)
    with pytest.raises(VarCandidateError, match="parse_boolean needs a string"):
        parse_boolean(True)


def test_regex_replace_miss_fails_the_candidate() -> None:
    environment = VarEnvironment()
    with pytest.raises(VarCandidateError, match="did not match"):
        environment.render(
            '{{ regex_replace(value, "[0-9]", "x") }}',
            {"value": "ab"},
        )
