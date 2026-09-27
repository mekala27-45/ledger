"""The daily demo as a make target: record the desk's replay and write docs/images/desk.gif.

Needs the built site in web/out (`make web`) and the site's Playwright. The page plays
its recorded replay because no API is running, which is the same thing a visitor sees
when the API is asleep, and the banner saying so is in every frame.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images" / "desk.gif"
WIDTH = 800


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def main() -> int:
    site = ROOT / "web" / "out"
    if not (site / "desk" / "index.html").exists():
        print("web/out has no desk page; run `make web` first")
        return 1
    port = free_port()
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--directory", str(site)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(
                ["node", "tests/record-demo.mjs", f"http://127.0.0.1:{port}/desk/", tmp, "36", "300"],
                cwd=ROOT / "web",
                check=True,
                env={**os.environ},
            )
            frames = []
            for path in sorted(Path(tmp).glob("frame-*.png")):
                image = Image.open(path).convert("RGB")
                height = round(image.height * WIDTH / image.width)
                frames.append(image.resize((WIDTH, height), Image.Resampling.LANCZOS).quantize(colors=48))
            OUT.parent.mkdir(parents=True, exist_ok=True)
            frames[0].save(OUT, save_all=True, append_images=frames[1:], duration=300, loop=0, optimize=True)
    finally:
        server.terminate()
    print(f"wrote {OUT.relative_to(ROOT)}: {len(frames)} frames, {OUT.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
