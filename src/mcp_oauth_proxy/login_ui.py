from __future__ import annotations

from html import escape

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sign in</title>
<style>
  body {{ font-family: system-ui, sans-serif; background: #0f1115; color: #e8e8e8;
         display: flex; min-height: 100vh; align-items: center; justify-content: center; margin: 0; }}
  .card {{ background: #1a1d24; padding: 2rem; border-radius: 12px; width: 320px;
          box-shadow: 0 8px 30px rgba(0,0,0,.4); }}
  h1 {{ font-size: 1.1rem; margin: 0 0 1rem; }}
  input {{ width: 100%; box-sizing: border-box; padding: .6rem; margin: .4rem 0 1rem;
          border-radius: 8px; border: 1px solid #333; background: #0f1115; color: #e8e8e8; }}
  button {{ width: 100%; padding: .6rem; border: 0; border-radius: 8px;
           background: #4f7cff; color: #fff; font-weight: 600; cursor: pointer; }}
  .error {{ background: #3a1d1d; color: #ffb4b4; padding: .5rem .7rem; border-radius: 8px;
           margin-bottom: 1rem; font-size: .85rem; }}
  .consent {{ background: #12151c; border: 1px solid #2a2f3a; border-radius: 8px;
             padding: .7rem .8rem; margin-bottom: 1rem; font-size: .82rem; }}
  .consent .row {{ margin: .3rem 0; }}
  .consent .label {{ color: #9aa4b2; display: block; font-size: .72rem;
                    text-transform: uppercase; letter-spacing: .03em; }}
  .consent .value {{ color: #e8e8e8; word-break: break-all; }}
  .consent .warn {{ color: #ffcf8f; margin: .6rem 0 0; }}
</style>
</head>
<body>
  <div class="card">
    <h1>Enter your access secret</h1>
    {error_block}
    {consent_block}
    <form method="post" action="login">
      <input type="hidden" name="txn" value="{txn}">
      <label>Access secret</label>
      <input type="password" name="secret" autofocus autocomplete="current-password" required>
      <button type="submit">Sign in</button>
    </form>
  </div>
</body>
</html>"""


def _consent_html(consent: dict) -> str:
    app = consent.get("client_name") or consent.get("client_id") or "an unknown application"
    redirect_uri = consent.get("redirect_uri") or "(none)"
    return (
        '<div class="consent">'
        '<div class="row"><span class="label">Application requesting access</span>'
        f'<span class="value">{escape(app)}</span></div>'
        '<div class="row"><span class="label">You will be redirected to</span>'
        f'<span class="value">{escape(redirect_uri)}</span></div>'
        '<p class="warn">Only enter your secret if you started this connection and '
        'recognize the destination above.</p>'
        '</div>'
    )


def render_login_page(txn_id: str, error: str | None = None, consent: dict | None = None) -> str:
    error_block = ""
    if error:
        error_block = f'<div class="error">{escape(error)}</div>'
    consent_block = _consent_html(consent) if consent else ""
    return _PAGE.format(
        txn=escape(txn_id, quote=True),
        error_block=error_block,
        consent_block=consent_block,
    )
