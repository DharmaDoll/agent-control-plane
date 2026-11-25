"""List candidate executables without invoking shims or loading project code."""
import json
import os
import shutil

CLIENTS = ("npm", "pnpm", "yarn", "bun", "pip", "pip3", "uv", "gem", "bundle",
           "cargo", "composer", "go")


if __name__ == "__main__":
    for client in CLIENTS:
        path = shutil.which(client)
        print(json.dumps({"client": client, "executable": os.path.abspath(path) if path else None,
                          "state": "candidate" if path else "missing from PATH"}))
