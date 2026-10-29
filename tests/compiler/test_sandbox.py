import os
import sys
import time

from backend.compiler.sandbox import ProcessResult, run_python, sandbox_copy, scrubbed_env


def test_scrubbed_env_has_no_secrets(monkeypatch, tmp_path):
    monkeypatch.setenv("NEBIUS_API_KEY", "sk-secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws")
    env = scrubbed_env(tmp_path)
    assert "NEBIUS_API_KEY" not in env and "AWS_SECRET_ACCESS_KEY" not in env
    assert env["HOME"] == str(tmp_path) and env["CASCADE_OFFLINE"] == "1"
    assert set(env) <= {"PATH", "HOME", "TMPDIR", "PYTHONDONTWRITEBYTECODE", "PYTHONHASHSEED",
                        "PYTHONNOUSERSITE", "CASCADE_OFFLINE", "LANG", "LC_ALL", "SYSTEMROOT"}


def test_sandbox_copy_excludes_noise_and_is_removed(tmp_path):
    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    (repo / "pkg" / "m.py").write_text("x = 1\n")
    (repo / ".git").mkdir()
    (repo / ".git" / "HEAD").write_text("ref")
    (repo / ".venv").mkdir()
    (repo / ".env").write_text("NEBIUS_API_KEY=sk")
    with sandbox_copy(repo) as work:
        assert (work / "pkg" / "m.py").read_text() == "x = 1\n"
        assert not (work / ".git").exists() and not (work / ".venv").exists() and not (work / ".env").exists()
        assert (work.parent / "home").is_dir()
        base = work.parent
    assert not base.exists()
    assert (repo / "pkg" / "m.py").exists()  # original untouched


def test_sandbox_removed_on_error(tmp_path):
    (tmp_path / "f.py").write_text("")
    try:
        with sandbox_copy(tmp_path) as work:
            base = work.parent
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert not base.exists()


def test_run_python_captures_output_and_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "sk-secret")
    (tmp_path / "home").mkdir()
    work = tmp_path / "w"
    work.mkdir()
    (work / "s.py").write_text(
        "import os, sys\nprint(os.environ.get('NEBIUS_API_KEY', 'absent'))\n"
        "print(sys.stdin.read())\nsys.stderr.write('err')\nsys.exit(3)\n"
    )
    r = run_python(["s.py"], cwd=work, timeout=30, stdin="hello")
    assert r == ProcessResult(3, "absent\nhello\n", "err", False)


def test_run_python_kills_on_timeout(tmp_path):
    (tmp_path / "home").mkdir()
    work = tmp_path / "w"
    work.mkdir()
    marker = tmp_path / "child_alive"
    (work / "child.py").write_text(f"import time\ntime.sleep(3)\nopen({str(marker)!r}, 'w').close()\n")
    (work / "s.py").write_text(
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, 'child.py'])\n"
        "print('started', flush=True)\ntime.sleep(60)\n"
    )
    start = time.monotonic()
    r = run_python(["s.py"], cwd=work, timeout=1)
    assert r.timed_out and r.returncode is None and "started" in r.stdout
    assert time.monotonic() - start < 10
    time.sleep(3.5)
    assert not marker.exists()  # the whole process group was killed


def test_run_python_truncates_huge_output(tmp_path, monkeypatch):
    import backend.compiler.sandbox as sb

    monkeypatch.setattr(sb, "MAX_OUTPUT_BYTES", 100)
    (tmp_path / "home").mkdir()
    work = tmp_path / "w"
    work.mkdir()
    (work / "s.py").write_text("print('x' * 1000)\n")
    r = run_python(["s.py"], cwd=work, timeout=30)
    assert r.stdout.startswith("[output truncated]") and len(r.stdout) < 200
    assert r.stdout.rstrip().endswith("x")


def test_uses_backend_interpreter(tmp_path):
    (tmp_path / "home").mkdir()
    work = tmp_path / "w"
    work.mkdir()
    (work / "s.py").write_text("import sys; print(sys.executable)\n")
    assert run_python(["s.py"], cwd=work, timeout=30).stdout.strip() == sys.executable


def test_tail_is_kept_so_result_lines_survive(tmp_path, monkeypatch):
    import backend.compiler.sandbox as sb

    monkeypatch.setattr(sb, "MAX_OUTPUT_BYTES", 1000)
    (tmp_path / "home").mkdir()
    work = tmp_path / "w"
    work.mkdir()
    (work / "s.py").write_text("print('x' * 50000)\nprint('RESULT-LINE')\n")
    assert run_python(["s.py"], cwd=work, timeout=30).stdout.rstrip().endswith("RESULT-LINE")


def test_background_helper_does_not_cause_false_timeout_or_hang(tmp_path):
    (tmp_path / "home").mkdir()
    work = tmp_path / "w"
    work.mkdir()
    (work / "s.py").write_text(
        "import subprocess, sys\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], start_new_session=True)\n"
        "print('done', flush=True)\n"
    )
    start = time.monotonic()
    r = run_python(["s.py"], cwd=work, timeout=10)
    assert not r.timed_out and r.returncode == 0 and r.stdout.strip() == "done"
    assert time.monotonic() - start < 8


def test_detached_child_cannot_block_timeout(tmp_path):
    (tmp_path / "home").mkdir()
    work = tmp_path / "w"
    work.mkdir()
    (work / "s.py").write_text(
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], start_new_session=True)\n"
        "time.sleep(30)\n"
    )
    start = time.monotonic()
    r = run_python(["s.py"], cwd=work, timeout=1)
    assert r.timed_out and time.monotonic() - start < 8
