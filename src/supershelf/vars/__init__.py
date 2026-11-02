"""Variable specs, catalogs, and the resolver."""

from typing import Any

__all__ = [
    "CastMiss",
    "CastValue",
    "DateScope",
    "FileVars",
    "KindCatalog",
    "KindSchema",
    "KindSchemaSpec",
    "KindVarRef",
    "ValidationRules",
    "ValidationSpec",
    "VarCatalog",
    "VarPlan",
    "VarSpec",
    "VarState",
    "VarTable",
    "cast_date_display",
    "cast_value",
    "check_assignment_key",
    "check_var_name",
    "layer_source",
    "reserved_var_name",
]

_CATALOG = {
    "KindCatalog",
    "KindSchema",
    "KindSchemaSpec",
    "KindVarRef",
    "VarCatalog",
}
_RESOLVE = {"DateScope", "FileVars", "VarPlan", "VarTable"}
_SPEC = {
    "CastMiss",
    "CastValue",
    "ValidationRules",
    "ValidationSpec",
    "VarSpec",
    "VarState",
    "cast_date_display",
    "cast_value",
    "check_assignment_key",
    "check_var_name",
    "layer_source",
    "reserved_var_name",
}


def __getattr__(name: str) -> Any:
    """Load a submodule only when a name from it is used."""
    if name in _CATALOG:
        from supershelf.vars import catalog as module
    elif name in _RESOLVE:
        from supershelf.vars import resolve as module
    elif name in _SPEC:
        from supershelf.vars import spec as module
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(module, name)
