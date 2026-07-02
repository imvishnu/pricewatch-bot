const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

const initData = tg.initData;
const $ = (id) => document.getElementById(id);

async function api(path, opts = {}) {
  const resp = await fetch(path, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Init-Data": initData,
      ...(opts.headers || {}),
    },
  });
  if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText);
  return resp.json();
}

const inr = (n) =>
  n == null ? "—" : "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 0 });

/* ---------- tabs ---------- */
let dealsCache = null;
document.querySelectorAll(".tab").forEach((btn) =>
  btn.addEventListener("click", () => showTab(btn.dataset.tab)));

function showTab(name) {
  document.querySelectorAll(".tab").forEach((b) =>
    b.classList.toggle("active", b.dataset.tab === name));
  ["deals", "tracked", "product"].forEach((v) =>
    $("view-" + v).classList.toggle("hidden", v !== name));
  if (name === "deals") loadDeals();
  if (name === "tracked") loadTracked();
}

/* ---------- deals ---------- */
let activeCat = "all";
async function loadDeals() {
  try {
    dealsCache = (await api("/api/deals")).deals;
  } catch (e) {
    $("deals-list").innerHTML = `<div class="empty">${e.message}</div>`;
    return;
  }
  const cats = [...new Set(dealsCache.map((d) => d.category).filter(Boolean))];
  $("deal-cats").innerHTML =
    [`<button class="chip ${activeCat === "all" ? "active" : ""}" data-cat="all">All</button>`]
      .concat(cats.map((c) =>
        `<button class="chip ${activeCat === c ? "active" : ""}" data-cat="${c}">${c}</button>`))
      .join("");
  $("deal-cats").querySelectorAll(".chip").forEach((ch) =>
    ch.addEventListener("click", () => { activeCat = ch.dataset.cat; renderDeals(); }));
  renderDeals();
}

function renderDeals() {
  $("deal-cats").querySelectorAll(".chip").forEach((ch) =>
    ch.classList.toggle("active", ch.dataset.cat === activeCat));
  const deals = dealsCache.filter((d) => activeCat === "all" || d.category === activeCat);
  $("deals-list").innerHTML = deals.length
    ? deals.map((d) => `
      <div class="card" data-asin="${d.asin}">
        <div class="title">${d.title}</div>
        <div class="row">
          <span class="price">${inr(d.latest_price)}</span>
          <span class="cat">${d.category || ""}</span>
        </div>
      </div>`).join("")
    : `<div class="empty">No deals yet — they appear as the watched channel posts.</div>`;
  $("deals-list").querySelectorAll(".card").forEach((c) =>
    c.addEventListener("click", () => openProduct(c.dataset.asin)));
}

/* ---------- tracked ---------- */
async function loadTracked() {
  let data;
  try {
    data = await api("/api/tracked");
  } catch (e) {
    $("tracked-list").innerHTML = `<div class="empty">${e.message}</div>`;
    return;
  }
  const rows = data.tracked;
  $("tracked-list").innerHTML = rows.length
    ? rows.map((t) => {
        let badge;
        if (t.snapshot_count < 10)
          badge = `<span class="badge warm">warming up ${t.snapshot_count}/10</span>`;
        else if (t.drop_pct != null && t.drop_pct >= 0)
          badge = `<span class="badge">▼ ${t.drop_pct}% vs median</span>`;
        else
          badge = `<span class="badge up">▲ ${Math.abs(t.drop_pct ?? 0)}% vs median</span>`;
        return `
        <div class="card" data-asin="${t.asin}">
          <div class="title">${t.title || t.asin}</div>
          <div class="row">
            <span class="price">${inr(t.latest_price)}</span>
            ${badge}
          </div>
          <div class="row">
            <span class="cat">${t.category || ""} · alert at ≥${t.threshold_pct}%</span>
            <button class="untrack" data-asin="${t.asin}">remove</button>
          </div>
        </div>`;
      }).join("")
    : `<div class="empty">Nothing tracked yet — paste a link above.</div>`;

  $("tracked-list").querySelectorAll(".card").forEach((c) =>
    c.addEventListener("click", () => openProduct(c.dataset.asin)));
  $("tracked-list").querySelectorAll(".untrack").forEach((b) =>
    b.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      await api("/api/untrack/" + b.dataset.asin, { method: "POST" });
      tg.HapticFeedback?.notificationOccurred("success");
      loadTracked();
    }));
}

$("track-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  try {
    await api("/api/track", {
      method: "POST",
      body: JSON.stringify({
        target: $("track-input").value.trim(),
        threshold_pct: Number($("track-pct").value) || 50,
      }),
    });
    $("track-input").value = "";
    tg.HapticFeedback?.notificationOccurred("success");
    loadTracked();
  } catch (e) {
    tg.showAlert(e.message);
  }
});

/* ---------- product detail + SVG chart ---------- */
async function openProduct(asin) {
  let p;
  try { p = await api("/api/product/" + asin); }
  catch (e) { tg.showAlert(e.message); return; }

  document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
  ["deals", "tracked"].forEach((v) => $("view-" + v).classList.add("hidden"));
  $("view-product").classList.remove("hidden");

  $("product-title").textContent = p.title || p.asin;
  $("product-meta").textContent =
    `${p.category || "uncategorised"} · ${p.snapshots.length} snapshots · ` +
    `amazon.in/dp/${p.asin}`;
  drawChart(p.snapshots);
}

function drawChart(snaps) {
  const svg = $("chart");
  const W = 320, H = 160, PAD = 12;
  if (snaps.length < 2) {
    svg.innerHTML = `<text x="160" y="84" text-anchor="middle"
      fill="var(--hint)" font-size="12">Not enough history for a chart yet</text>`;
    $("chart-legend").textContent = snaps.length === 1
      ? `Only snapshot: ${inr(snaps[0].p)}` : "";
    return;
  }
  const ps = snaps.map((s) => s.p);
  const min = Math.min(...ps), max = Math.max(...ps), span = max - min || 1;
  const x = (i) => PAD + (i / (snaps.length - 1)) * (W - 2 * PAD);
  const y = (p) => H - PAD - ((p - min) / span) * (H - 2 * PAD);
  const path = ps.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p).toFixed(1)}`).join(" ");
  const med = ps.slice().sort((a, b) => a - b)[Math.floor(ps.length / 2)];
  svg.innerHTML = `
    <line x1="${PAD}" y1="${y(med)}" x2="${W - PAD}" y2="${y(med)}"
      stroke="var(--hint)" stroke-dasharray="4 4" stroke-width="1"/>
    <path d="${path}" fill="none" stroke="var(--accent)" stroke-width="2"/>
    <circle cx="${x(ps.length - 1)}" cy="${y(ps[ps.length - 1])}" r="3.5"
      fill="var(--accent)"/>`;
  $("chart-legend").textContent =
    `Now ${inr(ps[ps.length - 1])} · median ${inr(med)} · ` +
    `low ${inr(min)} · high ${inr(max)}`;
}

$("back-btn").addEventListener("click", () => showTab("deals"));

/* ---------- boot ---------- */
showTab("deals");
