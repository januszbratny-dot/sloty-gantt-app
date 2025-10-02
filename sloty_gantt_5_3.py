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
                    "pref_range": s.get("pref_range", "")
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
        "client_counter": st.session_state.client_counter,
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
                    "pref_range": s.get("pref_range", "")
                }
                for s in slots
            ]
    st.session_state.clients_added = data.get("clients_added", [])
    st.session_state.heur_weights = data.get("heur_weights", {"delay": 0.34, "gap": 0.33, "balance": 0.33})
    st.session_state.balance_horizon = data.get("balance_horizon", "week")
    st.session_state.client_counter = data.get("client_counter", 1)
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

# ===================== HEURYSTYKA (bez zmian) =====================
# ... zachowana jak w Twoim kodzie ...

# ===================== PREDEFINIOWANE PRZEDZIAŁY =====================

PREFERRED_SLOTS = {
    "8:00-12:00": (time(8, 0), time(12, 0)),
    "12:00-16:00": (time(12, 0), time(16, 0)),
    "16:00-20:00": (time(16, 0), time(20, 0)),
}

# ===================== INTERFEJS =====================

st.title("Harmonogram slotów (z persystencją JSON)")

with st.sidebar:
    st.subheader("Konfiguracja slotów")
    txt = st.text_area(
        "Typy slotów (format: Nazwa, minuty, waga)",
        value="\n".join(f"{s['name']}, {s['minutes']}, {s.get('weight',1)}" for s in st.session_state.slot_types)
    )
    st.session_state.slot_types = parse_slot_types(txt)

    st.subheader("Brygady")
    txt_b = st.text_area("Lista brygad (po jednej w linii)", value="\n".join(st.session_state.brygady))
    st.session_state.brygady = [line.strip() for line in txt_b.splitlines() if line.strip()]
    ensure_brygady_in_state(st.session_state.brygady)

    for b in st.session_state.brygady:
        st.write(f"Godziny pracy {b}:")
        start_t = st.time_input(f"Start {b}", value=st.session_state.working_hours[b][0], key=f"{b}_start")
        end_t = st.time_input(f"Koniec {b}", value=st.session_state.working_hours[b][1], key=f"{b}_end")
        st.session_state.working_hours[b] = (start_t, end_t)

    st.subheader("Wagi heurystyki")
    d = st.slider("Delay", 0.0, 1.0, st.session_state.heur_weights["delay"])
    g = st.slider("Gap", 0.0, 1.0, st.session_state.heur_weights["gap"])
    bal = st.slider("Balance", 0.0, 1.0, st.session_state.heur_weights["balance"])
    s = d + g + bal
    if s == 0:
        st.session_state.heur_weights = {"delay": 0.34, "gap": 0.33, "balance": 0.33}
    else:
        st.session_state.heur_weights = {"delay": d/s, "gap": g/s, "balance": bal/s}

    st.session_state.balance_horizon = st.selectbox("Horyzont równomierności", ["week", "day"], index=0 if st.session_state.balance_horizon=="week" else 1)

    if st.button("Wyczyść harmonogram"):
        st.session_state.schedules = {b: {} for b in st.session_state.brygady}
        st.session_state.clients_added = []
        st.session_state.client_counter = 1
        save_state_to_json()
        st.success("Harmonogram wyczyszczony i zapisany.")

# ===================== DODAWANIE KLIENTA =====================

st.subheader("Dodaj klienta")
with st.form("add_client_form"):
    default_client_name = f"Klient {st.session_state.client_counter}"
    client_name = st.text_input("Nazwa klienta", value=default_client_name)

    # Losowanie typu slotu
    if st.session_state.slot_types:
        auto_slot_type_name = weighted_choice(st.session_state.slot_types)
    else:
        auto_slot_type_name = "Standard"

    # Losowanie przedziału preferencji
    auto_pref_range_label = random.choice(list(PREFERRED_SLOTS.keys()))
    auto_pref_start, auto_pref_end = PREFERRED_SLOTS[auto_pref_range_label]

    st.info(f"Automatycznie wybrano: **{auto_slot_type_name}**, preferencja: **{auto_pref_range_label}**")

    # Możliwość ręcznej zmiany
    slot_type_name = st.selectbox(
        "Wybierz typ slotu (możesz zmienić wylosowany)",
        [s["name"] for s in st.session_state.slot_types],
        index=[s["name"] for s in st.session_state.slot_types].index(auto_slot_type_name)
        if auto_slot_type_name in [s["name"] for s in st.session_state.slot_types] else 0
    )

    pref_range_label = st.radio(
        "Wybierz preferowany przedział czasowy",
        list(PREFERRED_SLOTS.keys()),
        index=list(PREFERRED_SLOTS.keys()).index(auto_pref_range_label)
    )

    pref_start, pref_end = PREFERRED_SLOTS[pref_range_label]

    day = st.date_input("Dzień", value=date.today())

    submitted = st.form_submit_button("Dodaj")
    if submitted:
        ok, info = schedule_client_immediately(client_name, slot_type_name, day, pref_start, pref_end)
        if ok:
            # dopisanie przedziału do slotu
            for b in st.session_state.schedules:
                for d, slots in st.session_state.schedules[b].items():
                    for s in slots:
                        if s["client"] == client_name and s["start"] == info["start"]:
                            s["pref_range"] = pref_range_label
            st.session_state.clients_added.append({"client": client_name, "slot_type": slot_type_name, "pref_range": pref_range_label})
            st.success(f"Klient {client_name} dodany ({slot_type_name}, {pref_range_label})")
            st.session_state.client_counter += 1
        else:
            st.error("Nie udało się znaleźć miejsca.")


# ===================== TABELA I WYKRESY =====================

all_slots = []
for b in st.session_state.brygady:
    for d, slots in st.session_state.schedules.get(b, {}).items():
        for s in slots:
            all_slots.append({
                "Brygada": b,
                "Dzień": d,
                "Klient": s["client"],
                "Typ": s["slot_type"],
                "Preferencja": s.get("pref_range", ""),
                "Start": s["start"],
                "Koniec": s["end"],
                "Czas [min]": s["duration_min"]
            })

df = pd.DataFrame(all_slots)
st.subheader("Tabela harmonogramu")
st.dataframe(df)

if not df.empty:
    st.subheader("Wykres Gantta")
    fig = px.timeline(df, x_start="Start", x_end="Koniec", y="Brygada", color="Klient", hover_data=["Typ", "Preferencja"])
    fig.update_yaxes(autorange="reversed")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Tygodniowa heatmapa obciążenia")
    week_days = week_days_containing(date.today())
    heatmap_data = []
    for b in st.session_state.brygady:
        row = []
        for d in week_days:
            util = compute_utilization_for_day(b, d)
            row.append(util)
        heatmap_data.append(row)
    hm_df = pd.DataFrame(heatmap_data, index=st.session_state.brygady, columns=[d.strftime("%a %d-%m") for d in week_days])
    st.dataframe((hm_df*100).round(1))

st.subheader("Historia dodawania")
st.dataframe(pd.DataFrame(st.session_state.clients_added))
