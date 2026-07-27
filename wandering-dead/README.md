# The Wandering Dead — A Linden County Story

A story-mode zombie survival game that runs entirely in your browser. Walk the
world top-down, fight the dead, and steer the story yourself: every major beat
ends in a choice that is yours to make, and your choices change scenes, allies,
the finale, and the epilogue you get.

**This is an original, fan-made homage in the spirit of the classic zombie
survival drama — a personal, non-commercial project. All characters, names,
dialogue, and locations are original. Not affiliated with any franchise.**

## How to play

No install, no server, no dependencies. Just open the file:

1. Clone or download this repository.
2. Open `wandering-dead/index.html` in any modern browser (double-clicking it works).
3. Click **NEW GAME**.

Progress saves automatically at each chapter, so you can close the tab and
**CONTINUE** later.

## Controls

| Key | Action |
| --- | --- |
| `W A S D` / arrow keys | Move |
| `SPACE` | Attack (melee swing or revolver shot) |
| `E` | Talk / interact / advance dialogue |
| `1` / `2` | Switch between melee and revolver |
| `H` | Use a bandage (+35 HP) |
| `1`–`3` / mouse | Pick a dialogue choice |

Tips: the dead are slow — walking away is always an option. Gunshots are loud
and *draw every shambler in earshot*, so save the revolver for when it matters.
Ammo boxes (+6 rounds) and bandages are scattered through the world.

## The story

You are **Deputy Nick Grayson** of Linden County, Georgia. Shot on duty, you
wake from a coma weeks later in an abandoned hospital — and the world has
ended while you slept. Your wife **Laura** and son **Cody** were last headed
for the refugee center in the city of Ashton, sixty miles east, along with
your partner and best friend **Zane Marsh**.

Six chapters stand between you and them:

1. **Wake** — escape the dark of Linden Memorial.
2. **The Family Next Door** — Morris and his son Dante teach you the new rules.
3. **The Long Road** — Route 9, a dry gas station, and a small wanderer.
4. **Ashton** — the dead own the city; a fast-talking stranger owns its back doors.
5. **The Camp by the Quarry** — a reunion, an old friend wearing a new face, and a very long night.
6. **Ashes** — one last conversation, in the middle of a dark road.

## Your choices matter

Six major decisions branch the story — who you help, who you forgive, who you
free, what you share, and how the last confrontation ends. Choices have
mechanical consequences (allies at your side during the night defense, extra
supplies, extra enemies) as well as narrative ones: the finale offers different
options depending on how you've treated people, and the epilogue is assembled
from everything you did. There are multiple endings — the best one has to be
earned across the whole story.

## Tech notes

Plain HTML5 canvas + vanilla JavaScript, three files, zero dependencies:

- `index.html` — page shell, HUD, dialogue box, and menu styling
- `maps.js` — chapter tile maps, spawn tables, and chapter metadata
- `game.js` — engine (movement, collision, zombie AI, combat, lighting),
  the dialogue/choice system, chapter scripts, and the endings

Saves use `localStorage` under the key `wandering-dead-save`.
