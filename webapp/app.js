const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();
tg.setHeaderColor?.("#0A2A24");
tg.setBackgroundColor?.("#080A0E");

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
  n == null
    ? "—"
    : `<span class="cur">₹</span>` +
      Number(n).toLocaleString("en-IN", { maximumFractionDigits: 0 });
const inrPlain = (n) =>
  n == null ? "—" : "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 0 });

/* ================= onboarding / tutorial ================= */
const OB_STEPS = [
  { art: "📌", title: "Track any Amazon.in product",
    text: "Paste a product link (or forward one from a deals channel) in the Tracked tab. Set how big a drop you care about — default is 50% below the product's 90-day median price." },
  { art: "📉", title: "Real drops, not fake MRP discounts",
    text: "We snapshot prices every few hours and compare against the median — so inflated “was ₹9,999” prices don't fool the alerts. Each product warms up with ~10 snapshots first." },
  { art: "🔥", title: "Deals feed, filtered your way",
    text: "The Deals tab shows products spotted in the watched deals channel. Filter by category chips — and set /categories in the bot to get those deals pushed to you in chat." },
];
let obStep = 0;

function renderOnboard() {
  const s = OB_STEPS[obStep];
  $("ob-art").textContent = s.art;
  $("ob-title").textContent = s.title;
  $("ob-text").textContent = s.text;
  $("ob-dots").innerHTML = OB_STEPS.map((_, i) =>
    `<div class="dot ${i === obStep ? "active" : ""}"></div>`).join("");
  $("ob-next").textContent = obStep === OB_STEPS.length - 1 ? "Got it 🚀" : "Next";
}

function openOnboard() { obStep = 0; renderOnboard(); $("onboard").classList.remove("hidden"); }
function closeOnboard() {
  $("onboard").classList.add("hidden");
  localStorage.setItem("pw_onboarded", "1");
}
$("ob-skip").addEventListener("click", closeOnboard);
$("ob-next").addEventListener("click", () => {
  if (obStep >= OB_STEPS.length - 1) return closeOnboard();
  obStep++; renderOnboard();
  tg.HapticFeedback?.selectionChanged();
});
$("help-btn").addEventListener("click", openOnboard);
if (!localStorage.getItem("pw_onboarded")) openOnboard();

/* ================= tabs ================= */
let dealsCache = null;
document.querySelectorAll(".tab").forEach((btn) =>
  btn.addEventListener("click", () => { tg.HapticFeedback?.selectionChanged(); showTab(btn.dataset.tab); }));

function showTab(name) {
  document.querySelectorAll(".tab").forEach((b) =>
    b.classList.toggle("active", b.dataset.tab === name));
  ["deals", "tracked", "product"].forEach((v) =>
    $("view-" + v).classList.toggle("hidden", v !== name));
  if (name === "deals") loadDeals();
  if (name === "tracked") loadTracked();
}

/* ================= deals ================= */
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
    ch.addEventListener("click", () => {
      activeCat = ch.dataset.cat; renderDeals();
      tg.HapticFeedback?.selectionChanged();
    }));
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
          ${d.category ? `<span class="cat">${d.category}</span>` : ""}
        </div>
      </div>`).join("")
    : `<div class="empty"><span class="big">🕵️</span>
       No deals spotted yet.<br>They'll appear here as the watched channel posts them.</div>`;
  $("deals-list").querySelectorAll(".card").forEach((c) =>
    c.addEventListener("click", () => openProduct(c.dataset.asin)));
}

/* ================= tracked ================= */
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
          badge = `<span class="badge warm">⏳ warming up ${t.snapshot_count}/10</span>`;
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
            <span class="cat">${t.category || "uncategorised"} · alert ≥${t.threshold_pct}%</span>
            <button class="untrack" data-asin="${t.asin}">✕ remove</button>
          </div>
        </div>`;
      }).join("")
    : `<div class="empty"><span class="big">📌</span>
       Nothing tracked yet.<br>Paste an Amazon link above to start watching a price.</div>`;

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
  const btn = ev.target.querySelector("button");
  btn.textContent = "…";
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
    tg.HapticFeedback?.notificationOccurred("error");
    tg.showAlert(e.message);
  } finally {
    btn.textContent = "Track";
  }
});

/* ================= product detail + chart ================= */
async function openProduct(asin) {
  let p;
  try { p = await api("/api/product/" + asin); }
  catch (e) { tg.showAlert(e.message); return; }

  document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
  ["deals", "tracked"].forEach((v) => $("view-" + v).classList.add("hidden"));
  $("view-product").classList.remove("hidden");

  $("product-title").textContent = p.title || p.asin;
  $("product-meta").textContent =
    `${p.category || "uncategorised"} · ${p.snapshots.length} snapshots · amazon.in/dp/${p.asin}`;
  drawChart(p.snapshots);
}

function drawChart(snaps) {
  const svg = $("chart");
  const W = 320, H = 190, PAD = 14;
  $("product-stats").innerHTML = "";
  if (snaps.length < 2) {
    svg.innerHTML = `<text x="160" y="99" text-anchor="middle"
      fill="#64748b" font-size="12">Not enough history for a chart yet — check back tomorrow</text>`;
    $("chart-legend").innerHTML = snaps.length === 1
      ? `<span>Only snapshot: <b>${inrPlain(snaps[0].p)}</b></span>` : "";
    return;
  }
  const ps = snaps.map((s) => s.p);
  const min = Math.min(...ps), max = Math.max(...ps), span = max - min || 1;
  const x = (i) => PAD + (i / (snaps.length - 1)) * (W - 2 * PAD);
  const y = (p) => H - PAD - ((p - min) / span) * (H - 2 * PAD - 8) - 4;
  const pts = ps.map((p, i) => `${x(i).toFixed(1)},${y(p).toFixed(1)}`);
  const line = "M" + pts.join(" L");
  const area = `${line} L${x(ps.length - 1)},${H - PAD} L${x(0)},${H - PAD} Z`;
  const med = ps.slice().sort((a, b) => a - b)[Math.floor(ps.length / 2)];
  const last = ps[ps.length - 1];

  svg.innerHTML = `
    <defs>
      <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#FF6A2B" stop-opacity=".35"/>
        <stop offset="100%" stop-color="#FF6A2B" stop-opacity="0"/>
      </linearGradient>
    </defs>
    <line x1="${PAD}" y1="${y(med)}" x2="${W - PAD}" y2="${y(med)}"
      stroke="#FFC23D" stroke-dasharray="5 5" stroke-width="1" opacity=".7"/>
    <path d="${area}" fill="url(#fill)"/>
    <path d="${line}" fill="none" stroke="#FF6A2B" stroke-width="2.5"
      stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${x(ps.length - 1)}" cy="${y(last)}" r="4.5" fill="#FF6A2B"
      stroke="#fff" stroke-width="1.5"/>`;

  $("chart-legend").innerHTML =
    `<span>— <b style="color:#FF6A2B">price</b></span>` +
    `<span>┄ <b style="color:#FFC23D">90-day median</b></span>`;

  const dropPct = med > 0 ? ((med - last) / med * 100) : 0;
  $("product-stats").innerHTML = `
    <div class="stat"><div class="v">${inrPlain(last)}</div><div class="k">now</div></div>
    <div class="stat"><div class="v">${inrPlain(med)}</div><div class="k">median</div></div>
    <div class="stat"><div class="v" style="color:${dropPct >= 0 ? "#22c55e" : "#ef4444"}">
      ${dropPct >= 0 ? "▼" : "▲"} ${Math.abs(dropPct).toFixed(1)}%</div><div class="k">vs median</div></div>
    <div class="stat"><div class="v">${inrPlain(min)}</div><div class="k">90d low</div></div>
    <div class="stat"><div class="v">${inrPlain(max)}</div><div class="k">90d high</div></div>
    <div class="stat"><div class="v">${ps.length}</div><div class="k">snapshots</div></div>`;
}

$("back-btn").addEventListener("click", () => showTab("deals"));

/* ================= boot ================= */
showTab("deals");
