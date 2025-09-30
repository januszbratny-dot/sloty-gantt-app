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
    st.session_state.brygady = ['Brygada 1', 'Brygada 2', 'Brygada 3']  # lista nazw brygad

if "working_hours" not in st.session_state:
    st.session_state.working_hours = {}  # brygada -> (start_time, end_time)
st.session_state.working_hours["Brygada 1"] = (time(8, 0), time(16, 0))
st.session_state.working_hours["Brygada 2"] = (time(10, 0), time(18, 0))
st.session_state.working_hours["Brygada 3"] = (time(12, 0), time(20, 0))

if "schedules" not in st.session_state:
    # schedules: brygada -> dict(date_str -> list of slots)
    # slot: {"start": datetime, "end": datetime, "slot_type": str, "duration_min": int, "client": str}
    st.session_state.schedules = {}

if "clients_added" not in st.session_state:
    st.session_state.clients_added = []  # historia dodawania

# Wagi heurystyki (delay/gap/balance)
if "heur_weights" not in st.session_state:
    st.session_state.heur_weights = {"delay": 0.5, "gap": 0.3, "balance": 0.2}

# Horyzont równomierności: "week" (domyślnie) lub "day"
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
    """Suma minut zajętości danej brygady w konkretnym dniu."""
    slots = get_day_slots_for_brygada(brygada, day)
    return sum(s["duration_min"] for s in slots)


def week_days_containing(day: date, week_start_monday: bool = True) -> List[date]:
    """Zwraca listę 7 dni (Pon–Ndz) zawierających wskazany dzień."""
    weekday = day.weekday()  # Pon=0 ... Ndz=6
    if week_start_monday:
        start = day - timedelta(days=weekday)
    else:
        start = day - timedelta(days=(weekday + 1) % 7)
    return [start + timedelta(days=i) for i in range(7)]


def used_minutes_for_week(brygada: str, any_day_in_week: date) -> int:
    """Suma minut zajętości brygady w tygodniu (Pon–Ndz) zawierającym podaną datę."""
    total = 0
    for d in week_days_containing(any_day_in_week):
        total += daily_used_minutes(brygada, d)
    return total

# -----------------------------
# Rozszerzona heurystyka (równomierność dzień/tydzień)
# -----------------------------
def find_best_insertion_for_client(client_name: str, slot_type_name: str, day: date,
                                   pref_start_time: time, pref_end_time: time):
    """
    Zwraca najlepszą parę (brygada, start_dt, end_dt, score) lub None.
    Heurystyka (łączne kryterium z wagami):
      - delay: minimalizacja opóźnienia względem początku okna preferencji,
      - gap: minimalizacja łącznej "pustki" (idle) w interwale po wstawieniu,
      - balance: minimalizacja nierównomierności obciążenia (odchylenie std wykorzystań).
        * jeśli horyzont = 'day' -> liczone na dany dzień,
        * jeśli horyzont = 'week' -> liczone na tydzień Pon–Ndz zawierający dzień rezerwacji.
    """
    candidates = []

    stype = next((s for s in st.session_state.slot_types if s["name"] == slot_type_name), None)
    if stype is None:
        return None
    dur_min = stype["minutes"]

    pref_start_dt = datetime.combine(day, pref_start_time)
    pref_end_dt = datetime.combine(day, pref_end_time)
    window_len = max(1, minutes_between(pref_start_dt, pref_end_dt))  # do normalizacji opóźnienia

    # wagi heurystyki
    W = st.session_state.heur_weights
    horizon = st.session_state.balance_horizon  # "week" lub "day"

    # profil bazowy: sumy minut i czasy pracy per brygada (dzień)
    base_minutes_day = {}
    work_map_day = {}
    for b in st.session_state.brygady:
        slots_b = get_day_slots_for_brygada(b, day)
        base_minutes_day[b] = sum(s["duration_min"] for s in slots_b)
        work_map_day[b] = total_work_minutes_for_brygada(b)

    # profil bazowy: sumy minut i czasy pracy per brygada (tydzień)
    week_days = week_days_containing(day)
    base_minutes_week = {}
    work_map_week = {}
    for b in st.session_state.brygady:
        base_minutes_week[b] = used_minutes_for_week(b, day)
        work_map_week[b] = work_map_day[b] * len(week_days)  # stałe godziny dla każdego dnia tygodnia

    for brygada in st.session_state.brygady:
        work_start_t, work_end_t = st.session_state.working_hours[brygada]
        day_start_dt = datetime.combine(day, work_start_t)
        day_end_dt = datetime.combine(day, work_end_t)

        # preferencje całkowicie poza godzinami pracy tej brygady -> pomijamy
        if pref_end_dt <= day_start_dt or pref_start_dt >= day_end_dt:
            continue

        # lista istniejących slotów i wolne interwały
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

        for (iv_start, iv_end) in intervals:
            # przecięcie z preferencjami i interwałem
            candidate_start_min = max(iv_start, pref_start_dt, day_start_dt)
            latest_start = min(
                iv_end - timedelta(minutes=dur_min),
                pref_end_dt - timedelta(minutes=dur_min),
                day_end_dt - timedelta(minutes=dur_min)
            )
            if candidate_start_min > latest_start:
                continue

            # wybierz najwcześniejszy start (można rozszerzyć o próbkowanie)
            start_candidate = candidate_start_min
            end_candidate = start_candidate + timedelta(minutes=dur_min)

            # 1) delay (znormalizowany)
            delay_min = max(0, minutes_between(pref_start_dt, start_candidate))
            delay_norm = delay_min / window_len

            # 2) gap: suma "pustek" przed i po w tym interwale, znormalizowana do czasu pracy brygady (dnia)
            idle_before = minutes_between(iv_start, start_candidate)
            idle_after = minutes_between(end_candidate, iv_end)
            gap_total = max(0, idle_before) + max(0, idle_after)
            work_total_minutes_day = work_map_day[brygada]
            gap_norm = (gap_total / work_total_minutes_day) if work_total_minutes_day > 0 else 1.0

            # 3) balance: odchylenie std wykorzystań po wstawieniu (dzień vs tydzień)
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

            # łączny score (im mniejszy, tym lepszy)
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
                       f"Zachowano poprzednie: {prev_start.strftime('%H:%M')}–{prev_end.strftime('%H:%M')}")
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
# UI: formularz dodawania klienta
# -----------------------------
st.subheader("Dodaj klienta (pojedynczo) — system przypisze optymalnie brygadę")
with st.form("add_client_form"):
    client_name = st.text_input("Nazwa klienta", value="")
    slot_type_names = [s["name"] for s in st.session_state.slot_types]
    slot_type_choice = st.selectbox("Typ slotu", options=slot_type_names)
    day_choice = st.date_input("Data preferowana", value=datetime.today().date())
    pref_start = st.time_input("Preferowany start (okno)", value=time(9, 0))
    pref_end = st.time_input("Preferowany koniec (okno)", value=time(17, 0))
    submit = st.form_submit_button("Dodaj klienta i przypisz")

if submit:
    if not client_name.strip():
        st.warning("Podaj nazwę klienta.")
    else:
        ensure_brygady_in_state(st.session_state.brygady)
        success, info = schedule_client_immediately(client_name.strip(), slot_type_choice,
                                                    day_choice, pref_start, pref_end)
        st.session_state.clients_added.append({
            "client": client_name.strip(),
            "slot_type": slot_type_choice,
            "date": day_choice.strftime("%Y-%m-%d"),
            "pref_start": pref_start.strftime("%H:%M"),
            "pref_end": pref_end.strftime("%H:%M"),
            "assigned": success,
            "assigned_info": info
        })
        if success:
            st.success(
                f"Pomyślnie przypisano klienta do brygady: {info['brygada']} "
                f"({info['start'].strftime('%Y-%m-%d %H:%M')} - {info['end'].strftime('%H:%M')})"
            )
        else:
            st.error("Brak dostępnego slotu pasującego do preferencji — klient nieprzydzielony.")

# -----------------------------
# Widoki: tabela, wykresy, historia
# -----------------------------
st.subheader("Aktualny harmonogram (tabela)")
rows = []
for b in st.session_state.brygady:
    for day_key, lst in st.session_state.schedules.get(b, {}).items():
        for s in lst:
            rows.append({
                "date": day_key,
                "brygada": b,
                "slot_type": s["slot_type"],
                "start": s["start"],
                "end": s["end"],
                "duration_min": s["duration_min"],
                "client": s["client"]
            })

if rows:
    df_all = pd.DataFrame(rows)
    df_display = df_all.sort_values(["date", "brygada", "start"]).reset_index(drop=True)
    df_display["start_str"] = df_display["start"].dt.strftime("%Y-%m-%d %H:%M")
    df_display["end_str"] = df_display["end"].dt.strftime("%Y-%m-%d %H:%M")
    st.dataframe(df_display[["date", "brygada", "slot_type", "start_str", "end_str", "duration_min", "client"]],
                 use_container_width=True)
else:
    st.info("Brak slotów w harmonogramie.")

# Wykres Gantta
if rows:
    try:
        fig = px.timeline(df_all, x_start="start", x_end="end", y="brygada",
                          color="slot_type", hover_data=["client", "date"],
                          category_orders={"brygada": st.session_state.brygady})
        fig.update_yaxes(title_text="Brygada", automargin=True)
        fig.update_xaxes(title_text="Czas", tickformat="%H:%M\n%d-%m")
        fig.update_layout(height=300 + 120 * min(6, len(st.session_state.brygady)))
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Błąd przy rysowaniu wykresu Gantta: {e}")

# Wykorzystanie per brygada na wybrany dzień
st.subheader("Wykorzystanie czasu (per brygada, wybrany dzień)")
col_day = st.date_input("Wybierz dzień do analizy wykorzystania", value=datetime.today().date(), key="util_day")
util_rows = []
for b in st.session_state.brygady:
    util = compute_utilization_for_day(b, col_day)
    util_rows.append({"brygada": b, "utilization_percent": round(util * 100, 1)})
if util_rows:
    st.table(pd.DataFrame(util_rows))

# -----------------------------
# NOWOŚĆ: Podgląd tygodniowy — heatmapa
# -----------------------------
st.subheader("Podgląd tygodniowy — heatmapa (Pon–Ndz)")

heat_col1, heat_col2 = st.columns([1, 1])
with heat_col1:
    week_anchor = st.date_input("Wybierz tydzień (podaj dowolny dzień w tygodniu):",
                                value=datetime.today().date(),
                                key="week_anchor")
with heat_col2:
    metric = st.radio("Metryka", options=["Procent wykorzystania", "Minuty zajętości"],
                      index=0, horizontal=True)

week_days = week_days_containing(week_anchor)
week_labels = [d.strftime("%d-%m") for d in week_days]

heat_rows = []
for b in st.session_state.brygady:
    for d, label in zip(week_days, week_labels):
        if metric == "Procent wykorzystania":
            val = compute_utilization_for_day(b, d) * 100.0
        else:
            val = daily_used_minutes(b, d)
        heat_rows.append({"brygada": b, "day_label": label, "value": round(val, 1)})

if heat_rows:
    df_week = pd.DataFrame(heat_rows)
    # pivot: wiersze = brygady, kolumny = dni tygodnia
    pivot = (df_week.pivot(index="brygada", columns="day_label", values="value")
                    .reindex(index=st.session_state.brygady))  # zachowaj kolejność brygad

    # Ustal zakres kolorów
    if metric == "Procent wykorzystania":
        zmin, zmax = 0, 100
        color_label = "Wykorzystanie [%]"
    else:
        # górny zakres na podstawie max dziennego czasu pracy wśród brygad
        max_work = max((total_work_minutes_for_brygada(b) for b in st.session_state.brygady), default=60)
        zmin, zmax = 0, max_work
        color_label = "Zajętość [min]"

    # Heatmapa
    fig_h = px.imshow(
        pivot.values,
        x=pivot.columns,
        y=pivot.index,
        color_continuous_scale="RdYlGn",
        zmin=zmin,
        zmax=zmax,
        aspect="auto",
        origin="upper",
        labels=dict(color=color_label)
    )
    fig_h.update_xaxes(side="top")
    fig_h.update_layout(height=300 + 40 * max(1, len(st.session_state.brygady)))
    st.plotly_chart(fig_h, use_container_width=True)

    # Pod spodem: tabela i eksport CSV
    st.caption("Tabela wartości (te same dane co na heatmapie):")
    st.dataframe(pivot.fillna(0.0), use_container_width=True)
    csv = pivot.reset_index().to_csv(index=False).encode("utf-8")
    st.download_button("Pobierz tabelę tygodniową (CSV)", data=csv,
                       file_name=f"heatmap_week_{week_days[0].isoformat()}_{week_days[-1].isoformat()}.csv",
                       mime="text/csv")
else:
    st.info("Brak danych do wyświetlenia (dodaj sloty lub zdefiniuj brygady i godziny).")

# -----------------------------
# Historia
# -----------------------------
st.subheader("Historia dodawania klientów")
if st.session_state.clients_added:
    hdf = pd.DataFrame(st.session_state.clients_added)
    st.dataframe(hdf, use_container_width=True)
else:
    st.write("Brak dodanych klientów.")

# -----------------------------
# Koniec + uwagi
# -----------------------------
st.markdown("---")
st.markdown(
    "Uwagi:\n\n"
    "- Heatmapa pokazuje tygodniowy przegląd obciążenia: w procentach (relatywnie do godzin pracy) lub w minutach.\n"
    "- Zakres tygodnia to zawsze Pon–Ndz zawierające wskazaną datę.\n"
    "- Wagi heurystyki i horyzont równomierności (dzień/tydzień) zmienisz w panelu bocznym."
)

if __name__ == "__main__":
    init_db()
    load_from_db()
    def init_db():
    def load_from_db():
