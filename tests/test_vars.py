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
    *,
    mode: str | None = None,
    dry_run: bool = False,
    environ: dict[str, str] | None = None,
) -> VarPlan:
    matcher = Matcher.from_document(document, "work")
    full: dict[str, object] = {"__root_dir__": str(root), "__profile__": "work"}
    if scope:
        full.update(scope)
    return VarPlan.from_document(
        document,
        "work",
        matcher,
        root,
        full,
        mode=mode,
        dry_run=dry_run,
        environ={} if environ is None else environ,
    )


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
        "default_vars": {"__date__": ["{{ missing }}", "2020-01-01"]},
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


def test_filename_stem_does_not_set_the_document_date(tmp_path: Path) -> None:
    plan = _plan(
        {"match_rules": [{"name": "notes", "kind": "note", "filename_glob": "**"}]},
        tmp_path,
        {"__default_date_format__": "%Y-%m-%d"},
    )
    dated = _values(
        plan,
        file=_file("bank2000/phone/2025-07-18.pdf"),
        match=_match("bank2000/phone/2025-07-18.pdf"),
    )
    assert dated["__file_stem__"] == "2025-07-18"
    assert "__date__" not in dated
    assert "__date__" not in _values(plan)


def test_missed_layer_keeps_the_previous_date(tmp_path: Path) -> None:
    plan = _plan(
        {
            "default_vars": {"__date__": "2020-01-01"},
            "match_rules": [
                {
                    "name": "notes",
                    "kind": "note",
                    "filename_glob": "**",
                    "vars": {"__date__": "{{ missing }}"},
                }
            ],
        },
        tmp_path,
        {"__default_date_format__": "%Y%m%d"},
    )
    resolved = plan.resolve(_file("20250718.pdf"), _match("20250718.pdf"), Path("/in"))
    assert dict(resolved.items)["__date__"] == "2020-01-01"
    assert resolved.sources["__date__"] == ("default",)

    unset = _plan(
        {
            "match_rules": [
                {
                    "name": "notes",
                    "kind": "note",
                    "filename_glob": "**",
                    "vars": {"__date__": ["{{ missing }}", "{{ __date__ }}"]},
                }
            ],
        },
        tmp_path,
        {"__default_date_format__": "%Y%m%d"},
    )
    assert "__date__" not in _values(
        unset,
        file=_file("20250718.pdf"),
        match=_match("20250718.pdf"),
    )


def test_missed_candidates_stay_unset_and_bad_literals_are_config_errors(tmp_path: Path) -> None:
    omitted = _plan(
        {
            "default_vars": {"__date__": "{{ missing }}", "owner": "ada"},
            "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "**"}],
        },
        tmp_path,
    )
    values = _values(omitted)
    assert "__date__" not in values
    assert values["owner"] == "ada"

    missed = _plan(
        {
            "default_vars": {"owner": "{{ missing }}"},
            "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "**"}],
        },
        tmp_path,
    )
    assert "owner" not in _values(missed)

    kept = _plan(
        {
            "default_vars": {"owner": "ada"},
            "match_rules": [
                {
                    "name": "notes",
                    "kind": "note",
                    "filename_glob": "**",
                    "vars": {"owner": "{{ missing }}"},
                }
            ],
        },
        tmp_path,
    )
    resolved = kept.resolve(_file(), _match(), Path("/in"))
    assert dict(resolved.items)["owner"] == "ada"
    assert resolved.sources["owner"] == ("default",)

    with pytest.raises(VarConfigError, match="cannot be cast"):
        _plan(
            {
                "default_vars": {"__date__": ["not-a-date", "2020-01-01"]},
                "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "**"}],
            },
            tmp_path,
        )


def test_kind_csv_and_extension(tmp_path: Path) -> None:
    kinds = tmp_path / "kinds"
    kinds.mkdir()
    (kinds / "note.csv").write_text(
        "PATH,owner\narchive.tar.gz,ada\n",
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
    kind_file.write_text("PATH,owner\na.txt,ada\n", encoding="utf-8")
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
    kind_file.write_text("PATH,owner\na.txt,ada\n", encoding="utf-8")
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
    shared.write_text("PATH,owner\na.txt,ada\n", encoding="utf-8")
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


def _kind_document(path: str, **config: object) -> dict[str, object]:
    settings: dict[str, object] = {"kind_overrides_config": [path]}
    settings.update(config)
    return {
        "config": settings,
        "default_vars": {"owner": "DEFAULT"},
        "match_rules": [
            {
                "name": "notes",
                "kind": "note",
                "filename_glob": "**",
                "vars": {"owner": "{{ owner }}-rule"},
            }
        ],
    }


def test_kind_row_is_literal_and_follows_the_rule(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text("PATH,owner,vendor\na.txt,{{ missing }},FromKind\n", encoding="utf-8")
    plan = _plan(
        {
            **_kind_document("{{ __root_dir__ }}/note.csv"),
            "overrides": [{"path": "a.txt", "vars": {"note": "{{ owner }}"}}],
        },
        tmp_path,
    )
    values = _values(plan)
    assert values["owner"] == "{{ missing }}"
    assert values["vendor"] == "FromKind"
    assert values["note"] == "{{ missing }}"


def test_kind_date_cell_is_stored_as_iso(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text("PATH,__date__\na.txt,25/04/2026\nb.txt,\n", encoding="utf-8")
    plan = _plan(
        _kind_document(
            "{{ __root_dir__ }}/note.csv",
            kind_overrides_date_format="%d/%m/%Y",
        ),
        tmp_path,
    )
    dated = _values(plan)
    assert dated["__date__"] == "2026-04-25"
    blank = _values(plan, file=_file("b.txt"), match=_match("b.txt"))
    assert "__date__" not in blank


def test_kind_date_cell_is_not_taken_from_the_stem(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text("PATH,__date__\n2025-07-18.pdf,2024-05-29\n", encoding="utf-8")
    plan = _plan(
        _kind_document("{{ __root_dir__ }}/note.csv"),
        tmp_path,
        {"__default_date_format__": "%Y-%m-%d"},
    )
    values = _values(
        plan,
        file=_file("2025-07-18.pdf"),
        match=_match("2025-07-18.pdf"),
    )
    assert values["__date__"] == "2024-05-29"


def test_bad_kind_date_stops_and_writes_nothing(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text("PATH,__date__\na.txt,yesterday\n", encoding="utf-8")
    original = kind.read_bytes()
    plan = _plan(
        _kind_document(
            "{{ __root_dir__ }}/note.csv",
            kind_overrides_date_format="%d/%m/%Y",
        ),
        tmp_path,
    )
    with pytest.raises(VarResolveError, match="variable __date__ failed"):
        _values(plan)
    plan.commit()
    assert kind.read_bytes() == original


def test_auto_appends_only_when_the_file_exists(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_bytes(b"PATH,owner\na.txt,ada")
    plan = _plan(_kind_document("{{ __root_dir__ }}/note.csv"), tmp_path)
    values = _values(plan, file=_file("b.txt"), match=_match("b.txt"))
    assert values["owner"] == "DEFAULT-rule"
    plan.commit()
    text = kind.read_bytes()
    assert text.startswith(b"PATH,owner\na.txt,ada\n")
    assert text.endswith(b"\nb.txt,\n")

    missing = tmp_path / "other.csv"
    skipped = _plan(_kind_document("{{ __root_dir__ }}/other.csv"), tmp_path)
    _values(skipped)
    skipped.commit()
    assert missing.exists() is False


def test_empty_kind_file_is_filled_in_auto(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text("\n\n", encoding="utf-8")
    plan = _plan(_kind_document("{{ __root_dir__ }}/note.csv"), tmp_path)
    _values(plan)
    plan.commit()
    assert kind.read_text(encoding="utf-8") == "PATH,__date__\na.txt,\n"


def test_manual_reads_and_does_not_append(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text("PATH,owner\n", encoding="utf-8")
    plan = _plan(
        _kind_document("{{ __root_dir__ }}/note.csv", kind_overrides_mode="manual"),
        tmp_path,
    )
    _values(plan)
    plan.commit()
    assert kind.read_text(encoding="utf-8") == "PATH,owner\n"


def test_always_creates_the_first_template(tmp_path: Path) -> None:
    plan = _plan(
        _kind_document("{{ __root_dir__ }}/kinds/{{ __kind__ }}.csv", kind_overrides_mode="always"),
        tmp_path,
    )
    values = _values(plan)
    assert values["owner"] == "DEFAULT-rule"
    plan.commit()
    created = tmp_path / "kinds" / "note.csv"
    assert created.read_text(encoding="utf-8") == "PATH,__date__\na.txt,\n"
    again = _plan(
        _kind_document("{{ __root_dir__ }}/kinds/{{ __kind__ }}.csv", kind_overrides_mode="always"),
        tmp_path,
    )
    _values(again)
    again.commit()
    assert created.read_text(encoding="utf-8") == "PATH,__date__\na.txt,\n"


def test_disabled_ignores_an_existing_kind_file(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    kind = tmp_path / "note.csv"
    kind.write_text("PATH,owner\na.txt,ada\n", encoding="utf-8")
    plan = _plan(
        _kind_document("{{ __root_dir__ }}/note.csv", kind_overrides_mode="disabled"),
        tmp_path,
    )
    values = _values(plan)
    plan.commit()
    assert values["owner"] == "DEFAULT-rule"
    assert kind.read_text(encoding="utf-8") == "PATH,owner\na.txt,ada\n"
    assert caplog.records == []


def test_flag_wins_over_env_and_config(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    plan = _plan(
        _kind_document("{{ __root_dir__ }}/note.csv", kind_overrides_mode="always"),
        tmp_path,
        mode="manual",
        environ={"SUPERSHELF_KIND_OVERRIDES_MODE": "always"},
    )
    _values(plan)
    plan.commit()
    assert kind.exists() is False


def test_empty_kind_mode_env_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(VarConfigError, match="SUPERSHELF_KIND_OVERRIDES_MODE"):
        _plan(
            {"match_rules": [{"name": "notes", "kind": "note", "filename_glob": "**"}]},
            tmp_path,
            environ={"SUPERSHELF_KIND_OVERRIDES_MODE": ""},
        )


def test_yaml_and_toml_rows_are_literal(tmp_path: Path) -> None:
    (tmp_path / "note.yaml").write_text(
        "- path: a.txt\n  vars:\n    owner: ada\n",
        encoding="utf-8",
    )
    yaml_plan = _plan(_kind_document("{{ __root_dir__ }}/note.yaml"), tmp_path)
    assert _values(yaml_plan)["owner"] == "ada"
    (tmp_path / "note.toml").write_text(
        '[[rows]]\npath = "b.txt"\n\n[rows.vars]\nowner = "bea"\n',
        encoding="utf-8",
    )
    toml_plan = _plan(_kind_document("{{ __root_dir__ }}/note.toml"), tmp_path)
    assert _values(toml_plan, file=_file("b.txt"), match=_match("b.txt"))["owner"] == "bea"


def test_dry_run_logs_and_does_not_write(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    kind = tmp_path / "note.csv"
    kind.write_text("PATH\n", encoding="utf-8")
    plan = _plan(_kind_document("{{ __root_dir__ }}/note.csv"), tmp_path, dry_run=True)
    _values(plan)
    plan.commit()
    assert kind.read_text(encoding="utf-8") == "PATH\n"
    assert f"Would append 1 rows to kind file {kind}" in caplog.text


def test_always_refuses_a_parent_that_is_a_file(tmp_path: Path) -> None:
    blocker = tmp_path / "blocked"
    blocker.write_text("x", encoding="utf-8")
    plan = _plan(
        _kind_document(
            "{{ __root_dir__ }}/blocked/note.csv",
            kind_overrides_mode="always",
        ),
        tmp_path,
    )
    _values(plan)
    with pytest.raises(VarConfigError, match="parent is not a directory"):
        plan.commit()


def test_duplicate_kind_path_keeps_the_first_row(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)
    kind = tmp_path / "note.csv"
    kind.write_text("PATH,owner\na.txt,ada\na.txt,bea\n", encoding="utf-8")
    plan = _plan(
        _kind_document("{{ __root_dir__ }}/note.csv", kind_overrides_mode="manual"),
        tmp_path,
    )
    assert _values(plan)["owner"] == "ada"
    assert "duplicated" in caplog.text


def test_semicolon_header_tip_shows_the_expected_columns(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text(
        "path;amount\nbank2000/phone/2025-07-18.pdf;427,59\n",
        encoding="utf-8",
    )
    plan = _plan(
        _kind_document("{{ __root_dir__ }}/note.csv", kind_overrides_sep=";"),
        tmp_path,
    )
    with pytest.raises(VarConfigError, match="first column is 'path'") as caught:
        _values(plan)
    assert caught.value.advice is not None
    assert "kind_overrides_sep is ';'" in caught.value.advice
    assert "For example: PATH;amount" in caught.value.advice


def test_semicolon_kind_row_keeps_a_comma_in_the_cell(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text(
        "PATH;amount\nbank2000/phone/2025-07-18.pdf;427,59\n",
        encoding="utf-8",
    )
    plan = _plan(
        _kind_document("{{ __root_dir__ }}/note.csv", kind_overrides_sep=";"),
        tmp_path,
    )
    values = _values(
        plan,
        file=_file("bank2000/phone/2025-07-18.pdf"),
        match=_match("bank2000/phone/2025-07-18.pdf"),
    )
    assert values["amount"] == "427,59"


def test_kind_overrides_sep_rejects_a_slash(tmp_path: Path) -> None:
    with pytest.raises(VarConfigError, match="kind_overrides_sep '/'") as caught:
        _plan(
            _kind_document("{{ __root_dir__ }}/note.csv", kind_overrides_sep="/"),
            tmp_path,
        )
    assert caught.value.advice is not None
    assert "For example: ','" in caught.value.advice


def test_sources_keep_every_layer(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text("PATH,vendor\na.txt,KindCo\n", encoding="utf-8")
    plan = _plan(
        {
            "config": {"kind_overrides_config": ["{{ __root_dir__ }}/note.csv"]},
            "default_vars": {"vendor": "UNKNOWN"},
            "match_rules": [
                {
                    "name": "notes",
                    "kind": "note",
                    "filename_glob": "a.txt",
                    "vars": {"vendor": "Bank2000"},
                }
            ],
            "overrides": [{"path": "a.txt", "vars": {"vendor": "Final"}}],
        },
        tmp_path,
    )
    resolved = plan.resolve(_file(), _match(), Path("/in"))

    assert dict(resolved.items)["vendor"] == "Final"
    assert resolved.sources["vendor"] == (
        "default",
        "rule:notes",
        f"kind:{kind}",
        "override:a.txt",
    )
    assert resolved.sources["__kind__"] == ("fact",)
    text = str(resolved.present(None))
    lines = text.splitlines()
    source_lines = resolved.present_sources().splitlines()
    assert [line.split(":", 1)[0] for line in lines] == sorted(
        line.split(":", 1)[0] for line in lines
    )
    assert len(lines) == len(source_lines)
    vendor_at = lines.index("vendor: Final")
    assert source_lines[vendor_at] == ", ".join(resolved.sources["vendor"])
    assert "sources:" not in text
    assert resolved.present("json")["vendor"]["value"] == "Final"


def test_regex_group_cast_is_not_repaired_by_a_later_layer(tmp_path: Path) -> None:
    plan = _plan(
        {
            "vars_schema": {"amount": {"type": "float"}},
            "match_rules": [
                {
                    "name": "notes",
                    "kind": "note",
                    "filename_regex": r"(?P<amount>[^.]+)\.txt",
                }
            ],
        },
        tmp_path,
    )
    resolved = plan.resolve(
        _file("12.50.txt"),
        _match("12.50.txt", groups={"amount": "12.50"}),
        Path("/in"),
    )

    assert dict(resolved.items)["amount"] == "12.50"
    assert resolved.dump_vars()["amount"]["value"] == 12.5
    assert resolved.sources["amount"] == ("fact",)

    broken = _plan(
        {
            "vars_schema": {"amount": {"type": "float"}},
            "match_rules": [
                {
                    "name": "notes",
                    "kind": "note",
                    "filename_regex": r"(?P<amount>[^.]+)\.txt",
                    "vars": {"amount": "1"},
                }
            ],
        },
        tmp_path,
    )
    with pytest.raises(VarResolveError, match="variable amount failed"):
        broken.resolve(
            _file("EUR12.50.txt"),
            _match("EUR12.50.txt", groups={"amount": "EUR12.50"}),
            Path("/in"),
        )


def test_int_group_drops_leading_zeros(tmp_path: Path) -> None:
    plan = _plan(
        {
            "vars_schema": {"amount": {"type": "int"}},
            "match_rules": [
                {
                    "name": "notes",
                    "kind": "note",
                    "filename_regex": r"(?P<amount>\d+)\.txt",
                }
            ],
        },
        tmp_path,
    )
    resolved = plan.resolve(
        _file("0012.txt"),
        _match("0012.txt", groups={"amount": "0012"}),
        Path("/in"),
    )

    assert dict(resolved.items)["amount"] == "12"
    assert resolved.dump_vars()["amount"]["value"] == 12


def test_bool_display_stays_text_in_templates(tmp_path: Path) -> None:
    plan = _plan(
        {
            "vars_schema": {"paid": {"type": "bool"}},
            "default_vars": {"paid": "no"},
            "match_rules": [
                {
                    "name": "notes",
                    "kind": "note",
                    "filename_glob": "a.txt",
                    "vars": {"flag": "{% if paid %}yes{% else %}no{% endif %}"},
                }
            ],
        },
        tmp_path,
    )
    resolved = plan.resolve(_file(), _match(), Path("/in"))
    values = dict(resolved.items)

    assert values["paid"] == "false"
    assert values["flag"] == "yes"
    assert resolved.dump_vars()["paid"]["value"] is False


def test_mandatory_none_stops_and_omitted_time_does_not(tmp_path: Path) -> None:
    plan = _plan(
        {
            "vars_schema": {
                "amount": {"type": "int", "mandatory": True},
                "opens": {"type": "time"},
                "__date__": {"mandatory": True},
            },
            "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "**"}],
        },
        tmp_path,
    )
    with pytest.raises(VarResolveError, match="variable __date__ failed") as caught:
        _values(plan)
    assert caught.value.advice == "__date__ is mandatory and no layer set it."

    dated = _plan(
        {
            "vars_schema": {
                "amount": {"type": "int", "mandatory": True},
                "opens": {"type": "time"},
            },
            "default_vars": {"amount": "12"},
            "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "**"}],
        },
        tmp_path,
    )
    values = _values(dated)
    assert values["amount"] == "12"
    assert "opens" not in values


def test_kind_schema_mandatory_applies_only_to_that_kind(tmp_path: Path) -> None:
    plan = _plan(
        {
            "vars_schema": {
                "amount": {"type": "int", "mandatory": True},
                "company_name": {"type": "text", "default": "Bank2000"},
            },
            "kind_schema": {
                "note": {
                    "vars_schema": {"amount": {"schema": "amount", "mandatory": False}}
                },
                "invoice": {
                    "desc": "A vendor bill",
                    "vars_schema": {
                        "amount": {"schema": "amount", "mandatory": False},
                        "company": {"schema": "company_name", "mandatory": True},
                    },
                },
            },
            "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "**"}],
        },
        tmp_path,
    )

    note = _values(plan)
    assert "amount" not in note
    assert note["company_name"] == "Bank2000"
    assert "company" not in note

    with pytest.raises(VarResolveError, match="variable amount failed"):
        _values(plan, match=_match(kind="other"))
    with pytest.raises(VarResolveError, match="variable company failed"):
        _values(plan, match=_match(kind="invoice", rule="bills"))


def test_kind_default_replaces_the_profile_default_for_that_kind(tmp_path: Path) -> None:
    plan = _plan(
        {
            "vars_schema": {"amount": {"type": "int", "default": 12}},
            "kind_schema": {
                "invoice": {
                    "vars_schema": {"amount": {"schema": "amount", "default": 15}}
                }
            },
            "match_rules": [{"name": "bills", "kind": "invoice", "filename_glob": "**"}],
        },
        tmp_path,
    )

    invoice = _values(plan, match=_match(kind="invoice", rule="bills"))
    other = _values(plan, match=_match(kind="note"))

    assert invoice["amount"] == "15"
    assert other["amount"] == "12"


def test_kind_validation_rejects_a_rule_literal_at_load(tmp_path: Path) -> None:
    with pytest.raises(VarConfigError, match="cannot be cast"):
        _plan(
            {
                "vars_schema": {"amount": {"type": "int"}},
                "kind_schema": {
                    "note": {
                        "vars_schema": {
                            "amount": {"schema": "amount", "validation": {"ge": 10}}
                        }
                    }
                },
                "match_rules": [
                    {
                        "name": "notes",
                        "kind": "note",
                        "filename_glob": "**",
                        "vars": {"amount": "5"},
                    }
                ],
            },
            tmp_path,
        )


def test_kind_cell_cast_failure_stops_the_file(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text("PATH,amount\na.txt,EUR12.50\n", encoding="utf-8")
    plan = _plan(
        {
            "config": {"kind_overrides_config": ["{{ __root_dir__ }}/note.csv"]},
            "vars_schema": {"amount": {"type": "float"}},
            "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "a.txt"}],
        },
        tmp_path,
    )
    with pytest.raises(VarResolveError, match="variable amount failed"):
        _values(plan)
