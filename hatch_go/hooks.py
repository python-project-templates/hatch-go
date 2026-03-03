from typing import Type

from hatchling.plugin import hookimpl

from .plugin import HatchGoBuildHook


@hookimpl
def hatch_register_build_hook() -> Type[HatchGoBuildHook]:
    return HatchGoBuildHook
