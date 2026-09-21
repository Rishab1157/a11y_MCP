"""
Workflow models.

Target  = WHICH element     
Step    = WHAT action to perform
Expect  = HOW we know it worked, and WHICH element proves it
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator, ConfigDict


class Target(BaseModel):
    """
    Identifies a UI element by its accessible name and role,
    rather than by CSS selectors or HTML structure.
    """
    
    model_config = ConfigDict(extra='forbid')
    
    name: Optional[str] = Field(
        None, description="Accessible name"
    )
    role: Optional[str] = Field(
        None, description="Accessibility role. It Helps distinguish elements with the same name."
    )
    within: Optional["Target"] = Field(
        None, description="Scope the search inside this ancestor"
    )
    nth: Optional[int] = Field(
        ge=0, description="Zero-based index into the final filtered matches"
    )
    css: Optional[str] = Field(
        None, description="CSS selector used as an additional constraint or fallback locator."
    )
Target.model_rebuild() 

class State(BaseModel):
    """Accessibility states the engine can actually observe."""
    
    model_config = ConfigDict(extra="forbid")
    
    # None  → don't check
    checked: Optional[bool] = Field(
        None, description="Whether the element is checked or unchecked."
    ) # Checkbox, switch, → checked
    expanded: Optional[bool] = Field(
        None, description="Whether the element is expanded or collapsed."
    ) # Dropdown, Expandable row  → expanded
    selected: Optional[bool] = Field(
        None, description="Whether the element is selected or unselected."
    ) # Tab, option, list item → selected
    disabled: Optional[bool] = Field(
        None, description="Whether the element is enabled or disabled."
    ) # Button, Input, Checkbox, Select/dropdown, Textarea → disabled
    required: Optional[bool] = Field(
        None, description="Whether the element is required or optional."
    )  # Input, Checkbox, Select/dropdown, Textarea → required
    readonly: Optional[bool] = Field(
        None, description="Whether the element is read-only or editable."
    )  # Input, Textarea → readonly
    invalid: Optional[str] = Field(
        None, description="Whether the element has a valid or invalid value."
    )  # Input, Textarea, Select → validation state
    value: Optional[str] = Field(
        None, description="Current value of the field."
    )  # Input, Textarea, Select, Contenteditable → current value
    
class Expect(BaseModel):
    """Assertion checked after the action.

    Element checks (`state`, `text_changed`) use their own `target`
    and are resolved against the DOM after the action.

    Page checks (`appears`, `disappears`, `text_contains`) use the
    given text as the locator and do not require a target.

    Strength order:
        state > appears/disappears > text_contains > text_changed
    """
    
    model_config = ConfigDict(extra='forbid')
    
    label: Optional[str] = Field(
        None, description="Short description for the trail"
    )
    # ── element-level: target required ────────────────────────────────────
    target: Optional[Target] = Field(
        None, description="The element this assertion is about. Required for `state`, `text_changed`. Resolved after the action."
    )
    state: Optional[State] = Field(
        None, description="Accessibility state the target must hold. Strongest proof."
    )
    text_changed: Optional[bool] = Field(
        None, description="Capture the target's text before the action and wait for "
        "it to change. Weakest anchor: proves something changed, "
        "not that the intended state was reached. An element that "
        "did not exist before and appears after counts as changed."
    )
    
    # ── page-level: no target ─────────────────────────────────────────────
    appears: Optional[str] = Field(
        None, description="Accessible name that must exist anywhere on the page."
    )
    disappears: Optional[str] = Field(
        None, description="Accessible name that must be gone, e.g. a loading "
    )
    text_contains: Optional[str] = Field(
        None, description="Text that must be present anywhere on the page."
    )
    timeout: int = Field(
        30, ge=1, le=600,
        description="Seconds to wait for this assertion"
    )

    @model_validator(mode="after")
    def _check_shape(self):
        element_level = self.state is not None or self.text_changed is not None

        if element_level and self.target is None:
            raise ValueError(
                "`state` and `text_changed` assert about one element and need their "
                "own `target`. The Step's target is never inherited — after a "
                "navigation it may no longer exist."
            )
        if self.target is not None and not element_level:
            raise ValueError(
                "`target` is only used by `state` and `text_changed`. Page-level "
                "assertions (appears, disappears, text_contains) carry their own name."
            )
        if not any(f is not None for f in (self.state, self.text_changed, self.appears, self.disappears, self.text_contains)):
            raise ValueError(
                "An Expect must assert something: state, text_changed, appears, "
                "disappears or text_contains."
            )
        return self
    
class Step(BaseModel):
    """One action against one target, with zero or more independent assertions."""
    
    model_config = ConfigDict(extra="forbid")
    
    action: Literal[
        "navigate", "click", "fill", "ensure_checked",
        "ensure_unchecked", "press", "hover", "scroll_to"
    ]
    target: Optional[Target] = Field(
        None, description="The element to act on. Required for every action except navigate."
    )
    value: Optional[str] = Field(
        None, description="Text for fill, key name for press, URL for navigate."
    )
    expects: list[Expect] = Field(
        default_factory=list,
        description="After every action, run all defined checks in order."
        "If any check fails, stop the step."
        "If there are no checks, the system assumes the action worked,"
        "which can allow an incorrect workflow state to go unnoticed"
    )