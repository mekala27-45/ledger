"""The site's number formats are the pipeline's number formats.

Every page formats manifest values in the browser with web/src/lib/format.ts, and
every document formats them with ledger_core.formats. This runs both over the same
grid and requires identical text, so a figure cannot read one way in the board pack
and another on the site.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ledger_core.formats import FORMATS, format_value

ROOT = Path(__file__).resolve().parents[2]
VALUES = [
    0.0,
    -0.0,
    1.0,
    -1.0,
    0.5,
    1.5,
    2.5,
    -2.5,
    0.125,
    -0.0004,
    0.00001,
    -0.00001,
    0.031234,
    -0.0512,
    0.9841568128,
    12.345,
    -0.4,
    -0.6,
    1234.5,
    -2500.0,
    40_000.0,
    -40_000.0,
    12_345_678.0,
    1_234_567_890.0,
    3.14159,
    1.005,
    0.0005,
    999.995,
    999_999.95,
    0.045,
    0.0000001,
    -999.5,
    9.999999,
]


def test_site_formats_match_the_pipeline() -> None:
    formats = [f for f in FORMATS if f != "text"]
    script = (
        "const { formatValue } = await import(process.argv[1]);"
        "const [values, formats] = JSON.parse(process.argv[2]);"
        "console.log(JSON.stringify(values.map((v) => formats.map((f) => formatValue(v, f)))));"
    )
    # JSON has no negative zero, so -0.0 travels as a marker and is restored in node.
    payload = json.dumps([["-0" if str(v) == "-0.0" else v for v in VALUES], formats])
    script = script.replace(
        "const [values, formats] = JSON.parse(process.argv[2]);",
        "const [raw, formats] = JSON.parse(process.argv[2]); const values = raw.map((v) => v === '-0' ? -0 : v);",
    )
    out = subprocess.run(
        [
            "node",
            "--experimental-strip-types",
            "--no-warnings",
            "--input-type=module",
            "-e",
            script,
            str(ROOT / "web" / "src" / "lib" / "format.ts"),
            payload,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    site = json.loads(out.stdout)
    mismatches = [
        (v, f, format_value(v, f), site[i][j])
        for i, v in enumerate(VALUES)
        for j, f in enumerate(formats)
        if format_value(v, f) != site[i][j]
    ]
    assert not mismatches, mismatches


def test_missing_values_read_the_same() -> None:
    assert format_value(None, "pct1") == "not applicable"
    assert format_value(None, "text") == "not available"
