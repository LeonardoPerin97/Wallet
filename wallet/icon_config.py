"""Central icon names and restrained placeholder glyphs for Wallet.

Subcategory.icon can hold any of the identifiers below. A later icon set can
replace these glyphs without changing database records or templates.
"""

ICON_GLYPHS = {
    "tag": "◇",
    "shopping-cart": "▣",
    "briefcase": "▤",
    "coffee": "◉",
    "restaurant": "⌁",
    "home": "⌂",
    "bolt": "ϟ",
    "car": "▰",
    "health": "+",
    "plane": "↗",
    "ticket": "▣",
    "shirt": "◇",
    "transfer": "↔",
}

# Fallbacks used only when a subcategory still has the generic "tag" icon.
# Keep the mapping here (rather than in templates) so the eventual icon set is
# a small, reviewable configuration change.
SUBCATEGORY_ICON_PLACEHOLDERS = {
    "stipendio": "briefcase",
    "supermercato": "shopping-cart",
    "bar": "coffee",
    "bar / caffè": "coffee",
    "ristoranti": "restaurant",
    "affitto / mutuo": "home",
    "bollette": "bolt",
    "carburante": "car",
    "autostrade / pedaggi": "car",
    "farmacia": "health",
    "aereo": "plane",
    "cinema": "ticket",
    "cinema / teatro / concerti": "ticket",
    "abbigliamento": "shirt",
}


def icon_for_subcategory(name, configured="tag"):
    identifier = (configured or "tag").strip().lower()
    if identifier == "tag":
        identifier = SUBCATEGORY_ICON_PLACEHOLDERS.get(name.strip().lower(), "tag")
    return identifier if identifier in ICON_GLYPHS else "tag"


def glyph_for_icon(identifier):
    return ICON_GLYPHS.get(identifier, ICON_GLYPHS["tag"])
