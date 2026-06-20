import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest


def test_login_gate_blocks_when_password_set(monkeypatch) -> None:
    # With UI_PASSWORD set and no prior auth, the app must show the password
    # prompt and NOT render the management UI (st.stop runs before any DB call,
    # so this test never touches Turso/sqlite or the network).
    monkeypatch.setenv("UI_PASSWORD", "secret123")
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)

    app = AppTest.from_file("src/ui.py").run()

    assert any(ti.label == "Password" for ti in app.text_input)
    assert "📊 Barrier Position Manager" not in [t.value for t in app.title]


def test_login_gate_accepts_correct_password(monkeypatch, tmp_path) -> None:
    # Entering the correct password authenticates the session. Redirect the
    # local-sqlite fallback to a temp file so the authed render can't touch the
    # real DB or the network.
    monkeypatch.setenv("UI_PASSWORD", "secret123")
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    from src.storage import repository

    monkeypatch.setattr(repository, "DEFAULT_POSITIONS_DB_PATH", tmp_path / "p.sqlite3")

    app = AppTest.from_file("src/ui.py").run()
    app.text_input[0].set_value("secret123")
    app.button[0].click()
    app.run()

    assert app.session_state["authenticated"] is True
