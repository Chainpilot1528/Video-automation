from pathlib import Path

from reckoning_pipeline.config import load_config
from reckoning_pipeline.doctor import (
    GIB, Status, check_architecture, check_disk, check_python, check_tool, has_failures, run_checks,
)


def _no_tools(_name):
    return None


def _all_tools(name):
    return f"/usr/local/bin/{name}"


def _version(args):
    return f"{Path(args[0]).name} version 1.0"


def _disk(free_gib):
    return lambda _path: (500 * GIB, 0, int(free_gib * GIB))


def test_missing_required_tool_fails_with_remedy():
    r = check_tool("ffmpeg", "ffmpeg", required=True, remedy="install it", which=_no_tools)
    assert r.status is Status.FAIL
    assert r.remedy == "install it"


def test_missing_optional_tool_warns():
    r = check_tool("ollama", "ollama", required=False, remedy="optional", which=_no_tools)
    assert r.status is Status.WARN


def test_tool_that_will_not_run_fails():
    r = check_tool("ffmpeg", "ffmpeg", required=True, remedy="x", which=_all_tools, run=lambda a: None)
    assert r.status is Status.FAIL
    assert "did not run" in r.detail


def test_present_tool_passes_with_version_flag():
    seen = []
    r = check_tool("ffprobe", "ffprobe", required=True, remedy="x", which=_all_tools,
                   run=lambda a: seen.append(a) or "ffprobe version 7")
    assert r.status is Status.PASS
    assert seen == [["/usr/local/bin/ffprobe", "-version"]]


def test_disk_thresholds(tmp_path):
    config = load_config({})
    assert check_disk(tmp_path, config, _disk(5)).status is Status.FAIL
    assert check_disk(tmp_path, config, _disk(15)).status is Status.WARN
    assert check_disk(tmp_path, config, _disk(100)).status is Status.PASS


def test_disk_check_walks_up_to_existing_parent(tmp_path):
    seen = []
    check_disk(tmp_path / "a" / "b", load_config({}), lambda p: seen.append(p) or (1, 0, 100 * GIB))
    assert seen == [tmp_path]


def test_python_version_rules():
    assert check_python((3, 10, 0)).status is Status.FAIL
    assert check_python((3, 11, 9)).status is Status.PASS
    assert check_python((3, 14, 7)).status is Status.WARN


def test_architecture():
    assert check_architecture("arm64").status is Status.PASS
    assert check_architecture("x86_64").status is Status.WARN


def test_run_checks_fails_without_ffmpeg(tmp_path):
    config = load_config({"PIPELINE_PROJECTS_ROOT": str(tmp_path)})
    results = run_checks(config, which=_no_tools, disk_usage=_disk(100))
    by_name = {r.name: r for r in results}
    assert by_name["ffmpeg"].status is Status.FAIL
    assert by_name["ffprobe"].status is Status.FAIL
    assert has_failures(results)


def test_run_checks_passes_with_tools(tmp_path):
    config = load_config({"PIPELINE_PROJECTS_ROOT": str(tmp_path)})
    results = run_checks(config, which=_all_tools, run=_version, disk_usage=_disk(100))
    assert not has_failures(results)


def test_projects_root_that_is_a_file_fails(tmp_path):
    f = tmp_path / "file"
    f.write_text("x")
    config = load_config({"PIPELINE_PROJECTS_ROOT": str(f)})
    results = run_checks(config, which=_all_tools, run=_version, disk_usage=_disk(100))
    assert {r.name: r for r in results}["projects_root"].status is Status.FAIL


def test_paid_providers_enabled_warns(tmp_path):
    config = load_config({"PIPELINE_PROJECTS_ROOT": str(tmp_path), "PIPELINE_ALLOW_PAID_PROVIDERS": "1"})
    results = run_checks(config, which=_all_tools, run=_version, disk_usage=_disk(100))
    assert {r.name: r for r in results}["providers"].status is Status.WARN
