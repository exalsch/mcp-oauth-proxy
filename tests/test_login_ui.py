from mcp_oauth_proxy.login_ui import render_login_page


def test_page_contains_form_and_txn():
    html = render_login_page("txn-abc")
    assert "<form" in html
    assert 'name="txn"' in html
    assert "txn-abc" in html
    assert 'name="secret"' in html
    assert 'type="password"' in html


def test_no_error_block_when_no_error():
    html = render_login_page("t1")
    assert "error" not in html.lower() or "class=\"error\"" not in html


def test_error_is_shown_and_escaped():
    html = render_login_page("t1", error="Bad <secret> & stuff")
    assert "Bad &lt;secret&gt; &amp; stuff" in html
    assert "<secret>" not in html


def test_txn_is_escaped():
    html = render_login_page('"><script>x')
    assert "<script>" not in html
