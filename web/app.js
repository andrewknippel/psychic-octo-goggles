"use strict";

// Static dashboard: fetch data.json (rewritten by the scanner every scan)
// and re-fetch it on a timer so the page stays live without a backend.
const REFRESH_MS = 60 * 1000;
// Consider the data stale (red dot) if it hasn't been regenerated in a while.
const STALE_MS = 30 * 60 * 1000;

function fmtPct(v) {
  if (v === null || v === undefined) return "n/a";
  const s = v > 0 ? "+" : "";
  return `${s}${v.toFixed(1)}%`;
}

function timeAgo(iso) {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const secs = Math.round((Date.now() - then) / 1000);
  if (secs < 60) return "just now";
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function reboundCard(c) {
  const card = el("div", "card");

  const top = el("div", "card-top");
  top.append(el("span", "ticker", c.ticker), el("span", "price", `$${c.last_price.toFixed(2)}`));
  card.append(top);

  const metrics = el("div", "metrics");
  metrics.append(chip(`3d ${fmtPct(c.change_3d_pct)}`, c.change_3d_pct >= 0 ? "up" : "down"));
  metrics.append(chip(`5d ${fmtPct(c.change_5d_pct)}`, c.change_5d_pct >= 0 ? "up" : "down"));
  if (c.rsi !== null && c.rsi !== undefined) metrics.append(chip(`RSI ${c.rsi.toFixed(0)}`, "rsi"));
  if (c.earnings_date) metrics.append(chip(`earnings ${c.earnings_date}`, "warn"));
  card.append(metrics);

  if (c.rsi !== null && c.rsi !== undefined) {
    const meter = el("div", "rsi-meter");
    const marker = el("div", "marker");
    marker.style.left = `${Math.max(0, Math.min(100, c.rsi))}%`;
    meter.append(marker);
    card.append(meter);
  }

  const reasons = (c.reasons || []).join("; ");
  card.append(el("div", "summary", reasons || c.summary));
  return card;
}

function moverCard(m) {
  const card = el("div", "card");
  const top = el("div", "card-top");
  top.append(el("span", "ticker", m.ticker), el("span", "price", `$${m.last_price.toFixed(2)}`));
  card.append(top);

  const metrics = el("div", "metrics");
  metrics.append(chip(`today ${fmtPct(m.change_1d_pct)}`, m.change_1d_pct >= 0 ? "up" : "down"));
  metrics.append(chip(`vol ${m.volume_surge.toFixed(1)}x`, "warn"));
  if (m.rsi !== null && m.rsi !== undefined) metrics.append(chip(`RSI ${m.rsi.toFixed(0)}`, "rsi"));
  card.append(metrics);

  card.append(el("div", "summary", (m.reasons || []).join("; ") || m.summary));
  return card;
}

function newsItem(p) {
  const a = el("a", "news-item");
  a.href = p.url || "#";
  a.target = "_blank";
  a.rel = "noopener noreferrer";

  const figure = el("div", "news-figure");
  figure.append(el("div", "news-name", p.name));
  if (p.role) figure.append(el("div", "news-role", p.role));
  a.append(figure);

  const body = el("div", "news-body");
  body.append(el("div", "news-headline", p.headline));
  const meta = [p.source, timeAgo(p.published_at)].filter(Boolean).join(" · ");
  body.append(el("div", "news-meta", meta));
  if (p.snippet) body.append(el("div", "news-snippet", p.snippet));
  a.append(body);
  return a;
}

function chip(text, kind) {
  return el("span", `chip ${kind || ""}`.trim(), text);
}

function render(container, items, makeNode, emptyMsg) {
  container.replaceChildren();
  if (!items || items.length === 0) {
    container.append(el("div", "empty", emptyMsg));
    return;
  }
  for (const it of items) container.append(makeNode(it));
}

function setStatus(data) {
  const badge = document.getElementById("mode-badge");
  badge.textContent = data.mode === "offline" ? "demo data" : "live";
  badge.className = `badge ${data.mode === "offline" ? "offline" : "live"}`;

  const updated = document.getElementById("updated");
  updated.textContent = `Updated ${timeAgo(data.generated_at)}`;

  const dot = document.getElementById("refresh-dot");
  const age = Date.now() - new Date(data.generated_at).getTime();
  dot.classList.toggle("stale", age > STALE_MS);
  dot.title = age > STALE_MS ? "Data may be stale" : "Auto-refreshing";
}

async function load() {
  try {
    // Cache-bust so a static server doesn't hand back a stale copy.
    const resp = await fetch(`data.json?t=${Date.now()}`, { cache: "no-store" });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();

    setStatus(data);
    render(document.getElementById("rebound-list"), data.rebound_candidates, reboundCard,
      "No rebound candidates right now — nothing has dipped into oversold territory with holding sentiment.");
    render(document.getElementById("movers-list"), data.day_movers, moverCard,
      "No same-day movers right now.");
    render(document.getElementById("news-list"), data.influencer_feed, newsItem,
      "No recent market-mover news in the lookback window.");
    document.getElementById("disclaimer").textContent = data.disclaimer || "";
  } catch (err) {
    const updated = document.getElementById("updated");
    updated.textContent = "Could not load data.json — run the scanner with --web-out first.";
    document.getElementById("refresh-dot").classList.add("stale");
    console.error("Failed to load dashboard data:", err);
  }
}

load();
setInterval(load, REFRESH_MS);
