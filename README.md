# Short-Term Stock Scanner

Compiles news headlines, Reddit posts, and StockTwits messages for a set of
tickers, blends that with price/volume momentum, and ranks the tickers by a
composite score aimed at **2-7 day** growth potential.

> **Not investment advice.** This is an automated attention + momentum
> screen. High-buzz, high-momentum names carry elevated reversal risk.
> Always do your own due diligence before trading anything it surfaces.

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
        │      price/volume history       │
        └────────────────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────┐
        │            scoring              │
        │ sentiment · momentum · buzz ·   │
        │           technical             │
        └────────────────────────────────┘
                         │
                         ▼
              ranked top-N candidates
```

### 1. Ticker discovery (`src/ticker_discovery.py`)

The candidate universe is the union of:
- Your `--watchlist` (always included).
- StockTwits' own trending-symbols feed.
- `$CASHTAG` mentions scraped out of hot posts in configured subreddits
  (`src/data_sources/reddit.py:extract_cashtags`), filtered against a
  blocklist of trading jargon that looks like a ticker (`$OTM`, `$YOLO`, etc).

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
well under that threshold. This cuts request volume roughly 4x but isn't a
guarantee -- Reddit's policies can still change or block a given IP/pattern
regardless.

StockTwits' "trending" feed also mixes in crypto/forex symbols using a
`.X` suffix (e.g. `XRP.X`, `BTC.X`) -- those are filtered out during
discovery since this tool is stocks-only and `yfinance` has no price data
under that symbol format.

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

### 5. Dip watch (`src/analysis/dip_scanner.py`)

A second, independent scan that looks for the *opposite* setup: tickers
that dropped sharply but show early signs of stabilizing. It reuses the
same news/social/price data already fetched for the main scan -- no extra
API calls. A ticker qualifies when **all** of:

- **5-day decline** at or past `DIP_DROP_PCT` (8%).
- **At least one reversal sign**: RSI(7) oversold (`DIP_RSI_OVERSOLD`, 32)
  and/or the 3-day return is less negative than the 5-day return (the drop
  is decelerating).
- **Sentiment hasn't turned bearish** -- at/above `DIP_MIN_SENTIMENT` (40).
  This is the key filter: a big drop *paired with* genuinely bearish
  news/social sentiment reads as a "falling knife" (real bad news, no
  reason to expect a bounce), not a dip-buy setup, and is excluded.

Every scan prints a **DIP WATCH** section below the main table. In the
default live-tracking loop, a ticker *newly* entering dip-watch status
(not one still sitting there from last cycle) triggers a terminal bell +
banner -- that's what "notify" means here: an on-screen/audible alert
while the terminal is open and the loop is running, not a push
notification to your phone or email (that would need a separate
service/credentials -- ask if you want that added).

**This is a heuristic candidate list, not a bounce prediction.** A stock
that's down sharply can keep falling regardless of what RSI or sentiment
say. Treat it as "worth a closer look," the same as everything else this
tool surfaces.

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
# Live: score a watchlist + trending, refresh every 10 min, until Ctrl+C
python main.py --watchlist AAPL,TSLA,NVDA,GME --top 10

# Same, but every 20 min instead of the default 10 (5 min floor enforced)
python main.py --watchlist AAPL,TSLA,NVDA --interval 20

# Single scan, then exit -- no loop
python main.py --watchlist AAPL,TSLA,NVDA --once

# Only score the named tickers, skip trending discovery
python main.py --watchlist AAPL,MSFT --no-trending --once

# Save full results on every refresh (all scored tickers, not just top N)
python main.py --watchlist AAPL,TSLA --output output/results.json

# Demo/test the pipeline with bundled synthetic data (no network required)
python main.py --offline --once -v
```

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

Sample output (deterministic -- the synthetic dataset uses a fixed seed, so
scores/RSI/volatility are stable run to run; only `earnings_date` and the
`as of` timestamp shift with the current date):

```
Top short-term (2-7 day) growth candidates as of 2026-07-09 05:50 UTC

#  Ticker    Score   Sent    Mom   Buzz   Tech  Conf    Price     3d%   Vol%  Risk
------------------------------------------------------------------------------------
1  TOPPY      54.5   80.5  100.0   80.5   47.8  0.67    14.20  +45.3%    6.3     4
2  MOMO       53.5   87.9   92.7   74.9   42.2  0.67    24.95  +10.2%    1.5     1
3  SLOW       24.7   70.0   53.9   47.1   45.8  0.43    49.18   +0.7%    0.3     1
4  DIPPY      21.3   80.0   15.6   51.3    7.5  0.48    36.02   -7.1%    1.6     1
5  BAGGY      13.8   13.9   16.8   62.0    7.2  0.59    13.48   -6.8%    1.2     1

(Vol% = avg daily price swing over the last ~10 days; Risk = number of risk flags below, '-' = none)

1. TOPPY -- 100% bullish across 11 social mentions; +45.3% over 3 days; 3.4x normal trading volume; RSI 100. Risk: Overbought (RSI 100); High volatility (~6.3%/day swings); Extended move (+45% in 3 days); Earnings in 2d (2026-07-11).
2. MOMO -- 100% bullish across 11 social mentions; +10.2% over 3 days; 2.5x normal trading volume; RSI 98. Risk: Overbought (RSI 98).
...

----------------------------------------------------------------------------------------
DIP WATCH -- sharp drops showing possible reversal signs (not a prediction, see README)
----------------------------------------------------------------------------------------
  DIPPY    $36.02      3d -7.1%  5d -10.6%  RSI 3
           DIPPY -10.6% (5d) -- down -10.6% over 5 days; RSI oversold at 3; decline decelerating over the last 3 days; sentiment not panicking (80/100)
```
(`QUIET` is deliberately excluded from this run -- it fails `MIN_MENTIONS`.) Note how
`TOPPY` still ranks #1 on raw score despite carrying four risk flags -- the
score measures attention + momentum, not safety, which is exactly why the
flags exist as a separate signal. `DIPPY` and `BAGGY` both dropped
comparably hard, but only `DIPPY` shows up in DIP WATCH -- `BAGGY`'s drop
comes with bearish sentiment (falling knife), `DIPPY`'s doesn't.

## Tuning

Every weight and threshold lives in `config.py` and can be overridden via
environment variables without touching code -- see the file for the full
list (`WEIGHT_SENTIMENT`, `WEIGHT_MOMENTUM`, `WEIGHT_BUZZ`,
`WEIGHT_TECHNICAL`, `MIN_MENTIONS`, `MIN_PRICE`, `MIN_AVG_VOLUME`,
`RECENCY_HALF_LIFE_HOURS`, `LOOKBACK_DAYS`, `RISK_RSI_OVERBOUGHT`,
`RISK_RSI_OVERSOLD`, `RISK_VOLATILITY_PCT`, `RISK_EXTENDED_MOVE_PCT`,
`RISK_EARNINGS_WINDOW_DAYS`, `DEFAULT_WATCH_INTERVAL_MINUTES`,
`MIN_WATCH_INTERVAL_MINUTES`, `DIP_DROP_PCT`, `DIP_RSI_OVERSOLD`,
`DIP_MIN_SENTIMENT`, `MAX_DISCOVERY_CANDIDATES`, etc).

`MAX_DISCOVERY_CANDIDATES` (default 20) caps how many auto-discovered
tickers get scored when you're not passing an explicit `--watchlist`. Each
candidate costs several network calls, so this is the main lever on both
runtime and how much load a run puts on the free data sources.

## Testing

```bash
pip install pytest
pytest -q
```

Tests cover sentiment weighting/blending, technical indicator math (RSI,
momentum, volume surge), the composite scoring/filtering/ranking logic,
dip-candidate detection (including the falling-knife exclusion), and
cashtag-based ticker discovery -- all against synthetic data, no network
required. `tests/test_integration_offline.py` runs the full scoring pipeline
end-to-end against the bundled sample dataset.

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
- This screens for *short-term attention + momentum*, which is a different
  (and riskier) signal than fundamental value. It is not a replacement for
  research into the underlying business, and past momentum is not a
  guarantee of continued momentum.
- DIP WATCH is the same kind of heuristic screen, aimed at the opposite
  setup (oversold/decelerating declines with non-bearish sentiment). It is
  not a bounce prediction -- sharp drops can, and do, keep falling.
- The dip alert (fired by the default live-tracking loop) is a local
  terminal bell + on-screen banner, not a push notification -- it only
  "reaches" you if that terminal is open and visible/audible. There's no
  phone/email delivery built in.
