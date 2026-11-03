"""pdf, exiftool, pdftotext, and the mime probe. Tools are faked."""

import json
import logging
from pathlib import Path

import pytest
from pypdf import PdfWriter

from supershelf.constants import LOGGER_NAME
from supershelf.errors import VarConfigError
from supershelf.scan import InputFile
from supershelf.vars import VarPlan
from tests.metadata_helpers import FakeRunner, input_file as _file
from tests.metadata_helpers import resolve_values, var_plan


def _write_pdf(path: Path, author: str = "Ada") -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.add_metadata({"/Author": author, "/Title": "Quarterly report"})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        writer.write(handle)


def _plan(document: dict[str, object], root: Path, runner: FakeRunner) -> VarPlan:
    return var_plan(document, root, runner, database=True)


def _values(plan: VarPlan, file: InputFile) -> dict[str, str]:
    return resolve_values(plan, file, use_file_path=True)


def _file_calls(runner: FakeRunner) -> list[list[str]]:
    return [call for call in runner.calls if call and call[0] == "file"]


def test_pdf_extension_does_not_spawn_file(tmp_path: Path) -> None:
    path = tmp_path / "scan.pdf"
    _write_pdf(path)
    runner = FakeRunner()
    runner.available.add("file")
    plan = _plan(
        {"default_vars": {"author": '{{ meta("pdf", "author") }}'}},
        tmp_path,
        runner,
    )
    assert _values(plan, _file("scan.pdf", path))["author"] == "Ada"
    assert _file_calls(runner) == []
    assert runner.which_calls.count("file") == 0


def test_pdf_without_a_suffix_probes_mime_once_per_hash(tmp_path: Path) -> None:
    path = tmp_path / "scan"
    _write_pdf(path, author="Ada")
    runner = FakeRunner()
    runner.available.add("file")
    runner.output["file"] = "application/pdf\n"
    plan = _plan(
        {
            "default_vars": {
                "author": '{{ meta("pdf", "author") }}',
                "title": '{{ meta("pdf", "title") }}',
            }
        },
        tmp_path,
        runner,
    )
    first = _file("scan", path)
    values = _values(plan, first)
    assert values["author"] == "Ada"
    assert values["title"] == "Quarterly report"
    other = _file("copy", path, digest=first.sha256 or "")
    again = _values(plan, other)
    assert again["author"] == "Ada"
    assert len(_file_calls(runner)) == 1


def test_fake_exiftool_and_pdftotext(tmp_path: Path) -> None:
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"%PDF-1.4\n")
    runner = FakeRunner()
    runner.available.update({"exiftool", "pdftotext"})
    runner.output["exiftool"] = json.dumps(
        [
            {
                "SourceFile": str(path),
                "File:FileName": "scan.pdf",
                "PDF:Author": "Ada",
                "Composite:Megapixels": 1,
            }
        ]
    )
    runner.output["pdftotext"] = "page one\n"
    plan = _plan(
        {
            "default_vars": {
                "author": '{{ meta("exiftool", "PDF:Author") }}',
                "pixels": '{{ meta("exiftool", "Composite:Megapixels") }}',
                "file_name": ['{{ meta("exiftool", "File:FileName") }}', "DROPPED"],
                "body": '{{ meta("pdftotext") }}',
            }
        },
        tmp_path,
        runner,
    )
    values = _values(plan, _file("scan.pdf", path))
    assert values["author"] == "Ada"
    assert values["pixels"] == "1"
    assert values["file_name"] == "DROPPED"
    assert values["body"] == "page one"
    exif = [call for call in runner.calls if call[0] == "exiftool"]
    text = [call for call in runner.calls if call[0] == "pdftotext"]
    assert exif == [["exiftool", "-json", "-G", str(path)]]
    assert text == [["pdftotext", "-q", "-enc", "UTF-8", str(path), "-"]]


def test_nonzero_exit_fails_the_candidate_and_is_not_rerun(tmp_path: Path) -> None:
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"%PDF-1.4\n")
    runner = FakeRunner()
    runner.available.add("exiftool")
    runner.codes["exiftool"] = 2
    plan = _plan(
        {
            "default_vars": {
                "author": ['{{ meta("exiftool", "PDF:Author") }}', "UNKNOWN"],
            }
        },
        tmp_path,
        runner,
    )
    first = _file("scan.pdf", path)
    assert _values(plan, first)["author"] == "UNKNOWN"
    second = _file("other.pdf", path)
    assert _values(plan, second)["author"] == "UNKNOWN"
    assert len([call for call in runner.calls if call[0] == "exiftool"]) == 1


def test_required_tool_missing_stops_at_load(tmp_path: Path) -> None:
    runner = FakeRunner()
    with pytest.raises(VarConfigError, match="not available") as caught:
        _plan(
            {"metadata_driver": {"exiftool": {"enable": "true"}}},
            tmp_path,
            runner,
        )
    assert caught.value.advice is not None
    assert "exiftool" in caught.value.advice


def test_optional_tool_missing_logs_once(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"%PDF-1.4\n")
    runner = FakeRunner()
    plan = _plan(
        {"default_vars": {"body": ['{{ meta("pdftotext") }}', "NONE"]}},
        tmp_path,
        runner,
    )
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        assert _values(plan, _file("scan.pdf", path))["body"] == "NONE"
        assert _values(plan, _file("other.pdf", path, digest="def"))["body"] == "NONE"
    notes = [record.message for record in caplog.records if "pdftotext" in record.message]
    assert len(notes) == 1
    assert runner.which_calls.count("pdftotext") == 1


def test_mime_probe_misses_when_file_is_absent(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = tmp_path / "scan"
    _write_pdf(path)
    runner = FakeRunner()
    plan = _plan(
        {"default_vars": {"author": ['{{ meta("pdf", "author") }}', "NONE"]}},
        tmp_path,
        runner,
    )
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        assert _values(plan, _file("scan", path))["author"] == "NONE"
        assert _values(plan, _file("other", path, digest="def"))["author"] == "NONE"
    notes = [record.message for record in caplog.records if "file is not on PATH" in record.message]
    assert len(notes) == 1
    assert _file_calls(runner) == []
