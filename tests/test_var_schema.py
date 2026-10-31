"""Catalog load and cast rules for variable types."""

import pytest

from supershelf.errors import VarConfigError
from supershelf.var_schema import (
    CastMiss,
    VarCatalog,
    VarSpec,
    VarState,
    cast_value,
)
from supershelf.var_template import VarEnvironment


def _catalog(document: dict[str, object] | None = None, **kwargs: object) -> VarCatalog:
    return VarCatalog.load({} if document is None else document, **kwargs)  # type: ignore[arg-type]


def _spec(body: dict[str, object], name: str = "amount") -> VarSpec:
    return _catalog({"vars_schema": {name: body}}).spec(name)


def test_implicit_text_stores_the_rendered_string() -> None:
    catalog = _catalog({}, names=["vendor"])
    spec = catalog.spec("vendor")

    assert spec.type == "text"
    assert spec.mandatory is False
    assert spec.internal is False
    cast = cast_value(spec, "Bank2000")

    assert cast.value == "Bank2000"
    assert cast.display == "Bank2000"


def test_builtin_text_is_locked_and_date_can_take_a_default() -> None:
    catalog = _catalog(
        {
            "vars_schema": {
                "__kind__": {"desc": "Matched kind", "unit": "label"},
                "__date__": {
                    "desc": "Document date",
                    "mandatory": True,
                    "default": "2026-04-25",
                    "validation": {"ge": "2020-01-01"},
                },
            }
        }
    )
    kind = catalog.spec("__kind__")
    dated = catalog.spec("__date__")

    assert kind.desc == "Matched kind"
    assert kind.unit == "label"
    assert kind.type == "text"
    assert kind.internal is True
    assert kind.mandatory is True
    assert dated.type == "date"
    assert dated.internal is False
    assert dated.mandatory is True
    assert dated.candidates == ("2026-04-25",)
    assert catalog.spec("file_ctime").internal is True


@pytest.mark.parametrize(
    ("document", "match"),
    [
        ({"vars_schema": {"__kind__": {"type": "text"}}}, "cannot set type"),
        ({"vars_schema": {"__kind__": {"internal": False}}}, "cannot set internal"),
        ({"vars_schema": {"__date__": {"type": "date"}}}, "cannot set type"),
        ({"vars_schema": {"__date__": {"internal": False}}}, "cannot set internal"),
        ({"vars_schema": {"__custom__": {"type": "text"}}}, "not a supershelf variable"),
        ({"vars_schema": {"amount": {"type": "list"}}}, "type list"),
        ({"vars_schema": {"amount": {"type": "INT"}}}, "unknown"),
        ({"vars_schema": {"amount": {"type": "timedate"}}}, "unknown"),
        ({"vars_schema": {"amount": {"mendatory": True}}}, "unknown"),
        ({"vars_schema": {"vendor": {"internal": True}}}, "cannot be internal"),
        ({"vars_schema": {"amount": {"type": "int", "default": None}}}, "null"),
        ({"vars_schema": {"amount": {"type": "int", "default": []}}}, "empty list"),
        ({"vars_schema": {"amount": {"type": "int", "default": [[1]]}}}, "nested list"),
        ({"vars_schema": {"1bad": {"type": "text"}}}, "not a variable name"),
        (
            {
                "vars_schema": {"vendor": {"default": "Bank2000"}},
                "default_vars": {"vendor": "UNKNOWN"},
            },
            "vars_schema.default and default_vars",
        ),
        ({"default_vars": {"__custom__": "x"}}, "not a supershelf variable"),
        ({"default_vars": {"amount": 12}}, "string or a list of strings"),
        ({"vars_schema": {"opens": {"type": "time", "default": "15:4"}}}, "cannot be cast"),
        (
            {"vars_schema": {"issued": {"type": "datetime", "validation": {"ge": "2026-04-25"}}}},
            "not a datetime",
        ),
        (
            {"vars_schema": {"amount": {"type": "int", "validation": {"ge": 1.5}}}},
            "must be an integer",
        ),
        (
            {"vars_schema": {"amount": {"type": "text", "validation": {"ge": 1}}}},
            "do not apply",
        ),
        (
            {"vars_schema": {"amount": {"type": "bool", "validation": {"pattern": "true"}}}},
            "do not apply",
        ),
        (
            {"vars_schema": {"amount": {"type": "text", "validation": {"pattern": "["}}}},
            "not a regular expression",
        ),
        (
            {"vars_schema": {"amount": {"type": "int", "validation": {"allowed": [1, 1]}}}},
            "duplicate",
        ),
        (
            {"vars_schema": {"amount": {"type": "int", "validation": {"allowed": []}}}},
            "non-empty",
        ),
    ],
)
def test_config_errors(document: dict[str, object], match: str) -> None:
    with pytest.raises(VarConfigError, match=match):
        _catalog(document)


def test_literal_ahead_of_a_template_fails_at_load() -> None:
    with pytest.raises(VarConfigError, match="cannot be cast"):
        _catalog(
            {"vars_schema": {"amount": {"type": "int", "default": ["12.0", "{{ other }}"]}}}
        )


def test_template_candidate_is_kept_and_compiled() -> None:
    environment = VarEnvironment()
    catalog = _catalog(
        {"vars_schema": {"amount": {"type": "int", "default": ["{{ missing }}", "12"]}}},
        compile_source=environment.compile_source,
    )

    assert catalog.spec("amount").candidates == ("{{ missing }}", "12")


def test_default_vars_fills_an_implicit_spec() -> None:
    catalog = _catalog({"default_vars": {"vendor": "Bank2000"}})
    spec = catalog.spec("vendor")

    assert spec.type == "text"
    assert spec.has_default is True
    assert spec.candidates == ("Bank2000",)


def test_schema_without_default_takes_default_vars() -> None:
    catalog = _catalog(
        {
            "vars_schema": {"vendor": {"type": "text", "desc": "Payer"}},
            "default_vars": {"vendor": "UNKNOWN"},
        }
    )

    assert catalog.spec("vendor").candidates == ("UNKNOWN",)
    assert catalog.spec("vendor").desc == "Payer"


def test_int_cast_display_and_allowed() -> None:
    spec = _spec(
        {"type": "int", "validation": {"allowed": [7, 10], "ge": 0, "le": 20}}
    )

    cast = cast_value(spec, "007")
    assert cast.value == 7
    assert cast.display == "7"
    assert cast_value(spec, "+7").display == "7"

    with pytest.raises(CastMiss, match="not an int"):
        cast_value(spec, "12.0")
    with pytest.raises(CastMiss, match="not an allowed value"):
        cast_value(spec, "15")
    with pytest.raises(CastMiss, match="empty"):
        cast_value(spec, "  ")


def test_float_keeps_spelling_and_matches_zero() -> None:
    plain = _spec({"type": "float"})
    cast = cast_value(plain, "12.50")

    assert cast.value == 12.5
    assert cast.display == "12.50"
    with pytest.raises(CastMiss, match="not a float"):
        cast_value(plain, "1e2")

    spec = _spec({"type": "float", "validation": {"allowed": [0], "ge": 0}})
    assert cast_value(spec, "-0").display == "-0"
    assert cast_value(spec, "-0.0").value == 0.0
    with pytest.raises(CastMiss, match="not an allowed value"):
        cast_value(spec, "1")


def test_bool_display() -> None:
    spec = _spec({"type": "bool"})

    assert cast_value(spec, "YES").display == "true"
    assert cast_value(spec, "1").value is True
    assert cast_value(spec, "no").display == "false"
    assert cast_value(spec, True, allow_typed=True).display == "true"

    with pytest.raises(CastMiss, match="not a bool"):
        cast_value(spec, "maybe")


def test_text_keeps_whitespace_pattern_and_allowed() -> None:
    plain = _spec({"type": "text"})
    assert cast_value(plain, "  ").display == "  "
    assert cast_value(plain, "").value == ""

    shaped = _spec(
        {"type": "text", "validation": {"pattern": "A+", "min_length": 2, "max_length": 3}},
        name="code",
    )
    assert cast_value(shaped, "AA").value == "AA"
    with pytest.raises(CastMiss, match="does not match"):
        cast_value(shaped, "AB")
    with pytest.raises(CastMiss, match="shorter than 2"):
        cast_value(shaped, "A")
    with pytest.raises(CastMiss, match="longer than 3"):
        cast_value(shaped, "AAAA")

    exact = _spec({"type": "text", "validation": {"allowed": ["007"]}}, name="code")
    assert cast_value(exact, "007").value == "007"
    with pytest.raises(CastMiss, match="not an allowed value"):
        cast_value(exact, "7")


def test_date_time_and_datetime() -> None:
    issued = _spec({"type": "date", "validation": {"ge": "2026-01-01", "le": "2026-12-31"}})
    opens = _spec({"type": "time", "validation": {"allowed": ["15:04:00"]}})
    issued_at = _spec({"type": "datetime"})

    assert cast_value(issued, "2026-04-25").value == "2026-04-25"
    with pytest.raises(CastMiss, match="not a YYYY-MM-DD date"):
        cast_value(issued, "2026-04-25T15:04")
    with pytest.raises(CastMiss, match="not a YYYY-MM-DD date"):
        cast_value(issued, "2026-02-31")

    same = cast_value(opens, "15:04")
    assert same.display == "15:04"
    assert same.value == "15:04"
    with pytest.raises(CastMiss, match="not a HH:MM"):
        cast_value(opens, "15:4")

    assert cast_value(issued_at, "2026-04-25T15:04").display == "2026-04-25T15:04"
    assert cast_value(issued_at, "2026-04-25T15:04:05").value == "2026-04-25T15:04:05"
    with pytest.raises(CastMiss, match="not a YYYY-MM-DDTHH:MM"):
        cast_value(issued_at, "2026-04-25")
    with pytest.raises(CastMiss, match="not a YYYY-MM-DDTHH:MM"):
        cast_value(issued_at, "2026-04-25 15:04")
    with pytest.raises(CastMiss, match="not a YYYY-MM-DDTHH:MM"):
        cast_value(issued_at, "2026-04-25T15:04Z")


def test_typed_literal_must_match_and_dumps_json() -> None:
    spec = _spec({"type": "int", "default": 12})
    cast = cast_value(spec, 12, allow_typed=True)
    state = VarState(value=cast.value, display=cast.display, value_sources=["default"])

    assert cast.display == "12"
    assert state.model_dump(mode="json") == {"value": 12, "value_sources": ["default"]}
    assert "display" not in state.model_dump(mode="json")
    VarSpec.model_json_schema()

    wide = _spec({"type": "float"})
    dumped = VarState(value=12.5, display="12.50", value_sources=["fact"])
    assert dumped.model_dump(mode="json")["value"] == 12.5
    assert dumped.display == "12.50"

    with pytest.raises(VarConfigError, match="does not match type float"):
        _spec({"type": "float", "default": 12})


def test_state_clear_drops_sources() -> None:
    state = VarState(value="2026-04-25", display="2026-04-25", value_sources=["filename"])
    state.clear()

    assert state.model_dump(mode="json") == {"value": None, "value_sources": []}


def test_leading_zeros_and_range() -> None:
    spec = _spec({"type": "int", "validation": {"gt": 0, "lt": 20}})
    cast = cast_value(spec, "0012")

    assert cast.value == 12
    assert cast.display == "12"
    with pytest.raises(CastMiss, match="greater than 0"):
        cast_value(spec, "0")
