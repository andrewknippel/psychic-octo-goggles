/* The Wandering Dead — chapter maps & metadata.
 *
 * Tile legend:
 *   #  wall / building        .  indoor floor        ,  grass
 *   -  asphalt road           _  sidewalk / concrete ~  bloodstained floor
 *   c  wrecked car (solid)    x  debris / tent (solid)
 *   T  tree (solid)           f  campfire (solid)    U  pickup truck (solid)
 *   d  closed door (solid until opened by story)     D  chapter exit
 *
 * Entity letters (per-chapter `spawn` table):
 *   P player   Z shambler   A ammo   B bandage   M melee weapon   J jerrycan
 *   G the girl at the pumps   N Morris   n Dante   Y Ben   X Earl
 *   L Laura    C Cody        V Zane
 */

const WD_CHAPTERS = [
  // ------------------------------------------------------------------
  // Chapter 1 — Linden Memorial Hospital
  // ------------------------------------------------------------------
  {
    key: "wake",
    name: "CHAPTER ONE",
    title: "Wake",
    floor: ".",
    dark: 0.82,
    intro: [
      "Linden County, Georgia.",
      "",
      "You remember the traffic stop. The muzzle flash from the truck bed.",
      "Zane screaming your name over the radio.",
      "",
      "Then a hospital ceiling, and a long, dreamless dark.",
      "",
      "The clock on the wall has stopped. The flowers on the sill are",
      "stalks in black water. Nobody has changed your dressing in weeks.",
      "",
      "And the hospital is quiet in a way hospitals never are.",
    ].join("\n"),
    objective: "Find a way out of Linden Memorial.",
    map: [
      "####################################",
      "#.....#....#....#....#.............#",
      "#..P..#....#....#.B..#......Z......#",
      "#.....#....#....#....#.............#",
      "###.#####.###.####.#####.####.######",
      "#..................................#",
      "#...M....Z.......~~................#",
      "#..................................#",
      "########.####dd#########.###########",
      "#....#.......##.......#............#",
      "#.B..#..~~...##...A...#............#",
      "#....#.......##.......#....Z.......#",
      "###.##.......##.......##########.###",
      "#.Z................................#",
      "#.....~~...........Z...............#",
      "#..................................#",
      "#..####....####....####............#",
      "#..#..#....#..#....#..#............#",
      "#..#..#..Z.#..#..B.#..#............#",
      "#..................................#",
      "#...Z...............Z............D.#",
      "####################################",
    ],
    spawn: {},
  },

  // ------------------------------------------------------------------
  // Chapter 2 — Juniper Street (Morris & Dante)
  // ------------------------------------------------------------------
  {
    key: "neighbors",
    name: "CHAPTER TWO",
    title: "The Family Next Door",
    floor: ",",
    dark: 0.0,
    intro: [
      "You made it three blocks from the hospital before your legs quit.",
      "",
      "You woke a second time on a lawn on Juniper Street, wrapped in a",
      "quilt that isn't yours, with a boy watching you from a porch and",
      "a man standing over you with a shovel he clearly hoped not to use.",
    ].join("\n"),
    objective: "Talk to the man on the porch.",
    map: [
      "####################################",
      "#......#.......#,,,,,,T,,,,,,,,,,,T#",
      "#..N...#...B...#,,,,,,,,,,,,,,,,,,,#",
      "#..n...#.......#,,T,,,,,,,,,,,,,,,,#",
      "###.#######.####,,,,,,,,,,,,,,,,,,,#",
      "#,,,,,,,,,,,,,,,,,,,,P,,,,,,,,,,,,,#",
      "#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,#",
      "#,T,,,,,,,,,,,,,,,,,,,,,,,,,,,T,,,,#",
      "#__________________________________#",
      "#----------------------------------#",
      "#---c----------c--------c----------#",
      "#----------------------------------#",
      "#------c---------Z--------c--------#",
      "#----------------------------------#",
      "#__________________________________#",
      "#,,,,,T,,,,,,,,,,,,,,,,,,,,,,,,,,,,#",
      "#,,,,,,,,,,Z,,,,,,,,,,,,,,,,,,,,,,,#",
      "#,,T,,,,,,,,,,,,,,,,,,,,,,T,,,,,,,,#",
      "#,,,,,,,,,,,,,,,,,,,,,A,,,,,,,,,,,,#",
      "#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,D,#",
      "#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,#",
      "####################################",
    ],
    spawn: {
      N: { type: "npc", id: "morris", name: "Morris", color: "#7fb2e5" },
      n: { type: "npc", id: "dante", name: "Dante", color: "#a5d8ff" },
    },
  },

  // ------------------------------------------------------------------
  // Chapter 3 — Route 9 / Two Pines Fuel
  // ------------------------------------------------------------------
  {
    key: "road",
    name: "CHAPTER THREE",
    title: "The Long Road",
    floor: ",",
    dark: 0.0,
    intro: [
      "Route 9 runs east through pine country, past the water tower,",
      "all the way to Ashton. Sixty miles of it.",
      "",
      "Every car out of the city sits dead on the westbound side, doors",
      "hanging open like something interrupted everyone at once.",
      "",
      "At the Two Pines Fuel stop, an old pickup faces east with its",
      "keys in the visor. All it needs is gas. All you need is the truck.",
    ].join("\n"),
    objective: "Find fuel for the pickup truck.",
    map: [
      "######################################",
      "#,,,,,,,,T,,,,,,,,,,#########,,,,,,,,#",
      "#,,T,,,,,,,,,,,,,,,,#...J...#,,,,,,,,#",
      "#,,,,,,,,,,,,,,,,,,,#.......#,,T,,,,,#",
      "#,,,,,,,,,,,,,,,,,,,####.####,,,,,,,,#",
      "#,,,,,,,,,,,,,,,,,,,,,Z,,,,,,,,,,,,,,#",
      "#________,,,,,,,,,,,,x,,G,,x,,,,,,,,,#",
      "#------------------------------------#",
      "#--c---c-----Z------c----------Z-----#",
      "#------------------------------------#",
      "#---Z-----c------Z---------c---------#",
      "#------------------------------------#",
      "#-c-----------c----------Z------c----#",
      "#------------------------------------#",
      "#____________________________________#",
      "#,,,,,,,,,,,,,,,B,,,,,,,,,,,,,,,,,,,,#",
      "#,,U,,,,,,,,,,,,T,,,,,,,,,,Z,,,,,,,,,#",
      "#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,#",
      "#,,,P,,,,,,,,,,,,,,,,,,,A,,,,,,,,,,,,#",
      "#,T,,,,,,,,,,,,,,,,,,,,,,,,T,,,,,,,,,#",
      "#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,#",
      "######################################",
    ],
    spawn: {
      G: { type: "girl" },
    },
  },

  // ------------------------------------------------------------------
  // Chapter 4 — Ashton, Mercer Street
  // ------------------------------------------------------------------
  {
    key: "city",
    name: "CHAPTER FOUR",
    title: "Ashton",
    floor: "-",
    dark: 0.15,
    intro: [
      "The truck dies eight blocks out, and you walk into Ashton the way",
      "you'd walk into a church you knew had burned down.",
      "",
      "The refugee center is ash. The Army checkpoints are sandbags and",
      "spent brass and nobody. And the dead own Mercer Street now —",
      "hundreds of them, drifting like litter in a slow wind.",
      "",
      "You go anyway. Laura and Cody came here. Somebody knows something.",
    ].join("\n"),
    objective: "Search Mercer Street for survivors.",
    map: [
      "#####################################",
      "#________________________############",
      "#--------------------------#........#",
      "#---Z--------c--------Z----#..B.....#",
      "#--------------------------#........#",
      "#-----c----------Z---------#........#",
      "#-------------------------_d....Y...#",
      "#---Z--------x-------------#........#",
      "#--------------------------#......X.#",
      "#-----------c------Z-------#........#",
      "#--Z-----------------------#...A....#",
      "#--------------------------####.#####",
      "#-------x------Z-----------#....#---#",
      "#--------------------------#..D.#---#",
      "#____________P_____________######---#",
      "#,,T,,,,,,,,,,,,,,,,,,,,,,,,,,,,,---#",
      "#,,,,,,,,,,,,,,,,,,,,,,,T,,,,,,,,---#",
      "#,,,,,B,,,,,,,,,,,,,,,,,,,,,,,,,,---#",
      "#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,---#",
      "#####################################",
    ],
    spawn: {
      Y: { type: "npc", id: "ben", name: "Ben", color: "#8ee59a" },
      X: { type: "npc", id: "earl", name: "Earl", color: "#e58a5a" },
    },
  },

  // ------------------------------------------------------------------
  // Chapter 5 — The Camp by the Quarry
  // ------------------------------------------------------------------
  {
    key: "camp",
    name: "CHAPTER FIVE",
    title: "The Camp by the Quarry",
    floor: ",",
    dark: 0.0,
    intro: [
      "Ben leads you up the ridge road as the sun drops, talking the",
      "whole way so you won't have to.",
      "",
      "Then the trees open up, and there's the quarry lake going copper",
      "in the light, and tents, and woodsmoke, and people — living",
      "people, arguing about laundry.",
      "",
      "And a boy in a sheriff's ball cap looks up from the fire.",
    ].join("\n"),
    objective: "Go to your family.",
    map: [
      "##################################",
      "#,,T,,,T,,,,,,D,,,,,,,T,,,,T,,,,,#",
      "#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,#",
      "#,T,,,,,,,,,,,,,,,,,,,,,,,,,,,T,,#",
      "#,,,,,x,,,,,,,,,,,,,,,,,x,,,,,,,,#",
      "#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,#",
      "#,,,,,,,,,x,,,,,,,,,,x,,,,,,,,,,,#",
      "#,T,,,,,,,,,,,,,,,,,,,,,,,,,,,,T,#",
      "#,,,,,,,,,,,,,L,,,,,,,,,,,,,,,,,,#",
      "#,,,,,,,,,,,,,,f,,C,,,,,,,,,,,,,,#",
      "#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,#",
      "#,,,,,,,,,,,V,,,,,,,,,,,,,,,,,,,,#",
      "#,,x,,,,,,,,,,,,,,,,,,,,,,,x,,,,,#",
      "#,,,,,,,,,,,,,,,,P,,,,,,,,,,,,,,,#",
      "#,T,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,#",
      "#,,,,,,,,,,,,,,,,Y,,,,,,,,,,,T,,,#",
      "#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,#",
      "#,,T,,,,T,,,,,,,,,,,,,T,,,,,,,,,,#",
      "#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,#",
      "##################################",
    ],
    spawn: {
      L: { type: "npc", id: "laura", name: "Laura", color: "#e5a5c8" },
      C: { type: "npc", id: "cody", name: "Cody", color: "#9ad8e5" },
      V: { type: "npc", id: "zane", name: "Zane", color: "#c46a6a" },
      Y: { type: "npc", id: "ben", name: "Ben", color: "#8ee59a" },
    },
  },

  // ------------------------------------------------------------------
  // Chapter 6 — The ARC Perimeter
  // ------------------------------------------------------------------
  {
    key: "arc",
    name: "CHAPTER SIX",
    title: "Ashes",
    floor: ",",
    dark: 0.55,
    intro: [
      "The radio loop is nine words long, on repeat, in a tired woman's",
      "voice: 'ARC Research Station. Perimeter power holding. Survivors",
      "welcome.'",
      "",
      "The camp votes to go. Zane votes with his jaw shut.",
      "",
      "A mile from the gate the caravan stops for a fallen pine, and",
      "when you look for Zane, he's already walked ahead into the dark.",
      "Alone. His holster unsnapped.",
    ].join("\n"),
    objective: "Follow Zane up the road.",
    map: [
      "##############################",
      "#,,,T,,,,,,,,D,,,,,,,,,T,,,,,#",
      "#,,,,,,,,,__________,,,,,,,,,#",
      "#,T,,,,,,,_--------_,,,,,,T,,#",
      "#,,,,,,,,,_--------_,,,,,,,,,#",
      "#,,,,T,,,,_---V----_,,,,,,,,,#",
      "#,,,,,,,,,_--------_,,,T,,,,,#",
      "#,,T,,,,,,_--------_,,,,,,,,,#",
      "#,,,,,,,,,_---Z----_,,,,,,,,,#",
      "#,,,,,,,,,_--------_,,T,,,,,,#",
      "#,T,,,,,,,_--------_,,,,,,,,,#",
      "#,,,,,,,,,_-Z------_,,,,,,,,,#",
      "#,,,,T,,,,_--------_,,,,T,,,,#",
      "#,,,,,,,,,_--------_,,,,,,,,,#",
      "#,,,,,,,,,_---P----_,,,,,,,,,#",
      "#,,,T,,,,,_--------_,,T,,,,,,#",
      "#,,,,,,,,,,,,,,,,,,,,,,,,,,,,#",
      "##############################",
    ],
    spawn: {
      V: { type: "npc", id: "zane", name: "Zane", color: "#c46a6a" },
    },
  },
];

if (typeof module !== "undefined") module.exports = { WD_CHAPTERS };
