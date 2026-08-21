from __future__ import annotations

import shutil
import tempfile
import urllib.request
from pathlib import Path

XTERM_VERSION = "6.0.0"
FIT_VERSION = "0.11.0"
ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "pah" / "web" / "static" / "vendor" / "xterm"
FILES = {
    f"https://unpkg.com/@xterm/xterm@{XTERM_VERSION}/lib/xterm.js": "xterm.js",
    f"https://unpkg.com/@xterm/xterm@{XTERM_VERSION}/css/xterm.css": "xterm.css",
    f"https://unpkg.com/@xterm/xterm@{XTERM_VERSION}/LICENSE": "LICENSE.xterm.txt",
    f"https://unpkg.com/@xterm/addon-fit@{FIT_VERSION}/lib/addon-fit.js": "addon-fit.js",
    f"https://unpkg.com/@xterm/addon-fit@{FIT_VERSION}/LICENSE": "LICENSE.addon-fit.txt",
}


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pah-xterm-") as tmp:
        tmpdir = Path(tmp)
        for url, name in FILES.items():
            target = tmpdir / name
            print(f"Downloading {url}")
            with urllib.request.urlopen(url, timeout=30) as response, target.open("wb") as out:
                shutil.copyfileobj(response, out)
            shutil.move(str(target), DEST / name)
    print(f"Vendored xterm.js {XTERM_VERSION} + addon-fit {FIT_VERSION} under {DEST}")
    print("Normal PAH runtime is now fully local/offline; these files are served by Flask.")


if __name__ == "__main__":
    main()
