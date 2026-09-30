"""Shared presentation palette; stored category hues remain user-controlled."""

import colorsys
import re
from functools import lru_cache

TYPE_COLORS = {
    "Entrata": "#00C878",
    "Trasferimento in entrata": "#00BEEA",
    "Uscita necessaria": "#FF3B52",
    "Uscita extra": "#FF9500",
    "Trasferimento in uscita": "#FF4081",
    "Investimento": "#8354FF",
}


@lru_cache(maxsize=256)
def vivid_category_color(value):
    """Increase saturation and lift dark colors, without changing stored data."""
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return "#5B6EEF"
    rgb = [int(value[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    hue, lightness, saturation = colorsys.rgb_to_hls(*rgb)
    # Keep intentionally neutral colors neutral; a gray has no meaningful hue.
    if saturation < 0.08:
        return value.upper()
    rgb = colorsys.hls_to_rgb(
        hue, min(0.58, max(0.50, lightness)), max(0.90, saturation)
    )
    return "#" + "".join(f"{round(channel * 255):02X}" for channel in rgb)
