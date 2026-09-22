import re

LOGIN_WORDS = ("login", "log in", "sign in", "signin", "authenticate")

SSO_HOSTS = (
    "login.microsoftonline.com", "accounts.google.com", "okta.com",
    "auth0.com", "onelogin.com", "pingidentity.com", "login.salesforce.com",
)

SSO_TEXT_HINTS = (
    "sign in with", "continue with", "log in with", "login with",
    "single sign", "sso", "saml", "use my organization",
    "microsoft", "google", "okta", "azure", "entra",
)

SSO_TEXT_MATCHERS = tuple(
    (hint, re.compile(rf"\b{re.escape(hint)}\b", re.I)) for hint in SSO_TEXT_HINTS
)