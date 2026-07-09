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
| Price/volume | `market_data.py` | None -- `yfinance` |

Every fetch is wrapped in a try/except that logs a warning and returns an
empty result on failure, so one flaky source never crashes the run --
tickers just get scored on whatever data did come through (and get
excluded entirely if that's not enough, see minimum thresholds below).

StockTwits messages carry an author-supplied **Bullish/Bearish** tag, which
is trusted over text-inferred sentiment when present -- it's a direct
statement of intent rather than an inference from wording.

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
liquidity/data thresholds in `config.py`: price below `MIN_PRICE` ($3),
20-day average volume below `MIN_AVG_VOLUME` (300k shares), or fewer than
`MIN_MENTIONS` (3) combined news+social mentions.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # optional: add a NEWSAPI_KEY for richer news coverage
```

## Usage

```bash
# Score an explicit watchlist plus whatever's trending on StockTwits/Reddit
python main.py --watchlist AAPL,TSLA,NVDA,GME --top 10

# Only score the named tickers, skip trending discovery
python main.py --watchlist AAPL,MSFT --no-trending

# Save full results (all scored tickers, not just the top N)
python main.py --watchlist AAPL,TSLA --output output/results.json

# Demo/test the pipeline with bundled synthetic data (no network required)
python main.py --offline -v
```

Sample output:

```
Top short-term (2-7 day) growth candidates as of 2026-07-09 04:52 UTC

#  Ticker    Score   Sent    Mom   Buzz   Tech  Conf    Price     3d%
---------------------------------------------------------------------
1  TOPPY      54.5   80.5  100.0   80.5   47.2  0.67    14.20  +45.3%
2  MOMO       53.5   87.9   93.2   74.9   42.1  0.67    25.21  +10.9%
3  SLOW       24.9   70.0   55.3   47.1   47.2  0.43    49.15   +1.1%
4  BAGGY      14.4   13.9   19.0   62.0    9.0  0.59    13.68   -6.4%

1. TOPPY -- 100% bullish across 11 social mentions; +45.3% over 3 days; 3.4x normal trading volume; RSI 100.
...
```
(`QUIET` is deliberately excluded from this run -- it fails `MIN_MENTIONS`.)

## Tuning

Every weight and threshold lives in `config.py` and can be overridden via
environment variables without touching code -- see the file for the full
list (`WEIGHT_SENTIMENT`, `WEIGHT_MOMENTUM`, `WEIGHT_BUZZ`,
`WEIGHT_TECHNICAL`, `MIN_MENTIONS`, `MIN_PRICE`, `MIN_AVG_VOLUME`,
`RECENCY_HALF_LIFE_HOURS`, `LOOKBACK_DAYS`, etc).

## Testing

```bash
pip install pytest
pytest -q
```

Tests cover sentiment weighting/blending, technical indicator math (RSI,
momentum, volume surge), the composite scoring/filtering/ranking logic, and
cashtag-based ticker discovery -- all against synthetic data, no network
required. `tests/test_integration_offline.py` runs the full scoring pipeline
end-to-end against the bundled sample dataset.

## Known limitations

- Free-tier data sources (Reddit public JSON, StockTwits public API, Yahoo
  RSS) are rate-limited and can change format without notice; treat network
  failures as expected and check `-v` logs if a run looks thin.
- Sentiment analysis (VADER) is a lexicon-based heuristic, not a financial
  NLP model -- it can misread sarcasm, options jargon, and negation in
  longer posts. StockTwits' explicit Bullish/Bearish tags are weighted more
  heavily for this reason.
- This screens for *short-term attention + momentum*, which is a different
  (and riskier) signal than fundamental value. It is not a replacement for
  research into the underlying business, and past momentum is not a
  guarantee of continued momentum.
