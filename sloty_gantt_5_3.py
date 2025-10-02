import streamlit as st
import os
import json
from datetime import datetime, timedelta, time

# ------------------ Persisting Helpers ------------------

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


def parse_time_str(t):
    try:
        return datetime.fromisoformat(t).time()
    except ValueError:
        try:
            return datetime.strptime(t, "%H:%M:%S").time()
        except ValueError:
            return datetime.strptime(t, "%H:%M").time()


def load_state_from_json(filename="schedules.json"):
    if not os.path.exists(filename):
        return False
    with open(filename, "r", encoding="utf-8") as f:
        data = json.load(f)

    st.session_state.slot_types = data.get("slot_types", [])
    st.session_state.brygady = data.get("brygady", [])
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


# ------------------ Core Functions ------------------

def total_work_minutes_for_brygada(brygada, day=None):
    """Zlicza łączny czas pracy brygady, opcjonalnie tylko dla wybranego dnia"""
    schedules = st.session_state.schedules.get(brygada, {})
    if day:
        slots = schedules.get(day, [])
        return sum(slot["duration_min"] for slot in slots)
    else:
        return sum(
            slot["duration_min"]
            for slots in schedules.values()
            for slot in slots
        )


def add_slot_to_brygada(brygada, day, start, end, slot_type, client):
    slot = {
        "start": start,
        "end": end,
        "slot_type": slot_type,
        "duration_min": int((end - start).total_seconds() / 60),
        "client": client,
    }
    st.session_state.schedules.setdefault(brygada, {}).setdefault(day, []).append(slot)
    save_state_to_json()


def find_best_insertion_for_client(client, duration_min, brygada, day, step_minutes=15):
    """Znajduje najlepsze miejsce na wstawienie klienta z próbkowaniem wielu możliwych startów"""
    wh_start, wh_end = st.session_state.working_hours[brygada]
    day_date = datetime.strptime(day, "%Y-%m-%d").date()
    slots_today = st.session_state.schedules[brygada].get(day, [])

    # generujemy potencjalne starty
    earliest_start = datetime.combine(day_date, wh_start)
    latest_start = datetime.combine(day_date, wh_end) - timedelta(minutes=duration_min)
    midpoint_start = earliest_start + (latest_start - earliest_start) / 2

    candidate_starts = [earliest_start, latest_start, midpoint_start]

    # dodatkowe próbkowanie co step_minutes
    probe = earliest_start
    while probe <= latest_start:
        candidate_starts.append(probe)
        probe += timedelta(minutes=step_minutes)

    best_score = float("inf")
    best_slot = None

    for start in candidate_starts:
        end = start + timedelta(minutes=duration_min)

        # sprawdź kolizje z istniejącymi slotami
        conflict = any(not (end <= s["start"] or start >= s["end"]) for s in slots_today)
        if conflict:
            continue

        # scoring heurystyczny (np. suma luk + balans obciążenia)
        gaps = sum((s["start"] - end).total_seconds() / 60 for s in slots_today if s["start"] > end)
        balance = total_work_minutes_for_brygada(brygada, day)
        score = gaps * st.session_state.heur_weights["gap"] + balance * st.session_state.heur_weights["balance"]

        if score < best_score:
            best_score = score
            best_slot = (start, end)

    return best_slot


# ------------------ Init Session State ------------------

if "slot_types" not in st.session_state:
    if not load_state_from_json():
        st.session_state.slot_types = [{"name": "Standard", "minutes": 60}]
        st.session_state.brygady = ["Brygada 1", "Brygada 2"]
        st.session_state.working_hours = {}
        st.session_state.schedules = {}
        st.session_state.clients_added = []
        st.session_state.heur_weights = {"delay": 0.34, "gap": 0.33, "balance": 0.33}
        st.session_state.balance_horizon = "week"
