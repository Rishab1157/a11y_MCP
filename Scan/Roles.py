"""Accessibility-tree vocabulary shared across scan tools.

The canonical vocabulary is ARIA. Chrome's CDP tree uses its own names for
some roles, so ChromiumAxTreeReader normalises them through CDP_TO_ARIA
before any role check runs. Firefox's dom-accessibility-api already returns
ARIA names and needs no translation.

The mapping below was harvested from ~15,000 AX nodes across Wikipedia, MDN,
GOV.UK, GitHub, BBC News and the W3C WAI pages.
"""

# Chrome invents role names that are not in the ARIA spec.
# Applied BEFORE filtering, so every downstream check speaks one vocabulary.

CDP_TO_ARIA = {
    # straight renames
    "image":              "img",
    "RootWebArea":        "document",
    "Figcaption":         "caption",
    "DescriptionList":    "list",
    "MenuListPopup":      "listbox",
    "Iframe":             "document",
    "DisclosureTriangle": "button",     # <summary> — genuinely interactive

    # Layout tables are NOT data tables. Chrome distinguishes them and so must
    # we: mapping these to table/row/cell would raise a false "unnamed table"
    # finding for every layout table on the page.
    "LayoutTable":        "generic",
    "LayoutTableRow":     "generic",
    "LayoutTableCell":    "generic",

    # No ARIA equivalent, and they carry no semantics of their own.
    "LabelText":          "generic",
    "Abbr":               "generic",
    "sectionheader":      "generic",    # ARIA 1.3 role, not in 1.2
    "LineBreak":          "generic",
}

# Roles never emitted as their own node; their content folds into the
# parent's "text" field.
FOLDED_ROLES = {"StaticText"}

# Dropped outright — CDP rendering artefacts, not elements.
# InlineTextBox sits BELOW StaticText (line-fragment granularity), so folding
# both would duplicate every string. It is also the most common node in the
# tree by far — 4,444 of ~15,000 in the harvest.
DROPPED_ROLES = {"InlineTextBox", "ListMarker"}

# Roles a keyboard user is expected to be able to reach and operate.
INTERACTIVE_ROLES = {
    "button", "link", "textbox", "checkbox", "radio", "combobox",
    "listbox", "menuitem", "menuitemcheckbox", "menuitemradio",
    "option", "searchbox", "slider", "spinbutton", "switch", "tab",
    "treeitem",
}

# Roles where an empty accessible name is a defect.
# Interactive controls, plus non-interactive roles that still convey meaning.
# Deliberately excludes paragraph, region and form, where empty is normal.
NAME_REQUIRED_ROLES = INTERACTIVE_ROLES | {
    "img", "heading", "table", "figure",
}

# Roles carrying no semantic meaning. "generic" is listed but kept anyway when
# the node holds direct text — a wrapper div is noise, a wrapper div containing
# "ALM CONNECTIONS" is content.
IGNORED_ROLES = {"none", "presentation", "generic"}

# Properties worth keeping; the rest are noise.
KEEP_PROPERTIES = {
    "focusable", "disabled", "required", "checked", "expanded",
    "selected", "invalid", "readonly", "level", "hidden",
}
