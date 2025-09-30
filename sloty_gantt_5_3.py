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

def load_from_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Load slot types (if any) into session_state
    try:
        c.execute("SELECT name, minutes FROM slot_types")
        rows = c.fetchall()
        if rows:
            st.session_state.slot_types = [{"name": n, "minutes": m} for n, m in rows]
    except Exception:
        pass

    # Load brygady and working hours
    try:
        c.execute("SELECT brygada, start, end FROM brygady")
        rows = c.fetchall()
        for b, start, end in rows:
            if b not in st.session_state.brygady:
                st.session_state.brygady.append(b)
            try:
                st.session_state.working_hours[b] = (
                    _dt.strptime(start, "%H:%M").time(),
                    _dt.strptime(end, "%H:%M").time()
                )
            except Exception:
                # ignore parse issues
                pass
    except Exception:
        pass

    # Load slots
    try:
        c.execute("SELECT brygada, data, start, end, slot_type, client, duration_min FROM sloty")
        rows = c.fetchall()
        for b, d, s, e, stype, cl, dur in rows:
            day_key = d  # stored as YYYY-MM-DD string
            # ensure keys exist
            if b not in st.session_state.schedules:
                st.session_state.schedules[b] = {}
            if day_key not in st.session_state.schedules[b]:
                st.session_state.schedules[b][day_key] = []
            try:
                st.session_state.schedules[b][day_key].append({
                    "start": _dt.fromisoformat(s),
                    "end": _dt.fromisoformat(e),
                    "slot_type": stype,
                    "duration_min": dur,
                    "client": cl
                })
            except Exception:
                # if parsing fails, skip
                continue
    except Exception:
        pass

    # Load history
    try:
        c.execute("SELECT client, slot_type, date, pref_start, pref_end, assigned, brygada, assigned_start, assigned_end FROM historia")
        rows = c.fetchall()
        for row in rows:
            client_entry = {
                "client": row[0],
                "slot_type": row[1],
                "date": row[2],
                "pref_start": row[3],
                "pref_end": row[4],
                "assigned": bool(row[5]),
            }
            if row[5]:
                client_entry["assigned_info"] = {
                    "brygada": row[6],
                    "start": _dt.fromisoformat(row[7]) if row[7] else None,
                    "end": _dt.fromisoformat(row[8]) if row[8] else None,
                }
            st.session_state.clients_added.append(client_entry)
    except Exception:
        pass

    conn.close()

def save_slot_to_db(brygada, date_obj, slot):
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
        # swallow DB errors but log in Streamlit
        st.warning(f"Nie udało się zapisać slotu do bazy: {e}")
    finally:
        conn.close()

def save_client_history(client_entry):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        info = client_entry.get("assigned_info") or {}
        c.execute("""
            INSERT INTO historia (client, slot_type, date, pref_start, pref_end, assigned, brygada, assigned_start, assigned_end)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            client_entry.get("client"),
            client_entry.get("slot_type"),
            client_entry.get("date"),
            client_entry.get("pref_start"),
            client_entry.get("pref_end"),
            int(client_entry.get("assigned", False)),
            info.get("brygada"),
            info.get("start").isoformat() if info.get("start") else None,
            info.get("end").isoformat() if info.get("end") else None
        ))
        conn.commit()
    except Exception as e:
        st.warning(f"Nie udało się zapisać historii do bazy: {e}")
    finally:
        conn.close()

def save_brygady_to_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        # upsert brygady
        for b in st.session_state.brygady:
            start, end = st.session_state.working_hours.get(b, (None, None))
            start_s = start.strftime("%H:%M") if start else None
            end_s = end.strftime("%H:%M") if end else None
            c.execute("""
                INSERT INTO brygady (brygada, start, end) VALUES (?, ?, ?)
                ON CONFLICT(brygada) DO UPDATE SET start=excluded.start, end=excluded.end
            """, (b, start_s, end_s))
        conn.commit()
    except Exception as e:
        st.warning(f"Nie udało się zapisać brygad do bazy: {e}")
    finally:
        conn.close()

def save_slot_types_to_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        for stype in st.session_state.slot_types:
            name = stype.get("name")
            minutes = int(stype.get("minutes", 0))
            c.execute("""
                INSERT INTO slot_types (name, minutes) VALUES (?, ?)
                ON CONFLICT(name) DO UPDATE SET minutes=excluded.minutes
            """, (name, minutes))
        conn.commit()
    except Exception as e:
        st.warning(f"Nie udało się zapisać typów slotów do bazy: {e}")
    finally:
        conn.close()
# --- end persistence ---

init_db()
load_from_db()

# -----------------------------
# Stan aplikacji (session_state)
# -----------------------------
if 'slot_types' not in st.session_state:
    st.session_state.slot_types = [
        {"name": "Standard", "minutes": 60},
        {"name": "Premium", "minutes": 120},
    ]

if 'brygady' not in st.session_state:
    st.session_state.brygady = ["Brygada A", "Brygada B"]

if 'working_hours' not in st.session_state:
    st.session_state.working_hours = {}

if 'schedules' not in st.session_state:
    st.session_state.schedules = {}

if 'clients_added' not in st.session_state:
    st.session_state.clients_added = []

# Helper functions

def ensure_brygady_in_state(brygady_list):
    for b in brygady_list:
        if b not in st.session_state.working_hours:
            st.session_state.working_hours[b] = (time(8, 0), time(16, 0))
        if b not in st.session_state.schedules:
            st.session_state.schedules[b] = {}


def get_day_slots_for_brygada(brygada: str, day: date):
    ds = st.session_state.schedules.get(brygada, {})
    return ds.get(day.strftime("%Y-%m-%d"), [])


def add_slot_to_brygada(brygada: str, day: date, slot: dict):
    day_key = day.strftime("%Y-%m-%d")
    if brygada not in st.session_state.schedules:
        st.session_state.schedules[brygada] = {}
    if day_key not in st.session_state.schedules[brygada]:
        st.session_state.schedules[brygada][day_key] = []
    st.session_state.schedules[brygada][day_key].append(slot)
    # persist
    try:
        save_slot_to_db(brygada, day, slot)
    except Exception:
        pass

# ... (pozostała część oryginalnego kodu bez zmian)

# (Dalsza część pliku pozostaje bez zmian — aplikacja Streamlit, heurystyka, UI, wykresy itp.)
