from __future__ import annotations

from logging import getLogger
from os import environ
from pathlib import Path, PurePosixPath
from shlex import split
from shutil import which
from subprocess import run

from pydantic import BaseModel, ConfigDict, field_validator


class GoLicenseConfig(BaseModel):
    """Opt-in go-licenses saved-file collection."""

    model_config = ConfigDict(extra="forbid")
    destination: str

    @field_validator("destination")
    @classmethod
    def validate_destination(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            not value
            or path.is_absolute()
            or path.as_posix() != value
            or any(part in (".", "..") or part.endswith((".dist-info", ".data")) for part in path.parts)
            or any(character in value for character in "\\:*?[]\x00")
            or value == "."
        ):
            raise ValueError("License destination must be a normalized wheel-relative directory.")
        return value


def _collection_flags(flags: str | None) -> str:
    """Pass dependency-selection flags to the collector through GOFLAGS."""
    if any(character in (flags or "") for character in "$`%;&|<>~*?[]{}\r\n"):
        raise ValueError("Go license collection cannot safely match shell-dependent build flags.")
    values = {"-tags", "-mod", "-modfile", "-overlay", "-compiler", "-pgo", "-covermode", "-coverpkg"}
    switches = {"-race", "-msan", "-asan", "-cover"}
    build_only_values = {"-ldflags", "-gcflags", "-asmflags", "-o", "-p"}
    build_only_switches = {"-a", "-n", "-x", "-v", "-work", "-trimpath", "-buildvcs"}
    result = []
    tokens = iter(split(flags or ""))
    for token in tokens:
        name, separator, value = token.partition("=")
        if name in values | build_only_values:
            if not separator:
                value = next(tokens, "")
            if not value:
                raise ValueError(f"Missing value for Go build flag '{name}'.")
            if name in values:
                if name == "-tags":
                    value = ",".join(value.replace(",", " ").split())
                if any(character.isspace() for character in value):
                    raise ValueError(f"Go license collection cannot represent '{name}' with whitespace in GOFLAGS.")
                result.append(f"{name}={value}")
        elif name in switches:
            result.append(token)
        elif name not in build_only_switches:
            raise ValueError(f"Unsupported Go build flag for license collection: '{token}'.")
    return " ".join(result)


def collect_licenses(project: Path, output: Path, build_environment: dict[str, str], flags: str | None = None) -> None:
    """Save original upstream artifacts outside the project, failing on unknown licenses."""
    environment = dict(environ)
    environment.update(build_environment)
    selection = _collection_flags(flags)
    environment["GOPACKAGESDRIVER"] = "off"
    collector = which("go-licenses", path=environment.get("PATH"))
    if collector is None:
        raise OSError("go-licenses is required for license collection; install github.com/google/go-licenses/v2@v2.0.1.")
    if selection:
        effective = run(["go", "env", "GOFLAGS"], cwd=project, env=environment, capture_output=True, text=True, check=False)
        if effective.returncode:
            raise RuntimeError(f"go env GOFLAGS failed: {effective.stderr.strip()}")
        environment["GOFLAGS"] = " ".join(part for part in (effective.stdout.strip(), selection) if part)
    completed = run([collector, "save", ".", f"--save_path={output}"], cwd=project, env=environment, capture_output=True, text=True, check=False)
    if completed.returncode:
        raise RuntimeError(f"go-licenses save failed with exit code {completed.returncode}: {completed.stderr.strip()}")
    if completed.stderr.strip():
        getLogger(__name__).warning("go-licenses: %s", completed.stderr.strip())
    if not output.is_dir():
        raise ValueError("go-licenses produced no saved license files.")
    files = []
    for file in output.rglob("*"):
        if file.is_symlink():
            raise ValueError(f"Saved license artifact must not be a symlink: '{file.relative_to(output)}'.")
        if file.is_file():
            files.append(file)
            if file.name.lower().startswith(("license", "licence", "copying")):
                text = file.read_bytes().strip().lower()
                if text in (b"", b"unknown", b"not found"):
                    raise ValueError(f"Missing saved license text: '{file.relative_to(output)}'.")
    if not files:
        raise ValueError("go-licenses produced no saved license files.")
