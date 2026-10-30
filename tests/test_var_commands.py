"""Built-in var commands."""

from pathlib import Path

import pytest
from pypdf import PdfWriter

from supershelf.errors import VarCandidateError
from supershelf.var_commands import FileBinding
from supershelf.var_template import VarEnvironment


def _binding(path: Path, digest: str = "abc") -> FileBinding:
    return FileBinding(path, digest, "2026-01-02T00:00:00+00:00", "2026-01-01T00:00:00+00:00")


def test_regex_time_var_tries_formats_in_order() -> None:
    environment = VarEnvironment()
    rendered = environment.render(
        '{{ regex_time_var(value, "%H:%M:%S", "%Y%m%d") }}',
        {"value": "20211231"},
        _binding(Path("a.txt")),
        {},
    )
    assert rendered == "2021-12-31"


def test_regex_replace_miss_fails_the_candidate() -> None:
    environment = VarEnvironment()
    with pytest.raises(VarCandidateError, match="did not match"):
        environment.render(
            '{{ regex_replace(value, "[0-9]", "x") }}',
            {"value": "ab"},
            _binding(Path("a.txt")),
            {},
        )


def test_file_returns_the_stored_timestamp() -> None:
    environment = VarEnvironment()
    rendered = environment.render(
        '{{ file("ctime") }}',
        {},
        _binding(Path("a.txt")),
        {},
    )
    assert rendered == "2026-01-02T00:00:00+00:00"


def test_pdf_dates_and_a_miss(tmp_path: Path) -> None:
    pdf = tmp_path / "a.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.add_metadata(
        {
            "/CreationDate": "D:20260425120000Z",
            "/ModDate": "D:20260426120000Z",
        }
    )
    with pdf.open("wb") as handle:
        writer.write(handle)
    environment = VarEnvironment()
    binding = _binding(pdf, "hash-1")
    assert environment.render("{{ pdf_cdate() }}", {}, binding, {}) == "2026-04-25"
    assert environment.render("{{ pdf_mdate() }}", {}, binding, {}) == "2026-04-26"

    text = tmp_path / "a.txt"
    text.write_text("hello", encoding="utf-8")
    with pytest.raises(VarCandidateError, match="PDF date"):
        environment.render("{{ pdf_cdate() }}", {}, _binding(text, "hash-2"), {})
