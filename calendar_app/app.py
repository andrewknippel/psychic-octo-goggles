#!/usr/bin/env python3
"""Drew's Calendar — a simple desktop calendar for car stuff, work, and life.

Runs anywhere Python runs, with zero third-party dependencies:

    python app.py        (or double-click on Windows: python app.py / app.py)

Events are saved automatically to `calendar.db` (SQLite) in this folder,
so your data survives restarts and can be backed up by copying one file.
"""

import calendar
import re
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import font as tkfont
    from tkinter import messagebox
except ModuleNotFoundError:  # pragma: no cover
    print(
        "Tkinter isn't available in this Python.\n"
        "On Windows/Mac, install Python from python.org (Tkinter is included).\n"
        "On Ubuntu/Debian: sudo apt install python3-tk"
    )
    sys.exit(1)

DB_PATH = Path(__file__).resolve().parent / "calendar.db"

# ---------------------------------------------------------------------------
# Look & feel
# ---------------------------------------------------------------------------

COLORS = {
    "bg": "#f4f5f7",
    "header_bg": "#1f2937",
    "header_fg": "#f9fafb",
    "cell_bg": "#ffffff",
    "cell_dim_bg": "#eceef1",
    "cell_border": "#d7dade",
    "today_ring": "#2563eb",
    "selected_bg": "#dbeafe",
    "sidebar_bg": "#ffffff",
    "muted": "#6b7280",
    "text": "#111827",
}

CATEGORIES = {
    "Car":      {"color": "#d97706", "emoji": "\U0001F697"},   # 🚗
    "Work":     {"color": "#2563eb", "emoji": "\U0001F4BC"},   # 💼
    "Personal": {"color": "#7c3aed", "emoji": "\U0001F3E0"},   # 🏠
    "Health":   {"color": "#059669", "emoji": "\U0001F49A"},   # 💚
    "Other":    {"color": "#6b7280", "emoji": "\U0001F4CC"},   # 📌
}

CAR_SERVICE_TYPES = [
    "Oil change",
    "Tire rotation",
    "New tires",
    "Registration / tags",
    "Insurance",
    "Inspection",
    "Repair",
    "Car wash / detail",
    "Fuel / mileage log",
    "Other",
]


def cat_color(category):
    return CATEGORIES.get(category, CATEGORIES["Other"])["color"]


def cat_emoji(category):
    return CATEGORIES.get(category, CATEGORIES["Other"])["emoji"]


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

class EventStore:
    """All reads/writes go through here; schema lives in one place."""

    def __init__(self, db_path=DB_PATH):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                date        TEXT NOT NULL,          -- YYYY-MM-DD
                time        TEXT NOT NULL DEFAULT '',
                category    TEXT NOT NULL DEFAULT 'Other',
                notes       TEXT NOT NULL DEFAULT '',
                car_service TEXT NOT NULL DEFAULT '',
                odometer    TEXT NOT NULL DEFAULT '',
                cost        TEXT NOT NULL DEFAULT '',
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        self.conn.commit()

    def add(self, **fields):
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        cur = self.conn.execute(
            f"INSERT INTO events ({cols}) VALUES ({marks})", tuple(fields.values())
        )
        self.conn.commit()
        return cur.lastrowid

    def update(self, event_id, **fields):
        sets = ", ".join(f"{c} = ?" for c in fields)
        self.conn.execute(
            f"UPDATE events SET {sets} WHERE id = ?",
            (*fields.values(), event_id),
        )
        self.conn.commit()

    def delete(self, event_id):
        self.conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
        self.conn.commit()

    def for_month(self, year, month):
        """{day -> [rows]} for every event in the given month."""
        prefix = f"{year:04d}-{month:02d}-"
        rows = self.conn.execute(
            "SELECT * FROM events WHERE date LIKE ? ORDER BY date", (prefix + "%",)
        ).fetchall()
        by_day = {}
        for row in rows:
            day = int(row["date"][8:10])
            by_day.setdefault(day, []).append(row)
        for events in by_day.values():
            events.sort(key=lambda r: time_sort_key(r["time"]))
        return by_day

    def for_day(self, day):
        rows = self.conn.execute(
            "SELECT * FROM events WHERE date = ?", (day.isoformat(),)
        ).fetchall()
        return sorted(rows, key=lambda r: time_sort_key(r["time"]))

    def upcoming(self, start, days=14):
        end = start + timedelta(days=days)
        rows = self.conn.execute(
            "SELECT * FROM events WHERE date >= ? AND date <= ? ORDER BY date",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        return sorted(rows, key=lambda r: (r["date"], time_sort_key(r["time"])))


def time_sort_key(text):
    """Sort '9:00 AM' before '1:30 PM'; untimed events go last."""
    parsed = parse_time(text)
    return (parsed is None, parsed or "")


def parse_time(text):
    """Return 'HH:MM' 24h string, or None if the field is empty/unparseable."""
    text = (text or "").strip()
    if not text:
        return None
    for fmt in ("%I:%M %p", "%I %p", "%I:%M%p", "%I%p", "%H:%M", "%H"):
        try:
            return datetime.strptime(text.upper(), fmt).strftime("%H:%M")
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# Add / edit dialog
# ---------------------------------------------------------------------------

class EventDialog(tk.Toplevel):
    """Modal form for creating or editing an event. Result in self.saved."""

    def __init__(self, master, store, day, event=None):
        super().__init__(master)
        self.store = store
        self.event = event
        self.saved = False

        self.title("Edit event" if event else "Add event")
        self.configure(bg=COLORS["sidebar_bg"], padx=18, pady=14)
        self.resizable(False, False)
        self.transient(master)

        body = tk.Frame(self, bg=COLORS["sidebar_bg"])
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(1, weight=1)

        def label(row, text):
            tk.Label(
                body, text=text, bg=COLORS["sidebar_bg"], fg=COLORS["muted"],
                anchor="w", font=("TkDefaultFont", 9),
            ).grid(row=row, column=0, sticky="w", pady=(8, 0), padx=(0, 10))

        # Title -------------------------------------------------------------
        label(0, "What")
        self.title_var = tk.StringVar(value=event["title"] if event else "")
        title_entry = tk.Entry(body, textvariable=self.title_var, width=38)
        title_entry.grid(row=0, column=1, sticky="ew", pady=(8, 0))

        # Category ----------------------------------------------------------
        label(1, "Category")
        self.category_var = tk.StringVar(
            value=event["category"] if event else "Car"
        )
        cat_row = tk.Frame(body, bg=COLORS["sidebar_bg"])
        cat_row.grid(row=1, column=1, sticky="w", pady=(8, 0))
        self._cat_buttons = {}
        for name, info in CATEGORIES.items():
            btn = tk.Button(
                cat_row, text=f"{info['emoji']} {name}", relief="flat",
                padx=7, pady=3, cursor="hand2", bd=0,
                command=lambda n=name: self._pick_category(n),
            )
            btn.pack(side="left", padx=(0, 4))
            self._cat_buttons[name] = btn

        # Date & time -------------------------------------------------------
        label(2, "Date")
        self.date_var = tk.StringVar(
            value=(event["date"] if event else day.isoformat())
        )
        date_row = tk.Frame(body, bg=COLORS["sidebar_bg"])
        date_row.grid(row=2, column=1, sticky="w", pady=(8, 0))
        tk.Entry(date_row, textvariable=self.date_var, width=12).pack(side="left")
        tk.Label(
            date_row, text="YYYY-MM-DD", bg=COLORS["sidebar_bg"],
            fg=COLORS["muted"], font=("TkDefaultFont", 8),
        ).pack(side="left", padx=(6, 0))

        label(3, "Time")
        self.time_var = tk.StringVar(value=event["time"] if event else "")
        time_row = tk.Frame(body, bg=COLORS["sidebar_bg"])
        time_row.grid(row=3, column=1, sticky="w", pady=(8, 0))
        tk.Entry(time_row, textvariable=self.time_var, width=12).pack(side="left")
        tk.Label(
            time_row, text="optional — e.g. 2:30 PM", bg=COLORS["sidebar_bg"],
            fg=COLORS["muted"], font=("TkDefaultFont", 8),
        ).pack(side="left", padx=(6, 0))

        # Car-only fields ---------------------------------------------------
        self.car_frame = tk.LabelFrame(
            body, text=" \U0001F697 Car details ", bg=COLORS["sidebar_bg"],
            fg=cat_color("Car"), padx=8, pady=6,
        )
        self.car_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self.car_frame.grid_columnconfigure(1, weight=1)

        tk.Label(
            self.car_frame, text="Service", bg=COLORS["sidebar_bg"],
            fg=COLORS["muted"], font=("TkDefaultFont", 9),
        ).grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.service_var = tk.StringVar(
            value=(event["car_service"] if event else "") or CAR_SERVICE_TYPES[0]
        )
        tk.OptionMenu(self.car_frame, self.service_var, *CAR_SERVICE_TYPES).grid(
            row=0, column=1, sticky="w"
        )

        tk.Label(
            self.car_frame, text="Odometer", bg=COLORS["sidebar_bg"],
            fg=COLORS["muted"], font=("TkDefaultFont", 9),
        ).grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(6, 0))
        self.odometer_var = tk.StringVar(value=event["odometer"] if event else "")
        odo_row = tk.Frame(self.car_frame, bg=COLORS["sidebar_bg"])
        odo_row.grid(row=1, column=1, sticky="w", pady=(6, 0))
        tk.Entry(odo_row, textvariable=self.odometer_var, width=12).pack(side="left")
        tk.Label(
            odo_row, text="miles", bg=COLORS["sidebar_bg"], fg=COLORS["muted"],
            font=("TkDefaultFont", 8),
        ).pack(side="left", padx=(6, 0))

        tk.Label(
            self.car_frame, text="Cost", bg=COLORS["sidebar_bg"],
            fg=COLORS["muted"], font=("TkDefaultFont", 9),
        ).grid(row=2, column=0, sticky="w", padx=(0, 10), pady=(6, 0))
        self.cost_var = tk.StringVar(value=event["cost"] if event else "")
        cost_row = tk.Frame(self.car_frame, bg=COLORS["sidebar_bg"])
        cost_row.grid(row=2, column=1, sticky="w", pady=(6, 0))
        tk.Label(
            cost_row, text="$", bg=COLORS["sidebar_bg"], fg=COLORS["muted"],
        ).pack(side="left")
        tk.Entry(cost_row, textvariable=self.cost_var, width=10).pack(side="left")

        # Notes -------------------------------------------------------------
        label(5, "Notes")
        self.notes_text = tk.Text(body, width=38, height=3, wrap="word")
        self.notes_text.grid(row=5, column=1, sticky="ew", pady=(8, 0))
        if event and event["notes"]:
            self.notes_text.insert("1.0", event["notes"])

        # Buttons -----------------------------------------------------------
        btn_row = tk.Frame(self, bg=COLORS["sidebar_bg"])
        btn_row.pack(fill="x", pady=(14, 0))
        tk.Button(
            btn_row, text="Save", bg=COLORS["today_ring"], fg="white",
            activebackground="#1d4ed8", activeforeground="white",
            relief="flat", padx=18, pady=5, cursor="hand2", command=self._save,
        ).pack(side="right")
        tk.Button(
            btn_row, text="Cancel", relief="flat", padx=12, pady=5,
            cursor="hand2", command=self.destroy,
        ).pack(side="right", padx=(0, 8))

        self._pick_category(self.category_var.get())

        # Center over the main window
        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_reqwidth()) // 2
        y = master.winfo_rooty() + (master.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

        title_entry.focus_set()
        self.bind("<Return>", lambda _e: self._save())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()

    def _pick_category(self, name):
        self.category_var.set(name)
        for cat, btn in self._cat_buttons.items():
            if cat == name:
                btn.configure(bg=cat_color(cat), fg="white",
                              activebackground=cat_color(cat),
                              activeforeground="white")
            else:
                btn.configure(bg="#e5e7eb", fg=COLORS["text"],
                              activebackground="#d1d5db",
                              activeforeground=COLORS["text"])
        if name == "Car":
            self.car_frame.grid()
        else:
            self.car_frame.grid_remove()

    def _save(self):
        title = self.title_var.get().strip()
        category = self.category_var.get()
        if not title:
            if category == "Car":
                title = self.service_var.get()  # car events can skip typing a title
            else:
                messagebox.showwarning(
                    "Missing title", "Give the event a short name first.",
                    parent=self,
                )
                return

        raw_date = self.date_var.get().strip()
        normalized = normalize_date(raw_date)
        if normalized is None:
            messagebox.showwarning(
                "Bad date",
                f"Couldn't understand the date {raw_date!r}.\n"
                "Use YYYY-MM-DD, e.g. 2026-07-20.",
                parent=self,
            )
            return

        raw_time = self.time_var.get().strip()
        if raw_time and parse_time(raw_time) is None:
            messagebox.showwarning(
                "Bad time",
                f"Couldn't understand the time {raw_time!r}.\n"
                "Try something like 2:30 PM or 14:30.",
                parent=self,
            )
            return

        is_car = category == "Car"
        fields = dict(
            title=title,
            date=normalized,
            time=raw_time,
            category=category,
            notes=self.notes_text.get("1.0", "end").strip(),
            car_service=self.service_var.get() if is_car else "",
            odometer=self.odometer_var.get().strip() if is_car else "",
            cost=self.cost_var.get().strip().lstrip("$") if is_car else "",
        )
        if self.event:
            self.store.update(self.event["id"], **fields)
        else:
            self.store.add(**fields)
        self.saved = True
        self.destroy()


def normalize_date(text):
    """Accept a few human formats; return canonical YYYY-MM-DD or None."""
    text = text.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%b %d %Y", "%B %d %Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    # 7/4 style — assume current year
    match = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})", text)
    if match:
        try:
            return date(date.today().year, int(match[1]), int(match[2])).isoformat()
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class CalendarApp(tk.Tk):
    MAX_PILLS = 3  # event pills shown per day cell before "+N more"

    def __init__(self, store=None):
        super().__init__()
        self.store = store or EventStore()
        self.today = date.today()
        self.shown = self.today.replace(day=1)   # first of the displayed month
        self.selected = self.today

        self.title("Drew's Calendar")
        self.geometry("1150x720")
        self.minsize(940, 600)
        self.configure(bg=COLORS["bg"])

        self.pill_font = tkfont.Font(family="TkDefaultFont", size=8)
        self.day_font = tkfont.Font(family="TkDefaultFont", size=10, weight="bold")

        self._build_header()
        self._build_body()
        self.refresh()

        self.bind("<Left>", lambda _e: self.change_month(-1))
        self.bind("<Right>", lambda _e: self.change_month(1))
        self.bind("n", lambda _e: self.open_dialog())

    # -- layout -------------------------------------------------------------

    def _build_header(self):
        header = tk.Frame(self, bg=COLORS["header_bg"], padx=16, pady=10)
        header.pack(fill="x")

        self.month_label = tk.Label(
            header, bg=COLORS["header_bg"], fg=COLORS["header_fg"],
            font=("TkDefaultFont", 16, "bold"),
        )
        self.month_label.pack(side="left")

        def header_btn(text, command, primary=False):
            return tk.Button(
                header, text=text, command=command, relief="flat", bd=0,
                cursor="hand2", padx=12, pady=4,
                bg=COLORS["today_ring"] if primary else "#374151",
                fg="white", activebackground="#1d4ed8" if primary else "#4b5563",
                activeforeground="white",
            )

        header_btn("➕ Add event", self.open_dialog, primary=True).pack(
            side="right", padx=(8, 0)
        )
        header_btn("Today", self.go_today).pack(side="right", padx=(8, 0))
        header_btn("▶", lambda: self.change_month(1)).pack(side="right")
        header_btn("◀", lambda: self.change_month(-1)).pack(
            side="right", padx=(16, 2)
        )

    def _build_body(self):
        body = tk.Frame(self, bg=COLORS["bg"])
        body.pack(fill="both", expand=True)

        # Sidebar packs first so it keeps its width when the window is narrow
        sidebar = tk.Frame(body, bg=COLORS["sidebar_bg"], width=310)
        sidebar.pack(side="right", fill="y")
        sidebar.pack_propagate(False)

        # Calendar grid (left) ---------------------------------------------
        grid_wrap = tk.Frame(body, bg=COLORS["bg"], padx=12, pady=10)
        grid_wrap.pack(side="left", fill="both", expand=True)

        weekday_row = tk.Frame(grid_wrap, bg=COLORS["bg"])
        weekday_row.pack(fill="x")
        for i, name in enumerate(["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]):
            weekday_row.grid_columnconfigure(i, weight=1, uniform="wd")
            tk.Label(
                weekday_row, text=name, bg=COLORS["bg"], fg=COLORS["muted"],
                font=("TkDefaultFont", 9, "bold"), pady=4,
            ).grid(row=0, column=i, sticky="ew")

        self.grid_frame = tk.Frame(grid_wrap, bg=COLORS["cell_border"])
        self.grid_frame.pack(fill="both", expand=True)

        # Sidebar (right, packed above) --------------------------------------
        self.day_header = tk.Label(
            sidebar, bg=COLORS["sidebar_bg"], fg=COLORS["text"], anchor="w",
            font=("TkDefaultFont", 12, "bold"), padx=14, pady=10,
        )
        self.day_header.pack(fill="x")

        canvas = tk.Canvas(
            sidebar, bg=COLORS["sidebar_bg"], highlightthickness=0
        )
        scrollbar = tk.Scrollbar(sidebar, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self.sidebar_inner = tk.Frame(canvas, bg=COLORS["sidebar_bg"])
        inner_id = canvas.create_window((0, 0), window=self.sidebar_inner, anchor="nw")
        self.sidebar_inner.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfigure(inner_id, width=e.width),
        )

    # -- navigation ---------------------------------------------------------

    def change_month(self, delta):
        year, month = self.shown.year, self.shown.month + delta
        while month < 1:
            month += 12
            year -= 1
        while month > 12:
            month -= 12
            year += 1
        self.shown = date(year, month, 1)
        self.refresh()

    def go_today(self):
        self.today = date.today()
        self.shown = self.today.replace(day=1)
        self.selected = self.today
        self.refresh()

    def select_day(self, day):
        self.selected = day
        if (day.year, day.month) != (self.shown.year, self.shown.month):
            self.shown = day.replace(day=1)
        self.refresh()

    # -- dialogs ------------------------------------------------------------

    def open_dialog(self, event_row=None):
        dialog = EventDialog(self, self.store, self.selected, event=event_row)
        self.wait_window(dialog)
        if dialog.saved:
            self.refresh()

    def delete_event(self, event_row):
        if messagebox.askyesno(
            "Delete event", f"Delete “{event_row['title']}”?", parent=self
        ):
            self.store.delete(event_row["id"])
            self.refresh()

    # -- rendering ----------------------------------------------------------

    def refresh(self):
        self.month_label.configure(
            text=self.shown.strftime("%B %Y")
        )
        self._draw_grid()
        self._draw_sidebar()

    def _draw_grid(self):
        for child in self.grid_frame.winfo_children():
            child.destroy()

        cal = calendar.Calendar(firstweekday=6)  # weeks start on Sunday
        weeks = cal.monthdatescalendar(self.shown.year, self.shown.month)
        events = self.store.for_month(self.shown.year, self.shown.month)

        for r in range(6):  # reset stale weights when week count shrinks
            used = r < len(weeks)
            self.grid_frame.grid_rowconfigure(
                r, weight=1 if used else 0, uniform="wk" if used else ""
            )
        for c in range(7):
            self.grid_frame.grid_columnconfigure(c, weight=1, uniform="dy")

        for r, week in enumerate(weeks):
            for c, day in enumerate(week):
                in_month = day.month == self.shown.month
                is_today = day == self.today
                is_selected = day == self.selected

                if is_selected:
                    bg = COLORS["selected_bg"]
                elif in_month:
                    bg = COLORS["cell_bg"]
                else:
                    bg = COLORS["cell_dim_bg"]

                cell = tk.Frame(
                    self.grid_frame, bg=bg, padx=5, pady=3,
                    highlightthickness=2 if is_today else 0,
                    highlightbackground=COLORS["today_ring"],
                )
                cell.grid(row=r, column=c, sticky="nsew", padx=1, pady=1)

                num = tk.Label(
                    cell, text=str(day.day), bg=bg, anchor="w",
                    fg=COLORS["text"] if in_month else COLORS["muted"],
                    font=self.day_font,
                )
                num.pack(anchor="w")

                day_events = events.get(day.day, []) if in_month else []
                for row in day_events[: self.MAX_PILLS]:
                    title = row["title"]
                    if len(title) > 16:
                        title = title[:15] + "…"
                    text = f"{cat_emoji(row['category'])} {title}"
                    pill = tk.Label(
                        cell, text=text, bg=cat_color(row["category"]),
                        fg="white", anchor="w", font=self.pill_font,
                        padx=4, pady=1,
                    )
                    pill.pack(fill="x", pady=(2, 0))
                    self._bind_day(pill, day)
                overflow = len(day_events) - self.MAX_PILLS
                if overflow > 0:
                    more = tk.Label(
                        cell, text=f"+{overflow} more", bg=bg,
                        fg=COLORS["muted"], anchor="w", font=self.pill_font,
                    )
                    more.pack(fill="x")
                    self._bind_day(more, day)

                self._bind_day(cell, day)
                self._bind_day(num, day)

    def _bind_day(self, widget, day):
        widget.bind("<Button-1>", lambda _e, d=day: self.select_day(d))
        widget.bind("<Double-Button-1>", lambda _e, d=day: self._quick_add(d))
        widget.configure(cursor="hand2")

    def _quick_add(self, day):
        self.selected = day
        self.open_dialog()

    def _draw_sidebar(self):
        if self.selected == self.today:
            title = "Today"
        else:
            title = self.selected.strftime("%a, %b %-d") if sys.platform != "win32" \
                else self.selected.strftime("%a, %b %d")
        self.day_header.configure(
            text=f"{title} · {self.selected.strftime('%Y-%m-%d')}"
        )

        for child in self.sidebar_inner.winfo_children():
            child.destroy()

        day_events = self.store.for_day(self.selected)
        if not day_events:
            tk.Label(
                self.sidebar_inner, text="Nothing scheduled.\nDouble-click a day"
                " or press “n” to add an event.",
                bg=COLORS["sidebar_bg"], fg=COLORS["muted"], justify="left",
                padx=14, pady=4,
            ).pack(anchor="w")
        for row in day_events:
            self._event_card(row, show_date=False)

        tk.Label(
            self.sidebar_inner, text="UPCOMING · NEXT 14 DAYS",
            bg=COLORS["sidebar_bg"], fg=COLORS["muted"], anchor="w",
            font=("TkDefaultFont", 8, "bold"), padx=14, pady=8,
        ).pack(fill="x", pady=(12, 0))

        upcoming = [
            r for r in self.store.upcoming(self.today)
            if r["date"] != self.selected.isoformat()
        ]
        if not upcoming:
            tk.Label(
                self.sidebar_inner, text="Nothing coming up.",
                bg=COLORS["sidebar_bg"], fg=COLORS["muted"], padx=14,
            ).pack(anchor="w")
        for row in upcoming:
            self._event_card(row, show_date=True)

    def _event_card(self, row, show_date):
        card = tk.Frame(
            self.sidebar_inner, bg=COLORS["sidebar_bg"], padx=14, pady=4
        )
        card.pack(fill="x")

        stripe = tk.Frame(card, bg=cat_color(row["category"]), width=4)
        stripe.pack(side="left", fill="y")

        content = tk.Frame(card, bg=COLORS["sidebar_bg"], padx=8)
        content.pack(side="left", fill="x", expand=True)

        top = f"{cat_emoji(row['category'])} {row['title']}"
        tk.Label(
            content, text=top, bg=COLORS["sidebar_bg"], fg=COLORS["text"],
            anchor="w", font=("TkDefaultFont", 10, "bold"), wraplength=190,
            justify="left",
        ).pack(anchor="w")

        details = []
        if show_date:
            event_date = date.fromisoformat(row["date"])
            details.append(event_date.strftime("%a %b ") + str(event_date.day))
        if row["time"]:
            details.append(row["time"])
        if row["category"] == "Car":
            if row["car_service"]:
                details.append(row["car_service"])
            if row["odometer"]:
                details.append(f"{row['odometer']} mi")
            if row["cost"]:
                details.append(f"${row['cost']}")
        if details:
            tk.Label(
                content, text="  ·  ".join(details), bg=COLORS["sidebar_bg"],
                fg=COLORS["muted"], anchor="w", font=("TkDefaultFont", 9),
                wraplength=190, justify="left",
            ).pack(anchor="w")
        if row["notes"]:
            tk.Label(
                content, text=row["notes"], bg=COLORS["sidebar_bg"],
                fg=COLORS["muted"], anchor="w", font=("TkDefaultFont", 9),
                wraplength=190, justify="left",
            ).pack(anchor="w")

        actions = tk.Frame(card, bg=COLORS["sidebar_bg"])
        actions.pack(side="right")
        tk.Button(
            actions, text="✎", relief="flat", bd=0, cursor="hand2",
            bg=COLORS["sidebar_bg"], fg=COLORS["muted"],
            command=lambda r=row: self.open_dialog(r),
        ).pack(side="left")
        tk.Button(
            actions, text="✕", relief="flat", bd=0, cursor="hand2",
            bg=COLORS["sidebar_bg"], fg="#dc2626",
            command=lambda r=row: self.delete_event(r),
        ).pack(side="left")


def main():
    app = CalendarApp()
    app.mainloop()


if __name__ == "__main__":
    main()
