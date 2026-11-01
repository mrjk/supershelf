"""Link rules: path, hash, duplicates, missing, unmatched, and the path filter."""

from pathlib import Path

from supershelf.constants import (
    ENV_RECORD_IDENTITY,
    EVENT_GENERATION,
    EVENT_MISSING,
    EVENT_MOVE,
    EVENT_NEW,
    EVENT_PRESENT,
    EVENT_UNMATCHED,
    EVENT_VARS,
    PRESENCE_MISSING,
    PRESENCE_PRESENT,
    PRESENCE_UNMATCHED,
    STATUS_REFRESH,
    STATUS_UNCHANGED,
)
from supershelf.database import DocumentRow
from supershelf.errors import RecordConfigError
from supershelf.record import (
    DuplicateListing,
    LiveFile,
    RecordIdentity,
    RecordPlan,
)
from supershelf.match import Matcher
from supershelf.scan import KeptPath
from supershelf.var_schema import VarState
from supershelf.vars import FileVars, VarPlan

import pytest

_IN = "/inbox"
_H1 = "a" * 64
_H2 = "b" * 64
_WHEN = "2026-04-25T00:00:00+00:00"


def _live(path: str, digest: str = _H1, **overrides: object) -> LiveFile:
    name = path.rsplit("/", 1)[-1]
    stem, dot, ext = name.rpartition(".")
    values: dict[str, object] = {
        "input_index": 1,
        "input_path": _IN,
        "path": path,
        "hash": digest,
        "mtime": _WHEN,
        "ctime": _WHEN,
        "match_kind": "bill",
        "rule": "bill",
        "file_dir": "" if "/" not in path else path.rsplit("/", 1)[0],
        "file_name": name,
        "file_stem": stem if dot else name,
        "file_ext": ext if dot else "",
        "vars_json": "{}",
    }
    values.update(overrides)
    return LiveFile(**values)  # type: ignore[arg-type]


def _doc(
    doc_id: int,
    path: str,
    digest: str = _H1,
    *,
    presence: str = PRESENCE_PRESENT,
    generation: int = 1,
    input_path: str = _IN,
    vars_json: str = "{}",
    mtime: str = _WHEN,
    index: int = 1,
) -> DocumentRow:
    live = _live(path, digest, input_path=input_path, vars_json=vars_json, mtime=mtime, input_index=index)
    return DocumentRow(
        id=doc_id,
        presence=presence,
        generation=generation,
        hash=digest,
        input_index=index,
        input_path=input_path,
        path=path,
        mtime=mtime,
        ctime=_WHEN,
        match_kind=live.match_kind,
        rule=live.rule,
        file_dir=live.file_dir,
        file_name=live.file_name,
        file_stem=live.file_stem,
        file_ext=live.file_ext,
        vars_json=vars_json,
        updated_at=_WHEN,
    )


def _plan(
    documents: list[DocumentRow],
    live: list[LiveFile],
    *,
    identity: str = "path",
    kept: set[tuple[str, str]] | None = None,
    walked: set[str] | None = None,
    selector: str | None = None,
    paths: list[str] | None = None,
) -> list:
    observed = paths if paths is not None else [item.path for item in live]
    return RecordPlan(
        identity,
        documents,
        live,
        kept if kept is not None else {item.location() for item in live},
        walked if walked is not None else {_IN},
        KeptPath.from_paths(selector, observed),
    ).rows()


def _statuses(rows: list) -> list[tuple[str, str]]:
    return [(row.status, row.file.path) for row in rows]


def test_identity_precedence() -> None:
    assert RecordIdentity.resolve({}, None, {}) == "path"
    assert RecordIdentity.resolve({"record_identity": "hash"}, None, {}) == "hash"
    assert (
        RecordIdentity.resolve(
            {"record_identity": "path"},
            None,
            {ENV_RECORD_IDENTITY: "hash"},
        )
        == "hash"
    )
    assert (
        RecordIdentity.resolve(
            {"record_identity": "hash"},
            "path",
            {ENV_RECORD_IDENTITY: "hash"},
        )
        == "path"
    )


def test_identity_rejects_a_bad_word() -> None:
    with pytest.raises(RecordConfigError, match="config.record_identity") as caught:
        RecordIdentity.resolve({"record_identity": "PATH"}, None, {})
    assert caught.value.rc == 2
    with pytest.raises(RecordConfigError, match=ENV_RECORD_IDENTITY):
        RecordIdentity.resolve({}, None, {ENV_RECORD_IDENTITY: ""})


def test_new_file_and_a_second_unchanged_run() -> None:
    first = _plan([], [_live("a.pdf")])
    assert _statuses(first) == [(EVENT_NEW, "a.pdf")]
    assert first[0].generation == 1
    assert first[0].duplicates == 0
    again = _plan([_doc(1, "a.pdf")], [_live("a.pdf")])
    assert _statuses(again) == [(STATUS_UNCHANGED, "a.pdf")]
    assert again[0].change() is None


def test_two_live_copies_are_two_documents() -> None:
    rows = _plan([], [_live("a.pdf"), _live("b.pdf")])
    assert _statuses(rows) == [(EVENT_NEW, "a.pdf"), (EVENT_NEW, "b.pdf")]
    assert [row.duplicates for row in rows] == [1, 1]
    rows = _plan([_doc(1, "a.pdf")], [_live("a.pdf"), _live("b.pdf")])
    assert _statuses(rows) == [(STATUS_UNCHANGED, "a.pdf"), (EVENT_NEW, "b.pdf")]
    assert [row.duplicates for row in rows] == [1, 1]


def test_move_when_the_old_path_is_gone() -> None:
    rows = _plan(
        [_doc(1, "a.pdf")],
        [_live("b.pdf")],
        kept=set(),
    )
    assert _statuses(rows) == [(EVENT_MOVE, "b.pdf")]
    assert rows[0].document_id == 1
    assert rows[0].generation == 1


def test_generation_when_bytes_change_at_the_same_path() -> None:
    rows = _plan([_doc(1, "a.pdf")], [_live("a.pdf", _H2)])
    assert _statuses(rows) == [(EVENT_GENERATION, "a.pdf")]
    assert rows[0].generation == 2
    assert rows[0].file.hash == _H2


def test_path_collision_keeps_the_document_at_the_old_path() -> None:
    rows = _plan(
        [_doc(1, "a.pdf")],
        [_live("a.pdf", _H2), _live("b.pdf", _H1)],
        identity="path",
    )
    assert _statuses(rows) == [(EVENT_GENERATION, "a.pdf"), (EVENT_NEW, "b.pdf")]
    assert rows[0].document_id == 1
    assert rows[0].generation == 2
    assert rows[1].file.hash == _H1
    assert [row.duplicates for row in rows] == [0, 0]


def test_hash_collision_moves_the_old_hash() -> None:
    rows = _plan(
        [_doc(1, "a.pdf")],
        [_live("a.pdf", _H2), _live("b.pdf", _H1)],
        identity="hash",
    )
    assert _statuses(rows) == [(EVENT_MOVE, "b.pdf"), (EVENT_NEW, "a.pdf")]
    assert rows[0].document_id == 1
    assert rows[0].file.hash == _H1
    assert rows[1].file.hash == _H2
    assert rows[0].generation == 1


def test_rename_plus_edit_is_missing_plus_new() -> None:
    for identity in ("path", "hash"):
        rows = _plan(
            [_doc(1, "a.pdf")],
            [_live("b.pdf", _H2)],
            identity=identity,
            kept=set(),
        )
        assert _statuses(rows) == [(EVENT_MISSING, "a.pdf"), (EVENT_NEW, "b.pdf")]
        assert rows[0].document_id == 1


def test_two_documents_that_want_one_hash_stay_missing() -> None:
    rows = _plan(
        [_doc(1, "a.pdf"), _doc(2, "b.pdf")],
        [_live("c.pdf")],
        kept=set(),
    )
    assert _statuses(rows) == [
        (EVENT_MISSING, "a.pdf"),
        (EVENT_MISSING, "b.pdf"),
        (EVENT_NEW, "c.pdf"),
    ]
    assert rows[2].duplicates == 0


def test_missing_file_keeps_the_row_once() -> None:
    rows = _plan([_doc(1, "a.pdf")], [], kept=set())
    assert _statuses(rows) == [(EVENT_MISSING, "a.pdf")]
    again = _plan(
        [_doc(1, "a.pdf", presence=PRESENCE_MISSING)],
        [],
        kept=set(),
    )
    assert again == []


def test_path_filter_does_not_mark_the_other_file_missing() -> None:
    rows = _plan(
        [_doc(1, "a.pdf"), _doc(2, "b.pdf", _H2)],
        [],
        kept={(_IN, "b.pdf")},
        selector="a.pdf",
        paths=["b.pdf"],
    )
    assert _statuses(rows) == [(EVENT_MISSING, "a.pdf")]
    assert rows[0].document_id == 1


def test_full_run_moves_onto_the_surviving_path() -> None:
    rows = _plan(
        [_doc(1, "a.pdf")],
        [_live("kept/b.pdf")],
        kept=set(),
    )
    assert _statuses(rows) == [(EVENT_MOVE, "kept/b.pdf")]


def test_filtered_run_does_not_follow_a_hash_outside_the_filter() -> None:
    rows = _plan(
        [_doc(1, "a.pdf")],
        [_live("kept/b.pdf")],
        kept=set(),
        selector="a.pdf",
        paths=["kept/b.pdf"],
    )
    assert _statuses(rows) == [(EVENT_MISSING, "a.pdf")]


def test_unmatched_then_present_again() -> None:
    kept = {(_IN, "a.pdf")}
    rows = _plan([_doc(1, "a.pdf")], [], kept=kept)
    assert _statuses(rows) == [(EVENT_UNMATCHED, "a.pdf")]
    again = _plan(
        [_doc(1, "a.pdf", presence=PRESENCE_UNMATCHED)],
        [],
        kept=kept,
    )
    assert again == []
    returned = _plan(
        [_doc(1, "a.pdf", presence=PRESENCE_UNMATCHED)],
        [_live("a.pdf")],
    )
    assert _statuses(returned) == [(EVENT_PRESENT, "a.pdf")]


def test_variable_change_does_not_bump_the_generation() -> None:
    rows = _plan(
        [_doc(1, "a.pdf")],
        [_live("a.pdf", vars_json='{"vendor":"Bank2000"}')],
    )
    assert rows[0].status == EVENT_VARS
    assert rows[0].generation == 1
    assert rows[0].file.vars_json == '{"vendor":"Bank2000"}'


def test_mtime_is_a_refresh() -> None:
    rows = _plan(
        [_doc(1, "a.pdf")],
        [_live("a.pdf", mtime="2026-05-01T00:00:00+00:00")],
    )
    assert rows[0].status == STATUS_REFRESH
    assert rows[0].change() is not None
    assert rows[0].generation == 1


def test_unwalked_input_is_left_alone() -> None:
    rows = _plan(
        [_doc(1, "a.pdf", input_path="/other")],
        [],
        kept=set(),
        walked={_IN},
    )
    assert rows == []


def test_ignored_database_path_is_out_of_scope() -> None:
    live = [_live("a.pdf")]
    plan = RecordPlan(
        "path",
        [_doc(1, "a.pdf")],
        live,
        {live[0].location()},
        {_IN},
        KeptPath.from_paths(None, ["a.pdf"]),
        ignored={(_IN, "a.pdf")},
    )
    assert plan.rows() == []


def test_duplicate_listing_marks_a_past_generation() -> None:
    from supershelf.database import EventRow

    def event(event_id: int, document_id: int, digest: str, path: str) -> EventRow:
        return EventRow(
            id=event_id,
            document_id=document_id,
            seq=1,
            event=EVENT_NEW,
            identity="path",
            recorded_at=_WHEN,
            generation=1,
            hash=digest,
            input_index=1,
            input_path=_IN,
            path=path,
            mtime=_WHEN,
            ctime=_WHEN,
            match_kind="bill",
            rule="bill",
            file_dir="",
            file_name=path,
            file_stem="bill",
            file_ext="pdf",
            vars_json="{}",
            output_name=None,
            operation=None,
            destination=None,
            source_hash=None,
            previous_json=None,
        )

    documents = [
        _doc(1, "a.pdf", _H2, generation=2),
        _doc(2, "b.pdf", _H1),
    ]
    events = [
        event(1, 1, _H1, "a.pdf"),
        event(2, 1, _H2, "a.pdf"),
        event(3, 2, _H1, "b.pdf"),
    ]
    events[1] = EventRow(
        id=2,
        document_id=1,
        seq=2,
        event=EVENT_GENERATION,
        identity="path",
        recorded_at=_WHEN,
        generation=2,
        hash=_H2,
        input_index=1,
        input_path=_IN,
        path="a.pdf",
        mtime=_WHEN,
        ctime=_WHEN,
        match_kind="bill",
        rule="bill",
        file_dir="",
        file_name="a.pdf",
        file_stem="a",
        file_ext="pdf",
        vars_json="{}",
        output_name=None,
        operation=None,
        destination=None,
        source_hash=None,
        previous_json=None,
    )
    hits = DuplicateListing.collect(documents, events)
    by_doc = {hit.document_id: hit for hit in hits if hit.hash == _H1}
    assert by_doc[1].current is False
    assert by_doc[2].current is True


def test_snapshot_keeps_date_and_drops_identity_facts(tmp_path: Path) -> None:
    plan = VarPlan.from_document(
        {"vars_schema": {"vendor": {"type": "text"}}},
        "work",
        Matcher.from_document({}, "work"),
        tmp_path,
        {"__root_dir__": str(tmp_path), "__profile__": "work"},
    )
    resolved = FileVars(
        "bill",
        "bill",
        (
            ("__kind__", VarState(value="bill", display="bill", value_sources=["fact"])),
            ("vendor", VarState(value="Bank2000", display="Bank2000", value_sources=["default"])),
            ("__date__", VarState(value="2026-04-25", display="2026-04-25", value_sources=["rule:bill"])),
            ("empty", VarState(value=None, display="", value_sources=[])),
        ),
    )
    text = plan.snapshot(resolved)
    assert "__kind__" not in text
    assert "Bank2000" in text
    assert "__date__" in text
    assert "empty" not in text
