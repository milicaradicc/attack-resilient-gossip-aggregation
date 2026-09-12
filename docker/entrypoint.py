from __future__ import annotations

import os

ROLE = os.environ.get("ROLE")

if ROLE == "controller":
    from docker.matrix_service import main
else:
    from docker.node_service import main

main()