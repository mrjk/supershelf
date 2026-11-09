"""Link rules: path, hash, duplicates, missing, unmatched, and the path filter."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

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
    STATUS_DUPLICATE,
    STATUS_REFRESH,
    STATUS_UNCHANGED,
)
from supershelf.database import DocumentRow, ShelfDatabase
from supershelf.errors import RecordConfigError
from supershelf.record import (
    DuplicateListing,
    LiveFile,
    RecordIdentity,
    RecordPlan,
    RecordSession,
)
from supershelf.scan import KeptPath
from supershelf.scan.match import Matcher
from supershelf.vars import FileVars, VarPlan, VarState
from tests.helpers import isolate_env

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
        "steps": ("path", "hash"),
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
    rule: str = "bill",
) -> DocumentRow:
    live = _live(
        path,
        digest,
        input_path=input_path,
        vars_json=vars_json,
        mtime=mtime,
        input_index=index,
        rule=rule,
    )
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


def _steps_from(identity: str | tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(identity, tuple):
        return identity
    if identity == "hash":
        return ("hash", "path")
    return ("path", "hash")


def _planner(
    documents: list[DocumentRow],
    live: list[LiveFile],
    *,
    identity: str | tuple[str, ...] = "path",
    kept: set[tuple[str, str]] | None = None,
    walked: set[str] | None = None,
    selector: str | None = None,
    paths: list[str] | None = None,
    rules: dict[str, tuple[str, ...]] | None = None,
    prior: dict[int, str] | None = None,
    profile: str = "",
) -> RecordPlan:
    steps = _steps_from(identity)
    prepared: list[LiveFile] = []
    for item in live:
        file_steps = steps
        if rules is not None and item.rule in rules:
            file_steps = rules[item.rule]
        prepared.append(replace(item, steps=file_steps))
    rule_map: dict[str, tuple[str, ...]] = {}
    for document in documents:
        rule_map.setdefault(document.rule, steps)
    for item in prepared:
        rule_map[item.rule] = item.steps
    if rules:
        rule_map.update(rules)
    if prior is None:
        word = identity if isinstance(identity, str) else steps[0]
        prior = {document.id: word for document in documents}
    observed = paths if paths is not None else [item.path for item in live]
    return RecordPlan(
        documents,
        prepared,
        kept if kept is not None else {item.location() for item in live},
        walked if walked is not None else {_IN},
        KeptPath.from_paths(selector, observed),
        rule_map,
        prior,
        profile=profile,
    )


def _plan(
    documents: list[DocumentRow],
    live: list[LiveFile],
    *,
    identity: str | tuple[str, ...] = "path",
    kept: set[tuple[str, str]] | None = None,
    walked: set[str] | None = None,
    selector: str | None = None,
    paths: list[str] | None = None,
    rules: dict[str, tuple[str, ...]] | None = None,
    prior: dict[int, str] | None = None,
    profile: str = "",
) -> list:
    return _planner(
        documents,
        live,
        identity=identity,
        kept=kept,
        walked=walked,
        selector=selector,
        paths=paths,
        rules=rules,
        prior=prior,
        profile=profile,
    ).rows()


def _statuses(rows: list) -> list[tuple[str, str]]:
    return [(row.status, row.file.path) for row in rows]


def test_identity_precedence() -> None:
    assert RecordIdentity.resolve({}, None, {}) == ("path", "hash")
    assert RecordIdentity.resolve({"record_identity": "hash"}, None, {}) == ("hash", "path")
    assert RecordIdentity.resolve({"record_identity": None}, None, {}) == ("path", "hash")
    assert RecordIdentity.resolve({"record_identity": ["path", "hash"]}, None, {}) == (
        "path",
        "hash",
    )
    assert RecordIdentity.resolve({"record_identity": ["hash"]}, None, {}) == ("hash",)
    assert RecordIdentity.resolve({}, "hash, path", {}) == ("hash", "path")
    assert (
        RecordIdentity.resolve(
            {"record_identity": "path"},
            None,
            {ENV_RECORD_IDENTITY: "hash"},
        )
        == ("hash", "path")
    )
    assert (
        RecordIdentity.resolve(
            {"record_identity": "hash"},
            "path",
            {ENV_RECORD_IDENTITY: "hash"},
        )
        == ("path", "hash")
    )
    assert RecordIdentity.same("path", ("path", "hash"))
    assert RecordIdentity.same("hash", ("hash", "path"))
    assert RecordIdentity.same("path", ("path",))
    assert RecordIdentity.same("path,hash", ("path",)) is False
    assert RecordIdentity.same("path,hash", ("path", "hash"))
    rules = RecordIdentity.rule_lists(
        {
            "match_rules": [
                {"name": "bill"},
                {"name": "draft", "record_identity": None},
                {"name": "note", "record_identity": ["path"]},
            ]
        },
        "work",
        ("hash", "path"),
    )
    assert rules["bill"] == ("hash", "path")
    assert rules["draft"] == ("hash", "path")
    assert rules["note"] == ("path",)


def test_identity_rejects_a_bad_word() -> None:
    with pytest.raises(RecordConfigError, match="config.record_identity") as caught:
        RecordIdentity.resolve({"record_identity": "PATH"}, None, {})
    assert caught.value.rc == 2
    with pytest.raises(RecordConfigError, match=ENV_RECORD_IDENTITY):
        RecordIdentity.resolve({}, None, {ENV_RECORD_IDENTITY: ""})
    with pytest.raises(RecordConfigError, match="--record-identity"):
        RecordIdentity.resolve({}, "path,", {})
    with pytest.raises(RecordConfigError, match="config.record_identity"):
        RecordIdentity.resolve({"record_identity": []}, None, {})
    with pytest.raises(RecordConfigError, match="config.record_identity"):
        RecordIdentity.resolve({"record_identity": ["path", "path"]}, None, {})
    with pytest.raises(RecordConfigError, match="config.record_identity"):
        RecordIdentity.resolve({"record_identity": "{{ author }}"}, None, {})
    with pytest.raises(RecordConfigError, match="config.record_identity"):
        RecordIdentity.resolve({"record_identity": "key"}, None, {})
    with pytest.raises(RecordConfigError, match="config.record_identity"):
        RecordIdentity.resolve({"record_identity": "hash, path"}, None, {})
    with pytest.raises(RecordConfigError, match="Profile work match rule other") as caught:
        RecordIdentity.rule_lists(
            {
                "match_rules": [
                    {"name": "bill", "glob": "**"},
                    {"name": "other", "glob": "nope-*", "record_identity": "HASH"},
                ]
            },
            "work",
            ("path", "hash"),
        )
    assert caught.value.rc == 2


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
    assert rows[0].identity == "path"
    hashed = _plan([_doc(1, "a.pdf")], [_live("b.pdf")], identity="hash", kept=set())
    assert _statuses(hashed) == [(EVENT_MOVE, "b.pdf")]
    assert hashed[0].identity == "hash"


def test_generation_when_bytes_change_at_the_same_path() -> None:
    rows = _plan([_doc(1, "a.pdf")], [_live("a.pdf", _H2)])
    assert _statuses(rows) == [(EVENT_GENERATION, "a.pdf")]
    assert rows[0].generation == 2
    assert rows[0].file.hash == _H2
    assert rows[0].identity == "path"
    hashed = _plan([_doc(1, "a.pdf")], [_live("a.pdf", _H2)], identity="hash")
    assert _statuses(hashed) == [(EVENT_GENERATION, "a.pdf")]
    assert hashed[0].identity == "hash"


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
    rows = _plan(
        [_doc(1, "a.pdf")],
        [],
        kept=kept,
        rules={"bill": ("hash", "path")},
    )
    assert _statuses(rows) == [(EVENT_UNMATCHED, "a.pdf")]
    assert rows[0].identity == "path"
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
        [_doc(1, "a.pdf")],
        live,
        {live[0].location()},
        {_IN},
        KeptPath.from_paths(None, ["a.pdf"]),
        {"bill": ("path", "hash")},
        {1: "path"},
        ignored={(_IN, "a.pdf")},
    )
    assert plan.rows() == []


def test_first_run_under_hash_keeps_the_lower_path() -> None:
    rows = _plan([], [_live("b.pdf"), _live("a.pdf")], identity="hash")
    by_path = {row.file.path: row for row in rows}
    assert by_path["a.pdf"].status == EVENT_NEW
    assert by_path["b.pdf"].status == STATUS_DUPLICATE
    assert by_path["b.pdf"].change() is None
    assert by_path["a.pdf"].duplicates == 1
    assert by_path["b.pdf"].duplicates == 1
    assert by_path["b.pdf"].file.hash == _H1


def test_hash_only_in_place_change_is_missing_plus_new() -> None:
    rows = _plan([_doc(1, "a.pdf")], [_live("a.pdf", _H2)], identity=("hash",))
    assert _statuses(rows) == [(EVENT_MISSING, "a.pdf"), (EVENT_NEW, "a.pdf")]
    assert rows[1].file.hash == _H2
    assert rows[1].document_id is None


def test_path_only_rename_is_missing_plus_new() -> None:
    rows = _plan(
        [_doc(1, "a.pdf")],
        [_live("b.pdf")],
        identity=("path",),
        kept=set(),
    )
    assert _statuses(rows) == [(EVENT_MISSING, "a.pdf"), (EVENT_NEW, "b.pdf")]
    assert rows[0].identity == "path"
    assert rows[1].identity == "path"


def test_hash_onto_a_stay_generates_the_replaced_path() -> None:
    rows = _plan(
        [_doc(1, "a.pdf"), _doc(2, "b.pdf")],
        [_live("a.pdf", _H2), _live("b.pdf")],
        identity="hash",
    )
    assert _statuses(rows) == [(EVENT_GENERATION, "a.pdf"), (STATUS_UNCHANGED, "b.pdf")]
    assert rows[0].document_id == 1
    assert rows[0].generation == 2
    assert rows[1].document_id == 2
    assert rows[0].change() is not None
    assert rows[1].change() is None


def test_several_hash_successors_move_to_the_lower_path() -> None:
    plan = _planner(
        [_doc(1, "a.pdf")],
        [_live("c.pdf"), _live("b.pdf")],
        identity="hash",
        kept=set(),
        profile="work",
    )
    rows = plan.rows()
    assert _statuses(rows) == [(EVENT_MOVE, "b.pdf"), (STATUS_DUPLICATE, "c.pdf")]
    assert rows[0].document_id == 1
    assert rows[1].change() is None
    assert len(plan.warnings) == 1
    warning = plan.warnings[0]
    assert "document 1" in warning
    assert _H1 in warning
    assert "b.pdf" in warning
    assert "c.pdf" in warning


def test_hash_collision_with_two_successors_warns() -> None:
    plan = _planner(
        [_doc(1, "a.pdf")],
        [_live("a.pdf", _H2), _live("c.pdf"), _live("b.pdf")],
        identity="hash",
        profile="work",
    )
    rows = plan.rows()
    by_path = {row.file.path: row for row in rows}
    assert by_path["b.pdf"].status == EVENT_MOVE
    assert by_path["b.pdf"].document_id == 1
    assert by_path["c.pdf"].status == STATUS_DUPLICATE
    assert by_path["a.pdf"].status == EVENT_NEW
    assert by_path["a.pdf"].file.hash == _H2
    assert len(plan.warnings) == 1
    assert "b.pdf" in plan.warnings[0]
    assert "c.pdf" in plan.warnings[0]


def test_mixed_rules_do_not_absorb_a_path_only_file() -> None:
    rules = {"invoice": ("hash", "path"), "draft": ("path",)}
    rows = _plan(
        [],
        [_live("a.pdf", rule="invoice"), _live("b.pdf", rule="draft")],
        rules=rules,
    )
    assert _statuses(rows) == [(EVENT_NEW, "a.pdf"), (EVENT_NEW, "b.pdf")]
    stayed = _plan(
        [_doc(1, "a.pdf", rule="invoice"), _doc(2, "b.pdf", rule="draft")],
        [_live("a.pdf", rule="invoice"), _live("b.pdf", rule="draft")],
        rules=rules,
    )
    assert _statuses(stayed) == [(STATUS_UNCHANGED, "a.pdf"), (STATUS_UNCHANGED, "b.pdf")]
    assert all(row.status != STATUS_DUPLICATE for row in stayed)


def test_hash_does_not_merge_two_stored_documents() -> None:
    rows = _plan(
        [_doc(1, "a.pdf"), _doc(2, "b.pdf")],
        [_live("a.pdf"), _live("b.pdf"), _live("c.pdf")],
        identity="hash",
    )
    assert _statuses(rows) == [
        (STATUS_UNCHANGED, "a.pdf"),
        (STATUS_UNCHANGED, "b.pdf"),
        (STATUS_DUPLICATE, "c.pdf"),
    ]
    assert rows[0].document_id == 1
    assert rows[1].document_id == 2
    assert rows[2].document_id is None
    assert rows[2].change() is None
    assert rows[2].file.hash == _H1


def test_rule_change_stores_the_new_first_step_and_warns_once() -> None:
    plan = _planner(
        [_doc(1, "a.pdf", rule="bill")],
        [_live("a.pdf", rule="invoice")],
        rules={"invoice": ("hash", "path"), "bill": ("path", "hash")},
        prior={1: "path"},
        profile="work",
    )
    rows = plan.rows()
    assert rows[0].status == EVENT_VARS
    assert rows[0].identity == "hash"
    assert rows[0].file.rule == "invoice"
    assert len(plan.warnings) == 1
    warning = plan.warnings[0]
    assert "match rule invoice" in warning
    assert "path,hash" in warning
    assert "hash,path" in warning


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
        {"vars_schema": {"vendor": {"type": "text"}, "issued": {"type": "date"}}},
        "work",
        Matcher.from_document({}, "work"),
        tmp_path,
        {"__profile__": {"name": "work"}, "__config__": {"root_dir": str(tmp_path)}},
    )
    resolved = FileVars(
        "bill",
        "bill",
        (
            ("__kind__", VarState(value="bill", display="bill", value_sources=["fact"])),
            ("vendor", VarState(value="Bank2000", display="Bank2000", value_sources=["default"])),
            ("issued", VarState(value="2026-04-25", display="2026-04-25", value_sources=["rule:bill"])),
            ("empty", VarState(value=None, display="", value_sources=[])),
        ),
    )
    text = plan.snapshot(resolved)
    assert "__kind__" not in text
    assert "Bank2000" in text
    assert "issued" in text
    body = json.loads(text)
    assert body["empty"] == {
        "type": "text",
        "value": None,
        "display": "",
        "value_sources": [],
    }


def test_a_second_missing_run_prints_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    target = inbox / "a.pdf"
    target.write_bytes(b"bank-2000")
    (tmp_path / "profile.work.toml").write_text(
        """\
[[inputs]]
path = "inbox"

[[match_rules]]
name = "bill"
glob = "**"
""",
        encoding="utf-8",
    )
    first = RecordSession.load(None, None, None).run(None, dry_run=False)
    assert [row["status"] for row in first] == ["new"]
    target.unlink()
    missing = RecordSession.load(None, None, None).run(None, dry_run=False)
    assert [row["status"] for row in missing] == ["missing"]
    again = RecordSession.load(None, None, None).run(None, dry_run=False)
    assert again == []
    with ShelfDatabase.open_read(tmp_path / "profile.work.sqlite") as database:
        documents = database.documents()
    assert len(documents) == 1
    assert documents[0].presence == PRESENCE_MISSING
