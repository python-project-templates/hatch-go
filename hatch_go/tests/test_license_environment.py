"""Verify Go environment selection without modifying global Go settings."""

import json
from os import environ
from subprocess import check_call
from sys import executable, platform
from zipfile import ZipFile

import pytest

from hatch_go.licenses import collect_licenses

pytest_plugins = ("hatch_go.tests.test_licenses",)


@pytest.fixture
def tagged_project(licensed_project):
    dependency = licensed_project / "tagged-dependency"
    dependency.mkdir()
    (dependency / "go.mod").write_text("module example.com/tagged-dependency\n\ngo 1.21\n")
    (dependency / "library.go").write_text("package tagged\n")
    (dependency / "LICENSE").write_bytes((licensed_project / "LICENSE").read_bytes())
    manifest = licensed_project / "go.mod"
    manifest.write_text(
        manifest.read_text() + "require example.com/tagged-dependency v1.0.0\nreplace example.com/tagged-dependency => ./tagged-dependency\n"
    )
    (licensed_project / "tagged.go").write_text('//go:build licenseextra\n\npackage main\n\nimport _ "example.com/tagged-dependency"\n')
    return licensed_project


@pytest.mark.parametrize("flags", [None, "-compiler=gc", "-tags=inactive"])
def test_persisted_goflags_match_compilation(tagged_project, tmp_path, monkeypatch, flags):
    goenv = tmp_path / "goenv"
    goenv.write_text("GOFLAGS=-tags=licenseextra\n")
    monkeypatch.setenv("GOENV", str(goenv))
    monkeypatch.delenv("GOFLAGS", raising=False)
    if flags:
        config = tagged_project / "pyproject.toml"
        config.write_text(
            config.read_text().replace(
                "[tool.hatch.build.hooks.hatch-go]\n", f"[tool.hatch.build.hooks.hatch-go]\ngo_build_flags = {json.dumps(flags)}\n"
            )
        )
    check_call([executable, "-m", "hatchling", "build", "-t", "wheel"], cwd=tagged_project)
    (wheel,) = (tagged_project / "dist").glob("*.whl")
    with ZipFile(wheel) as archive:
        assert ("project/licenses/go/example.com/tagged-dependency/LICENSE" in archive.namelist()) == (flags != "-tags=inactive")


@pytest.mark.parametrize("flags", ["-tags=$FEATURE_TAGS", "-tags=`printf licenseextra`", "-tags=%FEATURE_TAGS%", "-tags=license{,extra}"])
def test_shell_dependent_selection_fails_closed(tagged_project, tmp_path, monkeypatch, flags):
    monkeypatch.setenv("FEATURE_TAGS", "licenseextra")
    with pytest.raises(ValueError, match="shell"):
        collect_licenses(tagged_project, tmp_path / "saved", {"CGO_ENABLED": "0"}, flags)


@pytest.mark.skipif(platform == "win32", reason="Sentinel uses a POSIX shell executable.")
@pytest.mark.parametrize("automatic", [False, True])
def test_external_package_driver_cannot_replace_the_graph(licensed_project, tmp_path, monkeypatch, automatic):
    driver = tmp_path / "gopackagesdriver"
    marker = tmp_path / "driver-ran"
    driver.write_text(f'#!/bin/sh\nprintf intercepted > "{marker}"\nexit 1\n')
    driver.chmod(0o755)
    if automatic:
        monkeypatch.delenv("GOPACKAGESDRIVER", raising=False)
        monkeypatch.setenv("PATH", str(tmp_path) + ":" + environ["PATH"])
    else:
        monkeypatch.setenv("GOPACKAGESDRIVER", str(driver))
    output = tmp_path / "saved"
    collect_licenses(licensed_project, output, {"CGO_ENABLED": "0"})
    assert not marker.exists()
    assert (output / "example.com/transitive/LICENSE").is_file()
