/* ==========================================================================
 * THE WANDERING DEAD — A Linden County Story
 * An original fan-made story prototype. Personal, non-commercial use only.
 *
 * You are Deputy Nick Grayson. Walk with WASD/arrows, fight with SPACE,
 * talk and interact with E, and make the calls Nick never got to make.
 * ========================================================================== */
"use strict";

/* ---------------------------------------------------------------- helpers */
const $id = (s) => document.getElementById(s);
const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
const dist = (ax, ay, bx, by) => Math.hypot(ax - bx, ay - by);
const rand = (a, b) => a + Math.random() * (b - a);
const hash2 = (x, y) => {
  let h = (x * 374761393 + y * 668265263) | 0;
  h = (h ^ (h >> 13)) * 1274126177;
  return ((h ^ (h >> 16)) >>> 0) / 4294967295;
};

/* ------------------------------------------------------------------ audio */
let actx = null;
function ensureAudio() {
  if (!actx) {
    try { actx = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) { /* no audio */ }
  }
  if (actx && actx.state === "suspended") actx.resume();
}
function sfx(kind) {
  if (!actx) return;
  try {
    const t = actx.currentTime;
    const out = actx.createGain();
    out.connect(actx.destination);
    if (kind === "shot") {
      const len = 0.18, buf = actx.createBuffer(1, actx.sampleRate * len, actx.sampleRate);
      const d = buf.getChannelData(0);
      for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / d.length, 2);
      const src = actx.createBufferSource(); src.buffer = buf;
      const f = actx.createBiquadFilter(); f.type = "lowpass"; f.frequency.value = 1400;
      src.connect(f); f.connect(out);
      out.gain.setValueAtTime(0.5, t);
      src.start(t);
    } else if (kind === "swing") {
      const len = 0.09, buf = actx.createBuffer(1, actx.sampleRate * len, actx.sampleRate);
      const d = buf.getChannelData(0);
      for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * (i / d.length) * (1 - i / d.length) * 2;
      const src = actx.createBufferSource(); src.buffer = buf;
      const f = actx.createBiquadFilter(); f.type = "bandpass"; f.frequency.value = 900;
      src.connect(f); f.connect(out);
      out.gain.setValueAtTime(0.35, t);
      src.start(t);
    } else if (kind === "hit") {
      const o = actx.createOscillator(); o.type = "sine";
      o.frequency.setValueAtTime(160, t); o.frequency.exponentialRampToValueAtTime(50, t + 0.12);
      o.connect(out); out.gain.setValueAtTime(0.4, t); out.gain.exponentialRampToValueAtTime(0.001, t + 0.14);
      o.start(t); o.stop(t + 0.15);
    } else if (kind === "hurt") {
      const o = actx.createOscillator(); o.type = "square";
      o.frequency.setValueAtTime(110, t); o.frequency.exponentialRampToValueAtTime(55, t + 0.2);
      o.connect(out); out.gain.setValueAtTime(0.25, t); out.gain.exponentialRampToValueAtTime(0.001, t + 0.22);
      o.start(t); o.stop(t + 0.24);
    } else if (kind === "pickup") {
      const o = actx.createOscillator(); o.type = "triangle";
      o.frequency.setValueAtTime(520, t); o.frequency.setValueAtTime(780, t + 0.07);
      o.connect(out); out.gain.setValueAtTime(0.22, t); out.gain.exponentialRampToValueAtTime(0.001, t + 0.16);
      o.start(t); o.stop(t + 0.18);
    } else if (kind === "growl") {
      const o = actx.createOscillator(); o.type = "sawtooth";
      o.frequency.setValueAtTime(70, t); o.frequency.linearRampToValueAtTime(45, t + 0.35);
      const f = actx.createBiquadFilter(); f.type = "lowpass"; f.frequency.value = 300;
      o.connect(f); f.connect(out);
      out.gain.setValueAtTime(0.16, t); out.gain.exponentialRampToValueAtTime(0.001, t + 0.4);
      o.start(t); o.stop(t + 0.42);
    }
  } catch (e) { /* never let audio kill the game */ }
}

/* -------------------------------------------------------------- constants */
const TILE = 40;
const VIEW_W = 960, VIEW_H = 600;
const SOLID = new Set(["#", "c", "x", "T", "f", "U", "d"]);
const PLAYER_SPEED = 175;
const PLAYER_R = 13, ZOMBIE_R = 13;
const MELEE = {
  fists: { name: "Bare hands", dmg: 1, range: 46, cd: 0.42 },
  pole:  { name: "IV pole",    dmg: 2, range: 56, cd: 0.46 },
};
const GUN = { dmg: 3, range: 340, cd: 0.5, noise: 380 };
const SAVE_KEY = "wandering-dead-save";

const CAST = {
  Nick:   "#d8b36a", Morris: "#7fb2e5", Dante: "#a5d8ff", Ben: "#8ee59a",
  Earl:   "#e58a5a", Laura:  "#e5a5c8", Cody:  "#9ad8e5", Zane: "#c46a6a",
};

/* ------------------------------------------------------------ game state */
let G = null;          // whole game state
let mode = "title";    // title | card | play | dialogue | gameover | ending
let camera = { x: 0, y: 0 };
const keys = {};

function newGame() {
  return {
    chapter: 0,
    flags: {
      morrisHelped: false, mercyGirl: false, girlChoiceMade: false,
      earlFreed: false, forgaveZane: false, sharedAmmo: false,
      zaneOutcome: null, // 'redeemed' | 'gone' | 'dead'
    },
    persist: { hp: 100, maxHp: 100, ammo: 0, bandages: 1, melee: "fists", hasRevolver: false, weapon: "melee" },
    snapshot: null,   // for chapter retry
    run: null,        // per-chapter runtime
  };
}

/* -------------------------------------------------------------- map load */
function startChapter(i) {
  G.chapter = i;
  G.snapshot = JSON.stringify({ persist: G.persist, flags: G.flags });
  const ch = WD_CHAPTERS[i];
  const rows = ch.map;
  const run = {
    def: ch, w: rows[0].length, h: rows.length,
    tiles: rows.map((r) => [...r]),
    zombies: [], npcs: [], items: [], corpses: [], fx: [],
    doors: [], firePos: null, truckPos: null, girl: null,
    exitPos: null, exitOpen: false,
    allies: [], campHp: 100, night: false,
    ch: {},           // chapter-local scratch
    dark: ch.dark || 0,
  };
  for (let y = 0; y < run.h; y++) {
    for (let x = 0; x < run.tiles[y].length; x++) {
      const c = run.tiles[y][x];
      const px = x * TILE + TILE / 2, py = y * TILE + TILE / 2;
      const clear = () => (run.tiles[y][x] = ch.floor);
      if (c === "P") { run.px = px; run.py = py; clear(); }
      else if (c === "Z") { run.zombies.push(makeZombie(px, py)); clear(); }
      else if (c === "A") { run.items.push({ kind: "ammo", x: px, y: py }); clear(); }
      else if (c === "B") { run.items.push({ kind: "bandage", x: px, y: py }); clear(); }
      else if (c === "M") { run.items.push({ kind: "melee", x: px, y: py }); clear(); }
      else if (c === "J") { run.items.push({ kind: "fuel", x: px, y: py }); clear(); }
      else if (c === "d") { run.doors.push({ x, y }); }
      else if (c === "D") { run.exitPos = { x, y }; }
      else if (c === "f") { run.firePos = { x: px, y: py }; }
      else if (c === "U") { run.truckPos = { x: px, y: py }; }
      else if (ch.spawn[c]) {
        const def = ch.spawn[c];
        if (def.type === "girl") run.girl = { x: px, y: py, hp: 2, wt: 0, dir: rand(0, 6.28), zombified: false };
        else run.npcs.push({ id: def.id, name: def.name, color: def.color, x: px, y: py, gone: false });
        clear();
      }
    }
  }
  G.run = run;
  G.player = {
    x: run.px, y: run.py, dx: 0, dy: 1, atkCd: 0, invuln: 0, flash: 0,
  };
  camera.x = clamp(G.player.x - VIEW_W / 2, 0, run.w * TILE - VIEW_W);
  camera.y = clamp(G.player.y - VIEW_H / 2, 0, run.h * TILE - VIEW_H);
  setObjective(ch.name + " — " + ch.title, ch.objective);
  showCard(i);
}

function makeZombie(x, y, opts = {}) {
  return Object.assign({
    x, y, hp: 3, speed: rand(40, 62), state: "idle", dir: rand(0, 6.28),
    wt: rand(0, 2), atkCd: 0, hitFlash: 0, passive: false, tag: null, targetFire: false,
  }, opts);
}

/* ------------------------------------------------------------- collision */
function tileAt(tx, ty) {
  const r = G.run;
  if (ty < 0 || ty >= r.h || tx < 0 || tx >= r.w) return "#";
  return r.tiles[ty][tx];
}
function solidAt(px, py) {
  const c = tileAt(Math.floor(px / TILE), Math.floor(py / TILE));
  if (c === "D") return !G.run.exitOpen;
  return SOLID.has(c);
}
function circleHits(px, py, r) {
  return (
    solidAt(px - r, py - r) || solidAt(px + r, py - r) ||
    solidAt(px - r, py + r) || solidAt(px + r, py + r)
  );
}
function moveCircle(e, mx, my, r) {
  if (mx !== 0 && !circleHits(e.x + mx, e.y, r)) e.x += mx;
  if (my !== 0 && !circleHits(e.x, e.y + my, r)) e.y += my;
}

/* ------------------------------------------------------------------ HUD */
function updateHUD() {
  const p = G.persist;
  $id("hp-bar").querySelector(".fill").style.transform = `scaleX(${clamp(p.hp / p.maxHp, 0, 1)})`;
  const camp = $id("camp-bar");
  if (G.run && G.run.night) {
    camp.style.display = "block";
    camp.querySelector(".fill").style.transform = `scaleX(${clamp(G.run.campHp / 100, 0, 1)})`;
  } else camp.style.display = "none";
  let w;
  if (p.weapon === "gun" && p.hasRevolver) w = `Revolver — ${p.ammo} rds  [2]`;
  else w = `${MELEE[p.melee].name}  [1]` + (p.hasRevolver ? `   ·   revolver [2]: ${p.ammo} rds` : "");
  $id("weapon-line").textContent = w;
  $id("kit-line").textContent = `Bandages: ${p.bandages}  (H to use)`;
}
function setObjective(chapterName, text) {
  $id("objective").querySelector(".ch").textContent = chapterName;
  $id("objective").querySelector(".obj-text").textContent = text;
}
function setObjectiveText(text) {
  $id("objective").querySelector(".obj-text").textContent = text;
}
let toastTimer = null;
function toast(msg) {
  const t = $id("toast");
  t.textContent = msg;
  t.style.opacity = "1";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.style.opacity = "0"), 2600);
}

/* -------------------------------------------------------------- dialogue */
const dlg = { queue: [], i: -1, shown: 0, full: "", speaker: null, narr: false, choosing: false, opts: [], after: null };

function runScript(steps, after) {
  dlg.queue = steps.slice();
  dlg.i = -1;
  dlg.after = after || null;
  mode = "dialogue";
  $id("dialogue").style.display = "block";
  nextStep();
}
function endScript() {
  $id("dialogue").style.display = "none";
  $id("dlg-choices").style.display = "none";
  mode = "play";
  const cb = dlg.after;
  dlg.after = null;
  if (cb) cb();
}
function nextStep() {
  dlg.i++;
  if (dlg.i >= dlg.queue.length) { endScript(); return; }
  const st = dlg.queue[dlg.i];
  if (st.do) { st.do(); if (mode !== "dialogue") return; nextStep(); return; }
  if (st.ifFlag !== undefined) {
    const branch = G.flags[st.ifFlag] ? st.then || [] : st.else || [];
    dlg.queue.splice(dlg.i + 1, 0, ...branch);
    nextStep(); return;
  }
  if (st.choice) { showChoices(st.choice); return; }
  // plain line
  dlg.speaker = st.s || null;
  dlg.narr = !st.s;
  dlg.full = st.t || st.n || "";
  dlg.shown = 0;
  const sp = $id("dlg-speaker");
  if (dlg.speaker) {
    sp.textContent = dlg.speaker.toUpperCase();
    const base = dlg.speaker.split(" ")[0];
    sp.style.color = CAST[base] || "#d8d4c8";
    sp.style.display = "block";
  } else sp.style.display = "none";
  const tx = $id("dlg-text");
  tx.className = dlg.narr ? "narr" : "";
  tx.textContent = "";
  $id("dlg-more").style.visibility = "hidden";
  $id("dlg-choices").style.display = "none";
  dlg.choosing = false;
}
function showChoices(options) {
  const opts = options.filter((o) => !o.if || o.if());
  dlg.choosing = true;
  dlg.opts = opts;
  dlg.speaker = null;
  $id("dlg-speaker").style.display = "none";
  $id("dlg-text").className = "narr";
  $id("dlg-text").textContent = "What do you do?";
  $id("dlg-more").style.visibility = "hidden";
  const box = $id("dlg-choices");
  box.innerHTML = "";
  opts.forEach((o, i) => {
    const b = document.createElement("button");
    b.className = "choice-btn";
    b.innerHTML = `<span class="num">${i + 1}.</span>${o.t}`;
    b.onclick = (ev) => { ev.stopPropagation(); pickChoice(i); };
    box.appendChild(b);
  });
  box.style.display = "block";
}
function pickChoice(i) {
  const o = dlg.opts[i];
  if (!o) return;
  ensureAudio();
  dlg.choosing = false;
  $id("dlg-choices").style.display = "none";
  if (o.set) Object.assign(G.flags, o.set);
  if (o.then) dlg.queue.splice(dlg.i + 1, 0, ...o.then);
  nextStep();
}
function advanceDialogue() {
  if (dlg.choosing) return;
  if (dlg.shown < dlg.full.length) { dlg.shown = dlg.full.length; return; }
  nextStep();
}
function tickDialogue(dt) {
  if (dlg.choosing) return;
  if (dlg.shown < dlg.full.length) {
    dlg.shown = Math.min(dlg.full.length, dlg.shown + dt * 60);
    $id("dlg-text").textContent = dlg.full.slice(0, Math.floor(dlg.shown));
    if (dlg.shown >= dlg.full.length) $id("dlg-more").style.visibility = "visible";
  }
}
$id("dialogue").addEventListener("click", () => { if (mode === "dialogue") advanceDialogue(); });

/* ------------------------------------------------------------- inventory */
function giveRevolver(ammo) {
  G.persist.hasRevolver = true;
  G.persist.ammo += ammo;
  toast(`Revolver acquired — ${ammo} rounds. Press 2 to draw it.`);
}
function useBandage() {
  const p = G.persist;
  if (p.bandages <= 0) { toast("No bandages left."); return; }
  if (p.hp >= p.maxHp) { toast("You're not bleeding. Yet."); return; }
  p.bandages--;
  p.hp = Math.min(p.maxHp, p.hp + 35);
  sfx("pickup");
  toast("You bind the wound tight.");
}

/* ------------------------------------------------------------- scripts */
const SCRIPTS = {
  ch1_wake: () => [
    { n: "Your side burns where the bullet went in. The dressing is stiff and brown. The IV bag over the bed has been dry for a long, long time." },
    { s: "Nick", t: "(Laura...? Zane? ...Anybody?)" },
    { n: "Out in the hall a gurney lies on its side in the dark, and something, somewhere, is dragging its feet in slow, patient circles." },
  ],
  ch1_doors: () => [
    { n: "The cafeteria doors are wrapped in chain and padlocked twice. Someone has dragged four words across the steel in dried brown paint:" },
    { n: "STAY BACK.  THEY'RE STILL INSIDE." },
    { n: "You put your ear to the door. The steel breathes. Then it knocks back — once, twice, then twenty times, all at different heights." },
    { s: "Nick", t: "(Not that way. Not ever that way.)" },
  ],
  morris_meet: () => [
    { s: "Morris", t: "Easy now. Easy. You're alright — you went down on my lawn like a dropped marionette." },
    { s: "Morris", t: "Dante, it's fine, lower it. He's warm but he's not fevered. A bite fever would've cooked him through by now." },
    { s: "Nick", t: "Bite? Somebody... somebody BIT me?" },
    { s: "Morris", t: "You really don't know. Lord. You're the man from the hospital, aren't you. The deputy. Grayson." },
    { n: "He tells it to you plain and slow, the way you'd tell a child about a funeral. The dead got up. They bite. The bite is a promise. Only the head puts them down for keeps. They walk at night, mostly, and sound draws them like a dinner bell." },
    { s: "Morris", t: "They're not people anymore, deputy. My Jenna—" },
    { s: "Dante", t: "Dad." },
    { s: "Morris", t: "...My wife walks Juniper Street after dark. Her and three others. We stopped counting the nights." },
    { s: "Nick", t: "My wife. My son. They were headed to my sister's in Ashton when I went under—" },
    { s: "Morris", t: "Then there's your answer. Everybody got told Ashton — refugee center, National Guard, hot food. The whole county emptied that direction." },
    {
      choice: [
        {
          t: "“Stay the night. Help me make this house safe for you two first.”",
          set: { morrisHelped: true },
          then: [
            { s: "Morris", t: "...Thank you. There's four of them that keep to our street. If we're loud for one bad minute, my boy gets a hundred quiet nights." },
            { s: "Dante", t: "The pistol's no good indoors, Dad says. Swing hard and don't let them grab your sleeves." },
            { do: () => startYardFight() },
          ],
        },
        {
          t: "“I can't. Every hour I wait, they're another hour gone.”",
          then: [
            { s: "Morris", t: "I'd make the same call, deputy. But you don't walk out of my yard empty-handed. Hold on." },
            { do: () => { runGiftScene(); } },
          ],
        },
      ],
    },
  ],
  morris_thanks: () => [
    { s: "Dante", t: "That's four. That's all four of them, Dad. That's— Dad, that's all of them." },
    { s: "Morris", t: "First full night's sleep this house will get in a month. Now hold still, deputy. I pay my debts." },
    { do: () => { runGiftScene(); } },
  ],
  morris_gift: () => [
    { n: "Morris presses a revolver into your hands, and a box of shells, loose and heavy as a promise." },
    { s: "Morris", t: "Found it on a man who was past needing it. I can't use the thing. Every time I line up a shot, I see somebody I used to wave at." },
    { s: "Nick", t: "You'll do it when it's time, Morris. Or you won't — and that's alright too." },
    { s: "Morris", t: "Route 9, east, past the water tower — that's Ashton. And deputy... if you cross my Jenna on that road somewhere, you walk on by. You leave her be." },
    {
      do: () => {
        giveRevolver(G.flags.morrisHelped ? 18 : 12);
        if (G.flags.morrisHelped) { G.persist.bandages = Math.min(5, G.persist.bandages + 1); toast("Revolver, 18 rounds, and a bandage. Morris pays his debts."); }
        G.run.exitOpen = true;
        G.run.ch.giftDone = true;
        setObjectiveText("Head east — take the road out (bottom right).");
      },
    },
  ],
  girl_meet: () => [
    { n: "She's maybe eight years old. One shoe. A stuffed rabbit swings from her fist by one ear, keeping time with her steps." },
    { n: "She hears you and turns, unhurried, and what's left of her face is patient — almost polite — like a child waiting for a grown-up to speak first." },
    { s: "Nick", t: "(Nobody's coming for her. There's nobody left to come.)" },
    {
      choice: [
        {
          t: "End it. Quick, and quiet, and kind.",
          set: { mercyGirl: true, girlChoiceMade: true },
          then: [
            { n: "You do it the way you'd want somebody to do it for your own. She weighs nothing at all." },
            { n: "You lay her down in the shade of the Two Pines sign with the rabbit tucked under her arm, and you walk back out into the sun." },
            { do: () => { G.run.girl = null; } },
          ],
        },
        {
          t: "Turn away. Save your strength for the living.",
          set: { girlChoiceMade: true },
          then: [
            { n: "You tell yourself there's nothing left in there to save or to hurt. All the way across the lot, you can feel her behind you — wandering her circles, keeping her patient time." },
          ],
        },
      ],
    },
  ],
  road_leave: () => [
    { n: "The engine catches on the third try and settles into a big honest V8 idle — the loudest sound left in the county. You watch the mirrors, not the road." },
    {
      ifFlag: "mercyGirl",
      then: [{ n: "The pumps. The pines. And in the shade of the sign, a small shape lying still, finally just a girl asleep with her rabbit." }],
      else: [{ n: "The pumps. The pines. And drifting between them, a small shape keeping its patient circles, getting smaller, refusing to disappear." }],
    },
    { do: () => completeChapter() },
  ],
  ben_shout: () => [
    { n: "The street turns over all at once — like you tripped a wire only the dead could see. Every head on Mercer Street swings your way at the same moment." },
    { s: "Ben", t: "(a voice, from a doorway) HEY! Lawman! You want to keep being alive? Red door, dead ahead — RUN!" },
  ],
  ben_meet: () => [
    { s: "Ben", t: "In in in—" },
    { n: "You spill into a stockroom that smells of rice and motor oil. The man who saved you wedges the door with a pry bar like he's done it a hundred times, because he has." },
    { s: "Ben", t: "Ben Yee. Before all this I delivered groceries. Turns out knowing every back door in Ashton is a superpower now." },
    { s: "Nick", t: "Nick Grayson. I'm looking for my wife and my boy — they came for the refugee center." },
    { s: "Ben", t: "...The center's gone, man. Burned the first week. I'm sorry. But — hey. Hey. There's a camp. Old quarry north of town. Thirty-some people. Families." },
    { s: "Ben", t: "There's a Laura up there. And a kid with a sheriff's cap he won't take off for love or dinner." },
    { s: "Nick", t: "(The cap. My old duty cap. He wore it to bed the entire first year.)" },
    { s: "Earl", t: "HEY. Touching. Beautiful. Now somebody take these bracelets off before the dead come in here and eat the delivery boy's witnesses!" },
    { n: "Cuffed to the standpipe in the corner: a big weathered man with a hunter's forearms and a bar-fight face." },
    { s: "Ben", t: "That's Earl Nixon. Yesterday he got up on the roof with a rifle and a bottle, screaming at the sky, shooting at clouds. Brought half of Mercer down on our heads. When I took the rifle, he swung on me. So. Cuffs." },
    { s: "Earl", t: "My brother Darren is up at that quarry camp, lawman. Darren keeps that whole crowd in venison. You want to walk in there having left his kin chained to a PIPE?" },
    {
      choice: [
        {
          t: "Uncuff him. Nobody gets left for the dead. Nobody.",
          set: { earlFreed: true },
          then: [
            { s: "Earl", t: "...Huh. Didn't figure you for it, badge. Alright. I'll behave. Near you, anyway." },
            { s: "Ben", t: "Your call, lawman. Congratulations — he's your shadow now." },
          ],
        },
        {
          t: "He stays cuffed. He'll get us all killed.",
          then: [
            { s: "Ben", t: "...Then I leave the key on the sill. Out of reach till he's calm enough to work for it. Best I can do for both my consciences." },
            { s: "Earl", t: "You're gonna WHAT? Lawman! LAWMAN! Don't you walk— don't you WALK away from me—" },
          ],
        },
      ],
    },
    {
      do: () => {
        G.run.exitOpen = true;
        G.run.ch.metBen = true;
        setObjectiveText("Follow Ben down the loading hatch (marked exit).");
        if (!G.flags.earlFreed) { const e = G.run.npcs.find((n) => n.id === "earl"); if (e) e.stay = true; }
      },
    },
  ],
  camp_reunion: () => [
    { n: "You see the cap first. The boy under it goes still, the way deer go still — and then he's running, and so are you, and your bad side doesn't get a vote." },
    { s: "Cody", t: "DAD! Dad — dad dad dad—" },
    { s: "Laura", t: "Nick. NICK. Oh my God. They told me— I saw the hospital on the news, the fires, they said nobody—" },
    { n: "For a long minute the world is just the three of you and the smell of woodsmoke. Over Laura's shoulder, Zane Marsh stands with his arms folded, wearing a face you've never seen on him in fifteen years of riding together." },
    { s: "Zane", t: "The hospital was falling apart, brother. Military in the halls. I heard them clearing rooms. I got to your bed, and I put my ear to your chest, and I swear to God — I swear to God, Nick — there was nothing." },
    { s: "Zane", t: "So I made a call. I told them you were gone. Because it was the only way on this earth Laura was ever going to put Cody in that car." },
    { s: "Laura", t: "...I would never have left. He knew I would never have left." },
    {
      choice: [
        {
          t: "“You got them out alive, Zane. That's all of it. That's everything.”",
          set: { forgaveZane: true },
          then: [
            { s: "Zane", t: "...Yeah. Yeah." },
            { n: "Something in his shoulders comes down an inch. Not all the way down. An inch." },
          ],
        },
        {
          t: "“You buried me, Zane. You buried me, and then you moved into my life.”",
          then: [
            { s: "Zane", t: "I kept them ALIVE. You want the collar back, deputy? Take it. Take it all back." },
            { n: "He walks off toward the tree line. Laura doesn't watch him go — which, somehow, is worse." },
          ],
        },
      ],
    },
    { n: "The camp gathers at dusk: names, handshakes, a bowl of something hot. Then Zane comes back with a coffee can and business in his face." },
    { s: "Zane", t: "Camp matters. We are down to a can of loose shells for six guns. That bag you hauled up the ridge — this camp would sleep a lot easier if it were community property." },
    {
      choice: [
        {
          t: "Pour your box into the can. “We stand or we fall together.”",
          set: { sharedAmmo: true },
          then: [
            { n: "You pour your shells into the coffee can in front of everybody. It rattles like applause. It's the cheapest thing you will ever buy trust with." },
            { do: () => { G.persist.ammo = Math.max(6, Math.floor(G.persist.ammo / 2)); } },
          ],
        },
        {
          t: "“I keep my ammunition. My family comes first now.”",
          then: [
            { s: "Zane", t: "Sure. 'Course. Family first." },
            { n: "He says it in a way you decide not to hear twice." },
          ],
        },
      ],
    },
    { n: "The sun goes down behind the quarry wall. Out past the tents, down the dark of the ridge road, the pines begin — very quietly — to move." },
    { do: () => startCampDefense() },
  ],
  camp_morning: () => [
    { n: "Dawn comes up gray and thin over the quarry lake, and the count is taken twice because nobody believes it the first time. Everyone. Everyone made it." },
    {
      ifFlag: "sharedAmmo",
      then: [{ s: "Zane", t: "Every rifle on that line had rounds in it because of you. I know what that's worth, Nick. I know exactly what it cost, too." }],
      else: [{ s: "Zane", t: "We held. Barely. Half my line was swinging tent poles by the end. Remember that, next time you're counting that bag of yours." }],
    },
    { s: "Ben", t: "So — the radio's been doing its thing again all night. Listen." },
    { n: "A tired woman's voice, looping every thirty seconds: 'ARC Research Station. Perimeter power holding. Survivors welcome.' Forty miles north. Fuel for maybe forty-five." },
    { s: "Laura", t: "Cody needs walls, Nick. Everybody here needs walls." },
    {
      do: () => {
        G.run.exitOpen = true;
        setObjectiveText("Lead them out — take the north path.");
        const z = G.run.npcs.find((n) => n.id === "zane"); if (z) z.gone = true;
      },
    },
  ],
  finale: () => [
    { n: "He's standing in the middle of the road with his back to you, hat off, holster unsnapped. When he talks, he talks to the dark ahead, not to you." },
    { s: "Zane", t: "Fifteen years I stood on your left, brother. Then the world ends — and I finally get to be the one who saves them. Five weeks. I got five weeks of being the man." },
    { s: "Zane", t: "Then you walk up out of your own grave, and I hand it all back with a smile, and everybody just expects my heart to be IN it." },
    { n: "He turns around. The pistol is not quite pointed at you. It is not quite pointed away." },
    { s: "Zane", t: "So tell me, Nick. Tell me why I shouldn't just be the man again — right here, where nobody's watching." },
    {
      choice: [
        {
          t: "“Lower the gun, Zane. Come home with us.”",
          then: [
            {
              do: () => {
                const steps = G.flags.forgaveZane
                  ? [
                      { s: "Zane", t: "...Damn you for meaning it." },
                      { n: "The hammer comes down slow. He hands you the pistol grip-first, the way you were both taught, and his face folds up like a map nobody needs anymore." },
                      { s: "Zane", t: "Don't tell Cody about this. The kid thinks I hang the moon." },
                      { s: "Nick", t: "You carried his cap back to him once. He'll think it forever." },
                      { do: () => { G.flags.zaneOutcome = "redeemed"; } },
                    ]
                  : [
                      { s: "Zane", t: "See — you say the words. But I heard you at that camp, brother. Far as you're concerned, I'm buried already." },
                      { n: "He holsters the pistol, steps off the road, and lets the dark have him. You listen for a long time. There is no shot. There are no other footsteps. There is only gone." },
                      { do: () => { G.flags.zaneOutcome = "gone"; const z = G.run.npcs.find((n) => n.id === "zane"); if (z) z.gone = true; } },
                    ];
                dlg.queue.splice(dlg.i + 1, 0, ...steps);
              },
            },
          ],
        },
        {
          t: "Say nothing. Hold out your open hand.",
          if: () => G.flags.forgaveZane && G.flags.sharedAmmo,
          then: [
            { n: "You hold out your open hand and you wait — the way you'd gentle a spooked horse, the way you did the night his father died, the way you always have." },
            { s: "Zane", t: "...You son of a gun. You never did fight fair." },
            { n: "The pistol lands in your palm, warm from his grip. He laughs once — an awful, relieved, alive sound — and walks past you, back toward the trucks, back toward the fire." },
            { do: () => { G.flags.zaneOutcome = "redeemed"; } },
          ],
        },
        {
          t: "Go for your gun.",
          then: [
            { n: "You were always faster. Both of you knew it — it's half of why he needed the five weeks. The shot rolls out over the pines and comes back off the quarry walls twice." },
            { n: "He sits down in the road like a man remembering a chair, looks at you with more relief than surprise, and is gone before you can be sorry." },
            { s: "Nick", t: "(The dark ahead is already moving. Sound draws them. He taught that to rookies, once.)" },
            {
              do: () => {
                G.flags.zaneOutcome = "dead";
                const z = G.run.npcs.find((n) => n.id === "zane"); if (z) z.gone = true;
                sfx("shot");
                [[12, 3], [16, 5], [13, 8], [15, 8]].forEach(([tx, ty]) => {
                  G.run.zombies.push(makeZombie(tx * TILE + TILE / 2, ty * TILE + TILE / 2, { state: "chase", speed: rand(55, 70) }));
                });
              },
            },
          ],
        },
      ],
    },
    {
      do: () => {
        G.run.exitOpen = true;
        setObjectiveText("Take your family through the gate.");
      },
    },
  ],
};

function runGiftScene() {
  dlg.queue.splice(dlg.i + 1, 0, ...SCRIPTS.morris_gift());
}

/* -------------------------------------------------- chapter-specific logic */
function startYardFight() {
  const spots = [[3, 6], [9, 6], [14, 7], [24, 6]];
  spots.forEach(([tx, ty]) => {
    G.run.zombies.push(makeZombie(tx * TILE + TILE / 2, ty * TILE + TILE / 2, { tag: "yard", state: "chase", speed: rand(45, 60) }));
  });
  G.run.ch.yardLeft = spots.length;
  G.run.ch.yardActive = true;
  setObjectiveText(`Clear the shamblers from Juniper Street (${spots.length} left).`);
  sfx("growl");
}

function startCampDefense() {
  const r = G.run;
  r.night = true;
  r.dark = 0.6;
  r.campHp = 100;
  r.ch.phase = "defend";
  r.ch.toSpawn = 14;
  r.ch.spawnT = 1.2;
  r.ch.spawnPts = [[2, 2], [30, 2], [1, 9], [32, 9], [2, 17], [30, 17], [16, 18]];
  r.ch.spawnIdx = 0;
  setObjectiveText("NIGHT — keep the shamblers off the fire!");
  // gather the family at the fire, post the fighters in a ring
  const fire = r.firePos;
  const put = (id, dx, dy, ally) => {
    const n = r.npcs.find((p) => p.id === id && !p.gone);
    if (!n) return;
    n.x = fire.x + dx; n.y = fire.y + dy;
    if (ally) r.allies.push({ npc: n, cd: rand(0.5, 1.5), interval: ally.interval, range: ally.range, melee: !!ally.melee });
  };
  put("laura", -26, -14, null);
  put("cody", 22, -18, null);
  put("zane", -70, 60, G.flags.sharedAmmo ? { interval: 1.7, range: 250 } : { interval: 1.3, range: 55, melee: true });
  put("ben", 80, 40, G.flags.sharedAmmo ? { interval: 2.1, range: 230 } : { interval: 3.0, range: 200 });
  if (G.flags.earlFreed) {
    const earl = { id: "earl", name: "Earl", color: "#e58a5a", x: fire.x + 10, y: fire.y + 95, gone: false };
    r.npcs.push(earl);
    r.allies.push({ npc: earl, cd: 1, interval: 1.9, range: 260 });
  }
  toast(G.flags.sharedAmmo ? "The watch line has full guns tonight." : "The watch line is short on shells tonight.");
  updateHUD();
  sfx("growl");
}

const LOGIC = [
  /* ---- Chapter 1: hospital ---- */
  {
    onEnter() {
      G.run.exitOpen = true;
      runScript(SCRIPTS.ch1_wake());
    },
    doorPrompt: () => "Inspect the chained doors",
    onDoor() { runScript(SCRIPTS.ch1_doors()); },
  },
  /* ---- Chapter 2: Morris ---- */
  {
    onEnter() {},
    talk(id) {
      const c = G.run.ch;
      if (id === "morris") {
        if (!c.metMorris) { c.metMorris = true; runScript(SCRIPTS.morris_meet()); return; }
        if (c.yardActive) { say("Morris", "Four of them. Watch your sleeves, deputy!"); return; }
        if (c.giftDone) { say("Morris", "Route 9. East. God keep you, deputy."); return; }
        runScript(SCRIPTS.morris_meet());
        return;
      }
      if (id === "dante") {
        say("Dante", c.giftDone
          ? "If you find the Army out there... tell them Juniper Street is still here. Tell them somebody's still here."
          : "Dad said you're police. Real police. We waved a shirt at a helicopter once. It didn't come back.");
      }
    },
    onZombieKilled(z) {
      const c = G.run.ch;
      if (z.tag === "yard") {
        c.yardLeft--;
        if (c.yardLeft > 0) setObjectiveText(`Clear the shamblers from Juniper Street (${c.yardLeft} left).`);
        else { c.yardActive = false; runScript(SCRIPTS.morris_thanks()); }
      }
    },
  },
  /* ---- Chapter 3: the road ---- */
  {
    onEnter() {},
    update() {
      const r = G.run, p = G.player;
      if (r.girl && !G.flags.girlChoiceMade && dist(p.x, p.y, r.girl.x, r.girl.y) < 120) {
        runScript(SCRIPTS.girl_meet());
      }
    },
    onItem(kind) {
      if (kind === "fuel") {
        G.run.ch.hasFuel = true;
        toast("A jerrycan, half full. It sloshes like good news.");
        setObjectiveText("Fuel up the old pickup (southwest).");
        return true;
      }
      return false;
    },
    truckPrompt: () => (G.run.ch.hasFuel ? "Fuel the pickup and go" : "The old pickup"),
    onTruck() {
      if (!G.run.ch.hasFuel) { toast("The tank is bone dry. There'll be gas somewhere around the station."); return; }
      runScript(SCRIPTS.road_leave());
    },
  },
  /* ---- Chapter 4: the city ---- */
  {
    onEnter() {},
    doorPrompt: () => "A red steel door — barred from inside",
    onDoor() { toast("Barred from the inside. Whoever's in there likes it that way."); },
    update() {
      const r = G.run, p = G.player, c = r.ch;
      if (!c.ambushed && p.x > 14 * TILE && p.y < 15 * TILE) {
        c.ambushed = true;
        [[2, 2], [6, 9], [3, 12], [10, 2], [14, 10], [18, 3], [22, 8], [20, 12]].forEach(([tx, ty]) => {
          r.zombies.push(makeZombie(tx * TILE + TILE / 2, ty * TILE + TILE / 2, { state: "chase", speed: rand(50, 68) }));
        });
        r.zombies.forEach((z) => { if (!z.passive) z.state = "chase"; });
        r.doors.forEach((d) => { r.tiles[d.y][d.x] = "_"; });
        r.doors = [];
        setObjectiveText("RUN — get through the red door, east side of the street!");
        runScript(SCRIPTS.ben_shout());
        sfx("growl");
      }
      if (c.ambushed && !c.metBen && p.x > 28 * TILE) {
        runScript(SCRIPTS.ben_meet());
      }
    },
    talk(id) {
      const c = G.run.ch;
      if (id === "ben") say("Ben", c.metBen ? "Hatch. Down. Now-ish. The pry bar's good, but it's not a religion." : "Move move move—");
      if (id === "earl") {
        if (G.flags.earlFreed) say("Earl", "Keys, hatch, go. You can adopt more strays later, Officer Friendly.");
        else say("Earl", "LAWMAN. The key. The KEY. I will sing every verse of everything I know until you regret this!");
      }
    },
  },
  /* ---- Chapter 5: the camp ---- */
  {
    onEnter() {},
    update(dt) {
      const r = G.run, p = G.player, c = r.ch;
      if (!c.reunion) {
        const cody = r.npcs.find((n) => n.id === "cody");
        if (cody && dist(p.x, p.y, cody.x, cody.y) < 150) {
          c.reunion = true;
          runScript(SCRIPTS.camp_reunion());
        }
        return;
      }
      if (c.phase === "defend") {
        // spawner
        if (c.toSpawn > 0) {
          c.spawnT -= dt;
          if (c.spawnT <= 0) {
            c.spawnT = 2.0;
            c.toSpawn--;
            const [tx, ty] = c.spawnPts[c.spawnIdx++ % c.spawnPts.length];
            r.zombies.push(makeZombie(tx * TILE + TILE / 2, ty * TILE + TILE / 2, {
              state: "chase", speed: rand(52, 74), targetFire: Math.random() < 0.65,
            }));
            if (c.toSpawn % 4 === 0) sfx("growl");
          }
        }
        if (c.toSpawn <= 0 && r.zombies.length === 0) {
          c.phase = "morning";
          r.night = false;
          r.dark = 0;
          runScript(SCRIPTS.camp_morning());
        }
      }
    },
    talk(id) {
      const c = G.run.ch;
      if (id === "ben") say("Ben", c.reunion ? "Told you there was a Laura." : "Go on, man. Go. They're at the fire.");
      if (id === "laura") say("Laura", c.phase === "morning" ? "We're right behind you, Nick. We always were." : "Stay where I can see you. I've done my share of not-seeing-you for one apocalypse.");
      if (id === "cody") say("Cody", "I kept your cap safe. It kept me safe back.");
      if (id === "zane") say("Zane", "Get some rest, brother. The night shift's mine. Always is.");
      if (id === "earl") say("Earl", "Darren's around here somewhere. Do me a favor — the pipe thing stays in Ashton.");
    },
  },
  /* ---- Chapter 6: the ARC road ---- */
  {
    onEnter() {},
    update() {
      const r = G.run, p = G.player, c = r.ch;
      const zane = r.npcs.find((n) => n.id === "zane" && !n.gone);
      if (!c.finale && zane && dist(p.x, p.y, zane.x, zane.y) < 150) {
        c.finale = true;
        runScript(SCRIPTS.finale());
      }
    },
    talk(id) {
      if (id === "zane") {
        if (G.flags.zaneOutcome === "redeemed") say("Zane", "Well? Gate's right there, brother. Walk your family home.");
      }
    },
  },
];

function say(speaker, text) {
  runScript([{ s: speaker, t: text }]);
}

/* --------------------------------------------------------------- combat */
function attack() {
  const p = G.player, per = G.persist, r = G.run;
  if (p.atkCd > 0) return;
  if (per.weapon === "gun" && per.hasRevolver) {
    if (per.ammo <= 0) { toast("Click. Empty."); p.atkCd = 0.3; return; }
    per.ammo--;
    p.atkCd = GUN.cd;
    sfx("shot");
    // ray
    const len = Math.hypot(p.dx, p.dy) || 1;
    const ux = p.dx / len, uy = p.dy / len;
    let hitZ = null, hx = p.x, hy = p.y;
    for (let d = 10; d < GUN.range; d += 6) {
      hx = p.x + ux * d; hy = p.y + uy * d;
      if (solidAt(hx, hy)) break;
      hitZ = r.zombies.find((z) => dist(z.x, z.y, hx, hy) < ZOMBIE_R + 4) || null;
      if (r.girl && !hitZ && dist(r.girl.x, r.girl.y, hx, hy) < 12) { hurtGirl(GUN.dmg); break; }
      if (hitZ) break;
    }
    r.fx.push({ type: "tracer", x1: p.x + ux * 14, y1: p.y + uy * 14, x2: hx, y2: hy, ttl: 0.08 });
    r.fx.push({ type: "flash", x: p.x + ux * 16, y: p.y + uy * 16, ttl: 0.06 });
    if (hitZ) hurtZombie(hitZ, GUN.dmg, ux, uy);
    // noise
    r.zombies.forEach((z) => { if (!z.passive && dist(z.x, z.y, p.x, p.y) < GUN.noise) z.state = "chase"; });
  } else {
    const m = MELEE[per.melee];
    p.atkCd = m.cd;
    sfx("swing");
    const len = Math.hypot(p.dx, p.dy) || 1;
    const ux = p.dx / len, uy = p.dy / len;
    r.fx.push({ type: "swing", x: p.x, y: p.y, a: Math.atan2(uy, ux), ttl: 0.12, range: m.range });
    let hitAny = false;
    r.zombies.forEach((z) => {
      const d = dist(z.x, z.y, p.x, p.y);
      if (d < m.range + ZOMBIE_R) {
        const dot = ((z.x - p.x) * ux + (z.y - p.y) * uy) / (d || 1);
        if (dot > 0.25) { hurtZombie(z, m.dmg, ux, uy); hitAny = true; }
      }
    });
    if (r.girl) {
      const d = dist(r.girl.x, r.girl.y, p.x, p.y);
      if (d < m.range + 10) {
        const dot = ((r.girl.x - p.x) * ux + (r.girl.y - p.y) * uy) / (d || 1);
        if (dot > 0.25) hurtGirl(m.dmg);
      }
    }
    if (hitAny) sfx("hit");
  }
  updateHUD();
}
function hurtZombie(z, dmg, ux, uy) {
  z.hp -= dmg;
  z.hitFlash = 0.15;
  z.state = z.passive ? z.state : "chase";
  moveCircle(z, ux * 14, uy * 14, ZOMBIE_R);
  if (z.hp <= 0) killZombie(z);
}
function killZombie(z) {
  const r = G.run;
  r.zombies = r.zombies.filter((q) => q !== z);
  r.corpses.push({ x: z.x, y: z.y, ttl: 15 });
  sfx("hit");
  const hook = LOGIC[G.chapter].onZombieKilled;
  if (hook) hook(z);
}
function hurtGirl(dmg) {
  const r = G.run;
  if (!r.girl) return;
  r.girl.hp -= dmg;
  if (r.girl.hp <= 0) {
    r.corpses.push({ x: r.girl.x, y: r.girl.y, ttl: 15, small: true });
    r.girl = null;
    if (!G.flags.girlChoiceMade) { G.flags.girlChoiceMade = true; }
  }
}
function damagePlayer(dmg) {
  const p = G.player, per = G.persist;
  if (p.invuln > 0) return;
  per.hp -= dmg;
  p.invuln = 0.55;
  p.flash = 0.35;
  sfx("hurt");
  updateHUD();
  if (per.hp <= 0) {
    per.hp = 0;
    gameOver(G.run.night
      ? "The line broke, and the dark came all the way in."
      : "You go down among the wandering, and Linden County keeps its quiet.");
  }
}

/* --------------------------------------------------------------- update */
function update(dt) {
  if (mode === "dialogue") { tickDialogue(dt); return; }
  if (mode !== "play") return;
  const r = G.run, p = G.player, per = G.persist;

  // movement
  let mx = 0, my = 0;
  if (keys.KeyW || keys.ArrowUp) my -= 1;
  if (keys.KeyS || keys.ArrowDown) my += 1;
  if (keys.KeyA || keys.ArrowLeft) mx -= 1;
  if (keys.KeyD || keys.ArrowRight) mx += 1;
  if (mx || my) {
    const l = Math.hypot(mx, my);
    p.dx = mx / l; p.dy = my / l;
    moveCircle(p, (mx / l) * PLAYER_SPEED * dt, (my / l) * PLAYER_SPEED * dt, PLAYER_R);
  }
  p.atkCd = Math.max(0, p.atkCd - dt);
  p.invuln = Math.max(0, p.invuln - dt);
  p.flash = Math.max(0, p.flash - dt);

  // exit?
  if (r.exitOpen && r.exitPos) {
    const ex = r.exitPos.x * TILE + TILE / 2, ey = r.exitPos.y * TILE + TILE / 2;
    if (dist(p.x, p.y, ex, ey) < TILE * 0.6) { completeChapter(); return; }
  }

  // items
  r.items = r.items.filter((it) => {
    if (dist(it.x, it.y, p.x, p.y) < 26) {
      const hook = LOGIC[G.chapter].onItem;
      if (hook && hook(it.kind)) { sfx("pickup"); return false; }
      if (it.kind === "ammo") { per.ammo += 6; toast("+6 rounds."); }
      else if (it.kind === "bandage") { per.bandages = Math.min(5, per.bandages + 1); toast("+1 bandage."); }
      else if (it.kind === "melee") { per.melee = "pole"; toast("You unscrew the IV pole. Better than bare hands."); }
      sfx("pickup");
      updateHUD();
      return false;
    }
    return true;
  });

  // zombies
  const fire = r.firePos;
  r.zombies.forEach((z) => {
    z.atkCd = Math.max(0, z.atkCd - dt);
    z.hitFlash = Math.max(0, z.hitFlash - dt);
    const dp = dist(z.x, z.y, p.x, p.y);
    if (!z.passive) {
      if (z.state === "idle" && dp < 150) { z.state = "chase"; if (Math.random() < 0.4) sfx("growl"); }
      if (z.state === "chase" && dp > 420 && !r.night) z.state = "idle";
    }
    if (z.state === "chase") {
      let tx = p.x, ty = p.y;
      if (z.targetFire && fire && r.night) {
        const df = dist(z.x, z.y, fire.x, fire.y);
        if (df < dp || dp > 120) { tx = fire.x; ty = fire.y; }
      }
      const d = dist(z.x, z.y, tx, ty) || 1;
      moveCircle(z, ((tx - z.x) / d) * z.speed * dt, ((ty - z.y) / d) * z.speed * dt, ZOMBIE_R);
      // reached the fire?
      if (r.night && fire && dist(z.x, z.y, fire.x, fire.y) < 52) {
        r.campHp -= 12;
        killZombie(z);
        toast("They're at the fire line!");
        updateHUD();
        if (r.campHp <= 0) { gameOver("The fire went out. Everything after that was only mercy withheld."); }
        return;
      }
      if (dp < PLAYER_R + ZOMBIE_R + 2 && z.atkCd <= 0) {
        z.atkCd = 1.0;
        damagePlayer(9 + Math.floor(Math.random() * 5));
      }
    } else {
      z.wt -= dt;
      if (z.wt <= 0) { z.wt = rand(1.5, 3.5); z.dir = rand(0, Math.PI * 2); }
      moveCircle(z, Math.cos(z.dir) * 16 * dt, Math.sin(z.dir) * 16 * dt, ZOMBIE_R);
    }
  });
  // soft separation
  for (let i = 0; i < r.zombies.length; i++) {
    for (let j = i + 1; j < r.zombies.length; j++) {
      const a = r.zombies[i], b = r.zombies[j];
      const d = dist(a.x, a.y, b.x, b.y);
      if (d < 20 && d > 0.01) {
        const push = (20 - d) / 2, nx = (b.x - a.x) / d, ny = (b.y - a.y) / d;
        moveCircle(a, -nx * push, -ny * push, ZOMBIE_R);
        moveCircle(b, nx * push, ny * push, ZOMBIE_R);
      }
    }
  }

  // the girl at the pumps
  if (r.girl) {
    const g = r.girl;
    g.wt -= dt;
    if (g.wt <= 0) { g.wt = rand(2, 4); g.dir = rand(0, Math.PI * 2); }
    moveCircle(g, Math.cos(g.dir) * 11 * dt, Math.sin(g.dir) * 11 * dt, 9);
  }

  // allies
  r.allies.forEach((al) => {
    if (al.npc.gone) return;
    al.cd -= dt;
    if (al.cd <= 0) {
      let best = null, bd = 1e9;
      r.zombies.forEach((z) => {
        const d = dist(z.x, z.y, al.npc.x, al.npc.y);
        if (d < al.range && d < bd) { best = z; bd = d; }
      });
      if (best) {
        al.cd = al.interval;
        if (al.melee) {
          r.fx.push({ type: "swing", x: al.npc.x, y: al.npc.y, a: Math.atan2(best.y - al.npc.y, best.x - al.npc.x), ttl: 0.12, range: 50 });
          hurtZombie(best, 2, 0, 0);
        } else {
          r.fx.push({ type: "tracer", x1: al.npc.x, y1: al.npc.y, x2: best.x, y2: best.y, ttl: 0.07 });
          sfx("shot");
          hurtZombie(best, 3, 0, 0);
        }
      }
    }
  });

  // fx / corpses
  r.fx = r.fx.filter((f) => (f.ttl -= dt) > 0);
  r.corpses.forEach((c) => (c.ttl -= dt));
  r.corpses = r.corpses.filter((c) => c.ttl > 0);

  // chapter hook
  const hook = LOGIC[G.chapter].update;
  if (hook) hook(dt);

  // interact prompt
  const target = findInteract();
  const prompt = $id("interact-prompt");
  if (target) { prompt.textContent = `E — ${target.label}`; prompt.style.display = "block"; }
  else prompt.style.display = "none";

  // camera
  const mw = r.w * TILE, mh = r.h * TILE;
  camera.x = mw <= VIEW_W ? (mw - VIEW_W) / 2 : clamp(p.x - VIEW_W / 2, 0, mw - VIEW_W);
  camera.y = mh <= VIEW_H ? (mh - VIEW_H) / 2 : clamp(p.y - VIEW_H / 2, 0, mh - VIEW_H);
}

function findInteract() {
  const r = G.run, p = G.player, L = LOGIC[G.chapter];
  let best = null, bd = 1e9;
  const consider = (x, y, radius, label, act) => {
    const d = dist(p.x, p.y, x, y);
    if (d < radius && d < bd) { bd = d; best = { label, act }; }
  };
  r.npcs.forEach((n) => {
    if (n.gone) return;
    consider(n.x, n.y, 64, `Talk to ${n.name}`, () => { const t = L.talk; if (t) t(n.id); });
  });
  if (r.truckPos && L.onTruck) consider(r.truckPos.x, r.truckPos.y, 78, L.truckPrompt ? L.truckPrompt() : "Pickup", () => L.onTruck());
  if (L.onDoor) {
    r.doors.forEach((d) => {
      consider(d.x * TILE + TILE / 2, d.y * TILE + TILE / 2, 60, L.doorPrompt ? L.doorPrompt() : "Door", () => L.onDoor());
    });
  }
  return best;
}

/* ----------------------------------------------------- chapter flow */
function completeChapter() {
  $id("dialogue").style.display = "none";
  const next = G.chapter + 1;
  if (next >= WD_CHAPTERS.length) {
    localStorage.removeItem(SAVE_KEY);
    showEnding();
    return;
  }
  try {
    localStorage.setItem(SAVE_KEY, JSON.stringify({ chapter: next, persist: G.persist, flags: G.flags }));
  } catch (e) { /* private mode etc. */ }
  startChapter(next);
}
function gameOver(msg) {
  mode = "gameover";
  $id("dialogue").style.display = "none";
  $id("hud").style.display = "none";
  const ov = $id("overlay");
  ov.classList.remove("hidden");
  $id("overlay-inner").innerHTML = `
    <h1><span class="red">YOU ARE</span> WANDERING</h1>
    <div class="body-text" style="text-align:center">${msg}</div>
    <button class="menu-btn" id="btn-retry">TRY AGAIN</button>
  `;
  $id("btn-retry").onclick = () => {
    ensureAudio();
    const snap = JSON.parse(G.snapshot);
    G.persist = snap.persist;
    G.flags = snap.flags;
    startChapter(G.chapter);
  };
}

/* ------------------------------------------------------------ overlays */
function showTitle() {
  mode = "title";
  $id("hud").style.display = "none";
  const ov = $id("overlay");
  ov.classList.remove("hidden");
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem(SAVE_KEY)); } catch (e) { saved = null; }
  $id("overlay-inner").innerHTML = `
    <h1>THE <span class="red">WANDERING</span> DEAD</h1>
    <h2>A LINDEN COUNTY STORY</h2>
    <div class="body-text" style="text-align:center">
Deputy Nick Grayson went down with a bullet in his side and woke up
in a hospital the world forgot. His wife and son are sixty miles east.
Everything in between is dead — and walking.

Walk. Fight. And make the calls no one should have to make.</div>
    <button class="menu-btn" id="btn-new">NEW GAME</button>
    ${saved ? '<button class="menu-btn" id="btn-cont">CONTINUE — ' + WD_CHAPTERS[saved.chapter].name + "</button>" : ""}
    <div class="fine">
WASD / arrows — move · SPACE — attack · E — talk / interact · 1 / 2 — weapons · H — bandage<br><br>
An original fan-made homage in the spirit of the classic zombie survival drama.<br>
Personal, non-commercial project. Not affiliated with any franchise.</div>
  `;
  $id("btn-new").onclick = () => {
    ensureAudio();
    localStorage.removeItem(SAVE_KEY);
    G = newGame();
    startChapter(0);
  };
  if (saved) {
    $id("btn-cont").onclick = () => {
      ensureAudio();
      G = newGame();
      G.persist = saved.persist;
      G.flags = saved.flags;
      startChapter(saved.chapter);
    };
  }
}

function showCard(i) {
  mode = "card";
  const ch = WD_CHAPTERS[i];
  $id("hud").style.display = "none";
  const ov = $id("overlay");
  ov.classList.remove("hidden");
  $id("overlay-inner").innerHTML = `
    <h2>${ch.name}</h2>
    <h1 style="font-size:38px">${ch.title.toUpperCase()}</h1>
    <div class="body-text">${ch.intro}</div>
    <button class="menu-btn" id="btn-begin">BEGIN</button>
  `;
  $id("btn-begin").onclick = () => {
    ensureAudio();
    ov.classList.add("hidden");
    $id("hud").style.display = "block";
    updateHUD();
    mode = "play";
    const hook = LOGIC[i].onEnter;
    if (hook) hook();
  };
}

function showEnding() {
  mode = "ending";
  $id("hud").style.display = "none";
  const f = G.flags;
  const paras = [];
  paras.push("The gate rolls back on a floodlit yard: generators, clean water, a medic asking for names like names still matter — because here, they do. Cody falls asleep mid-sentence wearing your cap. Laura holds your hand like the world can't be trusted with it.");
  if (f.zaneOutcome === "redeemed") paras.push("Zane takes third watch, like always. Some mornings he laughs at breakfast and it almost sounds like fifteen years ago. You gave him the pistol back. He's earned the weight of it.");
  else if (f.zaneOutcome === "gone") paras.push("Nobody talks about Zane. But some nights there's a light out past the wire, small and stubborn as a held grudge, and you leave the north gate unbarred a little longer than you should.");
  else if (f.zaneOutcome === "dead") paras.push("Cody stopped asking about Zane after the first week. That's the part you carry — not the shot. The not-asking.");
  if (f.morrisHelped) paras.push("Nineteen days on, the perimeter horn sounds twice: a man and a boy at the gate, road-thin and alive. Morris shakes your hand like a man paying off a mortgage. Dante tells everyone who'll listen that Juniper Street held.");
  else paras.push("You think about Juniper Street more than you admit — the man with the shovel, the boy on the porch. You left them a clear conscience and an empty yard. You hope it was enough. You don't get to know.");
  if (f.mercyGirl) paras.push("Some nights you dream of Two Pines: the shade under the sign, the rabbit tucked in her arm, everything finally still. As nightmares go, it is the kindest one you own.");
  else if (f.girlChoiceMade) paras.push("Some nights you dream of Two Pines, and of small patient circles that never finish, and you wake with your hand already reaching for the lamp.");
  if (f.earlFreed) paras.push("Earl lasted eleven days inside the wire before he stole a truck, a rifle, and half a crate of penicillin. But every few weeks a dressed deer turns up hanging at the north fence, and Darren just grins and says his brother never could apologize in words.");
  else paras.push("Ben went back for Earl on the ninth day. He doesn't say what he found — an empty cuff, a key gone from the sill, a window out. You both choose to believe it, and mostly you manage.");
  if (f.sharedAmmo) paras.push("They voted you head of the watch before you'd pitched a tent. Turns out a coffee can of shells, poured out in front of everybody, buys more than trust — it buys you back your badge.");
  paras.push("The dead still wander. So does everyone left. But tonight there is a fence, and a fire, and every single person you could carry made it inside the wire.");

  const recap = [];
  recap.push(f.morrisHelped ? "You stayed the night to make Morris and Dante's house safe." : "You left Morris and Dante at first light.");
  if (f.girlChoiceMade) recap.push(f.mercyGirl ? "You gave the girl at Two Pines her rest." : "You walked away from the girl at Two Pines.");
  recap.push(f.earlFreed ? "You uncuffed Earl Nixon." : "You left Earl Nixon chained to the pipe.");
  recap.push(f.forgaveZane ? "You forgave Zane." : "You did not forgive Zane.");
  recap.push(f.sharedAmmo ? "You shared your ammunition with the camp." : "You kept your ammunition for your family.");
  recap.push({ redeemed: "On the ARC road, you brought Zane home.", gone: "On the ARC road, Zane walked into the dark.", dead: "On the ARC road, you were faster." }[f.zaneOutcome] || "");

  const ov = $id("overlay");
  ov.classList.remove("hidden");
  $id("overlay-inner").innerHTML = `
    <h2>EPILOGUE</h2>
    <h1 style="font-size:34px">THE <span class="red">WANDERING</span> DEAD</h1>
    <div class="body-text">${paras.join("\n\n")}</div>
    <ul class="recap">${recap.filter(Boolean).map((r) => `<li>${r}</li>`).join("")}</ul>
    <button class="menu-btn" id="btn-again">PLAY AGAIN</button>
    <div class="fine">Thank you for playing. Every choice you made shaped this ending — there are others.</div>
  `;
  $id("btn-again").onclick = () => showTitle();
}

/* ----------------------------------------------------------------- draw */
const cv = $id("game");
const ctx = cv.getContext("2d");
const darkCv = document.createElement("canvas");
darkCv.width = VIEW_W; darkCv.height = VIEW_H;
const dctx = darkCv.getContext("2d");
let animT = 0;

function draw() {
  ctx.fillStyle = "#0a0a0c";
  ctx.fillRect(0, 0, VIEW_W, VIEW_H);
  if (!G || !G.run || mode === "title" || mode === "ending") return;
  const r = G.run, p = G.player;
  ctx.save();
  ctx.translate(-Math.round(camera.x), -Math.round(camera.y));

  const x0 = Math.max(0, Math.floor(camera.x / TILE)), x1 = Math.min(r.w - 1, Math.ceil((camera.x + VIEW_W) / TILE));
  const y0 = Math.max(0, Math.floor(camera.y / TILE)), y1 = Math.min(r.h - 1, Math.ceil((camera.y + VIEW_H) / TILE));

  for (let ty = y0; ty <= y1; ty++) {
    for (let tx = x0; tx <= x1; tx++) {
      drawTile(tx, ty, r.tiles[ty][tx]);
    }
  }
  // corpses
  r.corpses.forEach((c) => {
    ctx.globalAlpha = clamp(c.ttl / 4, 0, 0.85);
    ctx.fillStyle = "#3d1512";
    ctx.beginPath(); ctx.ellipse(c.x, c.y, c.small ? 12 : 17, c.small ? 8 : 11, 0.5, 0, 7); ctx.fill();
    ctx.fillStyle = "#4a5545";
    ctx.beginPath(); ctx.ellipse(c.x, c.y, c.small ? 7 : 10, c.small ? 4 : 6, 0.5, 0, 7); ctx.fill();
    ctx.globalAlpha = 1;
  });
  // items
  r.items.forEach((it) => {
    const bob = Math.sin(animT * 4 + it.x) * 2;
    if (it.kind === "ammo") {
      ctx.fillStyle = "#c8a23c"; ctx.fillRect(it.x - 7, it.y - 5 + bob, 14, 10);
      ctx.fillStyle = "#7a6224"; ctx.fillRect(it.x - 7, it.y - 5 + bob, 14, 3);
    } else if (it.kind === "bandage") {
      ctx.fillStyle = "#e8e4da"; ctx.fillRect(it.x - 7, it.y - 7 + bob, 14, 14);
      ctx.fillStyle = "#b03a2e"; ctx.fillRect(it.x - 5, it.y - 2 + bob, 10, 4); ctx.fillRect(it.x - 2, it.y - 5 + bob, 4, 10);
    } else if (it.kind === "melee") {
      ctx.strokeStyle = "#a8b0b8"; ctx.lineWidth = 4;
      ctx.beginPath(); ctx.moveTo(it.x - 8, it.y + 8 + bob); ctx.lineTo(it.x + 8, it.y - 8 + bob); ctx.stroke();
      ctx.fillStyle = "#a8b0b8"; ctx.beginPath(); ctx.arc(it.x + 8, it.y - 8 + bob, 4, 0, 7); ctx.fill();
    } else if (it.kind === "fuel") {
      ctx.fillStyle = "#b03a2e"; ctx.fillRect(it.x - 8, it.y - 9 + bob, 16, 18);
      ctx.fillStyle = "#7a2820"; ctx.fillRect(it.x - 8, it.y - 9 + bob, 16, 5);
      ctx.fillStyle = "#e8e4da"; ctx.fillRect(it.x - 4, it.y - 2 + bob, 8, 7);
    }
  });
  // exit glow
  if (r.exitPos) {
    const ex = r.exitPos.x * TILE, ey = r.exitPos.y * TILE;
    if (r.exitOpen) {
      const pulse = 0.5 + Math.sin(animT * 5) * 0.25;
      ctx.fillStyle = `rgba(120, 200, 130, ${0.25 * pulse + 0.1})`;
      ctx.fillRect(ex - 6, ey - 6, TILE + 12, TILE + 12);
      ctx.strokeStyle = `rgba(150, 230, 160, ${pulse})`;
      ctx.lineWidth = 2;
      ctx.strokeRect(ex + 3, ey + 3, TILE - 6, TILE - 6);
    }
  }
  // the girl
  if (r.girl) drawGirl(r.girl);
  // npcs
  r.npcs.forEach((n) => { if (!n.gone) drawPerson(n.x, n.y, n.color, n.name); });
  // zombies
  r.zombies.forEach(drawZombie);
  // player
  drawPlayer(p);
  // fx
  r.fx.forEach((f) => {
    if (f.type === "tracer") {
      ctx.strokeStyle = "rgba(255, 230, 160, 0.9)"; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(f.x1, f.y1); ctx.lineTo(f.x2, f.y2); ctx.stroke();
    } else if (f.type === "flash") {
      ctx.fillStyle = "rgba(255, 240, 180, 0.9)";
      ctx.beginPath(); ctx.arc(f.x, f.y, 7, 0, 7); ctx.fill();
    } else if (f.type === "swing") {
      ctx.strokeStyle = `rgba(220, 220, 220, ${f.ttl / 0.12 * 0.7})`;
      ctx.lineWidth = 3;
      ctx.beginPath(); ctx.arc(f.x, f.y, f.range - 8, f.a - 0.8, f.a + 0.8); ctx.stroke();
    }
  });
  ctx.restore();

  // darkness / night
  const darkness = r.night ? 0.62 : r.dark;
  if (darkness > 0.01) {
    dctx.clearRect(0, 0, VIEW_W, VIEW_H);
    dctx.fillStyle = `rgba(4, 5, 14, ${darkness})`;
    dctx.fillRect(0, 0, VIEW_W, VIEW_H);
    dctx.globalCompositeOperation = "destination-out";
    const cut = (wx, wy, rad, strength) => {
      const sx = wx - camera.x, sy = wy - camera.y;
      const g = dctx.createRadialGradient(sx, sy, 10, sx, sy, rad);
      g.addColorStop(0, `rgba(0,0,0,${strength})`);
      g.addColorStop(1, "rgba(0,0,0,0)");
      dctx.fillStyle = g;
      dctx.beginPath(); dctx.arc(sx, sy, rad, 0, 7); dctx.fill();
    };
    cut(p.x, p.y, 185, 0.95);
    if (r.firePos && r.night) cut(r.firePos.x, r.firePos.y, 230 + Math.sin(animT * 9) * 12, 0.98);
    dctx.globalCompositeOperation = "source-over";
    ctx.drawImage(darkCv, 0, 0);
  }
  // hurt vignette
  if (p.flash > 0) {
    ctx.fillStyle = `rgba(160, 20, 10, ${p.flash * 0.9})`;
    ctx.fillRect(0, 0, VIEW_W, VIEW_H);
  }
}

function drawTile(tx, ty, c) {
  const x = tx * TILE, y = ty * TILE;
  const base = {
    ".": "#2b292d", ",": "#2e3a29", "-": "#232327", "_": "#3a3a3e",
    "~": "#2b292d", "c": "#232327", "x": null, "T": "#2e3a29", "f": "#2e3a29",
    "U": "#2e3a29", "d": null, "D": "#3a3a3e", "#": "#141318",
  }[c];
  // floor under decorations
  const under = { c: "#232327", x: G.run.def.key === "camp" ? "#2e3a29" : "#232327", d: "#141318" };
  ctx.fillStyle = base || under[c] || "#2b292d";
  ctx.fillRect(x, y, TILE, TILE);
  const h = hash2(tx, ty);
  if (c === ",") {
    ctx.fillStyle = "rgba(60, 90, 50, 0.5)";
    if (h > 0.4) ctx.fillRect(x + h * 28, y + (h * 53) % 30, 3, 3);
    if (h > 0.7) ctx.fillRect(x + (h * 91) % 32, y + h * 22, 2, 4);
  } else if (c === "." ) {
    ctx.strokeStyle = "rgba(0,0,0,0.18)"; ctx.lineWidth = 1;
    ctx.strokeRect(x + 0.5, y + 0.5, TILE, TILE);
  } else if (c === "-") {
    if (h > 0.85) { ctx.fillStyle = "rgba(200,190,120,0.25)"; ctx.fillRect(x + 16, y + 18, 10, 3); }
  } else if (c === "~") {
    ctx.fillStyle = "rgba(90, 18, 14, 0.75)";
    ctx.beginPath(); ctx.ellipse(x + 20, y + 20, 14 + h * 6, 9 + h * 5, h * 3, 0, 7); ctx.fill();
    ctx.beginPath(); ctx.ellipse(x + 8 + h * 20, y + 30, 5, 3, 0, 0, 7); ctx.fill();
  } else if (c === "#") {
    ctx.fillStyle = "#26242c";
    ctx.fillRect(x, y, TILE, 5);
    ctx.fillStyle = "rgba(0,0,0,0.35)";
    ctx.fillRect(x, y + TILE - 4, TILE, 4);
  } else if (c === "c") {
    const col = ["#5a3a3a", "#3a4a5a", "#54545a", "#4a5a42", "#5a523a"][Math.floor(h * 5)];
    ctx.fillStyle = col;
    ctx.fillRect(x + 2, y + 6, TILE - 4, TILE - 12);
    ctx.fillStyle = "rgba(20, 26, 34, 0.85)";
    ctx.fillRect(x + 7, y + 10, TILE - 14, TILE - 20);
    ctx.fillStyle = "rgba(0,0,0,0.3)";
    ctx.fillRect(x + 2, y + TILE - 8, TILE - 4, 3);
  } else if (c === "x") {
    if (G.run.def.key === "camp") {
      ctx.fillStyle = ["#6a5a40", "#4a5a5f", "#5f4a52"][Math.floor(h * 3)];
      ctx.beginPath();
      ctx.moveTo(x + 20, y + 4); ctx.lineTo(x + 38, y + 34); ctx.lineTo(x + 2, y + 34); ctx.closePath(); ctx.fill();
      ctx.fillStyle = "rgba(0,0,0,0.4)";
      ctx.beginPath(); ctx.moveTo(x + 20, y + 12); ctx.lineTo(x + 27, y + 34); ctx.lineTo(x + 13, y + 34); ctx.closePath(); ctx.fill();
    } else {
      ctx.fillStyle = "#4a463f";
      ctx.beginPath(); ctx.arc(x + 14, y + 22, 8, 0, 7); ctx.fill();
      ctx.beginPath(); ctx.arc(x + 27, y + 16, 7, 0, 7); ctx.fill();
      ctx.beginPath(); ctx.arc(x + 24, y + 29, 6, 0, 7); ctx.fill();
    }
  } else if (c === "T") {
    ctx.fillStyle = "#4a3826";
    ctx.fillRect(x + 16, y + 16, 8, 10);
    ctx.fillStyle = "rgba(30, 52, 26, 0.95)";
    ctx.beginPath(); ctx.arc(x + 20, y + 16, 17, 0, 7); ctx.fill();
    ctx.fillStyle = "rgba(44, 70, 36, 0.8)";
    ctx.beginPath(); ctx.arc(x + 14, y + 12, 9, 0, 7); ctx.fill();
  } else if (c === "f") {
    const fl = Math.sin(animT * 11 + 1) * 3;
    ctx.fillStyle = "#3a3026";
    ctx.fillRect(x + 6, y + 24, 28, 6);
    ctx.fillStyle = "#e08a2e";
    ctx.beginPath(); ctx.arc(x + 20, y + 18, 8 + fl * 0.5, 0, 7); ctx.fill();
    ctx.fillStyle = "#f0c060";
    ctx.beginPath(); ctx.arc(x + 20, y + 16, 4 + fl * 0.3, 0, 7); ctx.fill();
  } else if (c === "U") {
    ctx.fillStyle = "#5a4a32";
    ctx.fillRect(x - 12, y + 4, TILE + 24, TILE - 8);
    ctx.fillStyle = "rgba(24, 30, 38, 0.9)";
    ctx.fillRect(x + 4, y + 8, 18, TILE - 16);
    ctx.fillStyle = "#3f3423";
    ctx.fillRect(x - 12, y + 4, 12, TILE - 8);
  } else if (c === "d") {
    ctx.fillStyle = "#6a2a24";
    ctx.fillRect(x + 3, y + 2, TILE - 6, TILE - 4);
    ctx.fillStyle = "#c8a23c";
    ctx.fillRect(x + TILE - 12, y + TILE / 2 - 2, 4, 4);
  } else if (c === "D" && !(G.run && G.run.exitOpen)) {
    ctx.fillStyle = "#2a2a30";
    ctx.fillRect(x + 3, y + 3, TILE - 6, TILE - 6);
  }
}

function drawPerson(x, y, color, label) {
  ctx.fillStyle = "rgba(0,0,0,0.35)";
  ctx.beginPath(); ctx.ellipse(x, y + 9, 11, 5, 0, 0, 7); ctx.fill();
  ctx.fillStyle = color;
  ctx.beginPath(); ctx.arc(x, y, 12, 0, 7); ctx.fill();
  ctx.fillStyle = "#d8b090";
  ctx.beginPath(); ctx.arc(x, y - 3, 6, 0, 7); ctx.fill();
  if (label && G.player && dist(x, y, G.player.x, G.player.y) < 110) {
    ctx.font = "11px monospace";
    ctx.textAlign = "center";
    ctx.fillStyle = "rgba(0,0,0,0.6)";
    ctx.fillText(label, x + 1, y - 19);
    ctx.fillStyle = color;
    ctx.fillText(label, x, y - 20);
  }
}
function drawPlayer(p) {
  ctx.fillStyle = "rgba(0,0,0,0.35)";
  ctx.beginPath(); ctx.ellipse(p.x, p.y + 10, 12, 5, 0, 0, 7); ctx.fill();
  if (p.invuln > 0 && Math.floor(animT * 18) % 2 === 0) ctx.globalAlpha = 0.5;
  ctx.fillStyle = "#5f4a36";
  ctx.beginPath(); ctx.arc(p.x, p.y, 13, 0, 7); ctx.fill();
  // weapon direction
  const per = G.persist;
  const l = Math.hypot(p.dx, p.dy) || 1, ux = p.dx / l, uy = p.dy / l;
  if (per.weapon === "gun" && per.hasRevolver) {
    ctx.strokeStyle = "#1c1c20"; ctx.lineWidth = 4;
    ctx.beginPath(); ctx.moveTo(p.x + ux * 8, p.y + uy * 8); ctx.lineTo(p.x + ux * 20, p.y + uy * 20); ctx.stroke();
  } else {
    ctx.strokeStyle = "#a8b0b8"; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.moveTo(p.x + ux * 6, p.y + uy * 6); ctx.lineTo(p.x + ux * 18, p.y + uy * 18); ctx.stroke();
  }
  // head + hat
  ctx.fillStyle = "#d8b090";
  ctx.beginPath(); ctx.arc(p.x, p.y - 3, 7, 0, 7); ctx.fill();
  ctx.fillStyle = "#8a6c3c";
  ctx.beginPath(); ctx.arc(p.x, p.y - 4, 9, 0, 7); ctx.fill();
  ctx.fillStyle = "#6f5730";
  ctx.beginPath(); ctx.arc(p.x, p.y - 4, 5, 0, 7); ctx.fill();
  ctx.globalAlpha = 1;
}
function drawZombie(z) {
  ctx.fillStyle = "rgba(0,0,0,0.3)";
  ctx.beginPath(); ctx.ellipse(z.x, z.y + 9, 11, 5, 0, 0, 7); ctx.fill();
  const sway = Math.sin(animT * 6 + z.x * 0.1) * 3;
  ctx.fillStyle = z.hitFlash > 0 ? "#9a4a42" : "#55664e";
  ctx.beginPath(); ctx.arc(z.x, z.y, 12, 0, 7); ctx.fill();
  // arms out
  const a = z.state === "chase" && G.player ? Math.atan2(G.player.y - z.y, G.player.x - z.x) : z.dir;
  ctx.fillStyle = "#48573f";
  ctx.beginPath(); ctx.arc(z.x + Math.cos(a - 0.5) * 13, z.y + Math.sin(a - 0.5) * 13 + sway * 0.3, 4, 0, 7); ctx.fill();
  ctx.beginPath(); ctx.arc(z.x + Math.cos(a + 0.5) * 13, z.y + Math.sin(a + 0.5) * 13 - sway * 0.3, 4, 0, 7); ctx.fill();
  ctx.fillStyle = "#7c8a6a";
  ctx.beginPath(); ctx.arc(z.x + sway * 0.4, z.y - 3, 6, 0, 7); ctx.fill();
  ctx.fillStyle = "#b03a2e";
  ctx.fillRect(z.x - 3 + sway * 0.4, z.y - 5, 2, 2);
  ctx.fillRect(z.x + 2 + sway * 0.4, z.y - 5, 2, 2);
}
function drawGirl(g) {
  ctx.fillStyle = "rgba(0,0,0,0.3)";
  ctx.beginPath(); ctx.ellipse(g.x, g.y + 7, 8, 4, 0, 0, 7); ctx.fill();
  ctx.fillStyle = "#b8b0a8";
  ctx.beginPath(); ctx.arc(g.x, g.y, 8, 0, 7); ctx.fill();
  ctx.fillStyle = "#a09488";
  ctx.beginPath(); ctx.arc(g.x, g.y - 2, 5, 0, 7); ctx.fill();
  // the rabbit
  ctx.fillStyle = "#cfc4b4";
  ctx.fillRect(g.x + 7, g.y + 2, 5, 7);
  ctx.fillRect(g.x + 8, g.y - 2, 1, 4);
  ctx.fillRect(g.x + 10, g.y - 2, 1, 4);
}

/* ----------------------------------------------------------------- input */
window.addEventListener("keydown", (e) => {
  if (["Space", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(e.code)) e.preventDefault();
  if (e.repeat) return;
  keys[e.code] = true;
  ensureAudio();

  if (mode === "dialogue") {
    if (dlg.choosing) {
      const n = parseInt(e.key, 10);
      if (n >= 1 && n <= dlg.opts.length) pickChoice(n - 1);
      return;
    }
    if (["KeyE", "Space", "Enter"].includes(e.code)) advanceDialogue();
    return;
  }
  if (mode === "card") {
    if (e.code === "Enter" || e.code === "Space") { const b = $id("btn-begin"); if (b) b.click(); }
    return;
  }
  if (mode === "title" || mode === "gameover" || mode === "ending") {
    if (e.code === "Enter") {
      const b = $id("btn-new") || $id("btn-retry") || $id("btn-again");
      if (b) b.click();
    }
    return;
  }
  if (mode !== "play") return;

  if (e.code === "Space") attack();
  else if (e.code === "KeyE") {
    const t = findInteract();
    if (t) t.act();
  } else if (e.code === "KeyH") useBandage();
  else if (e.code === "Digit1") { G.persist.weapon = "melee"; updateHUD(); }
  else if (e.code === "Digit2") {
    if (G.persist.hasRevolver) { G.persist.weapon = "gun"; updateHUD(); }
    else toast("You don't have a gun. Yet.");
  }
});
window.addEventListener("keyup", (e) => { keys[e.code] = false; });
window.addEventListener("blur", () => { for (const k in keys) keys[k] = false; });

/* ------------------------------------------------------------------ loop */
let lastT = performance.now();
function frame(now) {
  const dt = clamp((now - lastT) / 1000, 0, 0.05);
  lastT = now;
  animT += dt;
  try {
    update(dt);
    draw();
  } catch (err) {
    console.error("[wandering-dead]", err);
  }
  requestAnimationFrame(frame);
}

/* ------------------------------------------------------------------ boot */
G = newGame();
showTitle();
requestAnimationFrame(frame);

/* debug / test hooks */
window.WD = {
  get G() { return G; },
  get mode() { return mode; },
  startChapter: (i) => { G = newGame(); startChapter(i); },
  begin: () => { const b = $id("btn-begin"); if (b) b.click(); },
  advance: () => advanceDialogue(),
  choose: (i) => pickChoice(i),
  choosing: () => dlg.choosing,
  inDialogue: () => mode === "dialogue",
};
