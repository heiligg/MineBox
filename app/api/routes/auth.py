from __future__ import annotations

from html import escape
from urllib.parse import parse_qs

from fastapi import APIRouter, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
)

from services import auth


router = APIRouter(tags=["authentication"])


PAGE_STYLE = """
<style>
    :root {
        color-scheme: dark;
        --background: #070b10;
        --panel: #101722;
        --panel-light: #151f2c;
        --border: #263446;
        --text: #edf3f8;
        --muted: #94a3b8;
        --green: #5ce173;
        --danger: #ff8d8d;
    }

    * {
        box-sizing: border-box;
    }

    body {
        display: grid;
        min-height: 100vh;
        margin: 0;
        padding: 24px;
        place-items: center;
        color: var(--text);
        background:
            radial-gradient(
                circle at top,
                #142231 0,
                var(--background) 48%
            );
        font-family:
            Inter,
            ui-sans-serif,
            system-ui,
            -apple-system,
            BlinkMacSystemFont,
            "Segoe UI",
            sans-serif;
    }

    .auth-shell {
        width: min(100%, 430px);
    }

    .brand {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 12px;
        margin-bottom: 22px;
    }

    .brand-mark {
        display: grid;
        width: 48px;
        height: 48px;
        place-items: center;
        color: #061009;
        border-radius: 13px;
        background: var(--green);
        font-size: 23px;
        font-weight: 950;
        box-shadow: 0 0 35px rgba(92, 225, 115, 0.18);
    }

    .brand-name {
        font-size: 27px;
        font-weight: 900;
        letter-spacing: -0.8px;
    }

    .brand-subtitle {
        color: var(--muted);
        font-size: 12px;
        letter-spacing: 1.6px;
        text-transform: uppercase;
    }

    .card {
        padding: 30px;
        border: 1px solid var(--border);
        border-radius: 18px;
        background: rgba(16, 23, 34, 0.97);
        box-shadow: 0 24px 75px rgba(0, 0, 0, 0.42);
    }

    h1 {
        margin: 0 0 8px;
        font-size: 24px;
    }

    .description {
        margin: 0 0 24px;
        color: var(--muted);
        line-height: 1.55;
    }

    label {
        display: block;
        margin: 17px 0 7px;
        color: #ced8e3;
        font-size: 13px;
        font-weight: 750;
    }

    input {
        width: 100%;
        min-height: 46px;
        padding: 0 13px;
        color: var(--text);
        border: 1px solid var(--border);
        border-radius: 10px;
        outline: none;
        background: #0a1018;
        font: inherit;
    }

    input:focus {
        border-color: var(--green);
        box-shadow: 0 0 0 3px rgba(92, 225, 115, 0.11);
    }

    button {
        width: 100%;
        min-height: 47px;
        margin-top: 23px;
        color: #051008;
        border: 1px solid var(--green);
        border-radius: 10px;
        background: var(--green);
        font: inherit;
        font-weight: 900;
        cursor: pointer;
    }

    button:hover {
        filter: brightness(1.06);
    }

    button:disabled {
        opacity: 0.58;
        cursor: wait;
    }

    .message {
        min-height: 21px;
        margin-top: 14px;
        color: var(--danger);
        font-size: 13px;
        line-height: 1.5;
    }

    .security-note {
        margin-top: 18px;
        color: var(--muted);
        font-size: 12px;
        line-height: 1.5;
        text-align: center;
    }
</style>
"""


def page_html(
    title: str,
    description: str,
    form_html: str,
    script_html: str,
) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta
        name="viewport"
        content="width=device-width, initial-scale=1"
    >
    <title>{escape(title)} · MineBox</title>
    {PAGE_STYLE}
</head>
<body>
    <main class="auth-shell">
        <div class="brand">
            <div class="brand-mark">M</div>

            <div>
                <div class="brand-name">MineBox</div>
                <div class="brand-subtitle">
                    Server Appliance
                </div>
            </div>
        </div>

        <section class="card">
            <h1>{escape(title)}</h1>
            <p class="description">
                {escape(description)}
            </p>

            {form_html}
        </section>

        <div class="security-note">
            Access is limited to authenticated MineBox users.
        </div>
    </main>

    {script_html}
</body>
</html>
"""


async def read_form_body(
    request: Request,
) -> dict[str, str]:
    raw_body = await request.body()

    parsed = parse_qs(
        raw_body.decode(
            "utf-8",
            errors="replace",
        ),
        keep_blank_values=True,
    )

    return {
        key: values[-1] if values else ""
        for key, values in parsed.items()
    }


@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
):
    if not auth.is_configured():
        return RedirectResponse(
            "/auth/setup",
            status_code=303,
        )

    if request.session.get("authenticated") is True:
        return RedirectResponse(
            "/",
            status_code=303,
        )

    form = """
<form id="login-form">
    <label for="username">Username</label>
    <input
        id="username"
        name="username"
        type="text"
        autocomplete="username"
        required
        autofocus
    >

    <label for="password">Password</label>
    <input
        id="password"
        name="password"
        type="password"
        autocomplete="current-password"
        required
    >

    <button id="submit-button" type="submit">
        Sign in
    </button>

    <div class="message" id="message"></div>
</form>
"""

    script = """
<script>
    const form = document.getElementById("login-form");
    const button = document.getElementById("submit-button");
    const message = document.getElementById("message");

    form.addEventListener("submit", async event => {
        event.preventDefault();

        button.disabled = true;
        message.textContent = "";

        const body = new URLSearchParams(
            new FormData(form)
        );

        try {
            const response = await fetch(
                "/auth/login",
                {
                    method: "POST",
                    headers: {
                        "Content-Type":
                            "application/x-www-form-urlencoded"
                    },
                    body
                }
            );

            const data = await response.json();

            if (!response.ok) {
                throw new Error(
                    data.detail || "Sign in failed."
                );
            }

            window.location.replace("/");
        } catch (error) {
            message.textContent = error.message;
        } finally {
            button.disabled = false;
        }
    });
</script>
"""

    return HTMLResponse(
        page_html(
            "Sign in",
            "Enter your MineBox administrator account.",
            form,
            script,
        )
    )


@router.get(
    "/auth/setup",
    response_class=HTMLResponse,
)
def setup_page(
    request: Request,
):
    if auth.is_configured():
        return RedirectResponse(
            "/login",
            status_code=303,
        )

    form = """
<form id="setup-form">
    <label for="username">Administrator username</label>
    <input
        id="username"
        name="username"
        type="text"
        value="admin"
        autocomplete="username"
        minlength="1"
        maxlength="64"
        required
        autofocus
    >

    <label for="password">Password</label>
    <input
        id="password"
        name="password"
        type="password"
        autocomplete="new-password"
        minlength="8"
        maxlength="200"
        required
    >

    <label for="confirmation">Confirm password</label>
    <input
        id="confirmation"
        name="confirmation"
        type="password"
        autocomplete="new-password"
        minlength="8"
        maxlength="200"
        required
    >

    <button id="submit-button" type="submit">
        Create administrator
    </button>

    <div class="message" id="message"></div>
</form>
"""

    script = """
<script>
    const form = document.getElementById("setup-form");
    const button = document.getElementById("submit-button");
    const message = document.getElementById("message");

    form.addEventListener("submit", async event => {
        event.preventDefault();

        button.disabled = true;
        message.textContent = "";

        const formData = new FormData(form);

        if (
            formData.get("password") !==
            formData.get("confirmation")
        ) {
            message.textContent =
                "The passwords do not match.";

            button.disabled = false;
            return;
        }

        const body = new URLSearchParams(formData);

        try {
            const response = await fetch(
                "/auth/setup",
                {
                    method: "POST",
                    headers: {
                        "Content-Type":
                            "application/x-www-form-urlencoded"
                    },
                    body
                }
            );

            const data = await response.json();

            if (!response.ok) {
                throw new Error(
                    data.detail ||
                    "Administrator setup failed."
                );
            }

            window.location.replace("/");
        } catch (error) {
            message.textContent = error.message;
        } finally {
            button.disabled = false;
        }
    });
</script>
"""

    return HTMLResponse(
        page_html(
            "Secure your MineBox",
            (
                "Create the administrator account used to "
                "manage this appliance."
            ),
            form,
            script,
        )
    )


@router.post("/auth/setup")
async def complete_setup(
    request: Request,
):
    if auth.is_configured():
        return JSONResponse(
            {
                "ok": False,
                "detail": (
                    "MineBox authentication is already "
                    "configured."
                ),
            },
            status_code=409,
        )

    form = await read_form_body(request)

    username = form.get("username", "")
    password = form.get("password", "")
    confirmation = form.get("confirmation", "")

    if password != confirmation:
        return JSONResponse(
            {
                "ok": False,
                "detail": "The passwords do not match.",
            },
            status_code=400,
        )

    try:
        auth.create_admin(
            username,
            password,
        )
    except ValueError as exc:
        return JSONResponse(
            {
                "ok": False,
                "detail": str(exc),
            },
            status_code=400,
        )

    request.session.clear()
    request.session["authenticated"] = True
    request.session["username"] = username.strip()

    return {
        "ok": True,
        "username": username.strip(),
    }


@router.post("/auth/login")
async def login(
    request: Request,
):
    if not auth.is_configured():
        return JSONResponse(
            {
                "ok": False,
                "detail": (
                    "MineBox authentication has not been "
                    "configured."
                ),
            },
            status_code=409,
        )

    form = await read_form_body(request)

    username = form.get("username", "")
    password = form.get("password", "")

    if not auth.verify_credentials(
        username,
        password,
    ):
        return JSONResponse(
            {
                "ok": False,
                "detail": (
                    "The username or password is incorrect."
                ),
            },
            status_code=401,
        )

    request.session.clear()
    request.session["authenticated"] = True
    request.session["username"] = username.strip()

    return {
        "ok": True,
        "username": username.strip(),
    }


@router.post("/auth/logout")
def logout(
    request: Request,
):
    request.session.clear()

    return {
        "ok": True,
    }


@router.get("/api/v1/auth/status")
def authentication_status(
    request: Request,
):
    authenticated = (
        request.session.get("authenticated") is True
    )

    return {
        "ok": True,
        "configured": auth.is_configured(),
        "authenticated": authenticated,
        "username": (
            request.session.get("username")
            if authenticated
            else None
        ),
    }
