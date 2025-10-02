import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import os
import json
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
        st.session_state.slot_types = [{"name": "Standard", "minutes": 60}]
        st.session_state.brygady = ["Brygada 1", "Brygada 2"]
        st.session_state.working_hours = {}
        st.session_state.schedules = {}
        st.session_state.clients_added = []
        st.session_state.heur_weights = {"delay": 0.34, "gap": 0.33, "balance": 0.33}
        st.session_state.balance_horizon = "week"

# ===================== FUNKCJE POMOCNICZE =====================

def parse_slot_types(text):
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) >= 2:
            try:
                minutes = int(parts[1])
                out.append({"name": parts[0].strip(), "minutes": minutes})
            except:
                pass
    return out

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

def find_best_insertion_for_client(client_name, slot_type_name, day, pref_start_time, pref_end_time):
    stype = next((s for s in st.session_state.slot_types if s["name"] == slot_type_name), None)
    if not stype:
        return None
    dur_min = stype["minutes"]
    pref_start_dt = datetime.combine(day, pref_start_time)
    pref_end_dt = datetime.combine(day, pref_end_time)
    window_len = max(1, minutes_between(pref_start_dt, pref_end_dt))

    base_minutes_day = {b: daily_used_minutes(b, day) for b in st.session_state.brygady}
    work_map_day = {b: total_work_minutes_for_brygada(b) for b in st.session_state.brygady}
    week_days = week_days_containing(day)
    base_minutes_week = {b: used_minutes_for_week(b, day) for b in st.session_state.brygady}
    work_map_week = {b: work_map_day[b] * len(week_days) for b in st.session_state.brygady}

    candidates = []
    for b in st.session_state.brygady:
        day_start_dt = datetime.combine(day, st.session_state.working_hours[b][0])
        day_end_dt = datetime.combine(day, st.session_state.working_hours[b][1])
        if pref_end_dt <= day_start_dt or pref_start_dt >= day_end_dt:
            continue
        slots = get_day_slots_for_brygada(b, day)
        intervals = []
        if not slots:
            intervals.append((day_start_dt, day_end_dt))
        else:
            intervals.append((day_start_dt, slots[0]["start"]))
            for i in range(len(slots) - 1):
                intervals.append((slots[i]["end"], slots[i+1]["start"]))
            intervals.append((slots[-1]["end"], day_end_dt))

        for (iv_start, iv_end) in intervals:
            if minutes_between(iv_start, iv_end) < dur_min:
                continue
            candidate_start_min = max(iv_start, pref_start_dt, day_start_dt)
            latest_start = min(iv_end - timedelta(minutes=dur_min), pref_end_dt - timedelta(minutes=dur_min), day_end_dt - timedelta(minutes=dur_min))
            if candidate_start_min > latest_start:
                continue
            start_candidate = candidate_start_min
            end_candidate = start_candidate + timedelta(minutes=dur_min)
            delay_min = max(0, minutes_between(pref_start_dt, start_candidate))
            delay_norm = delay_min / window_len
            idle_before = minutes_between(iv_start, start_candidate)
            idle_after = minutes_between(end_candidate, iv_end)
            gap_total = idle_before + idle_after
            work_total_minutes_day = work_map_day[b]
            gap_norm = gap_total / work_total_minutes_day if work_total_minutes_day > 0 else 0
            if st.session_state.balance_horizon == "day":
                mins_after = {bb: base_minutes_day[bb] for bb in st.session_state.brygady}
                mins_after[b] += dur_min
                util_list = [mins_after[bb] / work_map_day[bb] if work_map_day[bb] > 0 else 0 for bb in st.session_state.brygady]
            else:
                mins_after = {bb: base_minutes_week[bb] for bb in st.session_state.brygady}
                mins_after[b] += dur_min
                util_list = [mins_after[bb] / work_map_week[bb] if work_map_week[bb] > 0 else 0 for bb in st.session_state.brygady]
            fairness_std = pstdev(util_list) if len(util_list) > 1 else 0
            W = st.session_state.heur_weights
            score = W["delay"] * delay_norm + W["gap"] * gap_norm + W["balance"] * fairness_std
            candidates.append((score, delay_min, start_candidate, end_candidate, b))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1], x[2]))
    best = candidates[0]
    return {"brygada": best[4], "start": best[2], "end": best[3], "score": best[0]}

def schedule_client_immediately(client_name, slot_type_name, day, pref_start, pref_end):
    res = find_best_insertion_for_client(client_name, slot_type_name, day, pref_start, pref_end)
    if not res:
        return False, None
    slot = {
        "start": res["start"],
        "end": res["end"],
        "slot_type": slot_type_name,
        "duration_min": int((res["end"] - res["start"]).total_seconds() / 60),
        "client": client_name
    }
    add_slot_to_brygada(res["brygada"], day, slot)
    return True, res

# ===================== INTERFEJS =====================

st.title("Harmonogram slotów (z persystencją JSON)")

with st.sidebar:
    st.subheader("Konfiguracja slotów")
    txt = st.text_area("Typy slotów (format: Nazwa, minuty)", value="\n".join(f"{s['name']}, {s['minutes']}" for s in st.session_state.slot_types))
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
        save_state_to_json()
        st.success("Harmonogram wyczyszczony i zapisany.")

# ===================== PREDEFINIOWANE PRZEDZIAŁY =====================

PREFERRED_SLOTS = {
    "8:00-12:00": (time(8, 0), time(12, 0)),
    "12:00-16:00": (time(12, 0), time(16, 0)),
    "16:00-20:00": (time(16, 0), time(20, 0)),
}

# ===================== DODAWANIE KLIENTA =====================

st.subheader("Dodaj klienta")
with st.form("add_client_form"):
    client_name = st.text_input("Nazwa klienta")
    slot_type_name = st.selectbox("Typ slotu", [s["name"] for s in st.session_state.slot_types])
    day = st.date_input("Dzień", value=date.today())
    
    pref_range_label = st.selectbox("Preferowany przedział czasowy", list(PREFERRED_SLOTS.keys()))
    pref_start, pref_end = PREFERRED_SLOTS[pref_range_label]

    submitted = st.form_submit_button("Dodaj")
    if submitted:
        ok, info = schedule_client_immediately(client_name, slot_type_name, day, pref_start, pref_end)
        if ok:
            st.session_state.clients_added.append({
                "Klient": client_name,
                "Typ slotu": slot_type_name,
                "Dzień": str(day),
                "Preferencja": pref_range_label,
                "Brygada": info["brygada"],
                "Start": info["start"].strftime("%H:%M"),
                "Koniec": info["end"].strftime("%H:%M")
            })
            st.success(f"Klient {client_name} dodany do {info['brygada']} {info['start'].strftime('%H:%M')}-{info['end'].strftime('%H:%M')} (preferencja: {pref_range_label})")
        else:
            st.error("Nie udało się znaleźć miejsca.")

# ===================== TABELA I WYKRESY =====================

all_slots = []
for b in st.session_state.brygady:
    for d, slots in st.session_state.schedules.get(b, {}).items():
        for s in slots:
            pref_range = None
            for ca in st.session_state.clients_added:
                if ca["Klient"] == s["client"] and ca["Dzień"] == d:
                    pref_range = ca["Preferencja"]
                    break
            all_slots.append({
                "Brygada": b,
                "Dzień": d,
                "Klient": s["client"],
                "Typ": s["slot_type"],
                "Start": s["start"],
                "Koniec": s["end"],
                "Czas [min]": s["duration_min"],
                "Preferencja klienta": pref_range
            })

df = pd.DataFrame(all_slots)
st.subheader("Tabela harmonogramu")
st.dataframe(df)

if not df.empty:
    st.subheader("Wykres Gantta")
    fig = px.timeline(df, x_start="Start", x_end="Koniec", y="Brygada", color="Klient", hover_data=["Typ", "Preferencja klienta"])
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
