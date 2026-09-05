from __future__ import annotations

import os

ROLE = os.environ.get("ROLE")
MODE = os.environ.get("MODE")

if ROLE == "controller":
    if MODE == "matrix":
        from docker.matrix_service import main
    else:
        from docker.controller_service import main
else:
    from docker.node_service import main

main()
