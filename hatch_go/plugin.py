from __future__ import annotations

from logging import getLogger
from os import getenv
from pathlib import Path
from platform import machine as platform_machine
from sys import platform as sys_platform, version_info
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

from .structs import HatchGoBuildConfig, HatchGoBuildPlan
from .utils import import_string

__all__ = ("HatchGoBuildHook",)

log = getLogger(__name__)


class HatchGoBuildHook(BuildHookInterface[HatchGoBuildConfig]):
    """The hatch-go build hook."""

    PLUGIN_NAME = "hatch-go"
    _logger = log

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

        for path in build_data["force_include"]:
            self._logger.warning(f"Force include: {path}")
