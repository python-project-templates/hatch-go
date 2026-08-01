from hatchling.plugin import hookimpl

from .plugin import HatchGoBuildHook


@hookimpl
def hatch_register_build_hook() -> type[HatchGoBuildHook]:
    return HatchGoBuildHook
