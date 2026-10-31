"""Input walks."""

import hashlib
import logging
import os
from datetime import datetime
from pathlib import Path

import pytest

from supershelf.configs import ShelfConfig
from supershelf.constants import LOGGER_NAME
from supershelf.errors import SupershelfError
from supershelf.profile import ShelfProfile
from supershelf.scan import InputFile, InputScanResult, ResolvedInput, filter_kept

HELLO = b"hello"
HELLO_HASH = hashlib.sha256(HELLO).hexdigest()


def _profile(tmp_path: Path, body: str, name: str = "work") -> ShelfProfile:
    path = tmp_path / f"profile.{name}.toml"
    path.write_text(body, encoding="utf-8")
    loaded = ShelfConfig.from_path(path, logging.getLogger(LOGGER_NAME))
    return ShelfProfile.from_config(loaded)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _tree(root: Path) -> None:
    _write(root / "a.jpg", "a")
    _write(root / "note.txt", "note")
    _write(root / ".hidden.txt", "hidden")
    (root / "empty.txt").write_bytes(b"")
    _write(root / "sub" / "b.jpg", "b")
    _write(root / "sub" / "nested" / "c.jpg", "c")
    _write(root / "cache" / "x.jpg", "x")


def _scan(tmp_path: Path, inputs: str, *, quick: bool = False) -> list:
    inbox = tmp_path / "inbox"
    inbox.mkdir(exist_ok=True)
    _tree(inbox)
    profile = _profile(
        tmp_path,
        "[config]\nprofile = 'work'\n\n" + inputs,
    )
    return profile.scan(quick=quick)


def _paths(results) -> list[str]:
    assert len(results) == 1
    return [item.path for item in results[0].results]


def test_depth_limits_subdirectory_levels(tmp_path: Path) -> None:
    unlimited = _paths(_scan(tmp_path, "[[inputs]]\npath = 'inbox'\ndepth = 0\n"))
    assert "sub/nested/c.jpg" in unlimited
    assert "empty.txt" not in unlimited
    assert ".hidden.txt" in unlimited

    first = _paths(_scan(tmp_path, "[[inputs]]\npath = 'inbox'\ndepth = 1\n"))
    assert first == [".hidden.txt", "a.jpg", "note.txt"]

    second = _paths(_scan(tmp_path, "[[inputs]]\npath = 'inbox'\ndepth = 2\n"))
    assert "sub/b.jpg" in second
    assert "sub/nested/c.jpg" not in second


def test_star_stays_in_one_directory_and_exclude_runs_after_include(
    tmp_path: Path,
) -> None:
    top = _paths(
        _scan(tmp_path, "[[inputs]]\npath = 'inbox'\ninclude = ['*.jpg']\n")
    )
    assert top == ["a.jpg"]

    nested = _paths(
        _scan(
            tmp_path,
            "[[inputs]]\npath = 'inbox'\n"
            "include = ['**/*.jpg']\n"
            "exclude = ['**/cache/**']\n",
        )
    )
    assert "a.jpg" in nested
    assert "sub/nested/c.jpg" in nested
    assert "cache/x.jpg" not in nested
    assert "note.txt" not in nested


def test_relative_input_path_resolves_from_root_dir(tmp_path: Path) -> None:
    store = tmp_path / "store" / "inbox"
    _write(store / "note.txt", "note")
    profile = _profile(
        tmp_path,
        "[config]\nroot_dir = 'store'\n\n[[inputs]]\npath = 'inbox'\n",
    )

    results = profile.scan()

    assert results[0].config.path == store.resolve()
    assert [item.path for item in results[0].results] == ["note.txt"]
    assert profile.database_file.exists() is False


def test_file_fields_and_metadata(tmp_path: Path) -> None:
    profile = _profile(tmp_path, "[[inputs]]\npath = 'inbox'\ndepth = 2\n")
    inbox = tmp_path / "inbox"
    _write(inbox / "sub" / "b.jpg", "b")

    found = profile.scan()[0].results[0]

    assert found.path == "sub/b.jpg"
    assert found.directory == "sub"
    assert found.parent == "sub"
    assert found.stem == "b"
    assert found.suffix == ".jpg"
    assert found.absolute == inbox.resolve() / "sub" / "b.jpg"
    assert found.sha256 == hashlib.sha256(b"b").hexdigest()
    parsed = datetime.fromisoformat(found.mtime or "")
    assert parsed.tzinfo is not None
    assert found.mtime is not None and found.mtime.endswith("+00:00")
    assert found.ctime is not None and found.ctime.endswith("+00:00")
    assert profile.show_time(found.mtime or "") == datetime.fromisoformat(
        found.mtime or ""
    ).strftime(profile.default_date_format)


def test_quick_skips_metadata_but_still_ignores_empty_files(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _write(inbox / "a.txt", "hello")
    (inbox / "empty.txt").write_bytes(b"")
    profile = _profile(tmp_path, "[[inputs]]\npath = 'inbox'\n")

    found = profile.scan(quick=True)[0].results

    assert [item.path for item in found] == ["a.txt"]
    assert found[0].mtime is None
    assert found[0].ctime is None
    assert found[0].sha256 is None


def test_followed_symlink_keeps_the_path_under_the_input(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "real.txt").write_bytes(HELLO)
    (inbox / "alias.txt").symlink_to(inbox / "real.txt")
    profile = _profile(tmp_path, "[[inputs]]\npath = 'inbox'\n")

    found = {item.path: item for item in profile.scan()[0].results}

    assert found["alias.txt"].path == "alias.txt"
    assert found["alias.txt"].absolute.name == "alias.txt"
    assert found["alias.txt"].sha256 == HELLO_HASH
    assert found["real.txt"].sha256 == HELLO_HASH


def test_follow_symlinks_false_skips_links(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "real.txt").write_bytes(HELLO)
    (inbox / "alias.txt").symlink_to(inbox / "real.txt")
    profile = _profile(
        tmp_path,
        "[[inputs]]\npath = 'inbox'\nfollow_symlinks = false\n",
    )

    assert _paths(profile.scan()) == ["real.txt"]


def test_symlink_cycle_warns_and_skips(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a.txt").write_bytes(HELLO)
    (inbox / "loop").symlink_to(inbox, target_is_directory=True)
    profile = _profile(tmp_path, "[[inputs]]\npath = 'inbox'\n")

    assert _paths(profile.scan()) == ["a.txt"]
    assert "Symlink cycle" in caplog.text


def test_input_index_keeps_the_config_position(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)
    _write(tmp_path / "one" / "a.txt", "a")
    _write(tmp_path / "two" / "b.txt", "b")
    profile = _profile(
        tmp_path,
        "[[inputs]]\npath = 'missing'\n\n[[inputs]]\npath = 'one'\n\n"
        "[[inputs]]\npath = 'two'\n",
    )

    assert [item.index for item in profile.scan()] == [2, 3]


def test_show_time_uses_the_profile_format(tmp_path: Path) -> None:
    profile = _profile(
        tmp_path,
        "[config]\ndefault_date_format = '%d/%m/%Y'\n",
    )

    assert profile.show_time("2026-10-29T16:28:00+00:00") == "29/10/2026"


def test_missing_input_directory_warns(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)
    profile = _profile(tmp_path, "[[inputs]]\npath = 'missing'\n")

    assert profile.scan() == []
    assert "missing" in caplog.text


def test_input_path_that_is_a_file_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    profile = _profile(tmp_path, "[[inputs]]\npath = 'a.txt'\n")

    with pytest.raises(SupershelfError, match="not a directory"):
        profile.scan()


def test_negative_depth_is_an_error(tmp_path: Path) -> None:
    profile = _profile(tmp_path, "[[inputs]]\npath = 'inbox'\ndepth = -1\n")

    with pytest.raises(SupershelfError, match="depth"):
        profile.scan()


def test_unknown_input_key_is_an_error(tmp_path: Path) -> None:
    profile = _profile(tmp_path, "[[inputs]]\npath = 'inbox'\nbogus = true\n")

    with pytest.raises(SupershelfError, match="bogus"):
        profile.scan()


def test_profile_without_inputs_is_an_error(tmp_path: Path) -> None:
    profile = _profile(tmp_path, "[config]\nprofile = 'work'\n")

    with pytest.raises(SupershelfError, match="no inputs"):
        profile.scan()


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read mode 000 files")
def test_unreadable_file_and_directory_are_warnings(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)
    inbox = tmp_path / "inbox"
    secret = inbox / "secret.txt"
    locked = inbox / "locked"
    _write(secret, "nope")
    _write(locked / "x.txt", "x")
    _write(inbox / "ok.txt", "ok")
    secret.chmod(0)
    locked.chmod(0)
    profile = _profile(tmp_path, "[[inputs]]\npath = 'inbox'\n")
    try:
        paths = _paths(profile.scan())
    finally:
        secret.chmod(0o644)
        locked.chmod(0o755)

    assert paths == ["ok.txt"]
    assert "Cannot read" in caplog.text


def _result(*paths: str, index: int = 1, profile: str = "work") -> InputScanResult:
    return InputScanResult(
        profile=profile,
        index=index,
        config=ResolvedInput(
            path=Path("/inbox"),
            include=None,
            exclude=None,
            depth=0,
            follow_symlinks=True,
        ),
        results=[
            InputFile.from_relative(path, Path("/inbox") / path) for path in paths
        ],
    )


def _selected(groups: list[list[InputScanResult]]) -> list[list[str]]:
    return [
        [found.path for found in scan.results]
        for scans in groups
        for scan in scans
    ]


def test_filter_kept_without_a_path_returns_every_file() -> None:
    groups = [[_result("a.txt", "b.txt")]]

    assert filter_kept(groups, None) is groups


def test_filter_kept_exact_file_drops_a_longer_prefix() -> None:
    groups = [[_result("a.txt", "a.txt.bak", "b.txt")]]

    chosen = filter_kept(groups, "a.txt")

    assert _selected(chosen) == [["a.txt"]]
    assert [found.path for found in groups[0][0].results] == [
        "a.txt",
        "a.txt.bak",
        "b.txt",
    ]


def test_filter_kept_prefix_selects_paths_that_start_with() -> None:
    groups = [[_result("Bank2000/file.pdf", "Bank.txt", "notes/a.txt")]]

    chosen = filter_kept(groups, "Bank")

    assert _selected(chosen) == [["Bank2000/file.pdf", "Bank.txt"]]


def test_filter_kept_exact_file_applies_to_every_input() -> None:
    groups = [
        [_result("a.txt", "a.txt.bak"), _result("a.txt.bak", index=2)],
        [_result("a.txt", profile="home")],
    ]

    chosen = filter_kept(groups, "a.txt")

    assert _selected(chosen) == [["a.txt"], [], ["a.txt"]]


def test_filter_kept_leaves_an_unmatched_input_empty() -> None:
    groups = [[_result("Bank2000/file.pdf"), _result("notes/a.txt", index=2)]]

    chosen = filter_kept(groups, "Bank")

    assert _selected(chosen) == [["Bank2000/file.pdf"], []]


def test_filter_kept_unknown_path_is_an_error() -> None:
    with pytest.raises(SupershelfError, match="No kept file 'missing.pdf'"):
        filter_kept([[_result("a.txt")]], "missing.pdf")
