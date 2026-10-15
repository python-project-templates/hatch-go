"""Check Hatch mappings and complete collector trees with real builds."""

import json
from pathlib import Path
from subprocess import CalledProcessError, check_call, check_output
from sys import executable
from zipfile import ZipFile

import pytest

from hatch_go.licenses import collect_licenses

pytest_plugins = ("hatch_go.tests.test_licenses",)


@pytest.mark.parametrize("source", ["project/licenses/go", "project/licenses/go/example.com/license-dependency"])
@pytest.mark.parametrize("replacement", ["renamed", "../escaped"])
def test_saved_directory_rewrites_fail(licensed_project, source, replacement):
    config = licensed_project / "pyproject.toml"
    config.write_text(config.read_text().replace('src = "/"', f"{json.dumps(source)} = {json.dumps(replacement)}"))
    with pytest.raises(CalledProcessError):
        check_call([executable, "-m", "hatchling", "build", "-t", "wheel"], cwd=licensed_project)


@pytest.mark.parametrize("version", ["standard", "editable"])
def test_every_collector_artifact_is_preserved(licensed_project, tmp_path, version):
    check_call(["go", "mod", "download", "github.com/hashicorp/golang-lru@v1.0.2"], cwd=licensed_project)
    module = json.loads(check_output(["go", "mod", "download", "-json", "github.com/hashicorp/golang-lru@v1.0.2"], cwd=licensed_project))
    dependency = licensed_project / "dependency"
    (dependency / "LICENSE").write_bytes((Path(module["Dir"]) / "LICENSE").read_bytes())
    for name in (".venv/source.go", ".hg/source.go", "__pycache__/source.go", ".DS_Store"):
        file = dependency / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"Original collector artifact.\r\n")
    output = tmp_path / "saved"
    collect_licenses(licensed_project, output, {"CGO_ENABLED": "0"})
    originals = {file.relative_to(output).as_posix(): file.read_bytes() for file in output.rglob("*") if file.is_file()}
    assert "example.com/license-dependency/.venv/source.go" in originals
    check_call([executable, "-m", "hatchling", "build", "-t", f"wheel:{version}"], cwd=licensed_project)
    (wheel,) = (licensed_project / "dist").glob("*.whl")
    with ZipFile(wheel) as archive:
        prefix = "project/licenses/go/"
        saved = {name[len(prefix) :]: archive.read(name) for name in archive.namelist() if name.startswith(prefix)}
        assert saved == originals
