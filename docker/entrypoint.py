from __future__ import annotations

import os

ROLE = os.environ.get("ROLE")

if ROLE == "controller":
    from docker.matrix import main
else:
    from docker.node import main

main()