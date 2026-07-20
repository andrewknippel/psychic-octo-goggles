# Drew's Calendar 🗓️

A simple desktop calendar built for quickly jotting down **car stuff** (oil
changes, registration, insurance, repairs — with odometer and cost),
**work**, and everything else. No accounts, no internet, no installs beyond
Python itself. Your data lives in one local file you can back up by copying.

Categories: Car 🚗 · Work 💼 · Personal 🏠 · Health 💚 · Other 📌

## Run it

You need Python 3.8+ (from [python.org](https://www.python.org/downloads/) —
the standard installer includes everything this app needs).

```
python app.py
```

- **Windows:** double-click `Drews Calendar.bat` (or `app.py` directly).
- **Mac/Linux:** `python3 app.py` from this folder.

## Using it

| Action | How |
| --- | --- |
| Add an event | Double-click any day, press `n`, or hit **➕ Add event** |
| Add car details | Pick the **🚗 Car** category — service type, odometer, and cost fields appear |
| See a day's events | Click the day; they show in the right panel |
| Edit / delete | ✎ / ✕ buttons next to each event in the right panel |
| Change month | ◀ ▶ buttons or the ← → arrow keys |
| Jump to today | **Today** button |

The right panel always shows the selected day plus everything coming up in
the next 14 days, so registration renewals and appointments don't sneak up
on you.

Dates accept `2026-07-20`, `7/20/2026`, or just `7/20` (assumes this year).
Times are optional — `2:30 PM` or `14:30` both work.

For a car event you can even leave the title blank; it'll use the service
type (e.g. "Oil change") as the name.

## Your data

Everything is saved instantly to `calendar.db` (SQLite) in this folder.
Copy that one file to back up or move your calendar to another computer.
