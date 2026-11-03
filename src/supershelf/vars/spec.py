"""Variable spec, cast, and validation.

A declared VarSpec and a resolved VarState are different objects.
Jinja still sees the display string, except a set date, which is a date object.
The Python value stays on VarState.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    ValidationError,
    ValidationInfo,
    model_validator,
)

from supershelf.constants import (
    DATE_TEXT,
    TYPE_BOOL,
    TYPE_DATE,
    TYPE_DATETIME,
    TYPE_FLOAT,
    TYPE_INT,
    TYPE_TEXT,
    TYPE_TIME,
    VAR_NAME_PATTERN,
    VAR_TYPES,
)
from supershelf.errors import VarConfigError
from supershelf.template.environment import is_template

_IDENT = re.compile(VAR_NAME_PATTERN)
_INT_TEXT = re.compile(r"[+-]?[0-9]+\Z")
_FLOAT_TEXT = re.compile(r"[+-]?(?:[0-9]+\.[0-9]*|\.[0-9]+|[0-9]+)\Z")
_DATE_TEXT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_TIME_TEXT = re.compile(r"([0-9]{2}):([0-9]{2})(?::([0-9]{2}))?\Z")
_DATETIME_TEXT = re.compile(
    r"([0-9]{4}-[0-9]{2}-[0-9]{2})T([0-9]{2}:[0-9]{2}(?::[0-9]{2})?)\Z"
)
_BOOL_TRUE = frozenset({"true", "yes", "1"})
_BOOL_FALSE = frozenset({"false", "no", "0"})
_TIME_FORMATS = ("%H:%M:%S", "%H:%M")
_RESERVED_ADVICE = "A layer may set names that do not start with __."
_LENGTH_TYPES = frozenset({TYPE_TEXT, TYPE_DATE, TYPE_TIME, TYPE_DATETIME})
_RANGE_TYPES = frozenset({TYPE_INT, TYPE_FLOAT, TYPE_DATE, TYPE_TIME, TYPE_DATETIME})
_VALIDATION_KEYS = frozenset(
    {"allowed", "pattern", "min_length", "max_length", "ge", "gt", "le", "lt"}
)
_TYPE_ADVICE = "Use text, int, float, bool, date, time, or datetime."
_QUOTE_ADVICE = "Quote scalars such as dates so they stay strings."

VarTypeName = Literal["text", "int", "float", "bool", "date", "time", "datetime"]
JsonValue = int | float | bool | str | None


class CastMiss(Exception):
    """This candidate failed cast or validation. The message is the miss text."""


@dataclass(frozen=True)
class CastValue:
    """One successful cast. `value` is the JSON value. `display` is the printed string."""

    value: int | float | bool | str
    display: str
    comparable: object


@dataclass(frozen=True)
class _Limit:
    comparable: object
    text: str


@dataclass(frozen=True)
class ValidationRules:
    """Constraints that apply after a successful cast."""

    allowed: tuple[object, ...] | None = None
    allowed_json: tuple[object, ...] | None = None
    pattern: re.Pattern[str] | None = None
    pattern_text: str | None = None
    min_length: int | None = None
    max_length: int | None = None
    ge: _Limit | None = None
    gt: _Limit | None = None
    le: _Limit | None = None
    lt: _Limit | None = None


class ValidationSpec(BaseModel):
    """Raw validation mapping. Applicability depends on the variable type."""

    model_config = ConfigDict(extra="forbid", strict=True)

    allowed: Any = None
    pattern: Any = None
    min_length: Any = None
    max_length: Any = None
    ge: Any = None
    gt: Any = None
    le: Any = None
    lt: Any = None

    @model_validator(mode="before")
    @classmethod
    def _shape(cls, data: Any, info: ValidationInfo) -> Any:
        parent = "variable"
        if info.context:
            parent = str(info.context.get("label", parent))
        label = f"{parent}.validation"
        if not isinstance(data, dict):
            raise VarConfigError(
                f"{label} must be a mapping",
                advice="Set allowed, pattern, lengths, or a range.",
            )
        extras = [str(key) for key in data if key not in _VALIDATION_KEYS]
        if extras:
            joined = ", ".join(extras)
            raise VarConfigError(
                f"{label} has unknown keys: {joined}",
                advice="Use allowed, pattern, min_length, max_length, ge, gt, le, or lt.",
            )
        return data


class VarSpec(BaseModel):
    """One catalog entry. Unknown keys are a config error."""

    model_config = ConfigDict(extra="forbid", strict=True)

    desc: str = ""
    type: VarTypeName = TYPE_TEXT
    unit: str | None = None
    internal: bool = False
    mandatory: bool = False
    default: Any = None
    validation: ValidationSpec | None = None
    _rules: ValidationRules | None = PrivateAttr(default=None)

    @property
    def has_default(self) -> bool:
        """True when vars_schema.default or default_vars set this name."""
        return "default" in self.model_fields_set

    @property
    def candidates(self) -> tuple[object, ...]:
        """Assignment candidates. A list here is not the stored value."""
        if "default" not in self.model_fields_set:
            return ()
        raw = self.default
        if isinstance(raw, list):
            return tuple(raw)
        return (raw,)

    @property
    def rules(self) -> ValidationRules | None:
        """Prepared validation, or none when the spec has no validation key."""
        return self._rules

    @classmethod
    def load(
        cls,
        payload: Mapping[str, Any],
        *,
        label: str,
        from_schema: bool,
        compile_source: Callable[[str], None] | None,
    ) -> VarSpec:
        """Validate one spec. `from_schema` allows typed literals in default."""
        if "type" in payload:
            cls._reject_type(label, payload["type"])
        try:
            return cls.model_validate(
                payload,
                context={
                    "label": label,
                    "from_schema": from_schema,
                    "compile_source": compile_source,
                },
            )
        except ValidationError as exc:
            raise cls._config_error(label, exc) from exc

    def with_default(
        self,
        raw: object,
        *,
        label: str,
        from_schema: bool,
        compile_source: Callable[[str], None] | None,
    ) -> VarSpec:
        """Return a copy whose default slot is `raw`."""
        data = self.model_dump(exclude_unset=True)
        data["default"] = raw
        return self.load(
            data,
            label=label,
            from_schema=from_schema,
            compile_source=compile_source,
        )

    @model_validator(mode="after")
    def _finish(self, info: ValidationInfo) -> Self:
        label, from_schema, compile_source = self._context(info)
        if "validation" in self.model_fields_set and self.validation is None:
            raise VarConfigError(
                f"{label}.validation must be a mapping",
                advice="Set allowed, pattern, lengths, or a range.",
            )
        if self.validation is not None:
            self._rules = self._compile_rules(f"{label}.validation")
        if "default" in self.model_fields_set:
            self._check_default(f"{label}.default", from_schema, compile_source)
        return self

    @staticmethod
    def _context(
        info: ValidationInfo,
    ) -> tuple[str, bool, Callable[[str], None] | None]:
        ctx = info.context or {}
        label = str(ctx.get("label", "variable"))
        from_schema = bool(ctx.get("from_schema", True))
        compile_source = ctx.get("compile_source")
        return label, from_schema, compile_source

    @staticmethod
    def _reject_type(label: str, raw_type: object) -> None:
        if raw_type == "list":
            raise VarConfigError(
                f"{label} type list is not supported",
                advice="A stored value is one scalar. Use a candidate list for fallbacks.",
            )
        if not isinstance(raw_type, str) or raw_type not in VAR_TYPES:
            raise VarConfigError(
                f"{label} type {raw_type!r} is unknown",
                advice=_TYPE_ADVICE,
            )

    @staticmethod
    def _config_error(label: str, exc: ValidationError) -> VarConfigError:
        first = exc.errors()[0]
        loc = ".".join(str(part) for part in first["loc"])
        where = f"{label}.{loc}" if loc else label
        if first["type"] == "extra_forbidden":
            return VarConfigError(
                f"{where} is an unknown key",
                advice="Remove it. Check the spelling.",
            )
        return VarConfigError(
            f"{where} is invalid: {first['msg']}",
            advice="Check the field type and spelling.",
        )

    def _check_default(
        self,
        label: str,
        from_schema: bool,
        compile_source: Callable[[str], None] | None,
    ) -> None:
        raw = self.default
        if raw is None:
            raise VarConfigError(
                f"{label} is null",
                advice="Omit the key to leave the variable unset. null is not unset.",
            )
        if isinstance(raw, list):
            if not raw:
                raise VarConfigError(
                    f"{label} has an empty list",
                    advice="Add at least one candidate, or remove the key.",
                )
            candidates = tuple(raw)
        else:
            candidates = (raw,)
        for item in candidates:
            if isinstance(item, list):
                raise VarConfigError(
                    f"{label} contains a nested list",
                    advice="Each candidate is one scalar. The list is only the fallback order.",
                )
            self._check_candidate_shape(item, from_schema, label)
            if isinstance(item, str) and is_template(item):
                if compile_source is not None:
                    compile_source(item)
                continue
            try:
                cast_value(self, item, allow_typed=from_schema)
            except CastMiss as exc:
                raise VarConfigError(
                    f"{label} cannot be cast",
                    advice=str(exc),
                ) from exc

    def _check_candidate_shape(self, item: object, from_schema: bool, label: str) -> None:
        if isinstance(item, str):
            return
        if from_schema and _typed_matches(self.type, item):
            return
        if from_schema:
            raise VarConfigError(
                f"{label} candidate {item!r} does not match type {self.type}",
                advice="Use a typed literal of that type, or a string.",
            )
        raise VarConfigError(
            f"{label} must be a string or a list of strings",
            advice=_QUOTE_ADVICE,
        )

    def _compile_rules(self, label: str) -> ValidationRules:
        spec = self.validation
        assert spec is not None
        present = [key for key in _VALIDATION_KEYS if key in spec.model_fields_set]
        skipped = [key for key in present if key not in self._keys_for()]
        if skipped:
            joined = ", ".join(skipped)
            raise VarConfigError(
                f"{label} keys do not apply to type {self.type}: {joined}",
                advice="Remove the keys that do not apply to this type.",
            )
        raw = spec
        pattern: re.Pattern[str] | None = None
        pattern_text: str | None = None
        if "pattern" in present:
            pattern, pattern_text = self._prepare_pattern(raw.pattern, label)
        allowed = None
        allowed_json = None
        if "allowed" in present:
            allowed, allowed_json = self._prepare_allowed(raw.allowed, label)
        return ValidationRules(
            allowed=allowed,
            allowed_json=allowed_json,
            pattern=pattern,
            pattern_text=pattern_text,
            min_length=self._prepare_length(raw.min_length, f"{label}.min_length")
            if "min_length" in present
            else None,
            max_length=self._prepare_length(raw.max_length, f"{label}.max_length")
            if "max_length" in present
            else None,
            ge=self._prepare_bound(raw.ge, f"{label}.ge") if "ge" in present else None,
            gt=self._prepare_bound(raw.gt, f"{label}.gt") if "gt" in present else None,
            le=self._prepare_bound(raw.le, f"{label}.le") if "le" in present else None,
            lt=self._prepare_bound(raw.lt, f"{label}.lt") if "lt" in present else None,
        )

    def _keys_for(self) -> set[str]:
        keys = {"allowed"}
        if self.type in _LENGTH_TYPES:
            keys.update({"pattern", "min_length", "max_length"})
        if self.type in _RANGE_TYPES:
            keys.update({"ge", "gt", "le", "lt"})
        return keys

    @staticmethod
    def _prepare_pattern(raw: object, label: str) -> tuple[re.Pattern[str], str]:
        field = f"{label}.pattern"
        if not isinstance(raw, str):
            raise VarConfigError(
                f"{field} must be a string",
                advice="Use a regular expression. It is matched against the whole value.",
            )
        try:
            return re.compile(raw), raw
        except re.error as exc:
            raise VarConfigError(
                f"{field} is not a regular expression",
                advice=str(exc),
            ) from exc

    @staticmethod
    def _prepare_length(raw: object, label: str) -> int:
        if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
            raise VarConfigError(
                f"{label} must be a non-negative integer",
                advice="Lengths count characters in the display string.",
            )
        return raw

    def _prepare_allowed(
        self,
        raw: object,
        label: str,
    ) -> tuple[tuple[object, ...], tuple[object, ...]]:
        field = f"{label}.allowed"
        if not isinstance(raw, list) or not raw:
            raise VarConfigError(
                f"{field} must be a non-empty list",
                advice="List the values this variable may take.",
            )
        found: list[object] = []
        json_values: list[object] = []
        for item in raw:
            comparable, json_value = self._allowed_item(item, field)
            if any(comparable == previous for previous in found):
                raise VarConfigError(
                    f"{field} contains a duplicate",
                    advice="List each allowed value once.",
                )
            found.append(comparable)
            json_values.append(json_value)
        return tuple(found), tuple(json_values)

    def _allowed_item(self, item: object, label: str) -> tuple[object, object]:
        if self.type == TYPE_TEXT:
            if not isinstance(item, str):
                raise VarConfigError(
                    f"{label} item {item!r} must be a string",
                    advice="Text allowed values are strings.",
                )
            return item, item
        if self.type == TYPE_INT and isinstance(item, int) and not isinstance(item, bool):
            return item, item
        if self.type == TYPE_FLOAT and _is_float_number(item):
            number = float(item)  # type: ignore[arg-type]
            return number, number
        if self.type == TYPE_BOOL and isinstance(item, bool):
            return item, item
        if isinstance(item, str) and self.type != TYPE_TEXT:
            try:
                cast = cast_value(self, item, allow_typed=False)
            except CastMiss as exc:
                raise VarConfigError(
                    f"{label} item {item!r} does not match type {self.type}",
                    advice=str(exc),
                ) from exc
            return cast.comparable, cast.value
        raise VarConfigError(
            f"{label} item {item!r} does not match type {self.type}",
            advice="Use a value of that type.",
        )

    def _prepare_bound(self, raw: object, label: str) -> _Limit:
        if self.type == TYPE_INT:
            if isinstance(raw, bool) or not isinstance(raw, int):
                raise VarConfigError(
                    f"{label} must be an integer",
                    advice="An int bound is an int.",
                )
            return _Limit(raw, str(raw))
        if self.type == TYPE_FLOAT:
            if not _is_float_number(raw):
                raise VarConfigError(
                    f"{label} must be a number",
                    advice="A float bound is an int or a float.",
                )
            number = float(raw)  # type: ignore[arg-type]
            return _Limit(number, str(raw))
        if not isinstance(raw, str):
            raise VarConfigError(
                f"{label} must be a {self.type} string",
                advice="Quote the bound. A date bound is not a datetime bound.",
            )
        try:
            cast = cast_value(self, raw, allow_typed=False)
        except CastMiss as exc:
            raise VarConfigError(
                f"{label} is not a {self.type}",
                advice=str(exc),
            ) from exc
        return _Limit(cast.comparable, cast.display)


class VarState(BaseModel):
    """One resolved binding. The spec is not copied onto it."""

    model_config = ConfigDict(extra="forbid")

    value: JsonValue = None
    display: str = Field(default="", exclude=True)
    value_sources: list[str] = Field(default_factory=list)

    def write(self, cast: CastValue, label: str) -> None:
        """Store a successful cast and append the layer that wrote it."""
        self.value = cast.value
        self.display = cast.display
        self.value_sources.append(label)

    def clear(self) -> None:
        """Drop the value and the source list together."""
        self.value = None
        self.display = ""
        self.value_sources.clear()


def layer_source(prefix: str, detail: str) -> str:
    """A source label such as rule:invoice or kind:/tmp/invoice.csv."""
    return f"{prefix}:{detail}"


def cast_value(spec: VarSpec, raw: object, *, allow_typed: bool = False) -> CastValue:
    """Cast one produced value, then validate it. A miss raises CastMiss.

    Typed literals are accepted only when `allow_typed` is set, which is the
    vars_schema.default path. Assignment strings and rendered templates stay
    strings. Empty text is a value. Empty input for every other type is a miss,
    not None.
    """
    cast = _cast_unvalidated(spec, raw, allow_typed=allow_typed)
    _validate(spec, cast)
    return cast



def check_var_name(name: object, label: str) -> None:
    if not isinstance(name, str) or _IDENT.fullmatch(name) is None:
        raise VarConfigError(
            f"{label} is not a variable name",
            advice="Start with a letter or underscore, then use letters, digits, and underscores.",
        )


def reserved_var_name(name: str) -> bool:
    """A namespace root, or any other name that starts with __."""
    return name.startswith("__")


def check_assignment_key(key: object, label: str) -> None:
    """Reject a name that is not a variable, or a namespace root."""
    check_var_name(key, f"{label} key {key!r}")
    if isinstance(key, str) and reserved_var_name(key):
        raise VarConfigError(
            f"{label} cannot set {key}",
            advice=_RESERVED_ADVICE,
        )



def _typed_matches(var_type: str, raw: object) -> bool:
    if var_type == TYPE_INT:
        return isinstance(raw, int) and not isinstance(raw, bool)
    if var_type == TYPE_FLOAT:
        return isinstance(raw, float)
    if var_type == TYPE_BOOL:
        return isinstance(raw, bool)
    return False



def _is_float_number(raw: object) -> bool:
    return (isinstance(raw, float) or isinstance(raw, int)) and not isinstance(raw, bool)


def _cast_unvalidated(spec: VarSpec, raw: object, *, allow_typed: bool) -> CastValue:
    if isinstance(raw, str):
        return _cast_string(spec, raw)
    if allow_typed and _typed_matches(spec.type, raw):
        return _cast_typed(spec.type, raw)
    if allow_typed:
        raise VarConfigError(
            f"candidate {raw!r} does not match type {spec.type}",
            advice="Use a typed literal of that type, or a string.",
        )
    raise CastMiss(f"{raw!r} is not a string")


def _cast_typed(var_type: str, raw: object) -> CastValue:
    if var_type == TYPE_INT and isinstance(raw, int) and not isinstance(raw, bool):
        return CastValue(raw, str(raw), raw)
    if var_type == TYPE_FLOAT and isinstance(raw, float):
        return CastValue(raw, str(raw), raw)
    if var_type == TYPE_BOOL and isinstance(raw, bool):
        display = "true" if raw else "false"
        return CastValue(raw, display, raw)
    raise CastMiss(f"{raw!r} is not a {var_type}")


def _cast_string(spec: VarSpec, raw: str) -> CastValue:
    if spec.type == TYPE_TEXT:
        return CastValue(raw, raw, raw)
    if raw.strip() == "":
        raise CastMiss(f"{raw!r} is empty")
    text = raw.strip()
    if spec.type == TYPE_INT:
        return _cast_int(text)
    if spec.type == TYPE_FLOAT:
        return _cast_float(text)
    if spec.type == TYPE_BOOL:
        return _cast_bool(text)
    if spec.type == TYPE_DATE:
        return _cast_date(text)
    if spec.type == TYPE_TIME:
        return _cast_time(text)
    if spec.type == TYPE_DATETIME:
        return _cast_datetime(text)
    raise CastMiss(f"{text!r} is not a {spec.type}")


def _cast_int(text: str) -> CastValue:
    if _INT_TEXT.fullmatch(text) is None:
        raise CastMiss(f"{text!r} is not an int")
    value = int(text)
    return CastValue(value, str(value), value)


def _cast_float(text: str) -> CastValue:
    if _FLOAT_TEXT.fullmatch(text) is None:
        raise CastMiss(f"{text!r} is not a float")
    value = float(text)
    return CastValue(value, text, value)


def _cast_bool(text: str) -> CastValue:
    token = text.lower()
    if token in _BOOL_TRUE:
        return CastValue(True, "true", True)
    if token in _BOOL_FALSE:
        return CastValue(False, "false", False)
    raise CastMiss(f"{text!r} is not a bool")


def _cast_date(text: str) -> CastValue:
    if _DATE_TEXT.fullmatch(text) is None or not _round_trip_date(text):
        raise CastMiss(f"{text!r} is not a YYYY-MM-DD date")
    parsed = datetime.strptime(text, DATE_TEXT).date()
    return CastValue(text, text, parsed)


def cast_date_display(text: str, fmt: str) -> CastValue:
    """Parse a date written with the profile format. Store `YYYY-MM-DD`."""
    if not isinstance(fmt, str) or not fmt.strip() or fmt == DATE_TEXT:
        raise CastMiss(f"{text!r} is not a YYYY-MM-DD date")
    stripped = text.strip()
    try:
        parsed = datetime.strptime(stripped, fmt)
    except ValueError as exc:
        raise CastMiss(f"{text!r} is not a YYYY-MM-DD date") from exc
    if parsed.strftime(fmt) != stripped:
        raise CastMiss(f"{text!r} is not a YYYY-MM-DD date")
    iso = parsed.strftime(DATE_TEXT)
    return CastValue(iso, iso, parsed.date())


def _round_trip_date(text: str) -> bool:
    try:
        parsed = datetime.strptime(text, DATE_TEXT)
    except ValueError:
        return False
    return parsed.strftime(DATE_TEXT) == text


def _cast_time(text: str) -> CastValue:
    matched = _TIME_TEXT.fullmatch(text)
    if matched is None:
        raise CastMiss(f"{text!r} is not a HH:MM or HH:MM:SS time")
    hour = int(matched.group(1))
    minute = int(matched.group(2))
    second = int(matched.group(3)) if matched.group(3) is not None else 0
    if not _clock_ok(hour, minute, second):
        raise CastMiss(f"{text!r} is not a HH:MM or HH:MM:SS time")
    fmt = _TIME_FORMATS[0] if matched.group(3) is not None else _TIME_FORMATS[1]
    try:
        parsed = datetime.strptime(text, fmt)
    except ValueError as exc:
        raise CastMiss(f"{text!r} is not a HH:MM or HH:MM:SS time") from exc
    if parsed.strftime(fmt) != text:
        raise CastMiss(f"{text!r} is not a HH:MM or HH:MM:SS time")
    value = time(hour, minute, second)
    return CastValue(text, text, value)


def _cast_datetime(text: str) -> CastValue:
    matched = _DATETIME_TEXT.fullmatch(text)
    if matched is None:
        raise CastMiss(f"{text!r} is not a YYYY-MM-DDTHH:MM datetime")
    date_text, time_text = matched.group(1), matched.group(2)
    try:
        date_cast = _cast_date(date_text)
        time_cast = _cast_time(time_text)
    except CastMiss as exc:
        raise CastMiss(f"{text!r} is not a YYYY-MM-DDTHH:MM datetime") from exc
    parsed = datetime.combine(date_cast.comparable, time_cast.comparable)  # type: ignore[arg-type]
    return CastValue(text, text, parsed)


def _clock_ok(hour: int, minute: int, second: int) -> bool:
    return 0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59


def _validate(spec: VarSpec, cast: CastValue) -> None:
    rules = spec.rules
    if rules is None:
        return
    if rules.allowed is not None and not any(
        cast.comparable == item for item in rules.allowed
    ):
        raise CastMiss(f"{cast.display!r} is not an allowed value")
    if rules.pattern is not None and rules.pattern.fullmatch(cast.display) is None:
        raise CastMiss(
            f"{cast.display!r} does not match {rules.pattern_text}"
        )
    if rules.min_length is not None and len(cast.display) < rules.min_length:
        raise CastMiss(
            f"{cast.display!r} is shorter than {rules.min_length}"
        )
    if rules.max_length is not None and len(cast.display) > rules.max_length:
        raise CastMiss(
            f"{cast.display!r} is longer than {rules.max_length}"
        )
    _check_limit(cast, rules.ge, ">=")
    _check_limit(cast, rules.gt, ">")
    _check_limit(cast, rules.le, "<=")
    _check_limit(cast, rules.lt, "<")


def _check_limit(cast: CastValue, limit: _Limit | None, operator: str) -> None:
    if limit is None:
        return
    comparable = cast.comparable
    bound = limit.comparable
    passed = False
    if operator == ">=":
        passed = comparable >= bound  # type: ignore[operator]
    elif operator == ">":
        passed = comparable > bound  # type: ignore[operator]
    elif operator == "<=":
        passed = comparable <= bound  # type: ignore[operator]
    elif operator == "<":
        passed = comparable < bound  # type: ignore[operator]
    if passed:
        return
    words = {
        ">=": "greater than or equal to",
        ">": "greater than",
        "<=": "less than or equal to",
        "<": "less than",
    }[operator]
    raise CastMiss(f"{cast.display!r} must be {words} {limit.text}")
