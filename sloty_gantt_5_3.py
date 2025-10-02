import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import os
import json
import random
from datetime import datetime, timedelta, date, time
from statistics import pstdev

# ===================== PERSISTENCE (JSON) =====================

def schedules_to_jsonable():
    data = {}
    for b, days in st.session_state.schedules.items():
        data[b] = {}
        for d, slots in days.items():
            data[b][d] = [
                {
                    "start": s["start"].isoformat(),
                    "end": s["end"].isoformat(),
                    "slot_type": s["slot_type"],
                    "duration_min": s["duration_min"],
                    "client": s["client"],
                }
                for s in slots
            ]
    return {
        "slot_types": st.session_state.slot_types,
        "brygady": st.session_state.brygady,
        "working_hours": {
            b: (wh[0].isoformat(), wh[1].isoformat())
            for b, wh in st.session_state.working_hours.items()
        },
        "schedules": data,
        "clients_added": st.session_state.clients_added,
        "heur_weights": st.session_state.heur_weights,
        "balance_horizon": st.session_state.balance_horizon,
    }

def save_state_to_json(filename="schedules.json"):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(schedules_to_jsonable(), f, ensure_ascii=False, indent=2)

def load_state_from_json(filename="schedules.json"):
    if not os.path.exists(filename):
        return False
    with open(filename, "r", encoding="utf-8") as f:
        data = json.load(f)

    st.session_state.slot_types = data.get("slot_types", [])
    st.session_state.brygady = data.get("brygady", [])

    def parse_time_str(t):
        try:
            return datetime.fromisoformat(t).time()
        except ValueError:
            return datetime.strptime(t, "%H:%M:%S").time() if ":" in t else datetime.strptime(t, "%H:%M").time()

    st.session_state.working_hours = {
        b: (parse_time_str(wh[0]), parse_time_str(wh[1]))
        for b, wh in data.get("working_hours", {}).items()
    }

    st.session_state.schedules = {}
    for b, days in data.get("schedules", {}).items():
        st.session_state.schedules[b] = {}
        for d, slots in days.items():
            st.session_state.schedules[b][d] = [
                {
                    "start": datetime.fromisoformat(s["start"]),
                    "end": datetime.fromisoformat(s["end"]),
                    "slot_type": s["slot_type"],
                    "duration_min": s["duration_min"],
                    "client": s["client"],
                }
                for s in slots
            ]
    st.session_state.clients_added = data.get("clients_added", [])
    st.session_state.heur_weights = data.get("heur_weights", {"delay": 0.34, "gap": 0.33, "balance": 0.33})
    st.session_state.balance_horizon = data.get("balance_horizon", "week")
    return True

# ===================== INICJALIZACJA STANU =====================

if "slot_types" not in st.session_state:
    if not load_state_from_json():
        st.session_state.slot_types = [{"name": "Standard", "minutes": 60, "weight": 1}]
        st.session_state.brygady = ["Brygada 1", "Brygada 2"]
        st.session_state.working_hours = {}
        st.session_state.schedules = {}
        st.session_state.clients_added = []
        st.session_state.heur_weights = {"delay": 0.34, "gap": 0.33, "balance": 0.33}
        st.session_state.balance_horizon = "week"

if "client_counter" not in st.session_state:
    st.session_state.client_counter = 1

# ===================== FUNKCJE POMOCNICZE =====================

def parse_slot_types(text):
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) >= 3:
            try:
                minutes = int(parts[1])
                weight = float(parts[2])
                out.append({"name": parts[0].strip(), "minutes": minutes, "weight": weight})
            except:
                pass
        elif len(parts) == 2:  # kompatybilność wstecz
            try:
                minutes = int(parts[1])
                out.append({"name": parts[0].strip(), "minutes": minutes, "weight": 1})
            except:
                pass
    return out

def weighted_choice(slot_types):
    names = [s["name"] for s in slot_types]
    weights = [s.get("weight", 1) for s in slot_types]
    return random.choices(names, weights=weights, k=1)[0]

def ensure_brygady_in_state(brygady_list):
    for b in brygady_list:
        if b not in st.session_state.working_hours:
            st.session_state.working_hours[b] = (time(8, 0), time(16, 0))
        if b not in st.session_state.schedules:
            st.session_state.schedules[b] = {}

def get_day_slots_for_brygada(brygada, day):
    d = day.strftime("%Y-%m-%d")
    return sorted(st.session_state.schedules.get(brygada, {}).get(d, []), key=lambda s: s["start"])

def add_slot_to_brygada(brygada, day, slot):
    d = day.strftime("%Y-%m-%d")
    if d not in st.session_state.schedules[brygada]:
        st.session_state.schedules[brygada][d] = []
    lst = st.session_state.schedules[brygada][d]
    lst.append(slot)
    lst.sort(key=lambda s: s["start"])
    save_state_to_json()

def minutes_between(t1, t2):
    return int((t2 - t1).total_seconds() / 60)

def total_work_minutes_for_brygada(brygada):
    start_t, end_t = st.session_state.working_hours[brygada]
    return minutes_between(datetime.combine(date.today(), start_t), datetime.combine(date.today(), end_t))

def compute_utilization_for_day(brygada, day):
    used = sum(s["duration_min"] for s in get_day_slots_for_brygada(brygada, day))
    return used / total_work_minutes_for_brygada(brygada) if total_work_minutes_for_brygada(brygada) > 0 else 0

def daily_used_minutes(brygada, day):
    return sum(s["duration_min"] for s in get_day_slots_for_brygada(brygada, day))

def week_days_containing(day):
    monday = day - timedelta(days=day.weekday())
    return [monday + timedelta(days=i) for i in range(7)]

def used_minutes_for_week(brygada, any_day_in_week):
    return sum(daily_used_minutes(brygada, d) for d in week_days_containing(any_day_in_week))

# ===================== HEURYSTYKA =====================
# (ta część bez zmian – zostaje jak w poprzednim kodzie)
# ... skrócone dla przejrzystości ...

# ===================== PREDEFINIOWANE PRZEDZIAŁY =====================

PREFERRED_SLOTS = {
    "8:00-12:00": (time(8, 0), time(12, 0)),
    "12:00-16:00": (time(12, 0), time(16, 0)),
    "16:00-20:00": (time(16, 0), time(20, 0)),
}

# ===================== DODAWANIE KLIENTA =====================

st.subheader("Dodaj klienta")
with st.form("add_client_form"):
    default_client_name = f"Klient {st.session_state.client_counter}"
    client_name = st.text_input("Nazwa klienta", value=default_client_name)

    # losowy wybór slotu wg wagi
    if st.session_state.slot_types:
        slot_type_name = weighted_choice(st.session_state.slot_types)
    else:
        slot_type_name = "Standard"

    day = st.date_input("Dzień", value=date.today())

    # losowy przedział czasowy
    pref_range_label = random.choice(list(PREFERRED_SLOTS.keys()))
    pref_start, pref_end = PREFERRED_SLOTS[pref_range_label]

    st.write(f"Automatycznie wybrano: **{slot_type_name}**, preferencja: **{pref_range_label}**")

    submitted = st.form_submit_button("Dodaj")
    if submitted:
        # ... wywołanie schedule_client_immediately jak w poprzednim kodzie ...
        st.session_state.client_counter += 1
