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
import json

# -----------------------------
# Funkcje zapisu/odczytu danych do pliku JSON
# -----------------------------
def save_state_to_file(filename="harmonogram_data.json"):
    try:
        data = {
            "schedules": st.session_state.schedules,
            "clients_added": st.session_state.clients_added,
            "slot_types": st.session_state.slot_types,
            "brygady": st.session_state.brygady,
            "working_hours": {
                k: [v[0].strftime("%H:%M"), v[1].strftime("%H:%M")]
                for k, v in st.session_state.working_hours.items()
            },
            "heur_weights": st.session_state.heur_weights,
            "balance_horizon": st.session_state.balance_horizon,
        }
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        st.success("Dane zostały zapisane do pliku.")
    except Exception as e:
        st.error(f"Błąd zapisu danych: {e}")

def load_state_from_file(filename="harmonogram_data.json"):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
        st.session_state.schedules = data.get("schedules", {})
        st.session_state.clients_added = data.get("clients_added", [])
        st.session_state.slot_types = data.get("slot_types", [])
        st.session_state.brygady = data.get("brygady", [])
        st.session_state.working_hours = {
            k: (time.fromisoformat(v[0]), time.fromisoformat(v[1]))
            for k, v in data.get("working_hours", {}).items()
        }
        st.session_state.heur_weights = data.get("heur_weights", {"delay": 0.5, "gap": 0.3, "balance": 0.2})
        st.session_state.balance_horizon = data.get("balance_horizon", "week")
        st.success("Dane zostały wczytane z pliku.")
    except Exception as e:
        st.warning(f"Nie udało się wczytać danych: {e}")

# -----------------------------
# Konfiguracja strony i tytuł
# -----------------------------
st.set_page_config(page_title="Sloty Gantt - dynamiczny (heatmapa tygodniowa)", layout="wide")
st.title("Dynamiczny generator harmonogramu — brygady z indywidualnymi godzinami")

# -----------------------------
# Inicjalizacja stanu
# -----------------------------
if "slot_types" not in st.session_state:
    st.session_state.slot_types = [
        {"name": "Standard", "minutes": 60},
        {"name": "Premium", "minutes": 120}
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
def parse_slot_types(text: str) -> List[Dict[str, Any]]:
    out = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if "," not in line:
            continue
        try:
            name, mins = line.split(",", 1)
            out.append({"name": name.strip(), "minutes": int(mins.strip())})
        except Exception:
            continue
    return out

def ensure_brygady_in_state(brygady_list):
    for b in brygady_list:
        if b not in st.session_state.working_hours:
            st.session_state.working_hours[b] = (time(8, 0), time(16, 0))
        if b not in st.session_state.schedules:
            st.session_state.schedules[b] = {}

def get_day_slots_for_brygada(brygada: str, day: date):
    ds = st.session_state.schedules.get(brygada, {})
    return sorted(ds.get(day.strftime("%Y-%m-%d"), []), key=lambda s: s["start"])

def add_slot_to_brygada(brygada: str, day: date, slot: Dict[str, Any]):
    ds = st.session_state.schedules.setdefault(brygada, {})
    day_key = day.strftime("%Y-%m-%d")
    lst = ds.setdefault(day_key, [])
    lst.append(slot)
    ds[day_key] = sorted(lst, key=lambda s: s["start"])

def minutes_between(t1: datetime, t2: datetime) -> int:
    return int((t2 - t1).total_seconds() // 60)

def total_work_minutes_for_brygada(brygada: str) -> int:
    start_t, end_t = st.session_state.working_hours[brygada]
    return minutes_between(datetime.combine(date.today(), start_t),
                           datetime.combine(date.today(), end_t))

def compute_utilization_for_day(brygada: str, day: date) -> float:
    slots = get_day_slots_for_brygada(brygada, day)
    total = sum(s["duration_min"] for s in slots)
    work_total = total_work_minutes_for_brygada(brygada)
    return total / work_total if work_total > 0 else 0.0

def daily_used_minutes(brygada: str, day: date) -> int:
    slots = get_day_slots_for_brygada(brygada, day)
    return sum(s["duration_min"] for s in slots)

def week_days_containing(day: date, week_start_monday: bool = True) -> List[date]:
    weekday = day.weekday()  # Pon=0 ... Ndz=6
    if week_start_monday:
        start = day - timedelta(days=weekday)
    else:
        start = day - timedelta(days=(weekday + 1) % 7)
    return [start + timedelta(days=i) for i in range(7)]

def used_minutes_for_week(brygada: str, any_day_in_week: date) -> int:
    total = 0
    for d in week_days_containing(any_day_in_week):
        total += daily_used_minutes(brygada, d)
    return total

# -----------------------------
# Rozszerzona heurystyka (równomierność dzień/tydzień)
# -----------------------------
def find_best_insertion_for_client(client_name: str, slot_type_name: str, day: date,
                                  pref_start_time: time, pref_end_time: time):
    candidates = []
    stype = next((s for s in st.session_state.slot_types if s["name"] == slot_type_name), None)
    if stype is None:
        return None
    dur_min = stype["minutes"]
    pref_start_dt = datetime.combine(day, pref_start_time)
    pref_end_dt = datetime.combine(day, pref_end_time)
    window_len = max(1, minutes_between(pref_start_dt, pref_end_dt))
    W = st.session_state.heur_weights
    horizon = st.session_state.balance_horizon
    base_minutes_day = {}
    work_map_day = {}
    for b in st.session_state.brygady:
        slots_b = get_day_slots_for_brygada(b, day)
        base_minutes_day[b] = sum(s["duration_min"] for s in slots_b)
        work_map_day[b] = total_work_minutes_for_brygada(b)
    week_days = week_days_containing(day)
    base_minutes_week = {}
    work_map_week = {}
    for b in st.session_state.brygady:
        base_minutes_week[b] = used_minutes_for_week(b, day)
        work_map_week[b] = work_map_day[b] * len(week_days)
    for brygada in st.session_state.brygady:
        work_start_t, work_end_t = st.session_state.working_hours[brygada]
        day_start_dt = datetime.combine(day, work_start_t)
        day_end_dt = datetime.combine(day, work_end_t)
        if pref_end_dt <= day_start_dt or pref_start_dt >= day_end_dt:
            continue
        slots = get_day_slots_for_brygada(brygada, day)
        intervals = []
        if not slots:
            intervals.append((day_start_dt, day_end_dt))
        else:
            if slots[0]["start"] > day_start_dt:
                intervals.append((day_start_dt, slots[0]["start"]))
            for i in range(len(slots) - 1):
                a_end = slots[i]["end"]
                b_start = slots[i + 1]["start"]
                if b_start > a_end:
                    intervals.append((a_end, b_start))
            if slots[-1]["end"] < day_end_dt:
                intervals.append((slots[-1]["end"], day_end_dt))
        for iv_start, iv_end in intervals:
            candidate_start_min = max(iv_start, pref_start_dt, day_start_dt)
            latest_start = min(
                iv_end - timedelta(minutes=dur_min),
                pref_end_dt - timedelta(minutes=dur_min),
                day_end_dt - timedelta(minutes=dur_min)
            )
            if candidate_start_min > latest_start:
                continue
            start_candidate = candidate_start_min
            end_candidate = start_candidate + timedelta(minutes=dur_min)
            delay_min = max(0, minutes_between(pref_start_dt, start_candidate))
            delay_norm = delay_min / window_len
            idle_before = minutes_between(iv_start, start_candidate)
            idle_after = minutes_between(end_candidate, iv_end)
            gap_total = max(0, idle_before) + max(0, idle_after)
            work_total_minutes_day = work_map_day[brygada]
            gap_norm = (gap_total / work_total_minutes_day) if work_total_minutes_day > 0 else 1.0
            if horizon == "day":
                mins_after = dict(base_minutes_day)
                mins_after[brygada] = mins_after.get(brygada, 0) + dur_min
                util_list_after = [
                    (mins_after[b] / work_map_day[b] if work_map_day[b] > 0 else 0.0)
                    for b in st.session_state.brygady
                ]
            else:  # "week"
                mins_after = dict(base_minutes_week)
                mins_after[brygada] = mins_after.get(brygada, 0) + dur_min
                util_list_after = [
                    (mins_after[b] / work_map_week[b] if work_map_week[b] > 0 else 0.0)
                    for b in st.session_state.brygady
                ]
            fairness_std = pstdev(util_list_after) if len(util_list_after) >= 2 else 0.0
            score = W["delay"] * delay_norm + W["gap"] * gap_norm + W["balance"] * fairness_std
            candidates.append({
                "brygada": brygada,
                "start": start_candidate,
                "end": end_candidate,
                "delay_min": delay_min,
                "gap_norm": gap_norm,
                "fairness_std": fairness_std,
                "score": score,
                "interval": (iv_start, iv_end)
            })
    if not candidates:
        return None
    candidates.sort(key=lambda c: (c["score"], c["delay_min"], c["start"]))
    return candidates[0]

def schedule_client_immediately(client_name: str, slot_type_name: str, day: date,
                               pref_start: time, pref_end: time):
    best = find_best_insertion_for_client(client_name, slot_type_name, day, pref_start, pref_end)
    if best is None:
        return False, None
    stype = next((s for s in st.session_state.slot_types if s["name"] == slot_type_name), None)
    slot = {
        "start": best["start"],
        "end": best["end"],
        "slot_type": slot_type_name,
        "duration_min": stype["minutes"],
        "client": client_name
    }
    add_slot_to_brygada(best["brygada"], day, slot)
    return True, {"brygada": best["brygada"], "start": best["start"], "end": best["end"]}

# -----------------------------
# UI: ustawienia (sidebar)
# -----------------------------
st.sidebar.header("Ustawienia")

# Typy slotów
with st.sidebar.expander("Typy slotów (nazwa, minuty)"):
    cur = "\n".join([f'{s["name"]}, {s["minutes"]}' for s in st.session_state.slot_types])
    types_input = st.text_area("Typy slotów (linia per typ)", value=cur, height=140)
    if st.button("Zastosuj typy"):
        parsed = parse_slot_types(types_input)
        if parsed:
            st.session_state.slot_types = parsed
            st.success("Zaktualizowano typy slotów.")
        else:
            st.error("Nie udało się sparsować typów — użyj formatu: Nazwa, minuty")

# Brygady i godziny pracy
with st.sidebar.expander("Brygady i godziny pracy"):
    default_bryg = "Brygada 1\nBrygada 2"
    bry_input = st.text_area("Lista brygad (jedna w linii)",
                             value="\n".join(st.session_state.brygady) or default_bryg,
                             height=120)
    if st.button("Zastosuj brygady"):
        bryg_list = [b.strip() for b in bry_input.splitlines() if b.strip()]
        st.session_state.brygady = bryg_list
        ensure_brygady_in_state(bryg_list)
        st.success("Zaktualizowano listę brygad (pamiętaj ustawić dla nich godziny pracy poniżej).")
    st.markdown("Ustaw godziny pracy dla każdej brygady:")
    ensure_brygady_in_state([b.strip() for b in bry_input.splitlines() if b.strip()])
    for b in st.session_state.brygady:
        colA, colB = st.columns([1, 1])
        prev_start, prev_end = st.session_state.working_hours.get(b, (time(8, 0), time(16, 0)))
        with colA:
            start_t = st.time_input(f"{b} - start", value=prev_start, key=f"wh_start_{b}")
        with colB:
            end_t = st.time_input(f"{b} - koniec", value=prev_end, key=f"wh_end_{b}")
        if start_t >= end_t:
            st.warning(f"Godziny pracy dla {b} są niepoprawne (start ≥ koniec). "
                       f"Zachowano poprzednie: {prev_start.strftime('%H:%M')}-{prev_end.strftime('%H:%M')}")
        else:
            st.session_state.working_hours[b] = (start_t, end_t)

# Wagi heurystyki + horyzont równomierności
with st.sidebar.expander("Heurystyka: wagi i horyzont"):
    w_delay = st.slider("Opóźnienie vs preferencje", 0.0, 1.0,
                        st.session_state.heur_weights["delay"], 0.05)
    w_gap = st.slider("Minimalizacja przerw (idle)", 0.0, 1.0,
                      st.session_state.heur_weights["gap"], 0.05)
    w_balance = st.slider("Równomierność obciążenia", 0.0, 1.0,
                          st.session_state.heur_weights["balance"], 0.05)
    s = w_delay + w_gap + w_balance
    if s == 0:
        st.info("Suma wag = 0; przywrócono domyślne (0.5/0.3/0.2).")
        w_delay, w_gap, w_balance = 0.5, 0.3, 0.2
        s = 1.0
    st.session_state.heur_weights = {
        "delay": w_delay / s, "gap": w_gap / s, "balance": w_balance / s
    }
    horizon = st.radio("Horyzont równomierności",
                       options=["week", "day"],
                       format_func=lambda x: "Tydzień (Pon–Ndz)" if x == "week" else "Dzień",
                       index=0 if st.session_state.balance_horizon == "week" else 1,
                       horizontal=True)
    st.session_state.balance_horizon = horizon

# Reset harmonogramu
if st.sidebar.button("Wyczyść harmonogram (usuń wszystkie sloty)"):
    st.session_state.schedules = {b: {} for b in st.session_state.brygady}
    st.info("Harmonogram wyczyszczony.")

# -----------------------------
# Zapis/Odczyt danych (sidebar)
# -----------------------------
with st.sidebar.expander("Zapis/Odczyt danych"):
    if st.button("Wczytaj dane z pliku JSON"):
        load_state_from_file()
    if st.button("Zapisz dane do pliku JSON"):
        save_state_to_file()

