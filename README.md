# Stock Scanner

Two independent tools, since a short-term trade and a multi-year hold
shouldn't be picked with the same signals:

- **`main.py`** -- short-term (2-7 day) scanner. Compiles news headlines,
  Reddit posts, and StockTwits messages for a set of tickers, blends that
  with price/volume momentum, and ranks the tickers by a composite
  attention + momentum score. See below.
- **`long_term.py`** -- long-term (3-5 year) screener. Ignores buzz
  entirely and scores companies on growth, profitability, balance-sheet
  health, valuation, and analyst coverage. See
  [Long-term (3-5 year) stock picks](#long-term-3-5-year-stock-picks-long_termpy).

> **Not investment advice.** Both tools are automated screens, not
> recommendations. The short-term scanner surfaces high-buzz, high-momentum
> names that carry elevated reversal risk; the long-term screener surfaces
> statistically decent-looking businesses by the numbers, with no read on
> moat, management, or events that haven't happened yet. Always do your own
> due diligence before trading or investing in anything either one surfaces.

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
# Live: score ~15 auto-discovered tickers, show your top 5, every 10 min
python main.py

# Same idea, but always include these tickers in the scan too
python main.py --watchlist AAPL,TSLA,NVDA,GME

# Same, but every 20 min instead of the default 10 (5 min floor enforced)
python main.py --watchlist AAPL,TSLA,NVDA --interval 20

# Single scan, then exit -- no loop
python main.py --watchlist AAPL,TSLA,NVDA --once

# Only score the named tickers, skip trending discovery
python main.py --watchlist AAPL,MSFT --no-trending --once

# Cast a much wider net -- scan up to 60 auto-discovered tickers and show
# your top 15, instead of the ~15-scanned/top-5 default (bump --interval
# too, since a bigger pool scans slower)
python main.py --max-candidates 60 --interval 20 --top 15

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
dip-candidate detection (including the falling-knife exclusion), and
cashtag-based ticker discovery -- all against synthetic data, no network
required. `tests/test_integration_offline.py` runs the full scoring pipeline
end-to-end against the bundled sample dataset.

## Long-term (3-5 year) stock picks (`long_term.py`)

A separate tool, not a mode of the scanner above -- a 2-7 day momentum/
sentiment screen and a 3-5 year holding decision shouldn't be driven by the
same signals. `long_term.py` ignores news/social buzz entirely and instead
scores each company on its underlying business:

- **Growth** (`_growth_score`) -- blends revenue and earnings growth.
- **Profitability** (`_profitability_score`) -- blends profit margin,
  operating margin, and return on equity.
- **Financial health** (`_financial_health_score`) -- rewards low
  debt/equity and positive free cash flow, since surviving multiple
  rate/credit cycles over 3-5 years matters more than it does over a week.
- **Valuation** (`_valuation_score`) -- PEG ratio (P/E adjusted for growth)
  when available, otherwise a cruder forward-P/E-only fallback at reduced
  confidence.
- **Analyst coverage** (`_analyst_score`) -- blends the average analyst
  recommendation with implied upside to the mean price target.
- **Long-run trend** (`_trend_score`) -- multi-year CAGR blended with the
  trailing 1-year return, as a (backward-looking, lightly-weighted) proxy
  for sustained business quality.

These combine into a weighted composite (`LT_WEIGHT_*` in `config.py`,
default 25% growth / 20% profitability / 15% financial health / 20%
valuation / 10% analyst / 10% trend), multiplied by a **confidence** factor
based on data completeness -- yfinance doesn't report every field for every
company, and a score built on 2 of 6 sub-scores shouldn't be trusted as
much as one built on all 6. A missing sub-score falls back to a neutral 50
rather than excluding the ticker outright.

Tickers are excluded entirely below `MIN_PRICE` (same $5 penny-stock line
as the short-term scanner) or below `LT_MIN_MARKET_CAP` ($2B by default --
single-company risk is high for a "best long-term picks" list below that).

Risk flags (annotations, not scoring inputs, same philosophy as the
short-term scanner's) fire for: high debt load (D/E), rich valuation (PEG
or forward P/E), revenue *and* earnings both shrinking, weak analyst
sentiment, high beta, and thin data coverage.

### Candidate universe

There's no trending/hype discovery here on purpose -- what's getting
attention *right now* (the short-term scanner's whole premise) is close to
the opposite of what matters for a multi-year hold. Instead,
`src/long_term_universe.py` ships a curated, static pool of ~50
established, liquid, large/mid-cap companies spread across tech, health
care, consumer, financials, and industrials/energy. It's a reasonable
starting universe to screen, not a claim that these are already "the best
picks" -- the scoring does that. Add your own names with `--watchlist`
(always included in full; the pool fills the remaining `--max-candidates`
slots).

### Usage

```bash
# Scan the curated ~50-ticker pool (capped at --max-candidates, default 40), show top 10
python long_term.py

# Always include these, on top of the default pool
python long_term.py --watchlist AAPL,COST,LLY

# Only score the named tickers, skip the default pool entirely
python long_term.py --watchlist NVDA,ASML --no-default-pool

# Save full results
python long_term.py --output output/long_term.json

# Demo/test with bundled synthetic data (no network required)
python long_term.py --offline -v
```

Unlike `main.py`, there's no live-tracking loop -- fundamentals move on a
quarterly cadence, not minute to minute, so a single scan is the right
default. Rerun it whenever you want a fresh read (e.g. after an earnings
season). Each ticker costs a fundamentals lookup plus a 3-year price
history pull, so a full default-pool scan takes a while; narrow it with
`--watchlist --no-default-pool` or a lower `--max-candidates` for a
quicker run.

Sample output (offline demo, deterministic synthetic data):

```
Top long-term (3-5 year) picks as of 2026-07-09 20:56 UTC

QUICK PICKS (ticker, score out of 100):
1. COMPOUND (91.5)   2. VALUE (75.8)   3. STEADY (65.8)   4. HYPE (46.6)   5. TRAP (44.3)   6. THIN (25.3)

#  Ticker    Score  Grow  Prof Health   Val Analy Trend  Conf     Price   MktCap  Risk
--------------------------------------------------------------------------------------
1  COMPOUND   91.5    94   100     93    88    78    85  1.00    210.00     650B     -
2  VALUE      75.8    62    90     86    73    63    85  1.00    145.00     180B     -
3  STEADY     65.8    58    75     78    70    56    49  1.00     60.00      25B     -
4  HYPE       46.6    63    32     62     0    51   100  1.00     85.00      40B     2
5  TRAP       44.3    22    57     24   100    33    24  0.96     22.00       6B     3
6  THIN       25.3    50    50     50    50    50    56  0.50     40.00       4B     1

1. COMPOUND -- +18% revenue / +22% earnings growth; 25% profit margin; PEG 1.4; analyst avg rating 1.8/5.
...
4. HYPE -- +42% revenue / -12% earnings growth; -6% profit margin; PEG 6.5; analyst avg rating 3.1/5. Risk: Richly valued (PEG 6.5); High volatility stock (beta 2.3).
5. TRAP -- -8% revenue / -18% earnings growth; 2% profit margin; fwd P/E 9; analyst avg rating 3.8/5. Risk: High debt load (D/E 220%); Revenue and earnings both shrinking; Weak analyst sentiment (avg rating 3.8/5).
```

Note `HYPE` has the single highest raw growth number (+42% revenue) but
ranks 4th -- it's unprofitable, richly valued (PEG 6.5), and already had a
huge run, all of which the composite (correctly) treats as risk rather
than reward. `TRAP` has the cheapest headline valuation (fwd P/E 9) but
ranks near the bottom because that cheapness reflects a shrinking business
with heavy debt, not an overlooked bargain -- the classic value-trap
pattern.

### Known limitations (long-term screener)

- Built entirely on what `yfinance`'s free `.info` endpoint reports --
  no independent verification of a company's numbers, no read on
  competitive moat, management quality, or pending litigation/regulation.
- Multi-year CAGR/trend is backward-looking. A stock that compounded 20%/yr
  for the last 3 years has no guarantee of doing so for the next 3-5 --
  it's weighted at only 10% of the composite for that reason.
- The curated default pool (`src/long_term_universe.py`) is a fixed,
  manually-maintained list, not an exhaustive or continuously-updated
  universe -- a genuinely great long-term pick outside that list won't
  surface unless you add it via `--watchlist`.
- Same free-tier fragility as the short-term scanner: yfinance's endpoints
  can be slow, rate-limited, or return partial data; a company with
  several missing fields gets a reduced-confidence score rather than being
  silently treated as equally reliable.

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
