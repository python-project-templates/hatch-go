from __future__ import annotations

from logging import getLogger
from os import getenv, sep
from pathlib import Path, PurePosixPath
from platform import machine as platform_machine
from sys import platform as sys_platform, version_info
from tempfile import TemporaryDirectory
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from hatchling.builders.utils import normalize_inclusion_map

from .licenses import GoLicenseConfig, collect_licenses
from .structs import HatchGoBuildConfig, HatchGoBuildPlan
from .utils import import_string

__all__ = ("HatchGoBuildHook",)

log = getLogger(__name__)


class HatchGoBuildHook(BuildHookInterface):
    """The hatch-go build hook."""

    PLUGIN_NAME = "hatch-go"
    _logger = log
    _license_directory: TemporaryDirectory[str] | None = None

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        """Initialize the plugin."""
        # Log some basic information
        project_name = self.metadata.config["project"]["name"]
        self._logger.info("Initializing hatch-go plugin version %s", version)
        self._logger.info(f"Running hatch-go: {project_name}")

        # Only run if creating wheel
        if self.target_name != "wheel":
            self._logger.info("ignoring target name %s", self.target_name)
            return

        # Skip if SKIP_HATCH_GO is set
        if getenv("SKIP_HATCH_GO"):
            self._logger.info("Skipping the build hook since SKIP_HATCH_GO was set")
            return

        # Get build config class or use default
        build_config_class = import_string(self.config["build-config-class"]) if "build-config-class" in self.config else HatchGoBuildConfig

        # Instantiate build config
        config = build_config_class(name=project_name, **self.config)

        if config.licenses is not None and not config.skip:
            self._validate_license_destination(config.licenses.destination, build_data)

        # Get build plan class or use default
        build_plan_class = import_string(self.config["build-plan-class"]) if "build-plan-class" in self.config else HatchGoBuildPlan

        # Instantiate builder
        build_plan = build_plan_class(**config.model_dump())

        # Generate commands
        build_plan.generate()

        # Log commands if in verbose mode
        if build_plan.verbose:
            for command in build_plan.commands:
                self._logger.warning(command)

        if build_plan.skip:
            self._logger.warning("Skipping build")
            return

        # Execute build plan
        build_plan.execute()

        # Perform any cleanup actions
        build_plan.cleanup()

        if not build_plan._libraries:
            raise ValueError("No libraries were created by the build.")

        build_data["pure_python"] = False
        machine = platform_machine()
        version_major = version_info.major
        version_minor = version_info.minor

        if "darwin" in sys_platform:
            os_name = "macosx_11_0"
        elif "linux" in sys_platform:
            os_name = "linux"
        else:
            os_name = "win"

        build_data["tag"] = f"cp{version_major}{version_minor}-cp{version_major}{version_minor}-{os_name}_{machine}"

        # Force include libraries
        for path in Path(".").rglob("*"):
            if path.is_dir():
                continue
            if str(path).startswith("dist") or not str(path).startswith(config.module):
                continue
            if path.suffix in (".pyd", ".dll", ".so", ".dylib"):
                build_data["force_include"][str(path)] = str(path)

        if config.licenses is not None:
            self._validate_license_destination(config.licenses.destination, build_data)
            self._cleanup_licenses()
            directory = TemporaryDirectory(prefix="hatch-go-licenses-")
            try:
                output = Path(directory.name) / "go"
                project = (Path(self.root) / (config.path or Path(self.root))).resolve()
                collect_licenses(project, output, build_plan._build_environment, config.go_build_flags)
                inclusions = {}
                for file in sorted(output.rglob("*")):
                    if file.is_file():
                        destination = (PurePosixPath(config.licenses.destination) / file.relative_to(output).as_posix()).as_posix()
                        GoLicenseConfig.validate_destination(destination)
                        self._validate_license_destination(destination, build_data)
                        inclusions[str(file)] = destination
                build_data.setdefault("force_include", {}).update(inclusions)
                if version == "editable":
                    if not build_data.get("force_include_editable"):
                        normal = build_data["force_include"]
                        combined = self.build_config.get_force_include() if self.build_config is not None else {}
                        combined.update(normalize_inclusion_map(normal, self.root))
                        normal.clear()
                        normal.update(combined)
                        build_data["force_include_editable"] = normal
                    build_data["force_include_editable"].update(inclusions)
            except BaseException:
                directory.cleanup()
                raise
            self._license_directory = directory

        for path in build_data["force_include"]:
            self._logger.warning(f"Force include: {path}")

    def _validate_license_destination(self, value: str, build_data: dict[str, Any]) -> None:
        destination = PurePosixPath(value)
        root = Path(self.root).resolve()
        paths = {root / value}
        inclusions = list(build_data.get("force_include", {}).values())
        inclusions.extend(build_data.get("force_include_editable", {}).values())
        if self.build_config is not None:
            raw = str(Path(value))
            mapped = self.build_config.get_distribution_path(raw)
            prefix = self.build_config.get_distribution_path(raw + sep)
            if Path(mapped).as_posix() != value or Path(prefix).as_posix() != value:
                raise ValueError("License destination is rewritten by Hatch sources; choose an unmapped wheel-relative destination.")
            inclusions.extend(self.build_config.get_force_include().values())
            for source, replacement in self.build_config.sources.items():
                if raw.startswith(replacement):
                    paths.add(root / (source + raw[len(replacement) :]))
        for existing in paths:
            if existing.exists() or existing.is_symlink() or any(parent.is_file() or parent.is_symlink() for parent in existing.parents):
                raise ValueError(f"License destination collision: '{destination}' already exists in the project.")
        for included in inclusions:
            mapped = self.build_config.get_distribution_path(str(Path(included))) if self.build_config is not None else included
            other = PurePosixPath(Path(mapped).as_posix())
            if destination == other or destination in other.parents or other in destination.parents:
                raise ValueError(f"License destination collision with force_include: '{included}'.")

    def _cleanup_licenses(self) -> None:
        if self._license_directory is not None:
            self._license_directory.cleanup()
            self._license_directory = None

    def finalize(self, version: str, build_data: dict[str, Any], artifact_path: str) -> None:
        self._cleanup_licenses()

    def clean(self, versions: list[str]) -> None:
        self._cleanup_licenses()
