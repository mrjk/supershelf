"""JSON Schema for one profile's declared variables or kinds."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, create_model

from supershelf.constants import (
    TYPE_BOOL,
    TYPE_DATE,
    TYPE_DATETIME,
    TYPE_FLOAT,
    TYPE_INT,
    TYPE_TEXT,
    TYPE_TIME,
)
from supershelf.errors import VarConfigError
from supershelf.var_schema import VarCatalog, VarSpec, cast_value
from supershelf.var_template import is_template

_DRAFT = "https://json-schema.org/draft/2020-12/schema"
_DATE_PATTERN = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
_TIME_PATTERN = r"^[0-9]{2}:[0-9]{2}(?::[0-9]{2})?$"
_DATETIME_PATTERN = (
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(?::[0-9]{2})?$"
)
_JSON_TYPES: dict[str, type] = {
    TYPE_TEXT: str,
    TYPE_INT: int,
    TYPE_FLOAT: float,
    TYPE_BOOL: bool,
    TYPE_DATE: str,
    TYPE_TIME: str,
    TYPE_DATETIME: str,
}
_SPELLING = {
    TYPE_DATE: _DATE_PATTERN,
    TYPE_TIME: _TIME_PATTERN,
    TYPE_DATETIME: _DATETIME_PATTERN,
}
_NUMBER_TYPES = frozenset({TYPE_INT, TYPE_FLOAT})
_LENGTH_TYPES = frozenset({TYPE_TEXT, TYPE_DATE, TYPE_TIME, TYPE_DATETIME})


class _Object(BaseModel):
    """Base for a generated object. Extra keys are rejected."""

    model_config = ConfigDict(extra="forbid")


class DomainSchema:
    """JSON Schema of resolved values for one loaded profile."""

    def __init__(self, catalog: VarCatalog) -> None:
        self._catalog = catalog

    @classmethod
    def load(
        cls,
        document: Mapping[str, Any],
        compile_source: Callable[[str], None] | None = None,
    ) -> DomainSchema:
        """Load the catalog and require vars_schema or kind_schema."""
        catalog = VarCatalog.load(document, compile_source=compile_source)
        if not catalog.vars_schema_present and not catalog.kind_schema_present:
            raise VarConfigError(
                "vars_schema or kind_schema is required",
                advice="Declare vars_schema, kind_schema, or both.",
            )
        return cls(catalog)

    def document(self) -> dict[str, Any]:
        """One JSON Schema document. Kinds live under ``$defs`` when declared."""
        if self._catalog.kind_schema_present:
            return {
                "$schema": _DRAFT,
                "$defs": {
                    kind.name: self._object(kind.name, kind.desc, kind.vars.items(), kind.name)
                    for kind in self._catalog.kind_schemas()
                },
            }
        body = self._object("vars", "", self._catalog.domain_specs(), "")
        body["$schema"] = _DRAFT
        return body

    def _object(
        self,
        title: str,
        description: str,
        fields: Iterable[tuple[str, VarSpec]],
        kind: str,
    ) -> dict[str, Any]:
        ordered = list(fields)
        definitions: dict[str, Any] = {}
        defaults: dict[str, object] = {}
        used: set[str] = set()
        for name, spec in ordered:
            python_name = self._python_name(name, used)
            used.add(python_name)
            definitions[python_name] = self._field(
                spec,
                alias=name if python_name != name else None,
            )
            value = self._default(kind, name, spec)
            if value is not None:
                defaults[name] = value
        model = create_model(self._model_name(title), __base__=_Object, **definitions)
        schema = self._clean(model.model_json_schema(), ordered, defaults)
        if description:
            schema["description"] = description
        return schema

    def _default(self, kind: str, name: str, spec: VarSpec) -> object | None:
        candidates = self._catalog.default_candidates(kind, name)
        if not candidates or len(candidates) != 1:
            return None
        item = candidates[0]
        if isinstance(item, str) and is_template(item):
            return None
        return cast_value(spec, item, allow_typed=True).value

    def _field(self, spec: VarSpec, alias: str | None) -> Any:
        kwargs: dict[str, Any] = {}
        extra: dict[str, Any] = {}
        if alias is not None:
            kwargs["alias"] = alias
        if spec.desc:
            kwargs["description"] = spec.desc
        if spec.unit:
            extra["x-unit"] = spec.unit
        rules = spec.rules
        patterns = self._patterns(spec)
        if len(patterns) == 1:
            kwargs["pattern"] = patterns[0]
        elif patterns:
            extra["allOf"] = [{"pattern": item} for item in patterns]
        if rules is not None and rules.allowed_json is not None:
            extra["enum"] = list(rules.allowed_json)
        if rules is not None and spec.type in _NUMBER_TYPES:
            if rules.ge is not None:
                kwargs["ge"] = rules.ge.comparable
            if rules.gt is not None:
                kwargs["gt"] = rules.gt.comparable
            if rules.le is not None:
                kwargs["le"] = rules.le.comparable
            if rules.lt is not None:
                kwargs["lt"] = rules.lt.comparable
        if rules is not None and spec.type == TYPE_DATE:
            self._date_bounds(extra, rules)
        if rules is not None and spec.type in {TYPE_TIME, TYPE_DATETIME}:
            shelf = self._shelf_bounds(rules)
            if shelf:
                extra["x-supershelf"] = shelf
        if rules is not None and spec.type in _LENGTH_TYPES:
            if rules.min_length is not None:
                kwargs["min_length"] = rules.min_length
            if rules.max_length is not None:
                kwargs["max_length"] = rules.max_length
        if extra:
            kwargs["json_schema_extra"] = extra
        annotation = _JSON_TYPES[spec.type]
        if spec.mandatory:
            return (annotation, Field(**kwargs))
        return (annotation | None, Field(default=None, **kwargs))

    def _patterns(self, spec: VarSpec) -> list[str]:
        patterns: list[str] = []
        spelling = _SPELLING.get(spec.type)
        if spelling is not None:
            patterns.append(spelling)
        rules = spec.rules
        if (
            rules is not None
            and rules.pattern_text
            and spec.type in _LENGTH_TYPES
            and rules.pattern_text not in patterns
        ):
            patterns.append(rules.pattern_text)
        return patterns

    @staticmethod
    def _date_bounds(extra: dict[str, Any], rules: Any) -> None:
        mapping = (
            ("minimum", rules.ge),
            ("exclusiveMinimum", rules.gt),
            ("maximum", rules.le),
            ("exclusiveMaximum", rules.lt),
        )
        for keyword, limit in mapping:
            if limit is not None:
                extra[keyword] = limit.text

    @staticmethod
    def _shelf_bounds(rules: Any) -> dict[str, str]:
        shelf: dict[str, str] = {}
        for key, limit in (
            ("ge", rules.ge),
            ("gt", rules.gt),
            ("le", rules.le),
            ("lt", rules.lt),
        ):
            if limit is not None:
                shelf[key] = limit.text
        return shelf

    def _clean(
        self,
        schema: dict[str, Any],
        fields: list[tuple[str, VarSpec]],
        defaults: dict[str, object],
    ) -> dict[str, Any]:
        schema.pop("title", None)
        properties = schema.get("properties", {})
        for name, _spec in fields:
            prop = properties.get(name)
            if not isinstance(prop, dict):
                continue
            self._collapse_null(prop)
            prop.pop("title", None)
            if name in defaults:
                prop["default"] = defaults[name]
            elif prop.get("default") is None:
                prop.pop("default", None)
        required = [name for name, spec in fields if spec.mandatory]
        if required:
            schema["required"] = required
        else:
            schema.pop("required", None)
        schema["additionalProperties"] = False
        schema["type"] = "object"
        return schema

    @staticmethod
    def _collapse_null(prop: dict[str, Any]) -> None:
        options = prop.get("anyOf")
        if not isinstance(options, list):
            return
        kept = [
            item
            for item in options
            if isinstance(item, dict) and item.get("type") != "null"
        ]
        if len(kept) != 1 or len(options) != len(kept) + 1:
            return
        prop.pop("anyOf")
        if prop.get("default") is None:
            prop.pop("default", None)
        for key, value in kept[0].items():
            prop.setdefault(key, value)

    @staticmethod
    def _python_name(name: str, used: set[str]) -> str:
        if name.isidentifier() and not name.startswith("_") and name not in used:
            return name
        stem = "field_" + "".join(ch if ch.isalnum() else "_" for ch in name).strip("_")
        if not stem or stem[0].isdigit():
            stem = f"field_{stem}"
        candidate = stem
        index = 2
        while candidate in used:
            candidate = f"{stem}_{index}"
            index += 1
        return candidate

    @staticmethod
    def _model_name(title: str) -> str:
        cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in title)
        if not cleaned or cleaned[0].isdigit():
            return f"Kind_{cleaned}"
        return cleaned
