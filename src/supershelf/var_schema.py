"""Variable catalog, cast, and validation.

A declared VarSpec and a resolved VarState are different objects.
Jinja still sees the display string. The Python value stays on VarState.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
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
    KEY_DEFAULT_VARS,
    KEY_KIND_SCHEMA,
    KEY_VARS_SCHEMA,
    TYPE_BOOL,
    TYPE_DATE,
    TYPE_DATETIME,
    TYPE_FLOAT,
    TYPE_INT,
    TYPE_TEXT,
    TYPE_TIME,
    VAR_DATE,
    VAR_NAME_PATTERN,
    VAR_TYPES,
)
from supershelf.errors import VarConfigError
from supershelf.var_template import is_template

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
_DATE_LOCKED_KEYS = frozenset({"type", "internal"})
_DATE_KEYS = frozenset({"desc", "unit", "mandatory", "default", "validation"})
_RESERVED_ADVICE = "A layer may set __date__ and names that do not start with __."
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


class KindSchema:
    """One kind: a description and the local names that belong to it."""

    def __init__(self, name: str, desc: str, variables: dict[str, VarSpec]) -> None:
        self.name = name
        self.desc = desc
        self.vars = variables


_KIND_VAR_ADVICE = (
    "Use a catalog name, leave the value empty to use the local name, "
    "or set schema and any of desc, unit, mandatory, default, or validation."
)


def _blank_schema_name(value: object) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _reject_kind_var_keys(data: Mapping[str, Any], label: str) -> None:
    if "type" in data:
        raise VarConfigError(
            f"{label} cannot set type",
            advice="The type comes from the vars_schema entry named by schema.",
        )
    if "internal" in data:
        raise VarConfigError(
            f"{label} cannot set internal",
            advice="internal is only for variables supershelf fills in.",
        )


class KindVarRef(BaseModel):
    """Object form of one kind variable. `schema` may be omitted."""

    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)

    schema_name: str | None = Field(
        default=None,
        alias="schema",
        description="Catalog name. Omit, null, or blank to use the local name.",
    )
    desc: str | None = None
    unit: str | None = None
    mandatory: bool | None = None
    default: Any = None
    validation: ValidationSpec | None = None

    @model_validator(mode="before")
    @classmethod
    def _shape(cls, data: Any, info: ValidationInfo) -> Any:
        if isinstance(data, dict):
            label = "kind var"
            if info.context:
                label = str(info.context.get("var_label", info.context.get("label", label)))
            _reject_kind_var_keys(data, label)
        return data


class KindSchemaSpec(BaseModel):
    """One kind_schema entry, including the short variable forms."""

    model_config = ConfigDict(extra="forbid", strict=True)

    desc: str = ""
    vars_schema: dict[str, str | None | KindVarRef] = Field(
        description=(
            "Local name to a catalog reference. "
            "A string is the schema name. "
            "Null or a blank string uses the local name. "
            "An object may omit schema, which then uses the local name."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _expand(cls, data: Any, info: ValidationInfo) -> Any:
        label = "kind_schema"
        if info.context:
            label = str(info.context.get("label", label))
        if not isinstance(data, dict):
            raise VarConfigError(
                f"{label} must be a mapping",
                advice="Set desc and vars_schema.",
            )
        unknown = [str(key) for key in data if key not in {"desc", "vars_schema"}]
        if unknown:
            joined = ", ".join(unknown)
            raise VarConfigError(
                f"{label} has unknown keys: {joined}",
                advice="Set desc and vars_schema.",
            )
        if "desc" in data and not isinstance(data["desc"], str):
            raise VarConfigError(
                f"{label}.desc must be a string",
                advice="Use a short description, or omit desc.",
            )
        if "vars_schema" not in data:
            raise VarConfigError(
                f"{label} needs vars_schema",
                advice="Map each local name to a schema reference.",
            )
        raw_vars = data["vars_schema"]
        if not isinstance(raw_vars, dict):
            raise VarConfigError(
                f"{label}.vars_schema must be a mapping",
                advice="Map each local name to a schema reference.",
            )
        expanded: dict[object, Any] = {}
        for name, entry in raw_vars.items():
            key = str(name)
            var_label = f"{label}.vars_schema.{key}"
            expanded[key] = cls._expand_var(key, entry, var_label)
        return {**data, "vars_schema": expanded}

    @staticmethod
    def _expand_var(name: str, entry: object, label: str) -> dict[str, Any]:
        if _blank_schema_name(entry):
            return {"schema": name}
        if isinstance(entry, str):
            return {"schema": entry.strip()}
        if isinstance(entry, dict):
            _reject_kind_var_keys(entry, label)
            data = dict(entry)
            ref = data.get("schema")
            if "schema" not in data or _blank_schema_name(ref):
                data["schema"] = name
            elif not isinstance(ref, str):
                raise VarConfigError(
                    f"{label}.schema must be a string",
                    advice=(
                        "Point schema at a vars_schema name, or at __date__. "
                        "Leave it empty to use the local name."
                    ),
                )
            else:
                data["schema"] = ref.strip()
            return data
        raise VarConfigError(
            f"{label} must be a schema name, empty, or a mapping",
            advice=_KIND_VAR_ADVICE,
        )


class KindCatalog:
    """kind_schema entries for one profile. Absent means no overlays."""

    def __init__(self, present: bool, kinds: dict[str, KindSchema]) -> None:
        self.present = present
        self._kinds = kinds

    def items(self) -> tuple[KindSchema, ...]:
        """Kinds in profile order."""
        return tuple(self._kinds.values())

    def get(self, kind: str) -> KindSchema | None:
        """The schema for this kind, or none when the kind is not listed."""
        return self._kinds.get(kind)

    def var(self, kind: str, name: str) -> VarSpec | None:
        """The overlaid spec for this kind and name, or none."""
        found = self._kinds.get(kind)
        if found is None:
            return None
        return found.vars.get(name)

    @classmethod
    def load(
        cls,
        document: Mapping[str, Any],
        specs: Mapping[str, VarSpec],
        declared: set[str],
        compile_source: Callable[[str], None] | None,
    ) -> KindCatalog:
        """Parse kind_schema. A missing key is an empty catalog."""
        raw = document.get(KEY_KIND_SCHEMA)
        if raw is None:
            return cls(False, {})
        if not isinstance(raw, dict):
            raise VarConfigError(
                "kind_schema must be a mapping",
                advice="Map each kind name to desc and vars_schema.",
            )
        kinds: dict[str, KindSchema] = {}
        for kind, body in raw.items():
            kinds[str(kind)] = cls._kind(str(kind), body, specs, declared, compile_source)
        return cls(True, kinds)

    @classmethod
    def _kind(
        cls,
        kind: str,
        body: object,
        specs: Mapping[str, VarSpec],
        declared: set[str],
        compile_source: Callable[[str], None] | None,
    ) -> KindSchema:
        label = f"kind_schema.{kind}"
        try:
            parsed = KindSchemaSpec.model_validate(body, context={"label": label})
        except ValidationError as exc:
            raise VarSpec._config_error(label, exc) from exc
        variables: dict[str, VarSpec] = {}
        for name, entry in parsed.vars_schema.items():
            if not isinstance(entry, KindVarRef):
                raise VarConfigError(
                    f"{label}.vars_schema.{name} must be a schema name, empty, or a mapping",
                    advice=_KIND_VAR_ADVICE,
                )
            variables[name] = cls._var(
                kind,
                name,
                entry,
                specs,
                declared,
                compile_source,
            )
        return KindSchema(kind, parsed.desc, variables)

    @classmethod
    def _var(
        cls,
        kind: str,
        name: object,
        entry: KindVarRef,
        specs: Mapping[str, VarSpec],
        declared: set[str],
        compile_source: Callable[[str], None] | None,
    ) -> VarSpec:
        label = f"kind_schema.{kind}.vars_schema.{name}"
        check_var_name(name, label)
        key = str(name)
        if reserved_var_name(key):
            raise VarConfigError(
                f"{label} is reserved",
                advice=_RESERVED_ADVICE,
            )
        written = entry.model_dump(exclude_unset=True, by_alias=True)
        ref = written.pop("schema", None)
        if isinstance(ref, str):
            ref = ref.strip()
        if not isinstance(ref, str) or ref == "":
            raise VarConfigError(
                f"{label} needs schema",
                advice="Point schema at a vars_schema name, or at __date__.",
            )
        if reserved_var_name(ref):
            raise VarConfigError(
                f"{label} schema {ref} is reserved",
                advice="Point schema at a vars_schema name, or at __date__.",
            )
        if ref != VAR_DATE and ref not in declared:
            raise VarConfigError(
                f"{label} schema {ref} is not declared",
                advice="Add that name to vars_schema first.",
            )
        base = specs[ref]
        data = base.model_dump(exclude_unset=True)
        data.pop("default", None)
        for field in ("desc", "unit", "mandatory", "validation"):
            if field in written:
                data[field] = written[field]
        if "default" in written:
            data["default"] = written["default"]
        spec = VarSpec.load(
            data,
            label=label,
            from_schema=True,
            compile_source=compile_source,
        )
        if "default" not in written:
            cls._check_catalog_default(specs.get(key), spec, label)
        return spec

    @staticmethod
    def _check_catalog_default(
        catalog_spec: VarSpec | None,
        effective: VarSpec,
        label: str,
    ) -> None:
        if catalog_spec is None or not catalog_spec.has_default:
            return
        for item in catalog_spec.candidates:
            if isinstance(item, str) and is_template(item):
                continue
            try:
                cast_value(effective, item, allow_typed=True)
            except CastMiss as exc:
                raise VarConfigError(
                    f"{label} cannot be cast",
                    advice=str(exc),
                ) from exc


class VarCatalog:
    """Built-in entries, then the profile vars_schema, then implicit names."""

    def __init__(
        self,
        specs: dict[str, VarSpec],
        *,
        declared: tuple[str, ...],
        kinds: KindCatalog,
        vars_present: bool,
    ) -> None:
        self._specs = specs
        self._declared = declared
        self._kinds = kinds
        self.vars_schema_present = vars_present
        self.kind_schema_present = kinds.present

    def __contains__(self, name: str) -> bool:
        return name in self._specs

    def names(self) -> tuple[str, ...]:
        """Catalog names in insertion order."""
        return tuple(self._specs)

    def spec(self, name: str) -> VarSpec:
        """Return the spec, creating an implicit text spec for a new user name."""
        found = self._specs.get(name)
        if found is not None:
            return found
        self._specs[name] = self._implicit(name, f"variable {name}")
        return self._specs[name]

    def effective(self, kind: str, name: str) -> VarSpec:
        """The kind overlay for this name, or the profile spec."""
        found = self._kinds.var(kind, name)
        if found is not None:
            return found
        return self.spec(name)

    def names_for(self, kind: str) -> tuple[str, ...]:
        """Catalog names, plus kind-local names that are not in the catalog."""
        names = list(self._specs)
        found = self._kinds.get(kind)
        if found is None:
            return tuple(names)
        for name in found.vars:
            if name not in self._specs:
                names.append(name)
        return tuple(names)

    def default_candidates(self, kind: str, name: str) -> tuple[object, ...] | None:
        """Default-layer candidates. A kind default wins for that local name.

        A listed kind takes defaults only for names in its vars_schema.
        """
        found = self._kinds.get(kind)
        if found is not None and name not in found.vars:
            return None
        kind_spec = self._kinds.var(kind, name)
        if kind_spec is not None and kind_spec.has_default:
            return kind_spec.candidates
        catalog_spec = self._specs.get(name)
        if catalog_spec is not None and catalog_spec.has_default:
            return catalog_spec.candidates
        return None

    def domain_specs(self) -> tuple[tuple[str, VarSpec], ...]:
        """Declared user names. Locked internals are left out. __date__ stays when declared."""
        rows: list[tuple[str, VarSpec]] = []
        for name in self._declared:
            if reserved_var_name(name):
                continue
            rows.append((name, self._specs[name]))
        return tuple(rows)

    def csv_headers(self, kind: str) -> tuple[str, ...]:
        """Schema column names for this kind, in profile order.

        A kind_schema entry uses its local names. Otherwise declared
        vars_schema names are used. No schema means no extra columns.
        """
        found = self._kinds.get(kind)
        if found is not None:
            return tuple(found.vars)
        if self.vars_schema_present:
            return tuple(name for name, _spec in self.domain_specs())
        return ()

    def kind_schemas(self) -> tuple[KindSchema, ...]:
        """Parsed kinds, in profile order."""
        return self._kinds.items()

    @classmethod
    def load(
        cls,
        document: Mapping[str, Any],
        *,
        compile_source: Callable[[str], None] | None = None,
        names: Iterable[str] = (),
    ) -> VarCatalog:
        """Build the catalog before the walk, including kind_schema overlays."""
        specs = cls._builtins()
        raw_schema = document.get(KEY_VARS_SCHEMA)
        declared: list[str] = []
        if raw_schema is not None:
            declared = cls._load_schema(specs, raw_schema, compile_source)
        cls._load_default_vars(specs, document.get(KEY_DEFAULT_VARS), compile_source)
        kinds = KindCatalog.load(document, specs, set(declared), compile_source)
        for name in names:
            if name not in specs:
                specs[name] = cls._implicit(name, f"variable {name}")
        return cls(
            specs,
            declared=tuple(declared),
            kinds=kinds,
            vars_present=raw_schema is not None,
        )

    @staticmethod
    def _builtins() -> dict[str, VarSpec]:
        return {VAR_DATE: VarSpec(type=TYPE_DATE, internal=False, mandatory=False)}

    @classmethod
    def _load_schema(
        cls,
        specs: dict[str, VarSpec],
        raw: object,
        compile_source: Callable[[str], None] | None,
    ) -> list[str]:
        if not isinstance(raw, dict):
            raise VarConfigError(
                "vars_schema must be a mapping",
                advice="Map each variable name to a type spec.",
            )
        declared: list[str] = []
        for name, body in raw.items():
            label = f"vars_schema.{name}"
            check_var_name(name, label)
            if not isinstance(body, dict):
                raise VarConfigError(
                    f"{label} must be a mapping",
                    advice="Set type, desc, unit, mandatory, default, or validation.",
                )
            if name == VAR_DATE:
                specs[name] = cls._overlay_builtin(name, specs[name], body, compile_source)
                declared.append(str(name))
                continue
            if str(name).startswith("__"):
                raise VarConfigError(
                    f"{label} is not a supershelf variable",
                    advice="Do not declare names that start with __. Those are reserved.",
                )
            specs[str(name)] = cls._user_spec(str(name), body, compile_source)
            declared.append(str(name))
        return declared

    @staticmethod
    def _overlay_builtin(
        name: str,
        base: VarSpec,
        raw: Mapping[str, Any],
        compile_source: Callable[[str], None] | None,
    ) -> VarSpec:
        label = f"vars_schema.{name}"
        allowed = _DATE_KEYS
        forbidden = _DATE_LOCKED_KEYS
        advice = "On __date__, set desc, unit, mandatory, default, or validation."
        blocked = [key for key in forbidden if key in raw]
        if blocked:
            joined = ", ".join(blocked)
            raise VarConfigError(
                f"{label} cannot set {joined}",
                advice=advice,
            )
        unknown = [str(key) for key in raw if key not in allowed]
        if unknown:
            joined = ", ".join(unknown)
            raise VarConfigError(
                f"{label} has unknown keys: {joined}",
                advice=advice,
            )
        data = base.model_dump(exclude_unset=True)
        for key, value in raw.items():
            data[str(key)] = value
        return VarSpec.load(
            data,
            label=label,
            from_schema=True,
            compile_source=compile_source,
        )

    @staticmethod
    def _user_spec(
        name: str,
        raw: Mapping[str, Any],
        compile_source: Callable[[str], None] | None,
    ) -> VarSpec:
        label = f"vars_schema.{name}"
        if "internal" in raw and raw["internal"] is True:
            raise VarConfigError(
                f"{label} cannot be internal",
                advice="internal is only for variables supershelf fills in.",
            )
        payload = dict(raw)
        if "internal" not in payload:
            payload["internal"] = False
        return VarSpec.load(
            payload,
            label=label,
            from_schema=True,
            compile_source=compile_source,
        )

    @classmethod
    def _load_default_vars(
        cls,
        specs: dict[str, VarSpec],
        raw: object,
        compile_source: Callable[[str], None] | None,
    ) -> None:
        if raw is None:
            return
        if not isinstance(raw, dict):
            raise VarConfigError(
                "default_vars must be a mapping",
                advice="Use a name, then a string or a list of strings.",
            )
        for name, value in raw.items():
            label = f"default_vars.{name}"
            check_var_name(name, label)
            key = str(name)
            if reserved_var_name(key):
                raise VarConfigError(
                    f"default_vars cannot set {key}",
                    advice=_RESERVED_ADVICE,
                )
            spec = specs.get(key)
            if spec is None:
                spec = cls._implicit(key, label)
                specs[key] = spec
            if spec.has_default:
                raise VarConfigError(
                    f"{key} is set in vars_schema.default and default_vars",
                    advice="Remove one of them.",
                )
            specs[key] = spec.with_default(
                value,
                label=label,
                from_schema=False,
                compile_source=compile_source,
            )

    @staticmethod
    def _implicit(name: str, label: str) -> VarSpec:
        check_var_name(name, label)
        if reserved_var_name(name):
            raise VarConfigError(
                f"{label} is not a supershelf variable",
                advice="Do not declare names that start with __. Those are reserved.",
            )
        return VarSpec(type=TYPE_TEXT, mandatory=False, internal=False)


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
    """A namespace root, or any other name that starts with __ except __date__."""
    return name.startswith("__") and name != VAR_DATE


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
