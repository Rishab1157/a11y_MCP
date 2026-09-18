USERNAME_GUESSES = [
    # ── exact ids ─────────────────────────────────────────────────────────
    "#username",                                # id="username"
    "#user",                                    # id="user"
    "#email",                                   # id="email"
    "#login",                                   # id="login"

    # ── exact names ───────────────────────────────────────────────────────
    "input[name='username']",                   # <input name="username">
    "input[name='userName']",                   # camelCase variant
    "input[name='user_name']",                  # snake_case variant
    "input[name='user']",                       # <input name="user">
    "input[name='userId']",                     # <input name="userId">
    "input[name='user_id']",                    # <input name="user_id">
    "input[name='email']",                      # <input name="email">
    "input[name='login']",                      # <input name="login">
    "input[name='loginId']",                    # <input name="loginId">
    "input[name='login_id']",                   # <input name="login_id">

    # ── semantic attributes ───────────────────────────────────────────────
    "input[autocomplete='username']",           # browser-declared intent
    "input[autocomplete='email']",
    "input[type='email']",                      # <input type="email">

    # ── partial matches (i = case-insensitive) ────────────────────────────
    "input[id*='username' i]",
    "input[id*='user' i]",
    "input[id*='login' i]",
    "input[id*='email' i]",
    "input[placeholder*='username' i]",
    "input[placeholder*='user id' i]",
    "input[placeholder*='userid' i]",
    "input[placeholder*='email' i]",
    "input[placeholder*='user' i]",
    "input[placeholder*='login' i]",

    # ── last resort ───────────────────────────────────────────────────────
    # Matches almost any text box, including search and newsletter fields.
    # Must stay last: _find returns the first match.
    "input[type='text']",
]

PASSWORD_GUESSES = [
    # Nothing else in HTML is a password field — most reliable selector there is.
    "input[type='password']",

    "#password",                                # id="password"
    "input[name='password']",                   # <input name="password">
    "input[autocomplete='current-password']",   # browser-declared intent
    "input[autocomplete='new-password']",

    "input[id*='password' i]",
    "input[name*='password' i]",
    "input[placeholder*='password' i]",
]

SUBMIT_GUESSES = [
    # ── explicit submit controls ──────────────────────────────────────────
    "button[type='submit']",
    "input[type='submit']",
    "button[name='submit']",
    "input[name='submit']",

    # ── ids, scoped to clickable elements ─────────────────────────────────
    # Bare "#login" would also match <form id="login">, so the element is named.
    "button#login_button, input#login_button, a#login_button",
    "button#login-button, input#login-button, a#login-button",
    "button#submit-button, input#submit-button, a#submit-button",
    "button#submit_button, input#submit_button, a#submit_button",
    "button#submit, input#submit, a#submit",
    "button#signin, input#signin, a#signin",
    "button#sign-in, input#sign-in, a#sign-in",
    "button#sign_in, input#sign_in, a#sign_in",
    "button#login, input#login, a#login",

    # ── test hooks ────────────────────────────────────────────────────────
    "[data-testid*='submit' i]",
    "[data-testid*='login' i]",
    "[data-testid*='signin' i]",
    "[data-testid*='sign-in' i]",

    # ── accessible names ──────────────────────────────────────────────────
    "[role='button'][aria-label*='sign in' i]",
    "[role='button'][aria-label*='login' i]",
    "[role='button'][aria-label*='submit' i]",
]



