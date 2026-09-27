"""Number formats shared by the manifest, the renderer, the site bundle and the workbook.

A figure is stored raw in the manifest with a named format, and every surface
formats it through this module, so the README and the board pack cannot print the
same number two different ways.
"""

from __future__ import annotations

import math
from collections.abc import Callable

FormatFn = Callable[[float | int | str | None], str]


def _num(value: float | int | str | None) -> float:
    if value is None or isinstance(value, str):
        raise TypeError(f"expected a number, got {value!r}")
    return float(value)


def _plain(value: float, decimals: int) -> str:
    text = f"{value:,.{decimals}f}"
    return "0" if text in {"-0", "-0.0", "-0.00"} and decimals == 0 else text.replace("-0.00", "0.00")


def fmt_int(value: float | int | str | None) -> str:
    return f"{round(_num(value)):,}"


def _fixed(decimals: int) -> FormatFn:
    def inner(value: float | int | str | None) -> str:
        return _plain(_num(value), decimals)

    return inner


def _pct(decimals: int) -> FormatFn:
    def inner(value: float | int | str | None) -> str:
        return f"{_plain(_num(value) * 100.0, decimals)}%"

    return inner


def _usd(decimals: int) -> FormatFn:
    def inner(value: float | int | str | None) -> str:
        number = _num(value)
        sign = "-" if number < 0 else ""
        return f"{sign}${abs(number):,.{decimals}f}"

    return inner


def fmt_usd_millions(value: float | int | str | None) -> str:
    number = _num(value) / 1_000_000.0
    sign = "-" if number < 0 else ""
    return f"{sign}${abs(number):,.1f}M"


def fmt_usd_billions(value: float | int | str | None) -> str:
    number = _num(value) / 1_000_000_000.0
    sign = "-" if number < 0 else ""
    return f"{sign}${abs(number):,.2f}B"


def fmt_bps(value: float | int | str | None) -> str:
    return f"{round(_num(value)):,} bp"


def fmt_signed_pct1(value: float | int | str | None) -> str:
    number = _num(value) * 100.0
    sign = "+" if number > 0 else ""
    return f"{sign}{number:,.1f}%"


def fmt_text(value: float | int | str | None) -> str:
    if value is None:
        return "not available"
    return str(value)


FORMATS: dict[str, FormatFn] = {
    "int": fmt_int,
    "float1": _fixed(1),
    "float2": _fixed(2),
    "float3": _fixed(3),
    "float4": _fixed(4),
    "pct0": _pct(0),
    "pct1": _pct(1),
    "pct2": _pct(2),
    "pct3": _pct(3),
    "spct1": fmt_signed_pct1,
    "usd0": _usd(0),
    "usd2": _usd(2),
    "usdm": fmt_usd_millions,
    "usdb": fmt_usd_billions,
    "bps": fmt_bps,
    "text": fmt_text,
}


def format_value(value: float | int | str | None, fmt: str) -> str:
    if fmt not in FORMATS:
        raise KeyError(f"unknown format {fmt!r}")
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return "not available"
    return FORMATS[fmt](value)
