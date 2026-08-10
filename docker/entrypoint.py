from __future__ import annotations

import os

if os.environ.get("ROLE") == "controller":
    from docker.controller_service import main
else:
    from docker.node_service import main

main()
