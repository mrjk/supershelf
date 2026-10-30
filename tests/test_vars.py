"""Variable layers for one matched file."""

import logging
from pathlib import Path

import pytest

from supershelf.constants import LOGGER_NAME
from supershelf.errors import VarConfigError, VarResolveError
from supershelf.match import FileMatch, Matcher
from supershelf.scan import InputFile
from supershelf.vars import VarPlan


def _file(relative: str = "a.txt") -> InputFile:
    item = InputFile.from_relative(relative, Path("/tmp") / relative)
    item.mtime = "2026-01-01T00:00:00+00:00"
    item.ctime = "2026-01-02T00:00:00+00:00"
    item.sha256 = "abc"
    return item


def _match(
    path: str = "a.txt",
    kind: str = "note",
    rule: str = "notes",
    groups: dict[str, str] | None = None,
) -> FileMatch:
    return FileMatch("work", 1, path, kind, rule, groups or {})


def _plan(
    document: dict[str, object],
    root: Path,
    scope: dict[str, object] | None = None,
) -> VarPlan:
    matcher = Matcher.from_document(document, "work")
    full: dict[str, object] = {"__root_dir__": str(root), "__profile__": "work"}
    if scope:
        full.update(scope)
    return VarPlan.from_document(document, "work", matcher, root, full)


def _values(plan: VarPlan, **kwargs: object) -> dict[str, str]:
    file = kwargs.get("file", _file())
    match = kwargs.get("match", _match())
    assert isinstance(file, InputFile)
    assert isinstance(match, FileMatch)
    resolved = plan.resolve(file, match, Path("/in"))
    return dict(resolved.items)


def test_later_layer_replaces_and_keeps_first_position(tmp_path: Path) -> None:
    plan = _plan(
        {
            "default_vars": {"vendor": "UNKNOWN", "owner": "DEFAULT"},
            "match_rules": [
                {
                    "name": "notes",
                    "kind": "note",
                    "filename_glob": "a.txt",
                    "vars": {"vendor": "Bank2000", "extra": "yes"},
                }
            ],
        },
        tmp_path,
    )
    values = _values(plan)
    assert values["vendor"] == "Bank2000"
    assert values["owner"] == "DEFAULT"
    names = list(values)
    assert names.index("vendor") < names.index("extra")
    assert "__root_dir__" not in values


def test_list_keeps_the_first_success(tmp_path: Path) -> None:
    plan = _plan(
        {
            "default_vars": {"owner": ["{{ missing }}", "ada"]},
            "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "a.txt"}],
        },
        tmp_path,
    )
    assert _values(plan)["owner"] == "ada"


def test_self_reference_reads_the_previous_string(tmp_path: Path) -> None:
    document = {
        "default_vars": {"__date__": ["not-a-date", "2020-01-01"]},
        "match_rules": [
            {
                "name": "notes",
                "kind": "note",
                "filename_regex": r"(?P<date>\d+)\.txt",
                "vars": {
                    "__date__": [
                        '{{ regex_time_var(date, "%Y%m%d") }}',
                        "{{ __date__ }}",
                    ]
                },
            }
        ],
    }
    plan = _plan(document, tmp_path)
    kept = _values(plan, file=_file("nope.txt"), match=_match("nope.txt", groups={"date": "nope"}))
    assert kept["__date__"] == "2020-01-01"
    parsed = _values(
        plan,
        file=_file("20211231.txt"),
        match=_match("20211231.txt", groups={"date": "20211231"}),
    )
    assert parsed["__date__"] == "2021-12-31"


def test_internal_names_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(VarConfigError, match="cannot set __ctime__"):
        _plan(
            {
                "default_vars": {"__ctime__": "x"},
                "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "**"}],
            },
            tmp_path,
        )


def test_reserved_group_name_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(VarConfigError, match="reserved"):
        _plan(
            {
                "match_rules": [
                    {"name": "notes", "kind": "note", "regex": r"(?P<__kind__>.*)"}
                ]
            },
            tmp_path,
        )


def test_missing_date_is_omitted_and_other_failures_abort(tmp_path: Path) -> None:
    omitted = _plan(
        {
            "default_vars": {"__date__": "not-a-date", "owner": "ada"},
            "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "**"}],
        },
        tmp_path,
    )
    values = _values(omitted)
    assert "__date__" not in values
    assert values["owner"] == "ada"

    broken = _plan(
        {
            "default_vars": {"owner": "{{ missing }}"},
            "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "**"}],
        },
        tmp_path,
    )
    with pytest.raises(VarResolveError, match="variable owner failed"):
        _values(broken)


def test_kind_csv_and_extension(tmp_path: Path) -> None:
    kinds = tmp_path / "kinds"
    kinds.mkdir()
    (kinds / "note.csv").write_text(
        "name,value\nowner,{{ missing }}\nowner,ada\n",
        encoding="utf-8",
    )
    plan = _plan(
        {
            "config": {
                "kind_overrides_config": ["{{ __root_dir__ }}/kinds/{{ __kind__ }}.csv"]
            },
            "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "**"}],
        },
        tmp_path,
        {"__root_dir__": str(tmp_path)},
    )
    values = _values(plan, file=_file("archive.tar.gz"), match=_match("archive.tar.gz"))
    assert values["owner"] == "ada"
    assert values["__file_ext__"] == "gz"
    assert "__root_dir__" not in values


def test_omitted_kind_overrides_config_logs_the_default_paths(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    plan = _plan(
        {"match_rules": [{"name": "notes", "kind": "note", "filename_glob": "**"}]},
        tmp_path,
    )
    _values(plan)
    _values(plan, file=_file("b.txt"), match=_match("b.txt"))
    messages = [record.message for record in caplog.records if record.levelno == logging.DEBUG]
    assert messages == [
        f"Kind file {(tmp_path / name).resolve()} is missing for kind note"
        for name in (
            "profile.work.note.csv",
            "profile.work.note.toml",
            "profile.work.note.yaml",
            "profile.work.note.yml",
        )
    ]


def test_empty_kind_overrides_config_logs_that_there_are_no_candidates(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    plan = _plan(
        {
            "config": {"kind_overrides_config": []},
            "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "**"}],
        },
        tmp_path,
    )
    _values(plan)
    messages = [record.message for record in caplog.records if record.levelno == logging.DEBUG]
    assert messages == ["No kind_overrides_config for kind note"]


def test_kind_file_load_is_logged_once(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    kinds = tmp_path / "kinds"
    kinds.mkdir()
    kind_file = kinds / "note.csv"
    kind_file.write_text("name,value\nowner,ada\n", encoding="utf-8")
    plan = _plan(
        {
            "config": {
                "kind_overrides_config": ["{{ __root_dir__ }}/kinds/{{ __kind__ }}.csv"]
            },
            "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "**"}],
        },
        tmp_path,
        {"__root_dir__": str(tmp_path)},
    )
    _values(plan)
    _values(plan, file=_file("b.txt"), match=_match("b.txt"))
    loads = [record for record in caplog.records if record.levelno == logging.DEBUG]
    assert len(loads) == 1
    assert loads[0].message == f"Loaded kind file {kind_file.resolve()} for kind note"


def test_kind_file_search_logs_each_candidate_once(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    kinds = tmp_path / "kinds"
    kinds.mkdir()
    kind_file = kinds / "note.csv"
    kind_file.write_text("name,value\nowner,ada\n", encoding="utf-8")
    missing = kinds / "note.toml"
    plan = _plan(
        {
            "config": {
                "kind_overrides_config": [
                    "{{ __root_dir__ }}/kinds/{{ __kind__ }}.toml",
                    "{{ __root_dir__ }}/kinds/{{ __kind__ }}.csv",
                ]
            },
            "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "**"}],
        },
        tmp_path,
        {"__root_dir__": str(tmp_path)},
    )
    _values(plan)
    _values(plan, file=_file("b.txt"), match=_match("b.txt"))
    messages = [record.message for record in caplog.records if record.levelno == logging.DEBUG]
    assert messages == [
        f"Kind file {missing.resolve()} is missing for kind note",
        f"Loaded kind file {kind_file.resolve()} for kind note",
    ]


def test_kind_file_search_logs_a_cached_file_for_the_next_kind(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    shared = tmp_path / "shared.csv"
    shared.write_text("name,value\nowner,ada\n", encoding="utf-8")
    plan = _plan(
        {
            "config": {"kind_overrides_config": ["{{ __root_dir__ }}/shared.csv"]},
            "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "**"}],
        },
        tmp_path,
        {"__root_dir__": str(tmp_path)},
    )
    _values(plan)
    _values(plan, match=_match(kind="invoice", rule="notes"))
    messages = [record.message for record in caplog.records if record.levelno == logging.DEBUG]
    assert messages == [
        f"Loaded kind file {shared.resolve()} for kind note",
        f"Kind file {shared.resolve()} already loaded for kind invoice",
    ]


def test_override_replaces_kind(tmp_path: Path) -> None:
    plan = _plan(
        {
            "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "a.txt"}],
            "overrides": [{"path": "a.txt", "vars": {"__kind__": "custom", "owner": "zoe"}}],
        },
        tmp_path,
    )
    file = _file()
    match = _match()
    resolved = plan.resolve(file, match, tmp_path)
    assert resolved.kind == "custom"
    assert resolved.rule == "notes"
    assert dict(resolved.items)["__kind__"] == "custom"
    assert dict(resolved.items)["owner"] == "zoe"


def test_profile_scope_is_readable_and_not_printed(tmp_path: Path) -> None:
    plan = _plan(
        {
            "default_vars": {"where": "{{ __root_dir__ }}"},
            "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "**"}],
        },
        tmp_path,
        {"__root_dir__": "/data"},
    )
    values = _values(plan)
    assert values["where"] == "/data"
    assert "__root_dir__" not in values


def test_custom_module_and_a_name_clash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "shoutmod.py").write_text(
        'GLOBALS = {"shout": lambda value: value.upper()}\n',
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    plan = _plan(
        {
            "config": {"var_modules": ["shoutmod"]},
            "default_vars": {"owner": "ab", "name": "{{ shout(owner) }}"},
            "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "**"}],
        },
        tmp_path,
    )
    assert _values(plan)["name"] == "AB"

    (tmp_path / "clashmod.py").write_text(
        "GLOBALS = {'file': lambda value: value}\n",
        encoding="utf-8",
    )
    with pytest.raises(VarConfigError, match="already defined"):
        _plan(
            {
                "config": {"var_modules": ["clashmod"]},
                "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "**"}],
            },
            tmp_path,
        )
