"""Runner receipts distinguish file-job failures from reported test outcomes."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import run_tests_parallel as runner


def _run_summary(monkeypatch, capsys, results, collected):
    root = Path(runner.__file__).resolve().parent.parent
    files = [root / "tests" / name for name in results]
    monkeypatch.setattr(sys, "argv", [runner.__file__, "-j", "1"])
    monkeypatch.setattr(runner, "_discover_files", lambda _roots: files)
    monkeypatch.setattr(
        runner, "_count_tests",
        lambda *_args: {file: collected[file.name] for file in files},
    )
    monkeypatch.setattr(runner, "_save_durations", lambda *_args: None)

    def run_file(file, *_args):
        result = results[file.name]
        if isinstance(result, Exception):
            raise result
        rc, output, summary = result
        return file, rc, output, summary, 0.01

    monkeypatch.setattr(runner, "_run_one_file", run_file)
    rc = runner.main()
    return rc, capsys.readouterr().out


def test_timeout_preserves_reported_passes_without_claiming_all_tests_completed(
    monkeypatch, capsys,
):
    rc, output = _run_summary(monkeypatch, capsys, {
        "test_pass.py": (0, "70 passed in 1s", {"passed": 70}),
        "test_timeout.py": (124, "collected 45 items\n..............................", {}),
    }, {"test_pass.py": 70, "test_timeout.py": 45})

    assert rc == 1
    assert "1 successful, 1 failed (1 timed out)" in output
    assert "70 passed, 0 failed, 0 errors" in output
    assert "1 file with unavailable test-outcome summaries" in output
    assert "100% complete" not in output
    assert "no tests ran" not in output
    assert "timeout" in output


@pytest.mark.parametrize("passed, errors, exit_code", [(1, 1, 1), (0, 2, 2)])
def test_setup_or_collection_errors_do_not_claim_all_tests_passed(
    monkeypatch, capsys, passed, errors, exit_code,
):
    # Pytest uses singular "error" for a single setup/collection failure.
    pytest_output = f"{passed} passed, {errors} error{'s' if errors != 1 else ''} in 1s"
    rc, output = _run_summary(monkeypatch, capsys, {
        "test_error.py": (
            exit_code, pytest_output, runner._parse_pytest_summary(pytest_output),
        ),
    }, {"test_error.py": passed + errors})

    assert rc == 1
    assert "0 successful, 1 failed (0 timed out)" in output
    assert f"{passed} passed, 0 failed, {errors} errors" in output
    assert "reported pytest errors" in output
    assert "all tests passed" not in output


def test_runner_exception_does_not_invent_a_test_failure_or_no_tests_ran(
    monkeypatch, capsys,
):
    rc, output = _run_summary(monkeypatch, capsys, {
        "test_crash.py": OSError("unable to launch child"),
    }, {"test_crash.py": 8})

    assert rc == 1
    assert "0 successful, 1 failed (0 timed out)" in output
    assert "0 passed, 0 failed, 0 errors" in output
    assert "unavailable test-outcome summaries" in output
    assert "no tests ran" not in output
    assert "runner crashed" in output


def test_nonzero_exit_with_passes_only_does_not_claim_all_passed(monkeypatch, capsys):
    rc, output = _run_summary(monkeypatch, capsys, {
        "test_partial.py": (2, "2 passed in 1s", {"passed": 2}),
    }, {"test_partial.py": 5})

    assert rc == 1
    assert "2 passed, 0 failed, 0 errors" in output
    assert "non-zero exits without reported test failures or pytest errors" in output
    assert "all tests passed" not in output


@pytest.mark.parametrize("outcomes", [
    {"passed": 2, "skipped": 3}, {"skipped": 3}, {"xfailed": 4},
])
def test_success_keeps_nonpassing_outcomes_distinct(monkeypatch, capsys, outcomes):
    rc, output = _run_summary(monkeypatch, capsys, {
        "test_ok.py": (0, "reported outcomes", outcomes),
    }, {"test_ok.py": sum(outcomes.values())})

    assert rc == 0
    assert "1 successful, 0 failed (0 timed out)" in output
    assert f"{outcomes.get('passed', 0)} passed, 0 failed, 0 errors" in output
    for name in ("skipped", "xfailed"):
        assert f"{outcomes.get(name, 0)} {name}" in output
    assert "unavailable test-outcome summaries" not in output


def test_wrapper_reports_real_timeout_after_a_test_has_run(tmp_path):
    """Exercise collection, child output, termination and reporting together."""
    root = Path(runner.__file__).resolve().parent.parent
    scripts = tmp_path / "scripts"
    tests = tmp_path / "tests"
    scripts.mkdir()
    tests.mkdir()
    for name in ("run_tests.sh", "run_tests_parallel.py"):
        shutil.copy2(root / "scripts" / name, scripts / name)
    (tmp_path / ".venv").symlink_to(Path(sys.prefix), target_is_directory=True)
    (tests / "test_probe.py").write_text(
        "import time\n"
        "def test_first():\n"
        "    print('first test executed', flush=True)\n"
        "def test_wait():\n"
        "    time.sleep(30)\n"
    )
    result = subprocess.run(
        ["bash", str(scripts / "run_tests.sh"), "-j", "1", "--file-timeout", "5",
         "tests/test_probe.py", "--", "-s"],
        cwd=tmp_path, capture_output=True, text=True, timeout=25,
    )
    output = result.stdout + result.stderr
    assert "first test executed" in output, output
    assert result.returncode == 1, output
    assert "1 failed (1 timed out)" in output, output
    assert "unavailable test-outcome summaries" in output, output
    assert "no tests ran" not in output, output
    assert "100% complete" not in output, output
