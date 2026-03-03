from os import listdir
from pathlib import Path
from shutil import rmtree
from subprocess import check_call
from sys import executable, modules, path, platform, version_info

import pytest


class TestProject:
    @pytest.mark.parametrize(
        "project_folder",
        [
            "test_project_basic",
        ],
    )
    def test_basic(self, project_folder):
        # cleanup
        rmtree(f"hatch_go/tests/{project_folder}/dist", ignore_errors=True)
        for ext in ("*.so", "*.pyd", "*.dll", "*.dylib"):
            for f in Path(f"hatch_go/tests/{project_folder}/project").glob(ext):
                f.unlink()
        modules.pop("project", None)
        modules.pop("project.project", None)

        # compile
        check_call(
            [
                "hatchling",
                "build",
                "--hooks-only",
            ],
            cwd=f"hatch_go/tests/{project_folder}",
        )

        # assert built
        project_dir = f"hatch_go/tests/{project_folder}/project"
        files = listdir(project_dir)
        if platform == "win32":
            assert any(f.endswith(".pyd") for f in files), f"No .pyd file found in {files}"
        else:
            assert any(f.endswith(".so") for f in files), f"No .so file found in {files}"

        # dist
        check_call(
            [
                executable,
                "-m",
                "build",
                "-w",
                "-n",
            ],
            cwd=f"hatch_go/tests/{project_folder}",
        )

        dist_files = listdir(f"hatch_go/tests/{project_folder}/dist")
        assert len(dist_files) > 0, "No dist files created"
        assert f"cp3{version_info.minor}" in dist_files[0], f"Expected cp3{version_info.minor} in {dist_files[0]}"

        # import
        here = Path(__file__).parent / project_folder
        path.insert(0, str(here))
        try:
            import project.project

            assert project.project.hello() == "A string from Go"
            assert project.project.add(2, 3) == 5
            assert project.project.add(-1, 1) == 0
        finally:
            path.remove(str(here))
