# Stock Scanner: Rebound Candidates + Same-Day Movers + Momentum

Compiles news headlines, Reddit posts, and StockTwits messages for a set of
tickers and blends that with price/volume technicals. **Default output has
two sections:**

1. **REBOUND CANDIDATES** -- tickers with a low RSI that just dipped
   sharply but show early signs of stabilizing, framed around a "days to
   ~4 weeks" horizon.
2. **SAME-DAY MOMENTUM MOVERS** -- tickers up sharply *today* on unusually
   high volume. This is a distinct, separately-computed signal from #1 --
   see "Known limitations" for why it's explicitly not a same-day
   round-trip prediction.

Pass `--show-momentum` for a third, optional view: the original 2-7 day
momentum-ranked table (tickers already trending *up*, multi-day hold).

> **Not investment advice.** All three are automated heuristic screens --
> a low RSI after a big drop is not a guarantee of a bounce (it can keep
> falling, a "falling knife"), a big move on volume today doesn't predict
> where the rest of the day goes, and high-buzz momentum names carry
> elevated reversal risk. Always do your own due diligence before trading
> anything any of them surfaces.

## How it works

```
                 ┌──────────────┐
watchlist  ─────▶│              │
StockTwits ─────▶│   ticker     │──▶ candidate universe (tickers)
 trending        │  discovery   │
Reddit $cashtags▶│              │
                 └──────────────┘
                         │
                         ▼
        ┌────────────────────────────────┐
        │   per-ticker data collection    │
        │  news · Reddit · StockTwits ·   │
        │  price/volume history · earnings│
        └────────────────────────────────┘
                         │
              ┌──────────┼──────────────┐
              ▼          ▼              ▼
     ┌────────────┐ ┌────────────┐ ┌─────────────────┐
     │ dip/rebound│ │ same-day   │ │ momentum scoring │
     │ scan: low  │ │ mover scan:│ │ sentiment ·      │
     │ RSI + just │ │ big move + │ │ momentum · buzz ·│
     │ dipped +   │ │ volume     │ │ technical        │
     │ sentiment  │ │ surge      │ │ (--show-momentum)│
     │ not bearish│ │ today      │ │                  │
     └────────────┘ └────────────┘ └─────────────────┘
              │          │              │
              ▼          ▼              ▼
     REBOUND        SAME-DAY        ranked top-N
     CANDIDATES     MOMENTUM        (opt-in)
     (default)      MOVERS
                     (default)
```

### 1. Ticker discovery (`src/ticker_discovery.py`)

The candidate universe is the union of:
- Your `--watchlist` (always included).
- StockTwits' own trending-symbols feed.
- `$CASHTAG` mentions scraped out of hot posts across 6 configured
  subreddits (`wallstreetbets`, `stocks`, `StockMarket`, `investing`,
  `options`, `Daytrading` by default -- `src/data_sources/reddit.py:extract_cashtags`),
  filtered against a blocklist of trading jargon that looks like a ticker
  (`$OTM`, `$YOLO`, etc).

The auto-discovered portion is capped at `--max-candidates` (default 15,
`MAX_DISCOVERY_CANDIDATES` in `config.py`) on top of whatever's in
`--watchlist`. Raising it considers more tickers per scan at the cost of a
longer scan (~5 sequential network calls per ticker) and more exposure to
the free-tier rate limits described below -- if a scan starts
taking longer than `--interval`, raise `--interval` to match.

### 2. Data collection (`src/data_sources/`)

| Source | Module | Auth |
|---|---|---|
| News | `news.py` | NewsAPI if `NEWSAPI_KEY` is set, else free Yahoo Finance RSS |
| Reddit | `reddit.py` | None -- public read-only JSON endpoints |
| StockTwits | `stocktwits.py` | None -- public REST API |
| Price/volume + earnings date | `market_data.py` | None -- `yfinance` |

Every fetch is wrapped in a try/except that logs a warning and returns an
empty result on failure, so one flaky source never crashes the run --
tickers just get scored on whatever data did come through (and get
excluded entirely if that's not enough, see minimum thresholds below).

StockTwits messages carry an author-supplied **Bullish/Bearish** tag, which
is trusted over text-inferred sentiment when present -- it's a direct
statement of intent rather than an inference from wording.

Reddit's free JSON endpoints are sensitive to request volume/pattern --
firing one request per subreddit per ticker in a tight loop reliably
triggers `403 Blocked for url` responses, which looks like your network is
blocking it but is actually Reddit's own bot detection. Every Reddit call
uses a single combined multi-subreddit request (`r/sub1+sub2+.../...`)
instead of one per subreddit, plus a small delay before each call, to stay
well under that threshold. Yahoo's RSS feed gets the same small-delay
treatment for the same reason (`429 Too Many Requests` past a few dozen
tickers). Neither is a guarantee, though -- **the more tickers you scan
per run (`--max-candidates`), the more you'll run into these free-tier
limits**; there's no delay tuning that fully eliminates that trade-off.
Two ways to push it back:
- Get a free [NewsAPI](https://newsapi.org) key and set `NEWSAPI_KEY` --
  this replaces the Yahoo RSS path (and its rate limit) entirely, though
  NewsAPI's own free tier caps out at 100 requests/day, so it can run dry
  partway through a day of frequent large scans too.
- Turn `--max-candidates` back down, or raise `--interval` so the same
  ticket volume is spread over more wall-clock time.

None of this stops the tool from working -- a blocked/rate-limited source
just contributes nothing for that ticker that cycle, and scoring proceeds
on whatever data did come through (StockTwits and price/volume history
tend to hold up best under volume, since StockTwits has generous limits
and yfinance calls a different, less sensitive Yahoo endpoint).

StockTwits' "trending" feed also mixes in crypto/forex symbols using a
`.X` suffix (e.g. `XRP.X`, `BTC.X`) -- those are filtered out during
discovery since this tool is stocks-only and `yfinance` has no price data
under that symbol format.

`yfinance`'s earnings-date lookup (`get_earnings_dates`) parses an HTML
table and requires the `lxml` package -- it's in `requirements.txt`; if
you installed dependencies before it was added, rerun
`pip install -r requirements.txt` to pick it up.

### 3. Scoring (`src/analysis/`)

For each ticker:

- **Sentiment score** (`sentiment.py`) -- recency- and engagement-weighted
  average sentiment (VADER on text, or the explicit StockTwits tag) across
  news and social mentions, mapped to 0-100. Recency uses exponential decay
  with a ~30 hour half-life, tuned so mentions older than ~4 days barely
  matter for a one-week trade.
- **Momentum score** (`technical.py`) -- blends 3-day return, 5-day return,
  and 5-day/10-day moving-average trend.
- **Buzz score** (`scoring.py`) -- blends trading-volume surge (vs. 20-day
  average) with total mention count (log-scaled), as a proxy for "getting
  more attention than usual right now."
- **Technical score** (`technical.py`) -- RSI(7) positioned for continuation
  (peaks around RSI 60; penalized near 30 or 80+) plus short-MA trend
  confirmation. This is what keeps a straight-up-only "TOPPY" ticker from
  auto-winning on hype alone -- see `tests/test_technical.py`.

These combine into a weighted composite (weights in `config.py`,
default 35% sentiment / 30% momentum / 20% buzz / 15% technical), then get
multiplied by a **confidence** factor that scales with `log(mention_count)`
-- a ticker with 2 mentions is down-weighted relative to one with 40, even
if their raw scores are similar, since a single hyperbolic post shouldn't be
enough to rocket an obscure ticker to #1.

Tickers are excluded entirely (not just scored low) if they fail minimum
liquidity/data thresholds in `config.py`: price below `MIN_PRICE` ($5 --
the standard "penny stock" line), 20-day average volume below
`MIN_AVG_VOLUME` (300k shares), or fewer than `MIN_MENTIONS` (3) combined
news+social mentions.

### 4. Risk flags (`scoring.py`)

These are annotations, not scoring inputs -- they never change a ticker's
rank, they just stop a high score from being mistaken for a low-risk one.
Each `ScoreBreakdown` carries a `risk_flags` list (also folded into
`rationale`) and a raw `volatility_pct`/`earnings_date`, flagged when:

- **Overbought / oversold** -- RSI(7) at or past `RISK_RSI_OVERBOUGHT` (75)
  or `RISK_RSI_OVERSOLD` (25).
- **High volatility** -- daily-return stdev over the trailing ~10 days at or
  above `RISK_VOLATILITY_PCT` (6%/day).
- **Extended move** -- 3-day return at or above `RISK_EXTENDED_MOVE_PCT`
  (15%), i.e. most of the expected move may already be behind it.
- **Earnings in N days** -- next earnings date (via `yfinance`) falls inside
  `RISK_EARNINGS_WINDOW_DAYS` (7) of today, meaning a binary, momentum-blind
  event could land during the hold.

### 5. Buy alerts (`src/analysis/buy_alerts.py`) -- the actionable short list

**This is the "buy the dip" feature.** A *buy alert* is the strict subset of
rebound candidates that meets **both** of the things at once:

- **Down at least `BUY_ALERT_DROP_PCT` (8%) over the past week** (5 trading
  days), and
- **A low RSI** -- RSI(7) at or below `BUY_ALERT_RSI_MAX` (32).

(The rebound-candidate list in the next section is looser: it fires on the
dip plus *either* a low RSI *or* a merely decelerating decline. A buy alert
requires the low RSI specifically, because that's the exact rule this app was
built around.) Both thresholds default to the rebound-scan values but can be
tuned independently via env vars -- e.g. set `BUY_ALERT_DROP_PCT=12` for a
stricter alert list while the rebound radar stays at 8%.

Buy alerts are ranked most-oversold (lowest RSI) first, printed in a **BUY
ALERTS** section in the terminal, and shown in the top panel of the web app
(below). Each one carries a **"Buy in Fidelity" deep link**
(`FIDELITY_TRADE_URL`) that opens Fidelity's equity order-entry ticket
pre-filled to *Buy* that symbol.

> #### Why it doesn't place the order for you
>
> **Fidelity has no official trading API** -- there is no sanctioned way for a
> third-party app to place orders in a personal Fidelity brokerage account.
> The only technical ways to do it are unofficial browser automation or
> reverse-engineered endpoints, which violate Fidelity's terms of service (and
> pointing that at *unattended, real-money* orders is a great way to lose money
> to a broken selector or a bad data feed). So this app deliberately keeps a
> human on the trigger: it finds the dips and hands you a pre-filled ticket;
> **you** log in, review, and submit. The app can never place a trade, move
> money, or withdraw funds -- it only ever opens a buy ticket for you to
> confirm. If you want *genuine* hands-off automation, that requires a broker
> with an official trading API (e.g. Alpaca, Interactive Brokers, Tradier) --
> ask and it can be added as a separate, opt-in execution backend.

The web app can also raise a **notification** when a *new* ticker becomes a
buy alert (see the "Alerts" note under Web dashboard). Like the terminal bell,
this fires while the app/tab is open; true push-when-closed would need a push
server.

### 6. Rebound candidates (`src/analysis/dip_scanner.py`) -- the default output

This is what prints by default: an independent scan for the *opposite*
setup from momentum-chasing -- tickers that dropped sharply but show early
signs of stabilizing. It reuses the same news/social/price data already
fetched for the main scan -- no extra API calls. A ticker qualifies when
**all** of:

- **5-day decline** at or past `DIP_DROP_PCT` (8%) -- the "just dipped"
  part.
- **At least one reversal sign**: RSI(7) oversold (`DIP_RSI_OVERSOLD`, 32)
  and/or the 3-day return is less negative than the 5-day return (the drop
  is decelerating) -- the "low RSI" / "chance of rebounding" part.
- **Sentiment hasn't turned bearish** -- at/above `DIP_MIN_SENTIMENT` (40).
  This is the key filter: a big drop *paired with* genuinely bearish
  news/social sentiment reads as a "falling knife" (real bad news, no
  reason to expect a bounce), not a dip-buy setup, and is excluded.

Qualifying tickers are ranked **most-oversold (lowest RSI) first** and
printed in a **REBOUND CANDIDATES** section, along with an **earnings
flag** if the next earnings date falls within `DIP_EARNINGS_WINDOW_DAYS`
(28 -- roughly the "~4 weeks" horizon this mode is framed around): a report
landing during that window is real, technical-setup-independent risk.

In the default live-tracking loop, a ticker *newly* becoming a rebound
candidate (not one still sitting there from last cycle) triggers a
terminal bell + banner -- that's what "notify" means here: an
on-screen/audible alert while the terminal is open and the loop is
running, not a push notification to your phone or email (that would need
a separate service/credentials -- ask if you want that added).

**This is a heuristic candidate list, not a bounce prediction, and "~4
weeks" is a framing, not a promise.** Nothing -- this tool included -- can
guarantee a stock rebounds, or that it does so by any particular deadline.
A stock that's down sharply can keep falling regardless of what RSI or
sentiment say. Treat every name here as "worth a closer look," not a buy
signal.

### 7. Same-day momentum movers (`src/analysis/day_movers.py`) -- also default output

The second default section: tickers up sharply *today* on unusually high
volume. Also reuses already-fetched price data, no extra API calls. A
ticker qualifies when **both** of:

- **Today's gain** at or above `DAY_MOVER_MIN_CHANGE_PCT` (3%).
- **Volume surge** at or above `DAY_MOVER_MIN_VOLUME_SURGE` (1.5x the
  20-day average) -- without this, a stock drifting up on ordinary volume
  isn't unusual, it's noise.

Ranked biggest same-day gain first, printed in a **SAME-DAY MOMENTUM
MOVERS** section.

**Read this part carefully.** This is *not* the same claim as the original
2-7 day momentum table, and it is *not* a same-day round-trip prediction.
Real same-day (intraday) trading signals need real-time, minute-by-minute
price/volume data and live order flow -- this tool only has **daily**
bars, refreshed at most every few minutes while live tracking polls. Two
consequences worth understanding:

- If run while the market is open, the "latest" daily bar is typically
  still-forming, so `change_1d_pct` reflects the move *so far* today, not
  a finished session -- it can (and will) change by the time you look
  again.
- This flags unusual **activity**, not **direction for the rest of the
  day**. A stock up 5% on 3x volume at 11am can close up 15% or back down
  to flat by 4pm; nothing here distinguishes those outcomes. Buying and
  selling the same day is high-risk speculation regardless of what this
  list says -- treat it as "worth watching," not a signal to act on.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # optional: add a NEWSAPI_KEY for richer news coverage
```

## Usage

**Live tracking is on by default** -- a plain run keeps rescanning every
10 minutes and reprinting the table until you press Ctrl+C. Pass `--once`
if you just want a single scan.

```bash
# Live: scan ~15 auto-discovered tickers for REBOUND CANDIDATES, every 10 min
python main.py

# Same idea, but always include these tickers in the scan too
python main.py --watchlist AAPL,TSLA,NVDA,GME

# Also show the original momentum-ranked (2-7 day, trending-up) table
python main.py --show-momentum --top 5

# Same, but every 20 min instead of the default 10 (5 min floor enforced)
python main.py --watchlist AAPL,TSLA,NVDA --interval 20

# Single scan, then exit -- no loop
python main.py --watchlist AAPL,TSLA,NVDA --once

# Only score the named tickers, skip trending discovery
python main.py --watchlist AAPL,MSFT --no-trending --once

# Cast a much wider net -- scan up to 60 auto-discovered tickers instead
# of the ~15 default (bump --interval too, since a bigger pool scans slower)
python main.py --max-candidates 60 --interval 20

# Save full results on every refresh (all scored tickers, not just top N;
# only meaningful with --show-momentum, since that's what --top limits)
python main.py --watchlist AAPL,TSLA --show-momentum --output output/results.json

# Demo/test the pipeline with bundled synthetic data (no network required)
python main.py --offline --once -v
```

## Web dashboard

A static browser dashboard (in `web/`) is the phone-and-computer app. Its top
panel is **buy alerts** (down ≥8% this week *and* low RSI, each with a one-tap
**Buy in Fidelity** button), followed by the broader **rebound candidates**
(low-RSI dips), **same-day movers**, and a **market-mover news feed** -- recent
coverage of what powerful business figures (CEOs, the Fed chair, high-profile
investors) said or did, since those remarks routinely move markets.

**Install it like an app.** It ships a web manifest and a service worker
(`web/sw.js`), so on a phone ("Add to Home Screen") or desktop Chrome/Edge
("Install") it runs full-screen with its own icon and works offline (the app
shell is cached; quotes in `data.json` are always fetched fresh).

**Alerts.** Tap **🔔 Enable alerts** in the header to grant notification
permission. When a *new* ticker becomes a buy alert on a refresh, the app fires
a notification whose click opens that ticker's Fidelity buy ticket. This works
while the app/tab is open (foreground); notifying you when it's fully closed
would need a push server with VAPID keys, which this static build intentionally
doesn't include. Seen tickers are remembered in `localStorage` so you aren't
re-alerted for the same name.

It's a plain static page with no backend. The scanner writes a single
`web/data.json`, and the page fetches (and re-fetches, every 60s) that file.
"Live" therefore means *as fresh as the last scan* -- so run the scanner in
its normal live loop pointed at that file, and it rewrites the JSON on every
refresh:

```bash
# Terminal 1 -- keep web/data.json fresh (rescans + rewrites every 10 min)
python main.py --web-out web/data.json

# ...or a single build without the loop:
python main.py --once --web-out web/data.json

# ...or a fully offline demo build (no network, synthetic data):
python main.py --offline --once --web-out web/data.json

# Terminal 2 -- serve the static page (any static server works)
python -m http.server 8000 --directory web
# then open http://localhost:8000
```

The `web/` directory is fully static, so it can also be hosted on anything
that serves files (GitHub Pages, S3, Netlify, etc.) as long as `data.json`
is regenerated and uploaded on whatever cadence you want -- e.g. a cron job
running the `--once --web-out` command.

The market-mover roster is configurable via the `INFLUENCER_FIGURES` env var
(`"Name|Role,Name|Role,..."`); see `config.py`. That feed is news coverage
of these figures pulled from a keyless RSS search, **not** a scrape of their
raw social accounts -- quoting an outlet that verified a remark is more
honest than republishing an unverified post, and the platforms those posts
live on (X especially) need authenticated API access this keyless tool
doesn't assume.

> Note: the live scan and the news feed reach out to third-party endpoints
> (Yahoo Finance, Reddit, StockTwits, and the news RSS search). In a sandbox
> or CI environment whose egress policy blocks those hosts, the live fetch
> returns nothing -- use `--offline` there, which builds the dashboard from
> the bundled synthetic dataset instead.

Live mode is polling, not a push feed -- it just reruns the same scan on a
timer and reprints the table, so you don't have to keep retyping the
command by hand. `--interval` has a 5-minute floor
(`MIN_WATCH_INTERVAL_MINUTES` in `config.py`) because the free/keyless
Reddit, StockTwits, and Yahoo endpoints this tool relies on will start
rate-limiting or blocking a client that polls them too aggressively.

Penny stocks are excluded entirely: `MIN_PRICE` defaults to **$5**, the
commonly-cited SEC/industry line for what counts as a penny stock. A
ticker below that price never appears in the ranked table or DIP WATCH,
regardless of how it scores otherwise. Lower it via `MIN_PRICE` in
`config.py`/`.env` if you actually want penny stocks included.

Sample output, default mode (deterministic -- the synthetic dataset uses a
fixed seed, so scores/RSI/volatility are stable run to run; only
`earnings_date` shifts with the current date):

```
========================================================================================
REBOUND CANDIDATES -- low RSI, just dipped, sentiment not panicking (~4wk horizon, not a prediction)
========================================================================================
1. DIPPY    $36.02      3d -7.1%  5d -10.6%  RSI 3  earnings 2026-07-25
   DIPPY -10.6% (5d) -- down -10.6% over 5 days; RSI oversold at 3; decline decelerating over the last 3 days; sentiment not panicking (80/100); earnings in 15d (2026-07-25) -- added event risk inside the rebound window

Reminder: these are oversold-bounce candidates, not predictions -- a sharp drop can keep falling (a "falling knife") instead of rebounding. Verify independently.

========================================================================================
SAME-DAY MOMENTUM MOVERS -- big move + unusual volume today (not a round-trip guarantee)
========================================================================================
1. TOPPY    $14.20      today +13.8%
   TOPPY +13.8% today -- volume 3.4x its 20-day average; RSI 100
2. MOMO     $24.95      today +3.8%
   MOMO +3.8% today -- volume 2.5x its 20-day average; RSI 98

Reminder: same-day (intraday) trading is high-risk speculation. This only flags unusual price+volume activity happening today -- it does NOT predict which way the rest of the day goes, and it is not built from real-time/intraday data, only the latest daily bar. Verify independently before trading on it.
```
(`BAGGY` dropped just as hard as `DIPPY` but does **not** show up in
REBOUND CANDIDATES -- its drop comes with bearish sentiment, i.e. a
falling knife, not a bounce setup. That exclusion is the whole point of
the sentiment filter. Note `TOPPY` and `MOMO` appear in SAME-DAY MOMENTUM
MOVERS purely because they're up big today on high volume -- that's a
completely separate signal from REBOUND CANDIDATES above it.)

Sample output with `--show-momentum` (adds the original 2-7 day,
trending-*up* table above the default two sections -- all three print):

```
Top short-term (2-7 day) momentum candidates as of 2026-07-09 05:50 UTC

QUICK PICKS (ticker, score out of 100):
1. TOPPY (54.5)   2. MOMO (53.5)   3. SLOW (24.7)   4. DIPPY (21.3)   5. BAGGY (13.8)

#  Ticker    Score   Sent    Mom   Buzz   Tech  Conf    Price     3d%   Vol%  Risk
------------------------------------------------------------------------------------
1  TOPPY      54.5   80.5  100.0   80.5   47.8  0.67    14.20  +45.3%    6.3     4
2  MOMO       53.5   87.9   92.7   74.9   42.2  0.67    24.95  +10.2%    1.5     1
3  SLOW       24.7   70.0   53.9   47.1   45.8  0.43    49.18   +0.7%    0.3     1
4  DIPPY      21.3   80.0   15.6   51.3    7.5  0.48    36.02   -7.1%    1.6     1
5  BAGGY      13.8   13.9   16.8   62.0    7.2  0.59    13.48   -6.8%    1.2     1

(Vol% = avg daily price swing over the last ~10 days; Risk = number of risk flags below, '-' = none)

1. TOPPY -- 100% bullish across 11 social mentions; +45.3% over 3 days; 3.4x normal trading volume; RSI 100. Risk: Overbought (RSI 100); High volatility (~6.3%/day swings); Extended move (+45% in 3 days); Earnings in 2d (2026-07-11).
...
```
(`QUIET` is deliberately excluded from this run -- it fails `MIN_MENTIONS`.)
Note how `TOPPY` still ranks #1 on raw momentum score despite carrying four
risk flags -- that score measures attention + momentum, not safety, which
is exactly why the risk flags exist as a separate signal.

## Tuning

Every weight and threshold lives in `config.py` and can be overridden via
environment variables without touching code -- see the file for the full
list (`WEIGHT_SENTIMENT`, `WEIGHT_MOMENTUM`, `WEIGHT_BUZZ`,
`WEIGHT_TECHNICAL`, `MIN_MENTIONS`, `MIN_PRICE`, `MIN_AVG_VOLUME`,
`RECENCY_HALF_LIFE_HOURS`, `LOOKBACK_DAYS`, `RISK_RSI_OVERBOUGHT`,
`RISK_RSI_OVERSOLD`, `RISK_VOLATILITY_PCT`, `RISK_EXTENDED_MOVE_PCT`,
`RISK_EARNINGS_WINDOW_DAYS`, `DEFAULT_WATCH_INTERVAL_MINUTES`,
`MIN_WATCH_INTERVAL_MINUTES`, `DIP_DROP_PCT`, `DIP_RSI_OVERSOLD`,
`DIP_MIN_SENTIMENT`, `DIP_EARNINGS_WINDOW_DAYS`, `DAY_MOVER_MIN_CHANGE_PCT`,
`DAY_MOVER_MIN_VOLUME_SURGE`, `MAX_DISCOVERY_CANDIDATES`, etc).

`MAX_DISCOVERY_CANDIDATES` (default 15, or pass `--max-candidates` directly)
caps how many auto-discovered tickers get scored on top of `--watchlist`.
Each candidate costs ~5 sequential network calls, so this is the main lever
on both runtime and how much load a run puts on the free data sources --
raising it considers more tickers but makes each scan take longer, so bump
`--interval` to match if a cycle starts running past it.

## Testing

```bash
pip install pytest
pytest -q
```

Tests cover sentiment weighting/blending, technical indicator math (RSI,
momentum, volume surge), the composite scoring/filtering/ranking logic,
dip-candidate detection (including the falling-knife exclusion), same-day
mover detection, and cashtag-based ticker discovery -- all against
synthetic data, no network required. `tests/test_integration_offline.py`
runs the full scoring pipeline end-to-end against the bundled sample
dataset.

## Known limitations

- Free-tier data sources (Reddit public JSON, StockTwits public API, Yahoo
  RSS) are rate-limited and can change format without notice; treat network
  failures as expected and check `-v` logs if a run looks thin. Reddit in
  particular can still 403 an IP/pattern it doesn't like even with the
  batched-request mitigation above -- there's no way to fully guarantee
  access to a free, unauthenticated endpoint.
- Sentiment analysis (VADER) is a lexicon-based heuristic, not a financial
  NLP model -- it can misread sarcasm, options jargon, and negation in
  longer posts. StockTwits' explicit Bullish/Bearish tags are weighted more
  heavily for this reason.
- `--show-momentum`'s table screens for *short-term attention + momentum*,
  which is a different (and riskier) signal than fundamental value. It is
  not a replacement for research into the underlying business, and past
  momentum is not a guarantee of continued momentum.
- REBOUND CANDIDATES (the default output) is a heuristic screen for the
  opposite setup (oversold/decelerating declines with non-bearish
  sentiment), framed around a "days to ~4 weeks" horizon. That framing
  describes the timeframe this kind of setup is typically evaluated over
  -- it is **not** a prediction that a bounce happens, or that it happens
  by any deadline. Sharp drops can, and do, keep falling.
- The rebound alert (fired by the default live-tracking loop) is a local
  terminal bell + on-screen banner, not a push notification -- it only
  "reaches" you if that terminal is open and visible/audible. There's no
  phone/email delivery built in.
- SAME-DAY MOMENTUM MOVERS (the other default section) is **not** a
  same-day trading signal in any predictive sense -- it identifies unusual
  price+volume activity using the latest **daily** bar, which this tool
  has no way to distinguish from "about to keep climbing" vs. "about to
  give it all back before the close." There is no real-time/intraday data
  behind it. Treat same-day (intraday) buying and selling as high-risk
  speculation independent of anything this list shows.
