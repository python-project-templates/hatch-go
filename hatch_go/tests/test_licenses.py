"""Exercise saved license resources with real Go and Hatchling builds."""

import json
import tarfile
import venv
from importlib.metadata import distribution
from pathlib import Path
from shutil import copytree, ignore_patterns
from subprocess import CalledProcessError, CompletedProcess, check_call, check_output
from sys import executable, platform
from zipfile import ZipFile

import pytest
from hatchling.builders.wheel import WheelBuilder

from hatch_go.licenses import collect_licenses
from hatch_go.plugin import HatchGoBuildHook


@pytest.fixture
def licensed_project(tmp_path):
    project = tmp_path / "application"
    copytree(Path(__file__).parent / "test_project_basic", project, ignore=ignore_patterns("dist", "*.so", "*.pyd", "*.dll", "*.dylib", "*.h"))
    dist = distribution("hatch-go")
    license_path = next(path for path in (dist.files or []) if path.name == "LICENSE" and "licenses" in path.parts)
    license_text = Path(str(dist.locate_file(license_path))).read_bytes()
    (project / "LICENSE").write_bytes(license_text)
    (project / "NOTICE").write_bytes(b"Original notice for this test project.\r\n")
    dependency = project / "dependency"
    dependency.mkdir()
    (dependency / "go.mod").write_text("module example.com/license-dependency\n\ngo 1.21\n\nrequire example.com/transitive v0.4.0\n")
    (dependency / "library.go").write_text('package dependency\n\nimport _ "example.com/transitive"\n\nfunc Value() int { return 42 }\n')
    (dependency / "LICENSE").write_bytes(license_text)
    (dependency / "NOTICE.md").write_bytes(b"Original notice for this test dependency.\r\n")
    transitive = project / "transitive"
    transitive.mkdir()
    (transitive / "go.mod").write_text("module example.com/transitive\n\ngo 1.21\n")
    (transitive / "library.go").write_text("package transitive\n")
    (transitive / "LICENSE").write_bytes(license_text)
    (project / "go.mod").write_text(
        "module example.com/application\n\ngo 1.21\n\nrequire example.com/license-dependency v1.2.3\n"
        "require example.com/transitive v0.4.0 // indirect\n"
        "replace example.com/license-dependency => ./dependency\nreplace example.com/transitive => ./transitive\n"
    )
    (project / "dependency.go").write_text('package main\n\nimport _ "example.com/license-dependency"\n')
    config = project / "pyproject.toml"
    config.write_text(
        config.read_text().replace(
            '[tool.hatch.build.targets.sdist]\npackages = ["project"]',
            "[tool.hatch.build.targets.sdist]\nartifacts = []\n"
            'packages = ["project", "go.mod", "main.go", "exports.go", "dependency.go", "LICENSE", "NOTICE", "dependency", "transitive"]\n'
            'exclude = ["project/*.so", "project/*.pyd"]',
        )
        + '\n[tool.hatch.build.hooks.hatch-go.licenses]\ndestination = "project/licenses/go"\n'
    )
    return project


@pytest.mark.parametrize("version", ["standard", "editable"])
def test_real_wheel_preserves_license_and_notices(licensed_project, version):
    check_call([executable, "-m", "hatchling", "build", "-t", f"wheel:{version}"], cwd=licensed_project)
    (wheel,) = (licensed_project / "dist").glob("*.whl")
    with ZipFile(wheel) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names))
        for name, source in (
            ("example.com/application/LICENSE", "LICENSE"),
            ("example.com/application/NOTICE", "NOTICE"),
            ("example.com/license-dependency/LICENSE", "dependency/LICENSE"),
            ("example.com/license-dependency/NOTICE.md", "dependency/NOTICE.md"),
            ("example.com/transitive/LICENSE", "transitive/LICENSE"),
        ):
            assert archive.read(f"project/licenses/go/{name}") == (licensed_project / source).read_bytes()
        assert any(name.startswith("project/project.") and name.endswith((".so", ".pyd")) for name in names)
    assert not (licensed_project / "project/licenses").exists()


def test_missing_license_fails_real_build(licensed_project):
    (licensed_project / "dependency/LICENSE").unlink()
    with pytest.raises(CalledProcessError):
        check_call([executable, "-m", "hatchling", "build", "-t", "wheel"], cwd=licensed_project)


def test_existing_destination_is_not_overwritten(licensed_project):
    destination = licensed_project / "project/licenses/go"
    destination.mkdir(parents=True)
    sentinel = destination / "sentinel"
    sentinel.write_bytes(b"Do not replace this existing file.")
    with pytest.raises(CalledProcessError):
        check_call([executable, "-m", "hatchling", "build", "-t", "wheel"], cwd=licensed_project)
    assert sentinel.read_bytes() == b"Do not replace this existing file."


@pytest.mark.parametrize("flags", [None, "-tags=licenseextra", '-tags "licenseextra other"', "-tags=inactive", "-tags=licenseextra -ldflags='-s -w'"])
def test_build_tags_select_the_same_dependencies(licensed_project, flags, monkeypatch):
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
    monkeypatch.setenv("GOFLAGS", "-tags=licenseextra")
    if flags is not None:
        config = licensed_project / "pyproject.toml"
        config.write_text(
            config.read_text().replace(
                "[tool.hatch.build.hooks.hatch-go]\n", f"[tool.hatch.build.hooks.hatch-go]\ngo_build_flags = {json.dumps(flags)}\n"
            )
        )
    check_call([executable, "-m", "hatchling", "build", "-t", "wheel"], cwd=licensed_project)
    (wheel,) = (licensed_project / "dist").glob("*.whl")
    with ZipFile(wheel) as archive:
        assert ("project/licenses/go/example.com/tagged-dependency/LICENSE" in archive.namelist()) == (flags != "-tags=inactive")


def test_wheel_from_sdist_has_fresh_license_files(licensed_project):
    check_call([executable, "-m", "build", "--no-isolation"], cwd=licensed_project)
    (source,) = (licensed_project / "dist").glob("*.tar.gz")
    with tarfile.open(source) as archive:
        names = archive.getnames()
        assert not any("/project/licenses/" in name or name.endswith((".so", ".pyd")) for name in names)
        assert any(name.endswith("/dependency/LICENSE") for name in names)
    (wheel,) = (licensed_project / "dist").glob("*.whl")
    with ZipFile(wheel) as archive:
        assert archive.read("project/licenses/go/example.com/transitive/LICENSE") == (licensed_project / "transitive/LICENSE").read_bytes()


@pytest.mark.parametrize("version", ["standard", "editable"])
def test_configured_force_include_is_preserved(licensed_project, version):
    (licensed_project / "extra.txt").write_bytes(b"Another configured artifact.")
    config = licensed_project / "pyproject.toml"
    config.write_text(config.read_text() + '\n[tool.hatch.build.targets.wheel.force-include]\n"extra.txt" = "project/extra.txt"\n')
    check_call([executable, "-m", "hatchling", "build", "-t", f"wheel:{version}"], cwd=licensed_project)
    (wheel,) = (licensed_project / "dist").glob("*.whl")
    with ZipFile(wheel) as archive:
        assert archive.read("project/extra.txt") == b"Another configured artifact."
        assert archive.read("project/licenses/go/example.com/transitive/LICENSE") == (licensed_project / "transitive/LICENSE").read_bytes()


@pytest.mark.parametrize("inclusion", ["project/licenses/go", "project/licenses/go/existing", "project/licenses"])
def test_forced_destination_collisions_fail(licensed_project, inclusion):
    (licensed_project / "extra.txt").write_bytes(b"Existing artifact.")
    config = licensed_project / "pyproject.toml"
    config.write_text(config.read_text() + f'\n[tool.hatch.build.targets.wheel.force-include]\n"extra.txt" = "{inclusion}"\n')
    with pytest.raises(CalledProcessError):
        check_call([executable, "-m", "hatchling", "build", "-t", "wheel"], cwd=licensed_project)


def test_missing_collector_has_install_guidance(tmp_path):
    with pytest.raises(OSError, match="go-licenses is required"):
        collect_licenses(tmp_path, tmp_path / "saved", {"PATH": str(tmp_path)})


@pytest.mark.parametrize("contents", [b"", b"UNKNOWN", b"NOT FOUND"])
def test_placeholder_saved_text_is_rejected(tmp_path, monkeypatch, contents):
    output = tmp_path / "saved"

    def save(*args, **kwargs):
        output.mkdir()
        (output / "LICENSE").write_bytes(contents)
        return CompletedProcess(args[0], 0, "", "")

    monkeypatch.setattr("hatch_go.licenses.run", save)
    with pytest.raises(ValueError, match="Missing saved license text"):
        collect_licenses(tmp_path, output, {})


def test_symlink_saved_file_is_rejected(tmp_path, monkeypatch):
    output = tmp_path / "saved"
    source = tmp_path / "original"
    source.write_bytes(b"External data must not be packaged through a symlink.")

    def save(*args, **kwargs):
        output.mkdir()
        (output / "LICENSE").symlink_to(source)
        return CompletedProcess(args[0], 0, "", "")

    monkeypatch.setattr("hatch_go.licenses.run", save)
    with pytest.raises(ValueError, match="symlink"):
        collect_licenses(tmp_path, output, {})


@pytest.mark.parametrize("cleanup", ["finalize", "clean"])
def test_hook_cleans_its_temporary_saved_files(licensed_project, monkeypatch, cleanup):
    monkeypatch.chdir(licensed_project)
    builder = WheelBuilder(str(licensed_project))
    config = {"module": "project", "path": str(licensed_project), "licenses": {"destination": "project/licenses/go"}}
    hook = HatchGoBuildHook(str(licensed_project), config, builder.config, builder.metadata, "dist", "wheel")
    build_data = {"force_include": {}}
    hook.initialize("standard", build_data)
    saved = next(Path(path).parent for path in build_data["force_include"] if "hatch-go-licenses-" in path)
    assert saved.is_dir()
    if cleanup == "finalize":
        hook.finalize("standard", build_data, "unused.whl")
    else:
        hook.clean(["standard"])
    assert not saved.exists()


def test_symlinked_project_root_does_not_collide(licensed_project, monkeypatch, tmp_path):
    alias = tmp_path / "alias"
    alias.symlink_to(licensed_project, target_is_directory=True)
    monkeypatch.chdir(licensed_project)
    builder = WheelBuilder(str(alias))
    config = {"module": "project", "path": str(alias), "licenses": {"destination": "project/licenses/go"}}
    hook = HatchGoBuildHook(str(alias), config, builder.config, builder.metadata, "dist", "wheel")
    build_data = {"force_include": {}}
    try:
        hook.initialize("standard", build_data)
        assert any("hatch-go-licenses-" in path for path in build_data["force_include"])
    finally:
        hook.clean(["standard"])


@pytest.mark.parametrize("version", ["standard", "editable"])
def test_installed_native_extension_and_license_resources(licensed_project, tmp_path, version):
    check_call([executable, "-m", "hatchling", "build", "-t", f"wheel:{version}"], cwd=licensed_project)
    (wheel,) = (licensed_project / "dist").glob("*.whl")
    environment = tmp_path / "environment"
    venv.EnvBuilder().create(environment)
    python = environment / ("Scripts/python.exe" if platform == "win32" else "bin/python")
    check_call(["uv", "pip", "install", "--python", str(python), "--no-deps", str(wheel)])
    check_call(
        [
            str(python),
            "-I",
            "-c",
            (
                "from pathlib import Path; from importlib.metadata import distribution; import project.project as native; "
                'assert native.hello() == "A string from Go"; assert native.add(2, 3) == 5; '
                'dist = distribution("hatch-go-test-project-basic"); '
                'prefix = "project/licenses/go/"; '
                'assert Path(str(dist.locate_file(prefix + "example.com/license-dependency/NOTICE.md"))).read_bytes() '
                '== b"Original notice for this test dependency.\\r\\n"; '
                'assert Path(str(dist.locate_file(prefix + "example.com/transitive/LICENSE"))).stat().st_size > 1000'
            ),
        ],
        cwd=tmp_path,
    )


def test_reciprocal_dependency_retains_original_source(licensed_project):
    manifest = licensed_project / "go.mod"
    manifest.write_text(manifest.read_text() + "require github.com/hashicorp/golang-lru v1.0.2\n")
    (licensed_project / "third_party.go").write_text('package main\n\nimport _ "github.com/hashicorp/golang-lru"\n')
    check_call(["go", "mod", "tidy"], cwd=licensed_project)
    module = json.loads(check_output(["go", "list", "-m", "-json", "github.com/hashicorp/golang-lru"], cwd=licensed_project))
    original = Path(module["Dir"])
    assert module["Version"] == "v1.0.2"
    check_call([executable, "-m", "hatchling", "build", "-t", "wheel"], cwd=licensed_project)
    (wheel,) = (licensed_project / "dist").glob("*.whl")
    with ZipFile(wheel) as archive:
        for file in ("LICENSE", "2q.go", "simplelru/lru.go"):
            assert archive.read(f"project/licenses/go/github.com/hashicorp/golang-lru/{file}") == (original / file).read_bytes()


@pytest.mark.parametrize("reason", ["sdist", "skip", "environment"])
def test_skipped_builds_do_not_run_collector(licensed_project, monkeypatch, reason):
    builder = WheelBuilder(str(licensed_project))
    config = {"module": "project", "path": str(licensed_project), "licenses": {"destination": "project/licenses/go"}}
    if reason == "skip":
        config["skip"] = True
    if reason == "environment":
        monkeypatch.setenv("SKIP_HATCH_GO", "1")
    hook = HatchGoBuildHook(str(licensed_project), config, builder.config, builder.metadata, "dist", "sdist" if reason == "sdist" else "wheel")
    build_data = {"force_include": {}}
    hook.initialize("standard", build_data)
    assert build_data == {"force_include": {}}
    assert not (licensed_project / "project/licenses").exists()


@pytest.mark.parametrize("flags", ["-tags", "-C=other", '-overlay="path with spaces.json"'])
def test_unrepresentable_selection_flags_fail_before_collection(tmp_path, flags):
    with pytest.raises(ValueError):
        collect_licenses(tmp_path, tmp_path / "saved", {}, flags)


def test_package_load_error_fails_collection(licensed_project, tmp_path):
    (licensed_project / "invalid.go").write_text('package main\nimport "example.com/not-a-real-dependency"\n')
    with pytest.raises(RuntimeError, match="go-licenses save failed"):
        collect_licenses(licensed_project, tmp_path / "saved", {"CGO_ENABLED": "0"})


@pytest.mark.parametrize("create_directory", [False, True])
def test_missing_or_empty_collector_output_fails(tmp_path, monkeypatch, create_directory):
    output = tmp_path / "saved"

    def save(*args, **kwargs):
        if create_directory:
            output.mkdir()
        return CompletedProcess(args[0], 0, "", "")

    monkeypatch.setattr("hatch_go.licenses.run", save)
    with pytest.raises(ValueError, match="no saved license files"):
        collect_licenses(tmp_path, output, {})


def test_rewritten_license_destination_is_rejected(licensed_project):
    config = licensed_project / "pyproject.toml"
    config.write_text(config.read_text().replace('src = "/"', 'project = "renamed"'))
    with pytest.raises(CalledProcessError):
        check_call([executable, "-m", "hatchling", "build", "-t", "wheel"], cwd=licensed_project)
