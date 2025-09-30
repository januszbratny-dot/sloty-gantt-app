# sloty_gantt_8_fixed.py
# Aplikacja Streamlit — dynamiczny generator harmonogramu
# Dodano: obsługę uszkodzonej bazy SQLite (integrity_check + auto-reset)

import sqlite3
import json
import os
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, date, timedelta, time
from typing import List, Dict, Any
from statistics import pstdev

# --- Trwały zapis stanu do SQLite ---
DB_PATH = "harmonogram.db"


def _ensure_db_ok():
    """Sprawdź integralność bazy. Jeśli uszkodzona → usuń plik."""
    if not os.path.exists(DB_PATH):
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.execute("PRAGMA integrity_check;")
        result = cur.fetchone()
        conn.close()
        if not result or result[0] != "ok":
            os.remove(DB_PATH)
    except sqlite3.DatabaseError:
        try:
            conn.close()
        except:
            pass
        os.remove(DB_PATH)


def save_state_to_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, data TEXT)")
    data = {
        "slot_types": st.session_state.slot_types,
        "brygady": st.session_state.brygady,
        "working_hours": {k: (v[0].strftime("%H:%M"), v[1].strftime("%H:%M"))
                          for k, v in st.session_state.working_hours.items()},
        "schedules": st.session_state.schedules,
        "clients_added": st.session_state.clients_added,
        "heur_weights": st.session_state.heur_weights,
        "balance_horizon": st.session_state.balance_horizon,
    }
    c.execute("DELETE FROM state")
    c.execute("INSERT INTO state (data) VALUES (?)", (json.dumps(data),))
    conn.commit()
    conn.close()


def load_state_from_db():
    _ensure_db_ok()
    if not os.path.exists(DB_PATH):
        return
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, data TEXT)")
    c.execute("SELECT data FROM state ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    if row:
        data = json.loads(row[0])
        st.session_state.slot_types = data.get("slot_types", [])
        st.session_state.brygady = data.get("brygady", [])
        st.session_state.working_hours = {
            k: (time.fromisoformat(v[0]), time.fromisoformat(v[1]))
            for k, v in data.get("working_hours", {}).items()
        }
        st.session_state.schedules = data.get("schedules", {})
        st.session_state.clients_added = data.get("clients_added", [])
        st.session_state.heur_weights = data.get(
            "heur_weights", {"delay": 0.5, "gap": 0.3, "balance": 0.2}
        )
        st.session_state.balance_horizon = data.get("balance_horizon", "week")


# -----------------------------
# Konfiguracja strony i tytuł
# -----------------------------
st.set_page_config(page_title="Sloty Gantt - dynamiczny (heatmapa tygodniowa)", layout="wide")
st.title("Dynamiczny generator harmonogramu — brygady z indywidualnymi godzinami")

# --- Inicjalizacja stanu i ładowanie z bazy ---
if "initialized" not in st.session_state:
    load_state_from_db()
    st.session_state.initialized = True

if "slot_types" not in st.session_state:
    st.session_state.slot_types = [
        {"name": "Proste zlecenie", "minutes": 30},
        {"name": "Normalne zlecenie", "minutes": 60},
        {"name": "Skomplikowane zlecenie", "minutes": 120}
    ]

if "brygady" not in st.session_state:
    st.session_state.brygady = ['Brygada 1', 'Brygada 2', 'Brygada 3']

if "working_hours" not in st.session_state:
    st.session_state.working_hours = {}
st.session_state.working_hours["Brygada 1"] = (time(8, 0), time(16, 0))
st.session_state.working_hours["Brygada 2"] = (time(10, 0), time(18, 0))
st.session_state.working_hours["Brygada 3"] = (time(12, 0), time(20, 0))

if "schedules" not in st.session_state:
    st.session_state.schedules = {}

if "clients_added" not in st.session_state:
    st.session_state.clients_added = []

if "heur_weights" not in st.session_state:
    st.session_state.heur_weights = {"delay": 0.5, "gap": 0.3, "balance": 0.2}

if "balance_horizon" not in st.session_state:
    st.session_state.balance_horizon = "week"

# -----------------------------
# Funkcje pomocnicze
# -----------------------------

def get_schedule_for_day(day: date) -> Dict[str, List[Dict[str, Any]]]:
    day_key = str(day)
    if day_key not in st.session_state.schedules:
        st.session_state.schedules[day_key] = {b: [] for b in st.session_state.brygady}
    return st.session_state.schedules[day_key]


def add_slot(day: date, brygada: str, slot_type: str,
             start_time: time, end_time: time, client_name: str):
    sched = get_schedule_for_day(day)
    sched[brygada].append({
        "slot_type": slot_type,
        "start": start_time.strftime("%H:%M"),
        "end": end_time.strftime("%H:%M"),
        "client": client_name
    })
    sched[brygada].sort(key=lambda x: x["start"])


def used_minutes_for_day(day: date) -> Dict[str, int]:
    sched = get_schedule_for_day(day)
    used = {}
    for b in st.session_state.brygady:
        used[b] = sum(
            (datetime.strptime(s["end"], "%H:%M") - datetime.strptime(s["start"], "%H:%M")).seconds // 60
            for s in sched.get(b, [])
        )
    return used


def used_minutes_for_week(week_start: date) -> Dict[str, int]:
    totals = {b: 0 for b in st.session_state.brygady}
    for i in range(7):
        day = week_start + timedelta(days=i)
        day_used = used_minutes_for_day(day)
        for b in totals:
            totals[b] += day_used.get(b, 0)
    return totals


def fairness_std(horizon: str, ref_date: date) -> float:
    if horizon == "day":
        vals = list(used_minutes_for_day(ref_date).values())
    else:
        week_start = ref_date - timedelta(days=ref_date.weekday())
        vals = list(used_minutes_for_week(week_start).values())
    if len(vals) <= 1:
        return 0.0
    return pstdev(vals)


def find_best_insertion_for_client(client_name: str, slot_type: Dict[str, Any],
                                   pref_date: date, pref_time: time,
                                   horizon: str) -> Dict[str, Any]:
    slot_minutes = slot_type["minutes"]
    best_score = None
    best_option = None

    for brygada in st.session_state.brygady:
        start_work, end_work = st.session_state.working_hours[brygada]
        day_sched = get_schedule_for_day(pref_date)[brygada]
        free_intervals = []
        current = datetime.combine(pref_date, start_work)
        for s in day_sched:
            stime = datetime.combine(pref_date, datetime.strptime(s["start"], "%H:%M").time())
            etime = datetime.combine(pref_date, datetime.strptime(s["end"], "%H:%M").time())
            if stime > current:
                free_intervals.append((current, stime))
            current = max(current, etime)
        work_end = datetime.combine(pref_date, end_work)
        if current < work_end:
            free_intervals.append((current, work_end))

        for (fi_start, fi_end) in free_intervals:
            if (fi_end - fi_start).seconds // 60 >= slot_minutes:
                start_dt = fi_start
                end_dt = start_dt + timedelta(minutes=slot_minutes)
                delay_minutes = max(0, int((start_dt - datetime.combine(pref_date, pref_time)).total_seconds() // 60))
                gap_penalty = sum(max(0, (datetime.strptime(s["start"], "%H:%M") -
                                          end_dt.time()).total_seconds() // 60)
                                  for s in day_sched
                                  if datetime.strptime(s["start"], "%H:%M").time() > end_dt.time())
                add_slot(pref_date, brygada, slot_type["name"], start_dt.time(), end_dt.time(), client_name)
                fairness_after = fairness_std(horizon, pref_date)
                get_schedule_for_day(pref_date)[brygada].pop()
                score = (
                    -st.session_state.heur_weights["delay"] * delay_minutes
                    -st.session_state.heur_weights["gap"] * gap_penalty
                    -st.session_state.heur_weights["balance"] * fairness_after
                )
                if best_score is None or score > best_score:
                    best_score = score
                    best_option = {"brygada": brygada, "start": start_dt, "end": end_dt}
    return best_option


# -----------------------------
# Panel boczny — konfiguracja
# -----------------------------
st.sidebar.header("Konfiguracja")

with st.sidebar.expander("Rodzaje slotów"):
    for i, slot in enumerate(st.session_state.slot_types):
        st.session_state.slot_types[i]["name"] = st.text_input(f"Nazwa {i+1}", value=slot["name"], key=f"slot_name_{i}")
        st.session_state.slot_types[i]["minutes"] = st.number_input(f"Czas trwania {i+1} (min)",
                                                                    value=slot["minutes"], key=f"slot_minutes_{i}")
    if st.button("Dodaj slot"):
        st.session_state.slot_types.append({"name": "Nowy slot", "minutes": 60})
    save_state_to_db()

with st.sidebar.expander("Brygady"):
    new_brygada = st.text_input("Dodaj brygadę")
    if st.button("Dodaj brygadę"):
        if new_brygada not in st.session_state.brygady:
            st.session_state.brygady.append(new_brygada)
            st.session_state.working_hours[new_brygada] = (time(8, 0), time(16, 0))
            save_state_to_db()
    for b in st.session_state.brygady:
        st.write(b)

with st.sidebar.expander("Godziny pracy"):
    for b in st.session_state.brygady:
        start = st.time_input(f"{b} start", value=st.session_state.working_hours[b][0], key=f"{b}_start")
        end = st.time_input(f"{b} koniec", value=st.session_state.working_hours[b][1], key=f"{b}_end")
        st.session_state.working_hours[b] = (start, end)
    save_state_to_db()

with st.sidebar.expander("Heurystyka"):
    d = st.slider("Waga opóźnienia", 0.0, 1.0, st.session_state.heur_weights["delay"], 0.05)
    g = st.slider("Waga przerw (gap)", 0.0, 1.0, st.session_state.heur_weights["gap"], 0.05)
    b = st.slider("Waga balansu", 0.0, 1.0, st.session_state.heur_weights["balance"], 0.05)
    total = d + g + b
    if total > 0:
        st.session_state.heur_weights = {"delay": d/total, "gap": g/total, "balance": b/total}
    st.session_state.balance_horizon = st.radio("Horyzont balansu", ["day", "week"],
                                                index=0 if st.session_state.balance_horizon == "day" else 1)
    save_state_to_db()

with st.sidebar.expander("Reset"):
    if st.button("Wyczyść całą bazę"):
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.experimental_rerun()

# -----------------------------
# Formularz dodawania klienta
# -----------------------------
st.header("Dodaj klienta")

with st.form("add_client_form"):
    client_name = st.text_input("Nazwa klienta")
    slot_type_name = st.selectbox("Rodzaj slotu", [s["name"] for s in st.session_state.slot_types])
    pref_date = st.date_input("Preferowana data", value=date.today())
    pref_time = st.time_input("Preferowany czas", value=time(9, 0))
    submitted = st.form_submit_button("Dodaj klienta")
    if submitted and client_name:
        slot_type = next(s for s in st.session_state.slot_types if s["name"] == slot_type_name)
        option = find_best_insertion_for_client(client_name, slot_type, pref_date, pref_time,
                                                st.session_state.balance_horizon)
        assigned = False
        assigned_info = None
        if option:
            add_slot(pref_date, option["brygada"], slot_type["name"],
                     option["start"].time(), option["end"].time(), client_name)
            save_state_to_db()
            st.success(f"Przydzielono {client_name} do {option['brygada']} "
                       f"{option['start'].strftime('%Y-%m-%d %H:%M')}-{option['end'].strftime('%H:%M')}")
            assigned = True
            assigned_info = {
                "brygada": option["brygada"],
                "start": option["start"].strftime("%Y-%m-%d %H:%M"),
                "end": option["end"].strftime("%H:%M")
            }
        else:
            st.warning("Nie udało się znaleźć slotu dla klienta.")
        st.session_state.clients_added.append({
            "name": client_name,
            "slot_type": slot_type_name,
            "pref_date": str(pref_date),
            "pref_time": pref_time.strftime("%H:%M"),
            "assigned": assigned,
            "assigned_info": assigned_info
        })
        save_state_to_db()

# -----------------------------
# Widoki: tabela, Gantt, wykorzystanie
# -----------------------------
st.header("Harmonogram")

view_date = st.date_input("Wybierz dzień do podglądu", value=date.today())

sched = get_schedule_for_day(view_date)
rows = []
for b in st.session_state.brygady:
    for s in sched[b]:
        rows.append({"Brygada": b, "Klient": s["client"], "Rodzaj": s["slot_type"],
                     "Start": s["start"], "Koniec": s["end"]})
df = pd.DataFrame(rows)

st.subheader("Tabela")
st.dataframe(df if not df.empty else pd.DataFrame(columns=["Brygada", "Klient", "Rodzaj", "Start", "Koniec"]))

st.subheader("Gantt")
try:
    if not df.empty:
        fig = px.timeline(df, x_start="Start", x_end="Koniec", y="Brygada",
                          color="Klient", text="Rodzaj")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.write("Brak zadań.")
except Exception as e:
    st.error(f"Błąd w rysowaniu Gantta: {e}")

st.subheader("Wykorzystanie dnia")
used = used_minutes_for_day(view_date)
util_df = pd.DataFrame([{"Brygada": b, "Minuty": used[b]} for b in st.session_state.brygady])
st.dataframe(util_df)

st.subheader("Heatmapa tygodniowa")
week_start = view_date - timedelta(days=view_date.weekday())
heat_data = []
for i in range(7):
    d = week_start + timedelta(days=i)
    used_d = used_minutes_for_day(d)
    for b in st.session_state.brygady:
        start_work, end_work = st.session_state.working_hours[b]
        cap = (datetime.combine(d, end_work) - datetime.combine(d, start_work)).seconds // 60
        utilization = used_d[b] / cap * 100 if cap > 0 else 0
        heat_data.append({"Brygada": b, "Dzień": d.strftime("%a %d.%m"),
                          "Wykorzystanie %": utilization})
heat_df = pd.DataFrame(heat_data)
pivot = heat_df.pivot(index="Brygada", columns="Dzień", values="Wykorzystanie %")
st.dataframe(pivot)
st.dataframe(heat_df)

csv = heat_df.to_csv(index=False).encode("utf-8")
st.download_button("Pobierz heatmapę CSV", data=csv, file_name="heatmap.csv", mime="text/csv")

# -----------------------------
# Historia klientów
# -----------------------------
st.header("Historia dodanych klientów")
hist_df = pd.DataFrame(st.session_state.clients_added)
st.dataframe(hist_df if not hist_df.empty else pd.DataFrame(columns=[
    "name", "slot_type", "pref_date", "pref_time", "assigned", "assigned_info"
]))
