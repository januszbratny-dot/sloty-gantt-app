import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date, time, timedelta
import os

DB_PATH = "harmonogram.db"

def init_db(db_path=DB_PATH):
    """Create DB and tables if they don't exist. Commit and close connection."""
    conn = sqlite3.connect(db_path)
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

def add_slot(brygada, date_obj, start_obj, end_obj, slot_type, client, duration_min, db_path=DB_PATH):
    """Insert a slot into the sloty table and commit."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO sloty (brygada, data, start, end, slot_type, client, duration_min)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            brygada,
            date_obj.strftime("%Y-%m-%d"),
            start_obj.strftime("%H:%M"),
            end_obj.strftime("%H:%M"),
            slot_type,
            client,
            int(duration_min) if duration_min is not None else None
        ))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error saving slot: {e}")
        return False
    finally:
        conn.close()

def get_slots(db_path=DB_PATH):
    """Return all slots as a pandas DataFrame."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""SELECT id, brygada, data, start, end, slot_type, client, duration_min FROM sloty ORDER BY data, start""")
    rows = c.fetchall()
    conn.close()
    df = pd.DataFrame(rows, columns=["id","brygada","data","start","end","slot_type","client","duration_min"])
    return df

def delete_slot(slot_id, db_path=DB_PATH):
    """Delete slot by id and commit."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    try:
        c.execute("DELETE FROM sloty WHERE id = ?", (slot_id,))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error deleting slot: {e}")
        return False
    finally:
        conn.close()

def add_sample_data(db_path=DB_PATH):
    """Insert sample brygady, slot_types and a few slots for testing."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    try:
        # sample brygady
        c.execute("INSERT OR IGNORE INTO brygady(brygada, start, end) VALUES (?, ?, ?)", ("A", "08:00", "16:00"))
        c.execute("INSERT OR IGNORE INTO brygady(brygada, start, end) VALUES (?, ?, ?)", ("B", "09:00", "17:00"))
        # sample slot types
        c.execute("INSERT OR IGNORE INTO slot_types(name, minutes) VALUES (?, ?)", ("Standard", 60))
        c.execute("INSERT OR IGNORE INTO slot_types(name, minutes) VALUES (?, ?)", ("Short", 30))
        c.execute("INSERT OR IGNORE INTO slot_types(name, minutes) VALUES (?, ?)", ("Long", 120))
        # sample slots
        today = date.today()
        c.execute("INSERT INTO sloty(brygada, data, start, end, slot_type, client, duration_min) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  ("A", today.strftime("%Y-%m-%d"), "08:00", "09:00", "Standard", "Klient1", 60))
        c.execute("INSERT INTO sloty(brygada, data, start, end, slot_type, client, duration_min) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  ("B", (today + timedelta(days=1)).strftime("%Y-%m-%d"), "09:00", "10:00", "Short", "Klient2", 30))
        conn.commit()
    except Exception as e:
        st.error(f"Error inserting sample data: {e}")
    finally:
        conn.close()

def get_brygady(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT brygada FROM brygady ORDER BY brygada")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_slot_types(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT name, minutes FROM slot_types ORDER BY name")
    rows = c.fetchall()
    conn.close()
    return [ {"name": r[0], "minutes": r[1]} for r in rows ]

# ------------------ Streamlit UI ------------------
st.set_page_config(page_title="Sloty Gantt - Simple DB Demo", layout="wide")

st.title("Sloty Gantt — demo z trwałą bazą SQLite")
st.markdown("W tej uproszczonej wersji możesz dodawać sloty, przeglądać je i usuwać. Dane są zapisywane w pliku **harmonogram.db** w katalogu aplikacji.")

# ensure DB exists
init_db()

# left column: form to add a slot
left, right = st.columns([1,2])

with left:
    st.header("Dodaj slot")
    brygady = get_brygady()
    if not brygady:
        st.info("Brak zdefiniowanych brygad — dodam przykładowe dane.") 
        add_sample_data()
        brygady = get_brygady()

    slot_types = get_slot_types()
    slot_type_names = [st["name"] for st in slot_types] if slot_types else ["Standard"]

    form = st.form("add_slot_form")
    with form:
        brygada = st.selectbox("Brygada", options=brygady)
        slot_date = st.date_input("Data", value=date.today())
        start_time = st.time_input("Start", value=time(8,0))
        end_time = st.time_input("End", value=time(9,0))
        slot_type = st.selectbox("Typ slotu", options=slot_type_names)
        client = st.text_input("Klient", value="")
        duration = st.number_input("Czas trwania (min)", min_value=0, value=60)
        submitted = st.form_submit_button("Dodaj slot")
        if submitted:
            ok = add_slot(brygada, slot_date, start_time, end_time, slot_type, client, duration)
            if ok:
                st.success("Slot zapisany do bazy.")
            else:
                st.error("Nie udało się zapisać slotu.")
            st.experimental_rerun()

with right:
    st.header("Lista slotów")
    df = get_slots()
    if df.empty:
        st.info("Brak zapisanych slotów.")
    else:
        # show table, allow delete by selecting id
        st.dataframe(df.assign(data=pd.to_datetime(df['data'])), use_container_width=True)
        st.write("---")
        sel = st.number_input("Wpisz ID slotu do usunięcia", min_value=0, step=1)
        if st.button("Usuń slot o podanym ID"):
            if sel > 0:
                success = delete_slot(int(sel))
                if success:
                    st.success(f"Usunięto slot id={sel}")
                else:
                    st.error("Nie udało się usunąć slotu.")
                st.experimental_rerun()
            else:
                st.warning("Podaj poprawne ID (>0)")

# show DB path for debugging
st.caption(f"DB path: {os.path.abspath(DB_PATH)}")
