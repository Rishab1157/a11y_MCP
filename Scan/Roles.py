"""Accessibility-tree vocabulary shared across scan tools.

The canonical vocabulary is ARIA. Chrome's CDP tree uses its own names for
some roles, so ChromiumAxTreeReader normalises them through CDP_TO_ARIA
before any role check runs. Firefox's dom-accessibility-api already returns
ARIA names and needs no translation.
"""

# Chrome's AX tree invents role names that are not in the ARIA spec.
# Applied before filtering, so every downstream check speaks one vocabulary.
CDP_TO_ARIA = {
    "image": "img",
    "RootWebArea": "document",
    "LineBreak": "generic",
    "InlineTextBox": "generic",
}

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

# Roles carrying no semantic meaning. "generic" is listed but kept anyway
# when the node holds direct text — a wrapper div is noise, a wrapper div
# containing "ALM CONNECTIONS" is content.
IGNORED_ROLES = {
    "none", "presentation", "generic",
}

# Roles never emitted as their own node. StaticText is a CDP tree artefact,
# not an element; its content folds into the parent's "text" field.
FOLDED_ROLES = {
    "StaticText",
}

# Properties worth keeping; the rest are noise.
KEEP_PROPERTIES = {
    "focusable", "disabled", "required", "checked", "expanded",
    "selected", "invalid", "readonly", "level", "hidden",
}
