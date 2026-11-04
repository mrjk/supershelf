"""Variable layers for one matched file."""

import logging
from pathlib import Path

import pytest

from supershelf.cli import present_sources, present_vars
from supershelf.constants import LOGGER_NAME
from supershelf.errors import VarConfigError, VarResolveError
from supershelf.scan.match import FileMatch
from supershelf.scan import InputFile
from supershelf.vars import VarPlan
from tests.metadata_helpers import FILE_DIGEST, input_file as _file
from tests.metadata_helpers import resolve_values, var_plan


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
    return var_plan(
        document,
        root,
        scope=scope,
        mode=mode,
        dry_run=dry_run,
        environ={} if environ is None else environ,
    )


def _values(plan: VarPlan, **kwargs: object) -> dict[str, str]:
    file = kwargs.get("file", _file())
    match = kwargs.get("match", _match())
    assert isinstance(file, InputFile)
    assert isinstance(match, FileMatch)
    return resolve_values(plan, file, match)


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
    assert "__config__.root_dir" not in values


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
        "vars_schema": {"issued": {"type": "date"}},
        "default_vars": {"issued": ["{{ missing }}", "2020-01-01"]},
        "match_rules": [
            {
                "name": "notes",
                "kind": "note",
                "filename_regex": r"(?P<date>\d+)\.txt",
                "vars": {
                    "issued": [
                        '{{ __extract__.date | parse_date("%Y%m%d") }}',
                        "{{ issued }}",
                    ]
                },
            }
        ],
    }
    plan = _plan(document, tmp_path)
    kept = _values(plan, file=_file("nope.txt"), match=_match("nope.txt", groups={"date": "nope"}))
    assert kept["issued"] == "2020-01-01"
    parsed = _values(
        plan,
        file=_file("20211231.txt"),
        match=_match("20211231.txt", groups={"date": "20211231"}),
    )
    assert parsed["issued"] == "2021-12-31"


def test_parse_date_display_is_stored_as_iso_for_a_date(tmp_path: Path) -> None:
    plan = _plan(
        {
            "vars_schema": {"issued": {"type": "date"}},
            "default_vars": {
                "shown": '{{ "20211231" | parse_date("%Y%m%d") }}',
                "issued": '{{ "20211231" | parse_date("%Y%m%d") }}',
            },
            "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "**"}],
        },
        tmp_path,
        {"__config__": {"date_format": "%d/%m/%Y"}},
    )
    values = _values(plan)
    assert values["shown"] == "31/12/2021"
    assert values["issued"] == "2021-12-31"


def test_builtin_date_name_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(VarConfigError, match="not a supershelf variable"):
        _plan(
            {
                "vars_schema": {"__date__": {"type": "date"}},
                "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "**"}],
            },
            tmp_path,
        )


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


def test_filename_stem_does_not_set_a_date(tmp_path: Path) -> None:
    plan = _plan(
        {
            "vars_schema": {"issued": {"type": "date"}},
            "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "**"}],
        },
        tmp_path,
    )
    file = _file("bank2000/phone/2025-07-18.pdf")
    resolved = plan.resolve(
        file,
        _match("bank2000/phone/2025-07-18.pdf"),
        Path("/in"),
    )
    assert resolved.facts["__file__.stem"] == "2025-07-18"
    assert "issued" not in dict(resolved.items)
    assert "issued" not in _values(plan)


def test_missed_layer_keeps_the_previous_date(tmp_path: Path) -> None:
    plan = _plan(
        {
            "vars_schema": {"issued": {"type": "date"}},
            "default_vars": {"issued": "2020-01-01"},
            "match_rules": [
                {
                    "name": "notes",
                    "kind": "note",
                    "filename_glob": "**",
                    "vars": {"issued": "{{ missing }}"},
                }
            ],
        },
        tmp_path,
        {"__config__.date_format": "%Y%m%d"},
    )
    resolved = plan.resolve(_file("20250718.pdf"), _match("20250718.pdf"), Path("/in"))
    assert dict(resolved.items)["issued"] == "2020-01-01"
    assert resolved.sources["issued"] == ("default",)

    unset = _plan(
        {
            "vars_schema": {"issued": {"type": "date"}},
            "match_rules": [
                {
                    "name": "notes",
                    "kind": "note",
                    "filename_glob": "**",
                    "vars": {"issued": ["{{ missing }}", "{{ issued }}"]},
                }
            ],
        },
        tmp_path,
        {"__config__.date_format": "%Y%m%d"},
    )
    assert "issued" not in _values(
        unset,
        file=_file("20250718.pdf"),
        match=_match("20250718.pdf"),
    )


def test_missed_candidates_stay_unset_and_bad_literals_are_config_errors(tmp_path: Path) -> None:
    omitted = _plan(
        {
            "vars_schema": {"issued": {"type": "date"}},
            "default_vars": {"issued": "{{ missing }}", "owner": "ada"},
            "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "**"}],
        },
        tmp_path,
    )
    values = _values(omitted)
    assert "issued" not in values
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
                "vars_schema": {"issued": {"type": "date"}},
                "default_vars": {"issued": ["not-a-date", "2020-01-01"]},
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
                "kind_overrides_config": ["{{ __config__.root_dir }}/kinds/{{ __match__.kind }}.csv"]
            },
            "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "**"}],
        },
        tmp_path,
        {"__config__.root_dir": str(tmp_path)},
    )
    resolved = plan.resolve(_file("archive.tar.gz"), _match("archive.tar.gz"), Path("/in"))
    values = dict(resolved.items)
    assert values["owner"] == "ada"
    assert resolved.facts["__file__.ext"] == "gz"
    assert "__config__.root_dir" not in values


def test_kind_path_cannot_read_the_rule_or_the_file(tmp_path: Path) -> None:
    rules = [{"name": "notes", "kind": "note", "filename_glob": "**"}]
    with pytest.raises(VarConfigError, match="Unknown template key"):
        _plan(
            {
                "config": {
                    "kind_overrides_config": [
                        "{{ __config__.root_dir }}/{{ __match__.rule }}.csv"
                    ]
                },
                "match_rules": rules,
            },
            tmp_path,
        ).resolve(_file(), _match(), Path("/in"))
    with pytest.raises(VarConfigError, match="Unknown template name '__file__'"):
        _plan(
            {
                "config": {
                    "kind_overrides_config": [
                        "{{ __config__.root_dir }}/{{ __file__.name }}.csv"
                    ]
                },
                "match_rules": rules,
            },
            tmp_path,
        ).resolve(_file(), _match(), Path("/in"))


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
        for name in ("profile.work.note.csv",)
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
                "kind_overrides_config": ["{{ __config__.root_dir }}/kinds/{{ __match__.kind }}.csv"]
            },
            "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "**"}],
        },
        tmp_path,
        {"__config__.root_dir": str(tmp_path)},
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
    missing = kinds / "missing.csv"
    plan = _plan(
        {
            "config": {
                "kind_overrides_config": [
                    "{{ __config__.root_dir }}/kinds/missing.csv",
                    "{{ __config__.root_dir }}/kinds/{{ __match__.kind }}.csv",
                ]
            },
            "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "**"}],
        },
        tmp_path,
        {"__config__.root_dir": str(tmp_path)},
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
            "config": {"kind_overrides_config": ["{{ __config__.root_dir }}/shared.csv"]},
            "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "**"}],
        },
        tmp_path,
        {"__config__.root_dir": str(tmp_path)},
    )
    _values(plan)
    _values(plan, match=_match(kind="invoice", rule="notes"))
    messages = [record.message for record in caplog.records if record.levelno == logging.DEBUG]
    assert messages == [
        f"Loaded kind file {shared.resolve()} for kind note",
        f"Kind file {shared.resolve()} already loaded for kind invoice",
    ]


@pytest.mark.parametrize(
    "overrides",
    [
        [{"path": "a.txt", "vars": {"owner": "zoe"}}],
        [],
        None,
    ],
)
def test_overrides_key_is_rejected(tmp_path: Path, overrides: object) -> None:
    with pytest.raises(VarConfigError, match="overrides is not a profile key") as caught:
        _plan(
            {
                "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "a.txt"}],
                "overrides": overrides,
            },
            tmp_path,
        )
    assert caught.value.advice == "Per-file values belong in the kind file."


def test_profile_scope_is_readable_and_not_printed(tmp_path: Path) -> None:
    plan = _plan(
        {
            "default_vars": {"where": "{{ __config__.root_dir }}"},
            "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "**"}],
        },
        tmp_path,
        {"__config__": {"root_dir": "/data"}},
    )
    values = _values(plan)
    assert values["where"] == "/data"
    assert "__config__.root_dir" not in values


def test_bare_objects_print_their_text_and_the_date_uses_the_profile_format(
    tmp_path: Path,
) -> None:
    plan = _plan(
        {
            "vars_schema": {"issued": {"type": "date"}},
            "default_vars": {
                "issued": "2026-04-25",
                "file": "{{ __file__ }}",
                "shown": "{{ issued }}",
                "month": "{{ issued.strftime('%Y-%m') }}",
                "year": "{{ issued.Y }}",
            },
            "match_rules": [
                {
                    "name": "notes",
                    "kind": "note",
                    "filename_glob": "**",
                    "vars": {"issued": "{{ issued }}"},
                }
            ],
        },
        tmp_path,
        {"__config__": {"date_format": "%d/%m/%Y"}},
    )
    values = _values(plan, file=_file("bills/acme.pdf"), match=_match("bills/acme.pdf"))
    assert values["issued"] == "2026-04-25"
    assert values["file"] == "acme.pdf"
    assert values["shown"] == "25/04/2026"
    assert values["month"] == "2026-04"
    assert values["year"] == "2026"


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
        "GLOBALS = {'meta': lambda value: value}\n",
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
    plan = _plan(_kind_document("{{ __config__.root_dir }}/note.csv"), tmp_path)
    values = _values(plan)
    assert values["owner"] == "{{ missing }}"
    assert values["vendor"] == "FromKind"


def test_feed_column_is_ignored_and_custom_cell_wins(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text("PATH,vendor,VENDOR\na.txt,Mine,Generated\n", encoding="utf-8")
    plan = _plan(
        {
            **_kind_document("{{ __config__.root_dir }}/note.csv"),
            "default_vars": {"owner": "DEFAULT", "vendor": "RuleCo"},
        },
        tmp_path,
    )
    resolved = plan.resolve(_file(), _match(), Path("/in"))
    values = dict(resolved.items)
    assert values["vendor"] == "Mine"
    assert "VENDOR" not in values
    assert resolved.rule_layer["vendor"] == "RuleCo"
    assert "Mine" not in resolved.rule_layer.values()


def test_empty_custom_cell_ignores_the_feed_column(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text("PATH,VENDOR\na.txt,Generated\n", encoding="utf-8")
    plan = _plan(
        {
            **_kind_document("{{ __config__.root_dir }}/note.csv"),
            "default_vars": {"owner": "DEFAULT", "vendor": "RuleCo"},
        },
        tmp_path,
    )
    values = _values(plan)
    assert values["vendor"] == "RuleCo"
    assert "VENDOR" not in values


def test_wrapped_feed_columns_are_ignored(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text(
        "PATH,_PATH_,_SHA_,_DATE_,__DATE__\na.txt,from-feed,abc,2020-01-01,01/02/2026\n",
        encoding="utf-8",
    )
    plan = _plan(
        {
            **_kind_document("{{ __config__.root_dir }}/note.csv"),
            "default_vars": {
                "owner": "DEFAULT",
                "path": "kept",
                "sha": "real",
                "date": "2026-04-25",
            },
        },
        tmp_path,
    )
    values = _values(plan)
    assert values["path"] == "kept"
    assert values["sha"] == "real"
    assert values["date"] == "2026-04-25"
    assert "__date__" not in values


def test_uppercase_date_is_a_feed_column_and_bad_sha_stays_an_error(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text("PATH,DATE\na.txt,2026-04-25\n", encoding="utf-8")
    plan = _plan(_kind_document("{{ __config__.root_dir }}/note.csv"), tmp_path)
    values = _values(plan)
    assert "date" not in values
    assert "DATE" not in values

    kind.write_text("PATH,sha\na.txt,abc\n", encoding="utf-8")
    plan = _plan(_kind_document("{{ __config__.root_dir }}/note.csv"), tmp_path)
    with pytest.raises(VarConfigError, match="Use SHA"):
        _values(plan)

    kind.write_text("PATH,SHA\na.txt,abc\n", encoding="utf-8")
    plan = _plan(_kind_document("{{ __config__.root_dir }}/note.csv"), tmp_path)
    with pytest.raises(VarConfigError, match="64 lowercase hex"):
        _values(plan)


def test_mixed_case_column_stays_an_error(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text("PATH,Vendor\na.txt,Mine\n", encoding="utf-8")
    plan = _plan(_kind_document("{{ __config__.root_dir }}/note.csv"), tmp_path)
    with pytest.raises(VarConfigError, match="must be lowercase"):
        _values(plan)


def test_schema_append_keeps_a_feed_column(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text("PATH,VENDOR\na.txt,Generated\n", encoding="utf-8")
    plan = _plan(
        {
            **_kind_document("{{ __config__.root_dir }}/note.csv"),
            "vars_schema": {"vendor": {"type": "text"}},
            "default_vars": {"owner": "DEFAULT", "vendor": "RuleCo"},
        },
        tmp_path,
    )
    assert _values(plan)["vendor"] == "RuleCo"
    plan.commit()
    assert kind.read_text(encoding="utf-8") == (
        f"PATH,SHA,VENDOR,vendor\na.txt,{FILE_DIGEST},Generated,\n"
    )


def test_kind_date_cell_is_stored_as_iso(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text(
        "PATH,issued,note\na.txt,25/04/2026,25/04/2026\nb.txt,,\n",
        encoding="utf-8",
    )
    document = _kind_document(
        "{{ __config__.root_dir }}/note.csv",
        kind_overrides_date_format="%d/%m/%Y",
    )
    document["vars_schema"] = {"issued": {"type": "date"}}
    plan = _plan(document, tmp_path)
    dated = _values(plan)
    assert dated["issued"] == "2026-04-25"
    assert dated["note"] == "25/04/2026"
    blank = _values(plan, file=_file("b.txt"), match=_match("b.txt"))
    assert "issued" not in blank


def test_kind_date_cell_is_not_taken_from_the_stem(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text("PATH,issued\n2025-07-18.pdf,2024-05-29\n", encoding="utf-8")
    document = _kind_document("{{ __config__.root_dir }}/note.csv")
    document["vars_schema"] = {"issued": {"type": "date"}}
    plan = _plan(
        document,
        tmp_path,
        {"__config__.date_format": "%Y-%m-%d"},
    )
    values = _values(
        plan,
        file=_file("2025-07-18.pdf"),
        match=_match("2025-07-18.pdf"),
    )
    assert values["issued"] == "2024-05-29"


def test_bad_kind_date_stops_and_writes_nothing(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text("PATH,issued\na.txt,yesterday\n", encoding="utf-8")
    original = kind.read_bytes()
    document = _kind_document(
        "{{ __config__.root_dir }}/note.csv",
        kind_overrides_date_format="%d/%m/%Y",
    )
    document["vars_schema"] = {"issued": {"type": "date"}}
    plan = _plan(document, tmp_path)
    with pytest.raises(VarResolveError, match="variable issued failed"):
        _values(plan)
    plan.commit()
    assert kind.read_bytes() == original


def test_auto_appends_only_when_the_file_exists(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_bytes(b"PATH,owner\na.txt,ada")
    plan = _plan(_kind_document("{{ __config__.root_dir }}/note.csv"), tmp_path)
    values = _values(plan, file=_file("b.txt"), match=_match("b.txt"))
    assert values["owner"] == "DEFAULT-rule"
    plan.commit()
    text = kind.read_bytes()
    assert text == (
        b"PATH,SHA,owner\na.txt,,ada\nb.txt," + FILE_DIGEST.encode("ascii") + b",\n"
    )

    missing = tmp_path / "other.csv"
    skipped = _plan(_kind_document("{{ __config__.root_dir }}/other.csv"), tmp_path)
    _values(skipped)
    skipped.commit()
    assert missing.exists() is False


def test_empty_kind_file_is_filled_in_auto(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text("\n\n", encoding="utf-8")
    plan = _plan(_kind_document("{{ __config__.root_dir }}/note.csv"), tmp_path)
    _values(plan)
    plan.commit()
    assert kind.read_text(encoding="utf-8") == f"SHA,PATH\n{FILE_DIGEST},a.txt\n"


def test_manual_reads_and_does_not_append(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text("PATH,owner\n", encoding="utf-8")
    plan = _plan(
        _kind_document("{{ __config__.root_dir }}/note.csv", kind_overrides_mode="manual"),
        tmp_path,
    )
    _values(plan)
    plan.commit()
    assert kind.read_text(encoding="utf-8") == "PATH,owner\n"


def test_always_creates_the_first_template(tmp_path: Path) -> None:
    plan = _plan(
        _kind_document("{{ __config__.root_dir }}/kinds/{{ __match__.kind }}.csv", kind_overrides_mode="always"),
        tmp_path,
    )
    values = _values(plan)
    assert values["owner"] == "DEFAULT-rule"
    plan.commit()
    created = tmp_path / "kinds" / "note.csv"
    assert created.read_text(encoding="utf-8") == f"SHA,PATH\n{FILE_DIGEST},a.txt\n"
    again = _plan(
        _kind_document("{{ __config__.root_dir }}/kinds/{{ __match__.kind }}.csv", kind_overrides_mode="always"),
        tmp_path,
    )
    _values(again)
    again.commit()
    assert created.read_text(encoding="utf-8") == f"SHA,PATH\n{FILE_DIGEST},a.txt\n"


def test_always_creates_vars_schema_columns(tmp_path: Path) -> None:
    plan = _plan(
        {
            **_kind_document(
                "{{ __config__.root_dir }}/kinds/{{ __match__.kind }}.csv",
                kind_overrides_mode="always",
            ),
            "vars_schema": {
                "amount": {"type": "float"},
                "issued": {"type": "date", "desc": "Document date"},
                "vendor": {"type": "text"},
            },
        },
        tmp_path,
    )
    _values(plan)
    plan.commit()
    created = tmp_path / "kinds" / "note.csv"
    assert created.read_text(encoding="utf-8") == (
        f"SHA,PATH,amount,issued,vendor\n{FILE_DIGEST},a.txt,,,\n"
    )


def test_always_creates_kind_schema_local_names(tmp_path: Path) -> None:
    plan = _plan(
        {
            **_kind_document(
                "{{ __config__.root_dir }}/kinds/{{ __match__.kind }}.csv",
                kind_overrides_mode="always",
            ),
            "vars_schema": {
                "company_name": {"type": "text"},
                "employee_name": {"type": "text"},
            },
            "kind_schema": {
                "note": {
                    "vars_schema": {
                        "company": "company_name",
                        "employee": {"schema": "employee_name"},
                    }
                }
            },
        },
        tmp_path,
    )
    _values(plan)
    plan.commit()
    created = tmp_path / "kinds" / "note.csv"
    assert created.read_text(encoding="utf-8") == (
        f"SHA,PATH,company,employee\n{FILE_DIGEST},a.txt,,\n"
    )


def test_always_create_orders_feeds_by_the_schema_dict(tmp_path: Path) -> None:
    plan = _plan(
        {
            **_kind_document(
                "{{ __config__.root_dir }}/kinds/{{ __match__.kind }}.csv",
                kind_overrides_mode="always",
            ),
            "vars_schema": {
                "vendor": {"type": "text"},
                "owner": {"type": "text"},
                "issued": {"type": "date"},
            },
            "kind_schema": {
                "note": {
                    "feeds": ["issued", "vendor"],
                    "vars_schema": {
                        "vendor": "vendor",
                        "owner": "",
                        "issued": "issued",
                    },
                }
            },
        },
        tmp_path,
    )
    _values(plan)
    plan.commit()
    created = tmp_path / "kinds" / "note.csv"
    assert created.read_text(encoding="utf-8") == (
        f"SHA,PATH,VENDOR,ISSUED,vendor,owner,issued\n{FILE_DIGEST},a.txt,,,,,\n"
    )


def test_unlisted_kind_uses_vars_schema_columns(tmp_path: Path) -> None:
    plan = _plan(
        {
            **_kind_document(
                "{{ __config__.root_dir }}/kinds/{{ __match__.kind }}.csv",
                kind_overrides_mode="always",
            ),
            "vars_schema": {
                "amount": {"type": "float"},
                "vendor": {"type": "text"},
            },
            "kind_schema": {"invoice": {"vars_schema": {"amount": "amount"}}},
        },
        tmp_path,
    )
    _values(plan)
    plan.commit()
    created = tmp_path / "kinds" / "note.csv"
    assert created.read_text(encoding="utf-8") == (
        f"SHA,PATH,amount,vendor\n{FILE_DIGEST},a.txt,,\n"
    )


def test_empty_kind_schema_keeps_the_fresh_header(tmp_path: Path) -> None:
    plan = _plan(
        {
            **_kind_document(
                "{{ __config__.root_dir }}/kinds/{{ __match__.kind }}.csv",
                kind_overrides_mode="always",
            ),
            "vars_schema": {"amount": {"type": "float"}},
            "kind_schema": {"note": {"vars_schema": {}}},
        },
        tmp_path,
    )
    _values(plan)
    plan.commit()
    created = tmp_path / "kinds" / "note.csv"
    assert created.read_text(encoding="utf-8") == f"SHA,PATH\n{FILE_DIGEST},a.txt\n"


def test_schema_names_that_are_not_csv_columns_are_skipped(tmp_path: Path) -> None:
    plan = _plan(
        {
            **_kind_document(
                "{{ __config__.root_dir }}/kinds/{{ __match__.kind }}.csv",
                kind_overrides_mode="always",
            ),
            "vars_schema": {
                "Amount": {"type": "text"},
                "vendor": {"type": "text"},
                "date": {"type": "date"},
            },
        },
        tmp_path,
    )
    _values(plan)
    plan.commit()
    created = tmp_path / "kinds" / "note.csv"
    assert created.read_text(encoding="utf-8") == (
        f"SHA,PATH,vendor,date\n{FILE_DIGEST},a.txt,,\n"
    )


def test_blank_kind_file_uses_schema_columns(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text("\n\n", encoding="utf-8")
    plan = _plan(
        {
            **_kind_document("{{ __config__.root_dir }}/note.csv"),
            "vars_schema": {"amount": {"type": "float"}},
        },
        tmp_path,
    )
    _values(plan)
    plan.commit()
    assert kind.read_text(encoding="utf-8") == f"SHA,PATH,amount\n{FILE_DIGEST},a.txt,\n"


def test_missing_schema_columns_are_appended_on_the_right(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text(
        'PATH,amount,notes\na.txt,"12,50",ada\n\nshort.txt\n',
        encoding="utf-8",
    )
    plan = _plan(
        {
            **_kind_document("{{ __config__.root_dir }}/note.csv"),
            "vars_schema": {
                "amount": {"type": "text"},
                "vendor": {"type": "text"},
            },
        },
        tmp_path,
    )
    _values(plan)
    _values(plan, file=_file("b.txt"), match=_match("b.txt"))
    plan.commit()
    assert kind.read_text(encoding="utf-8") == (
        "PATH,SHA,amount,notes,vendor\n"
        f'a.txt,{FILE_DIGEST},"12,50",ada,\n'
        "\n"
        "short.txt,,,,\n"
        f"b.txt,{FILE_DIGEST},,,\n"
    )


def test_added_columns_keep_quoted_cell_text(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_bytes(b'PATH,note\r\na.txt,"hello\nworld"\r\n')
    plan = _plan(
        {
            **_kind_document("{{ __config__.root_dir }}/note.csv"),
            "vars_schema": {"vendor": {"type": "text"}},
        },
        tmp_path,
    )
    _values(plan)
    plan.commit()
    assert kind.read_bytes() == (
        b"PATH,SHA,note,vendor\r\na.txt,"
        + FILE_DIGEST.encode("ascii")
        + b',"hello\nworld",\r\n'
    )


def test_semicolon_schema_columns_use_the_separator(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text("PATH;amount\na.txt;12,50\n", encoding="utf-8")
    plan = _plan(
        {
            **_kind_document("{{ __config__.root_dir }}/note.csv", kind_overrides_sep=";"),
            "vars_schema": {"vendor": {"type": "text"}},
        },
        tmp_path,
    )
    _values(plan, file=_file("b.txt"), match=_match("b.txt"))
    plan.commit()
    assert kind.read_text(encoding="utf-8") == (
        "PATH;SHA;amount;vendor\n"
        "a.txt;;12,50;\n"
        f"b.txt;{FILE_DIGEST};;\n"
    )


def test_manual_does_not_add_schema_columns(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    original = "PATH,amount\na.txt,12\n"
    kind.write_text(original, encoding="utf-8")
    plan = _plan(
        {
            **_kind_document("{{ __config__.root_dir }}/note.csv", kind_overrides_mode="manual"),
            "vars_schema": {"vendor": {"type": "text"}},
        },
        tmp_path,
    )
    _values(plan)
    plan.commit()
    assert kind.read_text(encoding="utf-8") == original


def test_dry_run_does_not_add_schema_columns(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    kind = tmp_path / "note.csv"
    original = "PATH,amount\na.txt,12\n"
    kind.write_text(original, encoding="utf-8")
    plan = _plan(
        {
            **_kind_document("{{ __config__.root_dir }}/note.csv"),
            "vars_schema": {"vendor": {"type": "text"}},
        },
        tmp_path,
        dry_run=True,
    )
    _values(plan)
    _values(plan, file=_file("b.txt"), match=_match("b.txt"))
    plan.commit()
    assert kind.read_text(encoding="utf-8") == original
    assert f"Would add columns vendor to kind file {kind}" in caplog.text
    assert f"Would append 1 rows to kind file {kind}" in caplog.text


def test_disabled_ignores_an_existing_kind_file(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    kind = tmp_path / "note.csv"
    kind.write_text("PATH,owner\na.txt,ada\n", encoding="utf-8")
    plan = _plan(
        _kind_document("{{ __config__.root_dir }}/note.csv", kind_overrides_mode="disabled"),
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
        _kind_document("{{ __config__.root_dir }}/note.csv", kind_overrides_mode="always"),
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


def test_dry_run_logs_and_does_not_write(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    kind = tmp_path / "note.csv"
    kind.write_text("PATH\n", encoding="utf-8")
    plan = _plan(_kind_document("{{ __config__.root_dir }}/note.csv"), tmp_path, dry_run=True)
    _values(plan)
    plan.commit()
    assert kind.read_text(encoding="utf-8") == "PATH\n"
    assert f"Would append 1 rows to kind file {kind}" in caplog.text


def test_always_refuses_a_parent_that_is_a_file(tmp_path: Path) -> None:
    blocker = tmp_path / "blocked"
    blocker.write_text("x", encoding="utf-8")
    plan = _plan(
        _kind_document(
            "{{ __config__.root_dir }}/blocked/note.csv",
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
        _kind_document("{{ __config__.root_dir }}/note.csv", kind_overrides_mode="manual"),
        tmp_path,
    )
    assert _values(plan)["owner"] == "ada"
    assert "duplicated" in caplog.text


def test_sha_path_header_is_read(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text(
        f"SHA,PATH,vendor\n{FILE_DIGEST},a.txt,Mine\n",
        encoding="utf-8",
    )
    plan = _plan(_kind_document("{{ __config__.root_dir }}/note.csv"), tmp_path)
    assert _values(plan)["vendor"] == "Mine"


def test_existing_path_sha_header_is_not_reordered(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text(
        f"PATH,SHA,vendor\na.txt,{FILE_DIGEST},Mine\n",
        encoding="utf-8",
    )
    plan = _plan(
        {
            **_kind_document("{{ __config__.root_dir }}/note.csv"),
            "vars_schema": {
                "vendor": {"type": "text"},
                "amount": {"type": "text"},
            },
        },
        tmp_path,
    )
    assert _values(plan)["vendor"] == "Mine"
    plan.commit()
    assert kind.read_text(encoding="utf-8") == (
        f"PATH,SHA,vendor,amount\na.txt,{FILE_DIGEST},Mine,\n"
    )


def test_semicolon_header_tip_shows_the_expected_columns(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text(
        "path;amount\nbank2000/phone/2025-07-18.pdf;427,59\n",
        encoding="utf-8",
    )
    plan = _plan(
        _kind_document("{{ __config__.root_dir }}/note.csv", kind_overrides_sep=";"),
        tmp_path,
    )
    with pytest.raises(VarConfigError, match="first column is 'path'") as caught:
        _values(plan)
    assert caught.value.advice is not None
    assert "kind_overrides_sep is ';'" in caught.value.advice
    assert "For example: SHA;PATH;amount" in caught.value.advice


def test_semicolon_kind_row_keeps_a_comma_in_the_cell(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text(
        "PATH;amount\nbank2000/phone/2025-07-18.pdf;427,59\n",
        encoding="utf-8",
    )
    plan = _plan(
        _kind_document("{{ __config__.root_dir }}/note.csv", kind_overrides_sep=";"),
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
            _kind_document("{{ __config__.root_dir }}/note.csv", kind_overrides_sep="/"),
            tmp_path,
        )
    assert caught.value.advice is not None
    assert "For example: ','" in caught.value.advice


def test_sources_keep_every_layer(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text("PATH,vendor\na.txt,KindCo\n", encoding="utf-8")
    plan = _plan(
        {
            "config": {"kind_overrides_config": ["{{ __config__.root_dir }}/note.csv"]},
            "default_vars": {"vendor": "UNKNOWN"},
            "match_rules": [
                {
                    "name": "notes",
                    "kind": "note",
                    "filename_glob": "a.txt",
                    "vars": {"vendor": "Bank2000"},
                }
            ],
        },
        tmp_path,
    )
    resolved = plan.resolve(_file(), _match(), Path("/in"))

    assert dict(resolved.items)["vendor"] == "KindCo"
    assert resolved.sources["vendor"] == (
        "default",
        "rule:notes",
        f"kind:{kind}",
    )
    assert resolved.source_labels("__match__.kind") == ("fact",)
    text = str(present_vars(resolved, None))
    assert "__match__.kind:" not in text
    shown = str(present_vars(resolved, None, show_all=True))
    assert "__match__.kind:" in shown
    assert "file_ctime:" not in shown
    lines = text.splitlines()
    source_lines = present_sources(resolved).splitlines()
    assert [line.split(":", 1)[0] for line in lines] == sorted(
        line.split(":", 1)[0] for line in lines
    )
    assert len(lines) == len(source_lines)
    vendor_at = lines.index("vendor: KindCo")
    assert source_lines[vendor_at] == ", ".join(resolved.sources["vendor"])
    assert "sources:" not in text
    assert "__match__.kind" not in present_vars(resolved, "json")
    assert present_vars(resolved, "json")["vendor"]["value"] == "KindCo"
    assert present_vars(resolved, "json", show_all=True)["__match__.kind"]["value"] == "note"


def test_regex_capture_stays_on_extract_until_assigned(tmp_path: Path) -> None:
    plan = _plan(
        {
            "vars_schema": {"amount": {"type": "float"}},
            "match_rules": [
                {
                    "name": "notes",
                    "kind": "note",
                    "filename_regex": r"(?P<amount>[^.]+)\.txt",
                    "vars": {"amount": ["{{ __extract__.amount }}", "1"]},
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

    assert "amount" in dict(resolved.items)
    assert dict(resolved.items)["amount"] == "12.50"
    assert resolved.dump_vars()["amount"]["value"] == 12.5
    assert resolved.sources["amount"] == ("rule:notes",)
    assert "__extract__.amount" not in dict(resolved.items)
    assert "__extract__.amount" not in present_vars(resolved, None)
    shown = present_vars(resolved, None, show_all=True)
    assert "__extract__.amount: 12.50" in str(shown)
    assert resolved.source_labels("__extract__.amount") == ("fact",)
    dumped = present_vars(resolved, "json", show_all=True)
    assert dumped["__extract__.amount"]["value"] == "12.50"
    assert "__extract__.amount" not in present_vars(resolved, "json")

    fallback = plan.resolve(
        _file("EUR12.50.txt"),
        _match("EUR12.50.txt", groups={"amount": "EUR12.50"}),
        Path("/in"),
    )
    assert dict(fallback.items)["amount"] == "1"

    bare = _plan(
        {
            "vars_schema": {"amount": {"type": "float", "mandatory": True}},
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
    with pytest.raises(VarResolveError, match="variable amount failed"):
        bare.resolve(
            _file("12.50.txt"),
            _match("12.50.txt", groups={"amount": "12.50"}),
            Path("/in"),
        )


def test_missing_extract_field_tries_the_next_candidate(tmp_path: Path) -> None:
    plan = _plan(
        {
            "match_rules": [
                {
                    "name": "notes",
                    "kind": "note",
                    "filename_regex": r"(?P<amount>[^.]+)\.txt",
                    "vars": {"amount": ["{{ __extract__.amount }}", "{{ __extract__ }}", "fallback"]},
                }
            ],
        },
        tmp_path,
    )
    values = _values(plan, match=_match(groups={}))
    assert values["amount"] == "fallback"


def test_group_named_kind_stays_on_extract(tmp_path: Path) -> None:
    plan = _plan(
        {
            "match_rules": [
                {
                    "name": "notes",
                    "kind": "note",
                    "filename_regex": r"(?P<kind>\w+)\.txt",
                    "vars": {"label": "{{ __extract__.kind }}"},
                }
            ],
        },
        tmp_path,
    )
    resolved = plan.resolve(
        _file("bill.txt"),
        _match("bill.txt", groups={"kind": "bill"}),
        Path("/in"),
    )
    assert dict(resolved.items)["label"] == "bill"
    assert resolved.facts["__match__.kind"] == "note"
    assert resolved.facts["__extract__.kind"] == "bill"


def test_int_assignment_drops_leading_zeros_and_keeps_the_capture(tmp_path: Path) -> None:
    plan = _plan(
        {
            "vars_schema": {"amount": {"type": "int"}},
            "match_rules": [
                {
                    "name": "notes",
                    "kind": "note",
                    "filename_regex": r"(?P<amount>\d+)\.txt",
                    "vars": {"amount": "{{ __extract__.amount }}"},
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
    assert resolved.facts["__extract__.amount"] == "0012"


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
                "issued": {"type": "date", "mandatory": True},
                "amount": {"type": "int", "mandatory": True},
                "opens": {"type": "time"},
            },
            "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "**"}],
        },
        tmp_path,
    )
    with pytest.raises(VarResolveError, match="variable issued failed") as caught:
        _values(plan)
    assert str(caught.value) == (
        "Profile work input 1 path a.txt variable issued failed: "
        "issued is mandatory according the schema."
    )
    assert caught.value.advice is None

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
    assert "company_name" not in note
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


def test_listed_kind_skips_catalog_defaults_it_does_not_name(tmp_path: Path) -> None:
    plan = _plan(
        {
            "vars_schema": {
                "issued": {"type": "date"},
                "provider": {"type": "text"},
                "doc_count": {"type": "int", "default": 1},
                "doc_items": {"type": "int", "default": 1},
            },
            "kind_schema": {
                "statement": {
                    "desc": "A bank or card statement for one period",
                    "vars_schema": {
                        "issued": None,
                        "provider": None,
                    },
                },
                "receipt": {"vars_schema": {"doc_items": None}},
            },
            "match_rules": [{"name": "notes", "kind": "statement", "filename_glob": "**"}],
        },
        tmp_path,
    )

    statement = _values(plan, match=_match(kind="statement", rule="notes"))
    assert "doc_count" not in statement
    assert "doc_items" not in statement

    unlisted = _values(plan, match=_match(kind="note"))
    assert unlisted["doc_count"] == "1"
    assert unlisted["doc_items"] == "1"

    receipt = _values(plan, match=_match(kind="receipt", rule="receipts"))
    assert receipt["doc_items"] == "1"
    assert "doc_count" not in receipt


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
            "config": {"kind_overrides_config": ["{{ __config__.root_dir }}/note.csv"]},
            "vars_schema": {"amount": {"type": "float"}},
            "match_rules": [{"name": "notes", "kind": "note", "filename_glob": "a.txt"}],
        },
        tmp_path,
    )
    with pytest.raises(VarResolveError, match="variable amount failed"):
        _values(plan)


def test_hash_identity_rewrites_the_path_and_keeps_cells(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)
    kind = tmp_path / "note.csv"
    kind.write_text(
        f"PATH,SHA,owner\nold.txt,{FILE_DIGEST},Kept\n",
        encoding="utf-8",
    )
    plan = _plan(_hash_document("{{ __config__.root_dir }}/note.csv"), tmp_path)
    values = _values(plan, file=_file("new.txt"), match=_match("new.txt"))
    assert values["owner"] == "Kept"
    plan.commit()
    text = kind.read_text(encoding="utf-8")
    assert text == f"PATH,SHA,owner\nnew.txt,{FILE_DIGEST},Kept\n"
    assert f'path was "old.txt", now "new.txt" for hash {FILE_DIGEST}' in caplog.text


def test_hash_identity_fills_an_empty_sha_on_the_same_path(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text("PATH,owner\na.txt,Kept\n", encoding="utf-8")
    document = _hash_document("{{ __config__.root_dir }}/note.csv")
    plan = _plan(document, tmp_path)
    _values(plan)
    plan.commit()
    assert kind.read_text(encoding="utf-8") == f"PATH,SHA,owner\na.txt,{FILE_DIGEST},Kept\n"
    again = _plan(document, tmp_path)
    assert _values(again)["owner"] == "Kept"


def test_hash_identity_keeps_an_unmapped_row(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)
    kind = tmp_path / "note.csv"
    kind.write_text("PATH,owner\na.txt,Kept\ngone.txt,Old\n", encoding="utf-8")
    plan = _plan(_hash_document("{{ __config__.root_dir }}/note.csv"), tmp_path)
    _values(plan)
    plan.commit()
    text = kind.read_text(encoding="utf-8")
    assert f"a.txt,{FILE_DIGEST},Kept" in text
    assert "gone.txt,,Old" in text
    assert "path gone.txt was not remapped" in caplog.text


def test_shared_hash_does_not_move_the_row(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)
    kind = tmp_path / "note.csv"
    kind.write_text(
        f"PATH,SHA,owner\nold.txt,{FILE_DIGEST},Kept\n",
        encoding="utf-8",
    )
    plan = _plan(_hash_document("{{ __config__.root_dir }}/note.csv"), tmp_path)
    _values(plan, file=_file("a.txt"), match=_match("a.txt"))
    _values(plan, file=_file("b.txt"), match=_match("b.txt"))
    plan.commit()
    assert kind.read_text(encoding="utf-8") == f"PATH,SHA,owner\nold.txt,{FILE_DIGEST},Kept\n"
    assert f"hash {FILE_DIGEST} is shared by a.txt, b.txt" in caplog.text


def test_path_identity_refreshes_sha_and_leaves_a_rename(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)
    kind = tmp_path / "note.csv"
    previous = "b" * 64
    kind.write_text(f"PATH,SHA,owner\nold.txt,{previous},Kept\n", encoding="utf-8")
    plan = _plan(_kind_document("{{ __config__.root_dir }}/note.csv"), tmp_path)
    _values(plan, file=_file("old.txt"), match=_match("old.txt"))
    _values(plan, file=_file("new.txt", digest="c" * 64), match=_match("new.txt"))
    plan.commit()
    text = kind.read_text(encoding="utf-8")
    assert f"old.txt,{FILE_DIGEST},Kept" in text
    assert f"new.txt,{'c' * 64}," in text
    assert f'hash was "{previous}", now "{FILE_DIGEST}" for path old.txt' in caplog.text


def test_hash_identity_keeps_the_old_row_when_the_digest_changes(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)
    kind = tmp_path / "note.csv"
    previous = "b" * 64
    kind.write_text(f"PATH,SHA,owner\na.txt,{previous},Kept\n", encoding="utf-8")
    plan = _plan(_hash_document("{{ __config__.root_dir }}/note.csv"), tmp_path)
    _values(plan)
    plan.commit()
    text = kind.read_text(encoding="utf-8")
    assert f"a.txt,{previous},Kept" in text
    assert f"a.txt,{FILE_DIGEST}," in text
    assert f"path a.txt now has hash {FILE_DIGEST} and the old row was kept" in caplog.text


def test_duplicate_sha_is_an_error(tmp_path: Path) -> None:
    kind = tmp_path / "note.csv"
    kind.write_text(
        f"PATH,SHA,owner\na.txt,{FILE_DIGEST},One\nb.txt,{FILE_DIGEST},Two\n",
        encoding="utf-8",
    )
    plan = _plan(_kind_document("{{ __config__.root_dir }}/note.csv"), tmp_path)
    with pytest.raises(VarConfigError, match="is on a.txt and b.txt"):
        _values(plan)


def _hash_document(path: str) -> dict[str, object]:
    document = _kind_document(path)
    config = document["config"]
    assert isinstance(config, dict)
    config["record_identity"] = "hash"
    return document

