import pytest

from hatch_go.structs import HatchGoBuildConfig, HatchGoBuildPlan, _get_python_cgo_flags


class TestBuildConfig:
    def test_defaults(self):
        config = HatchGoBuildConfig(module="mymodule")
        assert config.module == "mymodule"
        assert config.verbose is False
        assert config.skip is False
        assert config.build_mode == "c-shared"
        assert config.cgo_enabled is True
        assert config.go_build_flags is None

    def test_custom_values(self):
        config = HatchGoBuildConfig(
            module="mymodule",
            verbose=True,
            skip=True,
            build_mode="c-archive",
            cgo_enabled=False,
            go_build_flags="-race",
        )
        assert config.verbose is True
        assert config.skip is True
        assert config.build_mode == "c-archive"
        assert config.cgo_enabled is False
        assert config.go_build_flags == "-race"

    def test_path_validation_default(self):
        config = HatchGoBuildConfig(module="mymodule")
        # Path defaults to None; validated to CWD when a non-None value is provided
        assert config.path is None

    def test_path_validation_invalid(self):
        with pytest.raises(ValueError, match="not a valid directory"):
            HatchGoBuildConfig(module="mymodule", path="/nonexistent/path/xyz")


class TestBuildPlan:
    def test_generate_linux(self, monkeypatch):
        monkeypatch.setenv("HATCH_GO_PLATFORM", "linux")
        monkeypatch.setenv("HATCH_GO_MACHINE", "x86_64")
        plan = HatchGoBuildPlan(module="mymodule")
        plan.generate()
        assert len(plan.commands) == 1
        cmd = plan.commands[0]
        assert 'GOOS="linux"' in cmd
        assert 'GOARCH="amd64"' in cmd
        assert 'CGO_ENABLED="1"' in cmd
        assert "-buildmode=c-shared" in cmd
        assert "-o mymodule.so" in cmd

    def test_generate_darwin(self, monkeypatch):
        monkeypatch.setenv("HATCH_GO_PLATFORM", "darwin")
        monkeypatch.setenv("HATCH_GO_MACHINE", "arm64")
        plan = HatchGoBuildPlan(module="mymodule")
        plan.generate()
        cmd = plan.commands[0]
        assert 'GOOS="darwin"' in cmd
        assert 'GOARCH="arm64"' in cmd
        assert "-o mymodule.dylib" in cmd

    def test_generate_windows(self, monkeypatch):
        monkeypatch.setenv("HATCH_GO_PLATFORM", "win32")
        monkeypatch.setenv("HATCH_GO_MACHINE", "AMD64")
        plan = HatchGoBuildPlan(module="mymodule")
        plan.generate()
        cmd = plan.commands[0]
        assert "GOOS" in cmd
        assert "windows" in cmd
        assert "GOARCH" in cmd
        assert "amd64" in cmd
        assert "-o mymodule.dll" in cmd

    def test_generate_debug_build(self, monkeypatch):
        monkeypatch.setenv("HATCH_GO_PLATFORM", "linux")
        monkeypatch.setenv("HATCH_GO_MACHINE", "x86_64")
        plan = HatchGoBuildPlan(module="mymodule", build_type="debug")
        plan.generate()
        cmd = plan.commands[0]
        assert '-ldflags="-s -w"' not in cmd

    def test_generate_release_build(self, monkeypatch):
        monkeypatch.setenv("HATCH_GO_PLATFORM", "linux")
        monkeypatch.setenv("HATCH_GO_MACHINE", "x86_64")
        plan = HatchGoBuildPlan(module="mymodule", build_type="release")
        plan.generate()
        cmd = plan.commands[0]
        assert '-ldflags="-s -w"' in cmd

    def test_generate_extra_flags(self, monkeypatch):
        monkeypatch.setenv("HATCH_GO_PLATFORM", "linux")
        monkeypatch.setenv("HATCH_GO_MACHINE", "x86_64")
        plan = HatchGoBuildPlan(module="mymodule", go_build_flags="-race")
        plan.generate()
        cmd = plan.commands[0]
        assert "-race" in cmd

    def test_generate_cgo_disabled(self, monkeypatch):
        monkeypatch.setenv("HATCH_GO_PLATFORM", "linux")
        monkeypatch.setenv("HATCH_GO_MACHINE", "x86_64")
        plan = HatchGoBuildPlan(module="mymodule", cgo_enabled=False)
        plan.generate()
        cmd = plan.commands[0]
        assert 'CGO_ENABLED="0"' in cmd

    def test_unsupported_platform(self, monkeypatch):
        monkeypatch.setenv("HATCH_GO_PLATFORM", "freebsd")
        monkeypatch.setenv("HATCH_GO_MACHINE", "x86_64")
        plan = HatchGoBuildPlan(module="mymodule")
        with pytest.raises(ValueError, match="Unsupported platform"):
            plan.generate()

    def test_unsupported_machine(self, monkeypatch):
        monkeypatch.setenv("HATCH_GO_PLATFORM", "linux")
        monkeypatch.setenv("HATCH_GO_MACHINE", "sparc")
        plan = HatchGoBuildPlan(module="mymodule")
        with pytest.raises(ValueError, match="Unsupported machine"):
            plan.generate()

    def test_output_filename_linux(self, monkeypatch):
        monkeypatch.setenv("HATCH_GO_PLATFORM", "linux")
        monkeypatch.setenv("HATCH_GO_MACHINE", "x86_64")
        plan = HatchGoBuildPlan(module="mymodule")
        assert plan._get_output_filename("linux") == "mymodule.so"

    def test_output_filename_darwin(self, monkeypatch):
        monkeypatch.setenv("HATCH_GO_PLATFORM", "darwin")
        monkeypatch.setenv("HATCH_GO_MACHINE", "arm64")
        plan = HatchGoBuildPlan(module="mymodule")
        assert plan._get_output_filename("darwin") == "mymodule.dylib"

    def test_output_filename_windows(self, monkeypatch):
        monkeypatch.setenv("HATCH_GO_PLATFORM", "win32")
        monkeypatch.setenv("HATCH_GO_MACHINE", "AMD64")
        plan = HatchGoBuildPlan(module="mymodule")
        assert plan._get_output_filename("win32") == "mymodule.dll"

    def test_go_env_linux_x86_64(self, monkeypatch):
        plan = HatchGoBuildPlan(module="mymodule")
        env = plan._get_go_env("linux", "x86_64")
        assert env["GOOS"] == "linux"
        assert env["GOARCH"] == "amd64"
        assert env["CGO_ENABLED"] == "1"

    def test_go_env_darwin_arm64(self):
        plan = HatchGoBuildPlan(module="mymodule")
        env = plan._get_go_env("darwin", "arm64")
        assert env["GOOS"] == "darwin"
        assert env["GOARCH"] == "arm64"

    def test_go_env_windows_amd64(self):
        plan = HatchGoBuildPlan(module="mymodule")
        env = plan._get_go_env("win32", "AMD64")
        assert env["GOOS"] == "windows"
        assert env["GOARCH"] == "amd64"

    def test_go_env_linux_aarch64(self):
        plan = HatchGoBuildPlan(module="mymodule")
        env = plan._get_go_env("linux", "aarch64")
        assert env["GOOS"] == "linux"
        assert env["GOARCH"] == "arm64"

    def test_go_env_linux_i686(self):
        plan = HatchGoBuildPlan(module="mymodule")
        env = plan._get_go_env("linux", "i686")
        assert env["GOOS"] == "linux"
        assert env["GOARCH"] == "386"


class TestCgoFlags:
    def test_cgo_flags_returns_strings(self):
        cflags, ldflags = _get_python_cgo_flags()
        assert isinstance(cflags, str)
        assert isinstance(ldflags, str)
        assert "-I" in cflags

    def test_cgo_flags_include_python_headers(self):
        cflags, _ldflags = _get_python_cgo_flags()
        assert "Python" in cflags or "python" in cflags.lower()
