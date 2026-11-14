"""Dev API server for `npm run dev`: uvicorn with auto-reload that watches only our source.

Run through the venv runner:  node scripts/py.mjs scripts/dev_api.py [extra uvicorn args]

Watched: server/main.py, server/core, server/rules, server/features, config/  (*.py, *.yaml).
Ignored: .venv, __pycache__, data/, server/tests.
uvicorn's --reload-dir only accepts directories (a file path is silently dropped), so we watch
`server/` and exclude the tests. That covers main.py, core/, rules/ and features/.

Windows fix: to restart its worker on a reload, uvicorn sends CTRL_C_EVENT, and Windows delivers
that to every process on the console. Under `npm run dev` that includes Vite, npm and
concurrently, so one reload took down the whole dev stack. On Windows we make the reloader
terminate the worker instead, the same way uvicorn already does on macOS/Linux. Our lifespan has
no shutdown work, so nothing is lost.
"""
from __future__ import annotations

import os
import sys

UVICORN_ARGS = [
    "server.main:app",
    "--port=8000",
    "--reload",
    "--reload-dir=server",
    "--reload-dir=config",
    "--reload-include=*.py",
    "--reload-include=*.yaml",
    # Patterns are matched against the end of each path (pathlib.Path.match), one level each.
    "--reload-exclude=.venv/*",
    "--reload-exclude=__pycache__/*",
    "--reload-exclude=data/*",
    "--reload-exclude=server/tests/*",
    "--reload-exclude=server/tests/*/*",
    "--reload-exclude=test_*.py",
]


def _patch_windows_restart() -> None:
    from uvicorn._subprocess import get_subprocess
    from uvicorn.supervisors.basereload import BaseReload

    def restart(self: BaseReload) -> None:
        self.process.terminate()  # TerminateProcess: no console-wide Ctrl+C
        self.process.join()
        self.process = get_subprocess(config=self.config, target=self.target, sockets=self.sockets)
        self.process.start()

    BaseReload.restart = restart  # type: ignore[method-assign]


def main() -> None:
    # Run from the project root so "server.main:app" and the relative reload dirs resolve.
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    sys.path.insert(0, os.getcwd())
    if sys.platform == "win32":
        _patch_windows_restart()

    from uvicorn.main import main as uvicorn_main

    # windows_expand_args=False: otherwise Click (uvicorn's CLI) glob-expands patterns such as
    # "server/tests/*" into file lists on Windows.
    uvicorn_main([*UVICORN_ARGS, *sys.argv[1:]], windows_expand_args=False)


if __name__ == "__main__":
    main()
