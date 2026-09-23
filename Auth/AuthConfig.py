from typing import Annotated, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class _AuthBase(BaseModel):
    """Shared settings for every auth mode."""
    model_config = ConfigDict(extra = "forbid")
    
    
class NoAuth(_AuthBase):
    """Public site — no authentication needed."""
    mode: Literal["none"] = "none"
    
    
class TokenAuth(_AuthBase):
    """Caller already holds a token. Inject it into browser storage."""
    mode: Literal["token"] = "token"
    
    token: str = Field(description = "The token value itself.")
    storage_key: str = Field("default-token-val", description="Name the app reads it under.")
    storage_type: Literal["local", "session", "cookie"] = "local"
    

class ApiAuth(_AuthBase):
    """POST credentials to the app's own login endpoint, then inject the token."""
    mode: Literal["api"] = "api"

    login_endpoint: str = Field(description="Full URL of the login API.")
    payload: dict = Field(description="Body the API expects, e.g. {'email':..,'password':..}.")
    token_field: str = Field("token", description=(
            "Key holding the token in the JSON response. Supports a dotted path "
            "for nested bodies, e.g. 'data.token'. Optional: pass null when the "
            "app authenticates by a session cookie rather than a stored token — "
            "the cookies the login endpoint sets are carried into the browser "
            "either way."
        )
    )
    storage_key: str = Field("token", description="Name the app reads it under.")
    storage_type: Literal["local", "session", "cookie"] = "local"
    headers: Optional[dict] = Field(None, description="Extra request headers if required.")
    
    
class FormAuth(_AuthBase):
    """Fill and submit a login form in the browser. Cannot handle SSO or MFA."""
    mode: Literal["form"] = "form"

    username: str
    password: str
    login_url: Optional[str] = Field(None, description="Defaults to the current page.")
    username_selector: Optional[str] = Field(None, description="CSS selector; auto-detected if unset.")
    password_selector: Optional[str] = None
    submit_selector: Optional[str] = None
    
    
class StorageAuth(_AuthBase):
    """Replay browser state exported from a real logged-in session."""
    mode: Literal["storage"] = "storage"

    local_storage: dict = Field(default_factory = dict)
    session_storage: dict = Field(default_factory = dict)
    cookies: list[dict] = Field(default_factory = list)
    
    
AnyAuthConfig = Annotated[
    NoAuth | TokenAuth | ApiAuth | FormAuth | StorageAuth,
    Field(discriminator="mode"),
]