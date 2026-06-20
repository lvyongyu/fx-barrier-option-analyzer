"""Minimal position-management UI (list + add + delete) backed by Turso.

The UI is the single entry point for trade terms; GitHub Actions only writes
knockout state. Run with:

    streamlit run src/ui.py

Requires TURSO_DATABASE_URL + TURSO_AUTH_TOKEN (loaded from .env), otherwise it
falls back to the local sqlite file like the CLI does.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

# `streamlit run src/ui.py` puts src/ on sys.path (not the repo root), so the
# `src` package isn't importable. Add the repo root so the app works however
# it's launched.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from src.data.data_loader import normalize_pair_label
from src.monitoring.monitor import new_position
from src.storage.repository import (
    connect_positions,
    delete_monitored_position,
    init_db,
    load_monitored_positions,
    monitored_position_label_exists,
    save_monitored_position,
)

load_dotenv()

DISPLAY_COLUMNS = [
    "id",
    "pair",
    "barrier_direction",
    "barrier",
    "strike",
    "spot",
    "trade_date",
    "expiry_date",
    "status",
    "triggered_date",
    "client_direction",
]


def load_positions() -> list[dict]:
    with connect_positions() as connection:
        init_db(connection)
        return load_monitored_positions(connection)


def validate(values: dict, existing_ids: set[str]) -> list[str]:
    errors: list[str] = []
    if not values["id"].strip():
        errors.append("ID is required.")
    elif values["id"].strip() in existing_ids:
        errors.append(f"ID '{values['id'].strip()}' already exists.")
    for field in ("spot", "strike", "barrier"):
        if values[field] <= 0:
            errors.append(f"{field.capitalize()} must be greater than 0.")
    # Barrier-direction vs spot sanity (the classic data-entry mistake).
    if values["barrier"] > 0 and values["spot"] > 0:
        if values["barrier_direction"] == "down" and values["barrier"] >= values["spot"]:
            errors.append("A 'down' barrier must be below spot.")
        if values["barrier_direction"] == "up" and values["barrier"] <= values["spot"]:
            errors.append("An 'up' barrier must be above spot.")
    if values["expiry_date"] <= values["trade_date"]:
        errors.append("Expiry must be after the trade date.")
    return errors


st.set_page_config(page_title="Barrier Positions", layout="wide")
st.title("📊 Barrier Position Manager")

positions = load_positions()
existing_ids = {str(p["id"]) for p in positions}

# --- List -------------------------------------------------------------------
st.subheader(f"Positions ({len(positions)})")
if positions:
    frame = pd.DataFrame(positions)
    frame = frame[[c for c in DISPLAY_COLUMNS if c in frame.columns]]
    st.dataframe(frame, use_container_width=True, hide_index=True)
else:
    st.info("No positions yet. Add one below.")

col_add, col_delete = st.columns(2)

# --- Add --------------------------------------------------------------------
with col_add:
    st.subheader("➕ Add position")
    with st.form("add_position", clear_on_submit=False):
        pid = st.text_input("ID", placeholder="audusd-07110-up-2026-12-30")
        pair = st.text_input("Pair", value="AUD/USD")
        c1, c2 = st.columns(2)
        trade_date = c1.date_input("Trade date", value=date.today())
        expiry_date = c2.date_input("Expiry date", value=date.today())
        c3, c4, c5 = st.columns(3)
        spot = c3.number_input("Spot", min_value=0.0, value=0.0, step=0.0001, format="%.4f")
        strike = c4.number_input("Strike", min_value=0.0, value=0.0, step=0.0001, format="%.4f")
        barrier = c5.number_input("Barrier", min_value=0.0, value=0.0, step=0.0001, format="%.4f")
        c6, c7 = st.columns(2)
        barrier_direction = c6.selectbox("Barrier direction", ["down", "up"])
        client_direction = c7.selectbox("Client direction", ["", "Importer", "Exporter"])
        product_type = st.text_input("Product type", value="Ratio Convertible Forward")
        note = st.text_area("Note", placeholder="Corpay ref / protected & ratio amounts / etc.")
        submitted = st.form_submit_button("Add")

    if submitted:
        values = {
            "id": pid,
            "spot": spot,
            "strike": strike,
            "barrier": barrier,
            "barrier_direction": barrier_direction,
            "trade_date": trade_date,
            "expiry_date": expiry_date,
        }
        errors = validate(values, existing_ids)
        try:
            pair_label = normalize_pair_label(pair)
        except ValueError as exc:
            errors.append(str(exc))
            pair_label = pair
        if errors:
            for message in errors:
                st.error(message)
        else:
            with connect_positions() as connection:
                init_db(connection)
                if monitored_position_label_exists(connection, pid.strip()):
                    st.error(f"ID '{pid.strip()}' already exists.")
                else:
                    position = new_position(
                        pid.strip(),
                        pair=pair_label,
                        trade_date=trade_date,
                        spot=spot,
                        strike=strike,
                        barrier=barrier,
                        expiry_date=expiry_date,
                        barrier_direction=barrier_direction,
                        product_type=product_type,
                        client_direction=client_direction or None,
                        note=note or None,
                    )
                    save_monitored_position(connection, position)
                    connection.commit()
                    st.success(f"Added '{pid.strip()}'.")
                    st.rerun()

# --- Delete -----------------------------------------------------------------
with col_delete:
    st.subheader("🗑️ Delete position")
    if not positions:
        st.caption("Nothing to delete.")
    else:
        target = st.selectbox("Select a position", sorted(existing_ids))
        confirm = st.checkbox(f"Confirm delete '{target}'")
        if st.button("Delete", type="primary", disabled=not confirm):
            with connect_positions() as connection:
                init_db(connection)
                deleted = delete_monitored_position(connection, target)
                connection.commit()
            if deleted:
                st.success(f"Deleted '{target}'.")
                st.rerun()
            else:
                st.warning(f"'{target}' not found.")
