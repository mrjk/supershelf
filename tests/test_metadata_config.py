"""metadata_driver load rules and the fs driver."""

from pathlib import Path

import pytest

from supershelf.errors import VarConfigError
from supershelf.match import FileMatch
from supershelf.scan import InputFile
from supershelf.vars import VarPlan
from tests.metadata_helpers import input_file as _file
from tests.metadata_helpers import resolve_values, var_plan


def _match(
    path: str = "a.txt",
    groups: dict[str, str] | None = None,
) -> FileMatch:
    return FileMatch("work", 1, path, "note", "notes", groups or {})


def _plan(
    document: dict[str, object],
    root: Path,
    scope: dict[str, object] | None = None,
) -> VarPlan:
    return var_plan(document, root, scope=scope)


def _values(plan: VarPlan, **kwargs: object) -> dict[str, str]:
    file = kwargs.get("file", _file())
    match = kwargs.get("match", _match())
    assert isinstance(file, InputFile)
    assert isinstance(match, FileMatch)
    return resolve_values(plan, file, match)


def _assert_builtin_defaults(plan: VarPlan) -> None:
    fs = plan.metadata.entry("fs")
    pdf = plan.metadata.entry("pdf")
    exif = plan.metadata.entry("exiftool")
    text = plan.metadata.entry("pdftotext")
    assert fs is not None and pdf is not None and exif is not None and text is not None
    assert fs.driver.ignores_enable is True
    assert fs.driver.extensions == ()
    assert fs.driver.mime_types == ()
    assert fs.options.enable == "auto"
    assert fs.options.timeout is None
    assert pdf.driver.ignores_enable is True
    assert pdf.driver.extensions == ("pdf",)
    assert pdf.driver.mime_types == ("application/pdf",)
    assert pdf.options.timeout is None
    assert exif.options.enable == "auto"
    assert exif.options.timeout == 30
    assert exif.driver.extensions == ()
    assert exif.driver.mime_types == ()
    assert text.options.enable == "auto"
    assert text.options.timeout == 30
    assert text.driver.single_field == "text"
    assert text.driver.extensions == ("pdf",)


def test_omitted_null_and_empty_keep_builtin_defaults(tmp_path: Path) -> None:
    omitted = _plan({}, tmp_path)
    empty = _plan({"metadata_driver": {}}, tmp_path)
    nulled = _plan({"metadata_driver": None}, tmp_path)
    _assert_builtin_defaults(omitted)
    _assert_builtin_defaults(empty)
    _assert_builtin_defaults(nulled)


def test_disabling_exiftool_keeps_pdf(tmp_path: Path) -> None:
    plan = _plan(
        {"metadata_driver": {"exiftool": {"enable": "false"}}},
        tmp_path,
    )
    exif = plan.metadata.entry("exiftool")
    assert exif is not None
    assert exif.options.enable == "false"
    assert plan.metadata.entry("pdf") is not None
    values = _values(
        _plan(
            {
                "metadata_driver": {"exiftool": {"enable": "false"}},
                "default_vars": {
                    "author": ['{{ meta("exiftool", "PDF:Author") }}', "UNKNOWN"],
                },
            },
            tmp_path,
        )
    )
    assert values["author"] == "UNKNOWN"


def test_unknown_builtin_option_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(VarConfigError, match="unknown option"):
        _plan({"metadata_driver": {"fs": {"nope": 1}}}, tmp_path)


def test_unknown_name_without_driver_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(VarConfigError, match="no driver"):
        _plan({"metadata_driver": {"covers": {"command": "tagtool"}}}, tmp_path)


def test_bad_enable_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(VarConfigError, match="enable"):
        _plan({"metadata_driver": {"exiftool": {"enable": "yes"}}}, tmp_path)


def test_zero_timeout_on_pdftotext_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(VarConfigError, match="timeout"):
        _plan({"metadata_driver": {"pdftotext": {"timeout": 0}}}, tmp_path)


def test_timeout_on_fs_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(VarConfigError, match="timeout"):
        _plan({"metadata_driver": {"fs": {"timeout": 30}}}, tmp_path)


def test_config_metadata_driver_names_the_top_level_key(tmp_path: Path) -> None:
    with pytest.raises(VarConfigError, match="config.metadata_driver") as caught:
        _plan({"config": {"metadata_driver": {}}}, tmp_path)
    assert caught.value.advice is not None
    assert "metadata_driver" in caught.value.advice
    assert "top level" in caught.value.advice


def test_literal_unknown_meta_driver_fails_at_load(tmp_path: Path) -> None:
    with pytest.raises(VarConfigError, match="missing"):
        _plan(
            {"default_vars": {"author": '{{ meta("missing", "author") }}'}},
            tmp_path,
        )


def test_regex_group_wins_without_calling_fs(tmp_path: Path) -> None:
    plan = _plan(
        {
            "default_vars": {
                "author": ["{{ author }}", '{{ meta("fs", "name") }}'],
            },
            "match_rules": [
                {
                    "name": "notes",
                    "kind": "note",
                    "filename_regex": r"(?P<author>\w+)\.txt",
                }
            ],
        },
        tmp_path,
    )
    values = _values(
        plan,
        file=_file("Ada.txt"),
        match=_match("Ada.txt", groups={"author": "Ada"}),
    )
    assert values["author"] == "Ada"


def test_fs_returns_walk_strings(tmp_path: Path) -> None:
    plan = _plan(
        {
            "default_vars": {
                "name": '{{ meta("fs", "name") }}',
                "stem": '{{ meta("fs", "stem") }}',
                "ext": '{{ meta("fs", "ext") }}',
                "path": '{{ meta("fs", "path") }}',
                "folder": '{{ meta("fs", "dir") }}',
                "digest": '{{ meta("fs", "hash") }}',
                "created": '{{ meta("fs", "ctime") }}',
                "modified": '{{ meta("fs", "mtime") }}',
                "root": ['{{ meta("fs", "dir") }}', "ROOT"],
                "missing": ['{{ meta("fs", "nope") }}', "FALLBACK"],
            },
        },
        tmp_path,
    )
    nested = _file("sub/report.pdf")
    values = _values(plan, file=nested, match=_match("sub/report.pdf"))
    assert values["name"] == "report.pdf"
    assert values["stem"] == "report"
    assert values["ext"] == "pdf"
    assert values["path"] == "sub/report.pdf"
    assert values["folder"] == "sub"
    assert values["digest"] == "abc"
    assert values["created"] == nested.ctime
    assert values["modified"] == nested.mtime
    assert values["missing"] == "FALLBACK"
    top = _values(plan)
    assert top["root"] == "ROOT"


def test_profile_without_meta_does_not_create_the_database(tmp_path: Path) -> None:
    database = tmp_path / "profile.work.sqlite"
    plan = _plan(
        {"default_vars": {"owner": "Ada"}},
        tmp_path,
        scope={
            "__profile_dir__": str(tmp_path),
            "__database_file__": str(database),
        },
    )
    assert _values(plan)["owner"] == "Ada"
    assert database.exists() is False


def test_custom_driver_and_import_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = tmp_path / "sample_meta"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "driver.py").write_text(
        "from supershelf.errors import VarCandidateError\n"
        "\n"
        "class InvoiceDriver:\n"
        "    def available(self, options):\n"
        "        return True\n"
        "    def accepts(self, file, options):\n"
        "        return True\n"
        "    def extract(self, file, field, options):\n"
        "        if field != 'number':\n"
        "            raise VarCandidateError('missing')\n"
        "        return options.get('lang', 'eng') + '-value'\n"
        "\n"
        "DRIVER = InvoiceDriver()\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    plan = _plan(
        {
            "metadata_driver": {
                "invoice": {"driver": "sample_meta.driver", "lang": "eng"},
            },
            "default_vars": {"number": '{{ meta("invoice", "number") }}'},
        },
        tmp_path,
    )
    assert _values(plan)["number"] == "eng-value"
    with pytest.raises(VarConfigError, match="Cannot import"):
        _plan(
            {"metadata_driver": {"invoice": {"driver": "sample_meta.missing"}}},
            tmp_path,
        )


def test_meta_driver_module_exports_driver() -> None:
    import supershelf.meta_driver as meta_driver

    from supershelf.metadata.drivers import CommandDriver

    assert isinstance(meta_driver.DRIVER, CommandDriver)
