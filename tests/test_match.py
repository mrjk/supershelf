"""match_rules classification."""

import logging
from pathlib import Path

import pytest

from supershelf.constants import LOGGER_NAME
from supershelf.errors import SupershelfError
from supershelf.match import Matcher
from supershelf.scan import InputFile, InputScanResult, ResolvedInput

FACTURE = {
    "name": "rule1",
    "kind": "facture",
    "regex": [
        r"banking_(?P<account>\d{12})/REL_(?P<date>\d+)_(?P<recept_id>\w{8})\.pdf"
    ],
    "directory_regex": [r"banking_(?P<account>\d{12})"],
    "filename_regex": [r"REL_(?P<date>\d+)_(?P<recept_id>\w{8})\.pdf"],
    "glob": ["banking*/REL*"],
    "directory_glob": ["banking*"],
    "filename_glob": ["REL*"],
}


def _file(relative: str) -> InputFile:
    return InputFile.from_relative(relative, Path(relative))


def _matcher(rules: object) -> Matcher:
    return Matcher.from_document({"match_rules": rules}, "work")


def _scan(*files: InputFile, profile: str = "work", index: int = 1) -> InputScanResult:
    return InputScanResult(
        profile=profile,
        index=index,
        config=ResolvedInput(
            path=Path("/in"),
            include=None,
            exclude=None,
            depth=0,
            follow_symlinks=True,
        ),
        results=list(files),
    )


def test_full_regex_wins_and_keeps_every_group() -> None:
    hit = _matcher([FACTURE]).claim(
        _file("banking_123456789012/REL_20211231_ABCD1234.pdf")
    )
    assert hit is not None
    assert hit.rule == "rule1"
    assert hit.kind == "facture"
    assert hit.groups == {
        "account": "123456789012",
        "date": "20211231",
        "recept_id": "ABCD1234",
    }


def test_regex_without_the_extension_does_not_match() -> None:
    bare = _matcher(
        [{"name": "r", "kind": "k", "filename_regex": r"REL_(?P<date>\d+)"}]
    )
    covered = _matcher(
        [{"name": "r", "kind": "k", "filename_regex": r"REL_(?P<date>\d+)\.pdf"}]
    )
    assert bare.claim(_file("REL_1.pdf")) is None
    hit = covered.claim(_file("REL_1.pdf"))
    assert hit is not None
    assert hit.groups == {"date": "1"}


def test_filename_regex_wins_when_the_path_and_directory_miss() -> None:
    hit = _matcher([FACTURE]).claim(_file("other/REL_20211231_ABCD1234.pdf"))
    assert hit is not None
    assert hit.groups == {"date": "20211231", "recept_id": "ABCD1234"}


def test_directory_regex_stops_before_the_filename_fields() -> None:
    hit = _matcher([FACTURE]).claim(_file("banking_123456789012/notes.txt"))
    assert hit is not None
    assert hit.groups == {"account": "123456789012"}


def test_filename_regex_runs_before_a_glob_that_would_also_match() -> None:
    matcher = _matcher(
        [
            {
                "name": "r",
                "kind": "k",
                "filename_regex": r"REL_(?P<date>\d+)\.pdf",
                "glob": "**",
            }
        ]
    )
    hit = matcher.claim(_file("REL_9.pdf"))
    assert hit is not None
    assert hit.groups == {"date": "9"}


def test_globs_fullmatch_the_field_candidate() -> None:
    nested = _file("banking_123/REL_1.pdf")
    by_name = _matcher([{"name": "r", "kind": "k", "filename_glob": "REL*"}])
    by_path = _matcher([{"name": "r", "kind": "k", "glob": "REL*"}])
    everything = _matcher([{"name": "r", "kind": "k", "glob": "**"}])
    directory = _matcher([{"name": "r", "kind": "k", "directory_glob": "banking*"}])

    assert by_name.claim(nested) is not None
    assert by_path.claim(nested) is None
    assert everything.claim(_file("top.pdf")) is not None
    assert directory.claim(_file("banking_123/2024/f.pdf")) is None
    assert directory.claim(_file("banking_123/f.pdf")) is not None


def test_empty_directory_skips_directory_patterns() -> None:
    matcher = _matcher([{"name": "r", "kind": "k", "directory_regex": ".*"}])
    assert matcher.claim(_file("top.pdf")) is None


def test_unmatched_file_warns_and_stays_on_the_scan(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)
    kept = _file("a.txt")
    scan = _scan(kept)
    matcher = _matcher([{"name": "r", "kind": "k", "filename_glob": "nope*"}])

    assert matcher.collect(scan) == []
    assert scan.results == [kept]
    assert "No match_rule for a.txt in profile work input 1" in caplog.text


def test_missing_match_rules_claims_nothing(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)
    kept = _file("a.txt")
    scan = _scan(kept)
    matcher = Matcher.from_document({}, "work")

    assert matcher.collect(scan) == []
    assert scan.results == [kept]
    assert "No match_rule" in caplog.text


@pytest.mark.parametrize(
    ("rules", "message"),
    [
        (
            [
                {"name": "a", "kind": "k", "glob": "*"},
                {"name": "a", "kind": "k", "glob": "*"},
            ],
            "duplicate match rule",
        ),
        ([{"glob": "*"}], "needs a name or a kind"),
        ([{"name": " ", "kind": " ", "glob": "*"}], "needs a name or a kind"),
        ([{"name": "a", "kind": "k"}], "no patterns"),
        ([{"name": "a", "kind": "k", "regex": "("}], "Invalid regex"),
        ([{"name": "a", "kind": "k", "regex": [1]}], "must be a string"),
    ],
)
def test_match_rule_config_errors(rules: list[object], message: str) -> None:
    with pytest.raises(SupershelfError, match=message):
        _matcher(rules)


def test_omitted_kind_uses_the_rule_name() -> None:
    matcher = _matcher([{"name": "unsorted", "glob": "**"}])
    hit = matcher.claim(_file("a.pdf"))
    assert hit is not None
    assert hit.rule == "unsorted"
    assert hit.kind == "unsorted"


def test_kind_alone_is_also_the_rule_name() -> None:
    matcher = _matcher([{"kind": "facture", "glob": "**"}])
    hit = matcher.claim(_file("a.pdf"))
    assert hit is not None
    assert hit.rule == "facture"
    assert hit.kind == "facture"


def test_explicit_kind_overrides_the_rule_name() -> None:
    matcher = _matcher([{"name": "rule1", "kind": "facture", "glob": "**"}])
    hit = matcher.claim(_file("a.pdf"))
    assert hit is not None
    assert hit.rule == "rule1"
    assert hit.kind == "facture"


def test_vars_key_is_ignored() -> None:
    matcher = _matcher(
        [{"name": "r", "kind": "k", "glob": "**", "vars": {"account": "x"}}]
    )
    hit = matcher.claim(_file("a.pdf"))
    assert hit is not None
    assert hit.kind == "k"
    assert hit.groups == {}
