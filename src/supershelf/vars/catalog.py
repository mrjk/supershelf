"""Kind overlays and the profile variable catalog."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    model_validator,
)

from supershelf.constants import (
    KEY_DEFAULT_VARS,
    KEY_KIND_SCHEMA,
    KEY_VARS_SCHEMA,
    TYPE_DATE,
    TYPE_TEXT,
    VAR_DATE,
)
from supershelf.errors import VarConfigError
from supershelf.template.environment import is_template
from supershelf.vars.spec import (
    _RESERVED_ADVICE,
    CastMiss,
    ValidationSpec,
    VarSpec,
    cast_value,
    check_var_name,
    reserved_var_name,
)

_DATE_LOCKED_KEYS = frozenset({"type", "internal"})
_DATE_KEYS = frozenset({"desc", "unit", "mandatory", "default", "validation"})


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
