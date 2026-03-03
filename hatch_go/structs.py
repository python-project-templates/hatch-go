from __future__ import annotations

from os import chdir, curdir, environ, system as system_call
from pathlib import Path
from platform import machine as platform_machine
from shutil import which
from sys import platform as sys_platform
from sysconfig import get_config_var, get_path
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, PrivateAttr, field_validator

__all__ = (
    "HatchGoBuildConfig",
    "HatchGoBuildPlan",
)

BuildType = Literal["debug", "release"]
BuildMode = Literal["c-shared", "c-archive"]


def _get_python_cgo_flags() -> tuple[str, str]:
    """Get CGO_CFLAGS and CGO_LDFLAGS for building against the current Python."""
    include_dir = get_path("include")
    platinclude_dir = get_path("platinclude")
    cflags_parts = [f"-I{include_dir}"]
    if platinclude_dir != include_dir:
        cflags_parts.append(f"-I{platinclude_dir}")

    # Get library linking flags
    libdir = get_config_var("LIBDIR")
    ldflags_parts = []

    if libdir:
        ldflags_parts.append(f"-L{libdir}")

    platform = environ.get("HATCH_GO_PLATFORM", sys_platform)
    if platform == "win32":
        # On Windows, link against pythonXY.lib
        python_lib = get_config_var("VERSION")
        if python_lib:
            ldflags_parts.append(f"-lpython{python_lib}")
    elif platform == "darwin":
        # On macOS, use -undefined dynamic_lookup to defer Python symbol resolution
        ldflags_parts.append("-undefined")
        ldflags_parts.append("dynamic_lookup")
    else:
        # On Linux, use -undefined dynamic_lookup or link against libpython
        # If building for embedding, we link; for extension modules, we don't need to
        ldflags_parts.append("-Wl,--unresolved-symbols=ignore-all")

    cgo_cflags = " ".join(cflags_parts)
    cgo_ldflags = " ".join(ldflags_parts)
    return cgo_cflags, cgo_ldflags


class HatchGoBuildConfig(BaseModel):
    """Build config values for Hatch Go Builder."""

    verbose: Optional[bool] = Field(default=False)
    skip: Optional[bool] = Field(default=False)
    name: Optional[str] = Field(default=None)

    module: str = Field(description="Python module name for the Go extension.")
    path: Optional[Path] = Field(default=None, description="Path to the Go project root directory.")

    build_mode: BuildMode = Field(
        default="c-shared",
        description="Go build mode: 'c-shared' produces a shared library (.so/.dylib/.dll), 'c-archive' produces a static archive.",
    )

    cgo_enabled: bool = Field(
        default=True,
        description="Whether to enable CGO for the build.",
    )

    go_build_flags: Optional[str] = Field(
        default=None,
        description="Additional flags to pass to `go build`.",
    )

    # Validate path
    @field_validator("path", mode="before")
    @classmethod
    def validate_path(cls, path: Optional[Path]) -> Path:
        if path is None:
            return Path.cwd()
        if not isinstance(path, Path):
            path = Path(path)
        if not path.is_dir():
            raise ValueError(f"Path '{path}' is not a valid directory.")
        return path


class HatchGoBuildPlan(HatchGoBuildConfig):
    build_type: BuildType = "release"
    commands: List[str] = Field(default_factory=list)

    _libraries: List[str] = PrivateAttr(default_factory=list)

    def _get_platform_info(self):
        """Get platform and machine info, respecting env overrides."""
        platform = environ.get("HATCH_GO_PLATFORM", sys_platform)
        machine = environ.get("HATCH_GO_MACHINE", platform_machine())
        return platform, machine

    def _get_output_filename(self, platform: str) -> str:
        """Get the output filename for the compiled Go shared library."""
        if platform == "win32":
            return f"{self.module}.dll"
        elif platform == "darwin":
            return f"{self.module}.dylib"
        else:
            return f"{self.module}.so"

    def _get_go_env(self, platform: str, machine: str) -> dict:
        """Get Go environment variables for cross-compilation."""
        env = {}

        if self.cgo_enabled:
            env["CGO_ENABLED"] = "1"
        else:
            env["CGO_ENABLED"] = "0"

        # Map Python platform/machine to GOOS/GOARCH
        if platform == "win32":
            env["GOOS"] = "windows"
        elif platform == "darwin":
            env["GOOS"] = "darwin"
        elif platform == "linux":
            env["GOOS"] = "linux"
        else:
            raise ValueError(f"Unsupported platform: {platform}")

        if machine in ("x86_64", "AMD64"):
            env["GOARCH"] = "amd64"
        elif machine in ("arm64", "aarch64"):
            env["GOARCH"] = "arm64"
        elif machine == "i686":
            env["GOARCH"] = "386"
        else:
            raise ValueError(f"Unsupported machine type: {machine}")

        return env

    def generate(self):
        self.commands = []

        platform, machine = self._get_platform_info()
        go_env = self._get_go_env(platform, machine)

        # Get Python CGO flags
        cgo_cflags, cgo_ldflags = _get_python_cgo_flags()
        go_env["CGO_CFLAGS"] = cgo_cflags
        go_env["CGO_LDFLAGS"] = cgo_ldflags

        # Construct env prefix for the command
        if platform == "win32":
            env_prefix_parts = [f"set {k}={v} &&" for k, v in go_env.items()]
            env_prefix = " ".join(env_prefix_parts)
        else:
            env_prefix_parts = [f'{k}="{v}"' for k, v in go_env.items()]
            env_prefix = " ".join(env_prefix_parts)

        # Output filename
        output_name = self._get_output_filename(platform)

        # Construct build command
        build_command = f"{env_prefix} go build -buildmode={self.build_mode}"

        if self.build_type == "release":
            # Strip debug info for release builds
            build_command += ' -ldflags="-s -w"'

        if self.go_build_flags:
            build_command += f" {self.go_build_flags}"

        build_command += f" -o {output_name}"

        # Add the package path (current directory)
        build_command += " ."

        self.commands.append(build_command)

        return self.commands

    def execute(self):
        """Execute the build commands."""
        cwd = Path(curdir).resolve()
        build_path = self.path or cwd
        chdir(build_path)

        for command in self.commands:
            ret = system_call(command)
            if ret != 0:
                raise RuntimeError(f"hatch-go build command failed with exit code {ret}: {command}")

        chdir(str(cwd))

        # Locate and copy build artifacts to the Python module directory
        platform, _machine = self._get_platform_info()
        output_name = self._get_output_filename(platform)
        source_file = Path(build_path) / output_name

        if not source_file.exists():
            raise FileNotFoundError(f"Build artifact '{source_file}' does not exist.")

        # Determine destination
        if platform == "win32":
            ext = ".pyd"
        elif platform == "darwin":
            ext = ".so"
        else:
            ext = ".so"

        # The Go shared lib output name is module.dylib/so/dll, we normalize to .so/.pyd for Python
        dest_name = f"{self.module}{ext}"
        dest_path = cwd / self.module / dest_name.split("/")[-1]

        # Ensure destination directory exists
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        if sys_platform == "win32":
            library_name = f"{self.module}\\{dest_name.split('/')[-1]}"
            self._libraries.append(library_name)
            copy_command = f'copy "{source_file}" "{dest_path}"'
        else:
            if which("cp") is None:
                raise EnvironmentError("cp command not found. Ensure it is installed and available in PATH.")
            library_name = f"{self.module}/{dest_name.split('/')[-1]}"
            self._libraries.append(library_name)
            copy_command = f'cp -f "{source_file}" "{dest_path}"'

        ret = system_call(copy_command)
        if ret != 0:
            raise RuntimeError(f"hatch-go copy command failed with exit code {ret}: {copy_command}")

        return self.commands

    def cleanup(self):
        """Clean up intermediate build artifacts."""
        platform, _machine = self._get_platform_info()
        build_path = self.path or Path.cwd()

        # Clean up the header file generated by -buildmode=c-shared
        header_file = Path(build_path) / f"{self.module}.h"
        if header_file.exists():
            header_file.unlink()

        # Clean up the shared library in the Go source directory
        output_name = self._get_output_filename(platform)
        output_file = Path(build_path) / output_name
        if output_file.exists():
            output_file.unlink()
