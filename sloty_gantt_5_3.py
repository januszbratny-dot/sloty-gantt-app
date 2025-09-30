# sloty_gantt_8.py
# Aplikacja Streamlit — dynamiczny generator harmonogramu
# Heurystyka: opóźnienie, minimalizacja przerw, RÓWNOMIERNOŚĆ (dzień/tydzień)
# + Podgląd tygodniowej heatmapy (Pon–Ndz) z wyborem metryki

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, date, timedelta, time
from typing import List, Dict, Any
from statistics import pstdev

# --- Persistence using SQLite ---
import sqlite3
from datetime import datetime as _dt
import os

DB_PATH = "harmonogram.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS sloty (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brygada TEXT,
            data TEXT,
            start TEXT,
            end TEXT,
            slot_type TEXT,
            client TEXT,
            duration_min INTEGER
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS brygady (
            brygada TEXT PRIMARY KEY,
            start TEXT,
            end TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS slot_types (
            name TEXT PRIMARY KEY,
            minutes INTEGER
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS historia (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client TEXT,
            slot_type TEXT,
            date TEXT,
            pref_start TEXT,
            pref_end TEXT,
            assigned INTEGER,
            brygada TEXT,
            assigned_start TEXT,
            assigned_end TEXT
        )
    """)
    conn.commit()
    conn.close()

# --- przykładowe funkcje ---
def save_slot(brygada, date_obj, slot):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            INSERT INTO sloty (brygada, data, start, end, slot_type, client, duration_min)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            brygada, date_obj.strftime("%Y-%m-%d"),
            slot["start"].isoformat(), slot["end"].isoformat(),
            slot.get("slot_type"), slot.get("client"), int(slot.get("duration_min", 0))
        ))
        conn.commit()
    except Exception as e:
        st.warning(f"Nie udało się zapisać slotu do bazy: {e}")
    finally:
        conn.close()


def load_slots():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT brygada, data, start, end, slot_type, client, duration_min FROM sloty")
    rows = c.fetchall()
    conn.close()
    return rows


# --- przy starcie aplikacji ---
if __name__ == "__main__":
    st.write("DB path:", os.path.abspath(DB_PATH))
    init_db()
    # tutaj wywołanie np. load_from_db() jeżeli jest zdefiniowane
