"""Generic command driver, output formats, and ProcessRunner."""

import sys
from pathlib import Path

import pytest

from supershelf.errors import VarCandidateError, VarConfigError
from supershelf.match import FileMatch, Matcher
from supershelf.metadata.parse import OutputParser
from supershelf.metadata.process import ProcessRunner
from supershelf.scan import InputFile
from supershelf.vars import VarPlan


class FakeRunner(ProcessRunner):
    """Records argv. Does not spawn the named program."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[list[str]] = []
        self.which_calls: list[str] = []
        self.available: set[str] = set()
        self.output: dict[str, str] = {}
        self.codes: dict[str, int] = {}

    def which(self, name: str) -> str | None:
        self.which_calls.append(name)
        if name in self.available or name in self.output:
            return name
        return None

    def run(self, argv: list[str], timeout: float) -> str:
        del timeout
        self.calls.append(list(argv))
        program = argv[0]
        code = self.codes.get(program, 0)
        if code != 0:
            raise VarCandidateError(f"{program} exited {code}")
        return self.output.get(program, "")


def _file(relative: str = "a.txt", absolute: Path | None = None) -> InputFile:
    path = Path("/tmp") / relative if absolute is None else absolute
    item = InputFile.from_relative(relative, path)
    item.mtime = "2026-01-01T00:00:00+00:00"
    item.ctime = "2026-01-02T00:00:00+00:00"
    item.sha256 = "abc"
    return item


def _plan(
    document: dict[str, object],
    root: Path,
    runner: FakeRunner,
    scope: dict[str, object] | None = None,
) -> VarPlan:
    matcher = Matcher.from_document(document, "work")
    full: dict[str, object] = {
        "__root_dir__": str(root),
        "__profile__": "work",
        "__profile_dir__": str(root),
    }
    if scope:
        full.update(scope)
    return VarPlan.from_document(
        document,
        "work",
        matcher,
        root,
        full,
        runner=runner,
    )


def _values(plan: VarPlan, file: InputFile | None = None) -> dict[str, str]:
    chosen = _file() if file is None else file
    match = FileMatch("work", 1, chosen.path, "note", "notes", {})
    return dict(plan.resolve(chosen, match, Path("/in")).items)


def test_parser_samples_from_the_spec() -> None:
    parser = OutputParser()
    shell = parser.parse("shell", "title=Quarterly report\npages=12\n")
    assert shell == {"title": "Quarterly report", "pages": "12"}
    yaml = parser.parse("yaml", "info:\n  title: Quarterly report\n")
    assert yaml == {"info.title": "Quarterly report"}
    toml = parser.parse("toml", 'title = "Quarterly report"\npages = "12"\n')
    assert toml["title"] == "Quarterly report"
    assert toml["pages"] == "12"
    ini = parser.parse("ini", "[doc]\ntitle = Quarterly report\n")
    assert ini["doc.title"] == "Quarterly report"


def test_shell_skips_comments_and_keeps_the_last_repeat() -> None:
    parsed = OutputParser().parse(
        "shell",
        "# comment\n\nexport title='Quarterly report'\ntitle=\"Later\"\n",
    )
    assert parsed["title"] == "Later"


def test_bad_shell_key_and_toml_duplicate_fail() -> None:
    with pytest.raises(VarCandidateError):
        OutputParser().parse("shell", "1bad=value\n")
    with pytest.raises(VarCandidateError):
        OutputParser().parse("toml", 'title = "a"\ntitle = "b"\n')
    with pytest.raises(VarCandidateError):
        OutputParser().parse("yaml", "- not a mapping\n")


def test_percent_p_keeps_a_path_with_a_space(tmp_path: Path) -> None:
    runner = FakeRunner()
    runner.available.add("tagtool")
    runner.output["tagtool"] = "title=Quarterly report\n"
    plan = _plan(
        {
            "metadata_driver": {
                "tags": {
                    "driver": "supershelf.meta_driver",
                    "command": "tagtool",
                    "arguments": ["--path", "%p", "--name", "%n"],
                    "output_format": "shell",
                }
            },
            "default_vars": {"title": '{{ meta("tags", "title") }}'},
        },
        tmp_path,
        runner,
    )
    values = _values(plan, _file("my file.pdf", Path("/tmp/my file.pdf")))
    assert values["title"] == "Quarterly report"
    assert runner.calls == [["tagtool", "--path", "/tmp/my file.pdf", "--name", "my file.pdf"]]


def test_script_path_is_the_program(tmp_path: Path) -> None:
    script = tmp_path / "tools" / "covers.sh"
    script.parent.mkdir()
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    resolved = str(script.resolve())
    runner = FakeRunner()
    runner.output[resolved] = "title=Quarterly report\npages=12\n"
    plan = _plan(
        {
            "metadata_driver": {
                "covers": {
                    "driver": "supershelf.meta_driver",
                    "command": "tools/covers.sh",
                    "arguments": "--file %p --hash %h --lang eng",
                    "output_format": "shell",
                    "ext": ["pdf"],
                }
            },
            "default_vars": {"title": '{{ meta("covers", "title") }}'},
        },
        tmp_path,
        runner,
    )
    values = _values(plan, _file("report.pdf", tmp_path / "report.pdf"))
    assert values["title"] == "Quarterly report"
    assert runner.calls[0][0] == resolved
    assert runner.calls[0][1:] == [
        "--file",
        str(tmp_path / "report.pdf"),
        "--hash",
        "abc",
        "--lang",
        "eng",
    ]
    assert "sh" not in runner.calls[0]


def test_two_command_drivers_do_not_share_a_bag(tmp_path: Path) -> None:
    script = tmp_path / "tools" / "covers.sh"
    script.parent.mkdir()
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    resolved = str(script.resolve())
    runner = FakeRunner()
    runner.available.add("tagtool")
    runner.output[resolved] = "title=From covers\n"
    runner.output["tagtool"] = "info:\n  title: From tags\n"
    plan = _plan(
        {
            "metadata_driver": {
                "covers": {
                    "driver": "supershelf.meta_driver",
                    "command": "tools/covers.sh",
                    "arguments": "%p",
                    "output_format": "shell",
                },
                "tags": {
                    "driver": "supershelf.meta_driver",
                    "command": "tagtool",
                    "arguments": ["%p"],
                    "output_format": "yaml",
                    "timeout": 5,
                },
            },
            "default_vars": {
                "cover": '{{ meta("covers", "title") }}',
                "tag": '{{ meta("tags", "info.title") }}',
            },
        },
        tmp_path,
        runner,
    )
    values = _values(plan, _file("report.pdf", tmp_path / "report.pdf"))
    assert values["cover"] == "From covers"
    assert values["tag"] == "From tags"
    assert [call[0] for call in runner.calls] == [resolved, "tagtool"]
    covers = plan.metadata.entry("covers")
    tags = plan.metadata.entry("tags")
    assert covers is not None and tags is not None
    assert covers.options.options_key != tags.options.options_key
    assert covers.driver is tags.driver


def test_bad_quote_and_unknown_token_fail_at_load(tmp_path: Path) -> None:
    runner = FakeRunner()
    with pytest.raises(VarConfigError, match="quote"):
        _plan(
            {
                "metadata_driver": {
                    "covers": {
                        "driver": "supershelf.meta_driver",
                        "command": "tagtool",
                        "arguments": "\"unterminated",
                        "output_format": "shell",
                    }
                }
            },
            tmp_path,
            runner,
        )
    with pytest.raises(VarConfigError, match="placeholder"):
        _plan(
            {
                "metadata_driver": {
                    "covers": {
                        "driver": "supershelf.meta_driver",
                        "command": "tagtool",
                        "arguments": ["%q"],
                        "output_format": "shell",
                    }
                }
            },
            tmp_path,
            runner,
        )


def test_process_runner_maps_exit_timeout_and_encoding() -> None:
    runner = ProcessRunner()
    with pytest.raises(VarCandidateError, match="exited"):
        runner.run([sys.executable, "-c", "import sys; sys.exit(3)"], 5)
    with pytest.raises(VarCandidateError, match="UTF-8"):
        runner.run(
            [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'\\xff')"],
            5,
        )
    with pytest.raises(VarCandidateError, match="timed out"):
        runner.run([sys.executable, "-c", "import time; time.sleep(5)"], 0.2)


def test_options_key_ignores_ext_and_timeout(tmp_path: Path) -> None:
    runner = FakeRunner()
    runner.available.add("tagtool")

    def key(ext: list[str], timeout: int) -> str:
        plan = _plan(
            {
                "metadata_driver": {
                    "tags": {
                        "driver": "supershelf.meta_driver",
                        "command": "tagtool",
                        "arguments": ["%p"],
                        "output_format": "yaml",
                        "ext": ext,
                        "timeout": timeout,
                    }
                }
            },
            tmp_path,
            runner,
        )
        entry = plan.metadata.entry("tags")
        assert entry is not None
        return entry.options.options_key

    assert key(["pdf"], 5) == key(["txt"], 30)
