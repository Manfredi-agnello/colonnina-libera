// Pagina mappa: colonnine sulla mappa e in elenco, filtri, scheda di dettaglio.
import * as maplibregl from "../vendor/maplibre/maplibre-gl.mjs";
import {
  intestazione, carica, tempoFa, nomeOperatore, ETICHETTA_STATO, CONNETTORI,
  numero, euro, conIva, esc, temaAttuale, CONTATTO,
} from "./comune.js";

intestazione("mappa");

const STILI = {
  chiaro: "https://tiles.openfreemap.org/styles/positron",
  scuro: "https://tiles.openfreemap.org/styles/fiord",
};
const SICILIA = [[11.9, 35.4], [15.75, 38.85]];
const SERVIZI = {
  CAFE: "Bar", RESTAURANT: "Ristorante", SUPERMARKET: "Supermercato", HOTEL: "Hotel",
  RECREATION_AREA: "Area svago", PARKING_LOT: "Parcheggio", NATURE: "Natura", BUS_STOP: "Fermata bus",
  SHOPPING: "Negozi", MALL: "Centro commerciale", WIFI: "Wi-Fi", TAXI_STAND: "Taxi",
  TRAIN_STATION: "Stazione", AIRPORT: "Aeroporto", MUSEUM: "Museo", SPORT: "Sport", PHARMACY: "Farmacia",
};
const PARCHEGGIO = {
  ON_STREET: "In strada", PARKING_LOT: "Parcheggio", PARKING_GARAGE: "Autorimessa",
  ALONG_MOTORWAY: "Lungo l'autostrada", ON_DRIVEWAY: "Area privata",
};

const $ = id => document.getElementById(id);
const stato = {
  siti: [], perId: new Map(), profili: {}, prezzi: null, aggiornato: null,
  osm: null, ocm: null, fuori: [],   // altre fonti (file separati, ognuno con la sua licenza)
  filtri: { libere: false, rapide: false, potenza: 0, presa: "", operatore: "", fuori: false, preferite: false, aperte: false },
  vista: "mappa", io: null, aperto: null,
};

// ── preferite (salvate solo nel browser di chi le sceglie) ───────────────

const preferite = new Set((() => {
  try { return JSON.parse(localStorage.getItem("preferite") || "[]"); } catch { return []; }
})());
function salvaPreferite() {
  try { localStorage.setItem("preferite", JSON.stringify([...preferite])); } catch { /* navigazione privata */ }
}

// ── orari ───────────────────────────────────────────────────────────────
// Orari dichiarati dall'operatore alla PUN: [[giorno 1-7 (1 = lunedì), "08:30", "20:00"], ...].
// L'ora è sempre quella italiana, anche se il telefono è impostato su un altro fuso.

const NOMI_GIORNI = ["", "lun", "mar", "mer", "gio", "ven", "sab", "dom"];
function adessoInItalia() {
  const parti = Object.fromEntries(new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Rome", weekday: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(new Date()).map(p => [p.type, p.value]));
  const giorno = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].indexOf(parti.weekday) + 1;
  return { giorno, ora: `${parti.hour}:${parti.minute}` };
}

// true = aperta, false = chiusa, null = non lo sappiamo
function apertaAdesso(s) {
  if (s.fuori) return null;
  if (s.h24) return true;
  if (!s.orari?.length) return null;
  const { giorno, ora } = adessoInItalia();
  const ieri = giorno === 1 ? 7 : giorno - 1;
  return s.orari.some(([g, inizio, fine]) => {
    const notte = fine <= inizio;                      // es. 20:00-02:00: finisce il giorno dopo
    if (g === giorno) return ora >= inizio && (notte || ora < fine);
    return notte && g === ieri && ora < fine;
  });
}

function testoOrari(orari) {
  const perGiorno = Array.from({ length: 8 }, () => []);
  for (const [g, inizio, fine] of orari) perGiorno[g].push(`${inizio}–${fine}`);
  const gruppi = [];
  for (let g = 1; g <= 7; g++) {
    const fasce = perGiorno[g].join(", ") || "chiusa";
    const ultimo = gruppi.at(-1);
    if (ultimo && ultimo.fasce === fasce) ultimo.fine = g;
    else gruppi.push({ inizio: g, fine: g, fasce });
  }
  return gruppi.map(x => `${NOMI_GIORNI[x.inizio]}${x.fine > x.inizio ? `–${NOMI_GIORNI[x.fine]}` : ""} ${x.fasce}`).join(" · ");
}

// ── dati ────────────────────────────────────────────────────────────────

function statoSito(punti) {
  const reali = punti.filter(p => p.tempo_reale && p.stato !== "rimossa");
  if (reali.some(p => p.stato === "libera")) return "libera";
  if (reali.some(p => p.stato === "occupata")) return "occupata";
  if (reali.length && reali.every(p => p.stato === "guasta")) return "guasta";
  return "sconosciuto";
}

function prepara(live) {
  stato.aggiornato = live.aggiornato;
  const pun = live.siti.map(s => {
    const punti = s.punti.filter(p => p.stato !== "rimossa");
    const prese = new Set(punti.flatMap(p => p.connettori.map(c => c[0])));
    return {
      ...s, punti,
      stato: statoSito(punti),
      libere: punti.filter(p => p.tempo_reale && p.stato === "libera").length,
      kw: Math.max(0, ...punti.map(p => p.kw || 0)),
      dc: punti.some(p => p.corrente === "DC"),
      prese, nomeOp: nomeOperatore(s.operatore),
    };
  });
  stato.siti = [...pun, ...stato.fuori];
  stato.perId = new Map(stato.siti.map(s => [s.id, s]));
}

// Colonnine NON presenti nella PUN, segnalate da entrambe le altre fonti.
function preparaFuori() {
  const ocm = new Map((stato.ocm?.fuori_pun || []).map(c => [c.chiave, c]));
  stato.fuori = (stato.osm?.fuori_pun || []).filter(o => ocm.has(o.chiave)).map(o => {
    const m = ocm.get(o.chiave);
    const prese = { ...(m.prese || {}), ...(o.prese || {}) };
    const op = o.operatore || m.operatore;
    return {
      id: o.chiave, fuori: true, lat: o.lat, lon: o.lon, osmDati: o, ocmDati: m,
      operatore: op, nomeOp: op ? nomeOperatore(op) : "Operatore non indicato",
      indirizzo: o.name && o.name !== op ? o.name : "Colonnina non presente nella PUN",
      citta: "", punti: [], stato: "fuori", libere: 0, kw: 0,
      dc: "IEC_62196_T2_COMBO" in prese || "CHADEMO" in prese,
      prese: new Set(Object.keys(prese)), conteggioPrese: prese,
    };
  });
}

function passaFiltri(s) {
  const f = stato.filtri;
  if (f.preferite) return preferite.has(s.id);   // le preferite si vedono sempre, anche con altri filtri
  if (s.fuori && !f.fuori) return false;
  if (f.libere && s.stato !== "libera") return false;
  if (f.aperte && apertaAdesso(s) === false) return false;   // chi non indica gli orari resta visibile
  if (f.rapide && !s.dc) return false;
  if (f.potenza && s.kw < f.potenza) return false;
  if (f.presa && !s.prese.has(f.presa)) return false;
  if (f.operatore && s.nomeOp !== f.operatore) return false;
  return true;
}

function geojson() {
  return {
    type: "FeatureCollection",
    features: stato.siti.filter(passaFiltri).map(s => ({
      type: "Feature", id: undefined,
      geometry: { type: "Point", coordinates: [s.lon, s.lat] },
      properties: { id: s.id, stato: s.stato, libera: s.stato === "libera" ? 1 : 0 },
    })),
  };
}

// ── mappa ───────────────────────────────────────────────────────────────

const mappa = new maplibregl.Map({
  container: "mappa",
  style: STILI[temaAttuale()],
  bounds: SICILIA,
  fitBoundsOptions: { padding: 20 },
  attributionControl: false,
  maxBounds: [[10.5, 34.5], [17, 39.6]],
});
mappa.addControl(new maplibregl.AttributionControl({
  compact: true,
  customAttribution: 'Dati colonnine: <a href="https://www.piattaformaunicanazionale.it/">PUN</a> (MASE/GSE), rielaborati, non ufficiali · <a href="note-legali.html">Note legali</a>',
}), "bottom-right");
mappa.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");

function colore(nome) {
  return getComputedStyle(document.documentElement).getPropertyValue(`--${nome}`).trim();
}

// Icone disegnate al volo: colore + simbolo, così lo stato si capisce anche senza i colori.
function disegnaIcone() {
  const simboli = { libera: "✓", occupata: "●", guasta: "✕", sconosciuto: "?" };
  const tinte = { libera: "libera", occupata: "occupata", guasta: "guasta", sconosciuto: "ignoto" };
  const r = window.devicePixelRatio > 1 ? 2 : 1;
  simboli.fuori = "!";
  for (const [st, simbolo] of Object.entries(simboli)) {
    const vuota = st === "fuori";   // cerchio vuoto: non sappiamo nemmeno se esiste ancora
    const lato = 30 * r;
    const c = document.createElement("canvas");
    c.width = c.height = lato;
    const ctx = c.getContext("2d");
    ctx.beginPath();
    ctx.arc(lato / 2, lato / 2, lato / 2 - 2 * r, 0, Math.PI * 2);
    ctx.fillStyle = vuota ? colore("carta") : colore(tinte[st]);
    ctx.fill();
    ctx.lineWidth = 2.5 * r;
    ctx.strokeStyle = vuota ? colore("ignoto") : colore("carta");
    ctx.stroke();
    ctx.fillStyle = vuota ? colore("ignoto") : colore("su-mare");
    ctx.font = `700 ${(st === "occupata" ? 11 : 15) * r}px system-ui, sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(simbolo, lato / 2, lato / 2 + r);
    const img = ctx.getImageData(0, 0, lato, lato);
    if (mappa.hasImage(`st-${st}`)) mappa.removeImage(`st-${st}`);
    mappa.addImage(`st-${st}`, img, { pixelRatio: r });
  }
}

function aggiungiLivelli() {
  disegnaIcone();
  if (!mappa.getSource("siti")) {
    mappa.addSource("siti", {
      type: "geojson", data: geojson(), cluster: true, clusterRadius: 42, clusterMaxZoom: 11,
      clusterProperties: { libere: ["+", ["get", "libera"]] },
    });
  }
  mappa.addLayer({
    id: "gruppi", type: "circle", source: "siti", filter: ["has", "point_count"],
    paint: {
      "circle-color": colore("mare"),
      "circle-radius": ["step", ["get", "point_count"], 16, 20, 20, 100, 26],
      "circle-stroke-width": 3, "circle-stroke-color": colore("carta"),
    },
  });
  mappa.addLayer({
    id: "gruppi-numero", type: "symbol", source: "siti", filter: ["has", "point_count"],
    layout: { "text-field": ["get", "point_count_abbreviated"], "text-font": ["Noto Sans Regular"], "text-size": 13 },
    paint: { "text-color": colore("su-mare") },
  });
  mappa.addLayer({
    id: "punti", type: "symbol", source: "siti", filter: ["!", ["has", "point_count"]],
    layout: {
      "icon-image": ["concat", "st-", ["get", "stato"]],
      "icon-allow-overlap": true,
      "symbol-sort-key": ["match", ["get", "stato"], "libera", 3, "occupata", 2, "guasta", 1, "fuori", -1, 0],
    },
  });
}

mappa.on("style.load", aggiungiLivelli);
// Crediti della mappa chiusi all'inizio (si aprono con la "i"), così non coprono la legenda.
mappa.once("load", () => document.querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show"));
document.addEventListener("tema", e => mappa.setStyle(STILI[e.detail]));

mappa.on("click", "gruppi", async e => {
  const f = e.features[0];
  const zoom = await mappa.getSource("siti").getClusterExpansionZoom(f.properties.cluster_id);
  mappa.easeTo({ center: f.geometry.coordinates, zoom });
});
mappa.on("click", "punti", e => apri(e.features[0].properties.id));
for (const l of ["gruppi", "punti"]) {
  mappa.on("mouseenter", l, () => { mappa.getCanvas().style.cursor = "pointer"; });
  mappa.on("mouseleave", l, () => { mappa.getCanvas().style.cursor = ""; });
}
mappa.on("moveend", () => { if (stato.vista === "elenco") disegnaElenco(); });

function aggiornaMappa() {
  mappa.getSource("siti")?.setData(geojson());
  if (stato.vista === "elenco") disegnaElenco();
  const attivi = ["potenza", "presa", "operatore", "fuori"].filter(k => stato.filtri[k]).length;
  $("legenda-fuori").hidden = !stato.filtri.fuori;
  $("n-filtri").hidden = !attivi;
  $("n-filtri").textContent = attivi;
}

// ── filtri ──────────────────────────────────────────────────────────────

function interruttore(id, chiave) {
  $(id).addEventListener("click", () => {
    stato.filtri[chiave] = !stato.filtri[chiave];
    $(id).setAttribute("aria-pressed", String(stato.filtri[chiave]));
    aggiornaMappa();
  });
}
interruttore("f-libere", "libere");
interruttore("f-preferite", "preferite");
$("f-preferite").addEventListener("click", () => {
  if (!stato.filtri.preferite) return;
  if (!preferite.size) return messaggio("Non hai ancora preferite: apri una colonnina e tocca ☆ Salva.");
  const visibili = stato.siti.filter(s => preferite.has(s.id));
  if (stato.vista === "mappa" && visibili.length) {
    const lon = visibili.map(s => s.lon), lat = visibili.map(s => s.lat);
    mappa.fitBounds([[Math.min(...lon), Math.min(...lat)], [Math.max(...lon), Math.max(...lat)]],
      { padding: 80, maxZoom: 14 });
  }
});
interruttore("f-rapide", "rapide");
interruttore("f-aperte", "aperte");

function mostraPannello(si) {
  $("pannello-filtri").hidden = !si;
  $("apri-filtri").setAttribute("aria-expanded", String(si));
  if (si) $("f-potenza").focus();
}
$("apri-filtri").addEventListener("click", () => mostraPannello($("pannello-filtri").hidden));
$("chiudi-filtri").addEventListener("click", () => { mostraPannello(false); $("apri-filtri").focus(); });
$("f-potenza").addEventListener("change", e => { stato.filtri.potenza = +e.target.value; aggiornaMappa(); });
$("f-presa").addEventListener("change", e => { stato.filtri.presa = e.target.value; aggiornaMappa(); });
$("f-operatore").addEventListener("change", e => { stato.filtri.operatore = e.target.value; aggiornaMappa(); });
$("f-fuori").addEventListener("change", e => { stato.filtri.fuori = e.target.checked; aggiornaMappa(); });
$("azzera-filtri").addEventListener("click", () => {
  Object.assign(stato.filtri, { potenza: 0, presa: "", operatore: "", fuori: false });
  $("f-potenza").value = "0"; $("f-presa").value = ""; $("f-operatore").value = ""; $("f-fuori").checked = false;
  aggiornaMappa();
});

function riempiOperatori() {
  const conta = new Map();
  for (const s of stato.siti.filter(x => !x.fuori)) conta.set(s.nomeOp, (conta.get(s.nomeOp) || 0) + 1);
  const voci = [...conta].sort((a, b) => a[0].localeCompare(b[0], "it"));
  $("f-operatore").insertAdjacentHTML("beforeend",
    voci.map(([n, c]) => `<option value="${esc(n)}">${esc(n)} (${c})</option>`).join(""));
}

// ── vista elenco ────────────────────────────────────────────────────────

function distanzaKm(a, b) {
  const r = 6371, rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad, dLon = (b.lon - a.lon) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * r * Math.asin(Math.sqrt(h));
}

function disegnaElenco() {
  const c = mappa.getCenter();
  const da = stato.io || { lat: c.lat, lon: c.lng };
  const tutti = stato.siti.filter(passaFiltri)
    .map(s => ({ s, d: distanzaKm(da, s) }))
    .sort((a, b) => a.d - b.d);
  const mostrati = tutti.slice(0, 50);
  $("elenco-info").textContent =
    `${mostrati.length} ${mostrati.length === 1 ? "più vicina" : "più vicine"} ${stato.io ? "a te" : "al centro della mappa"}, ` +
    `su ${tutti.length} che ${tutti.length === 1 ? "rispetta" : "rispettano"} i filtri.`;
  $("elenco-lista").innerHTML = mostrati.map(({ s, d }) => `
    <li><button type="button" class="voce" data-id="${esc(s.id)}">
      <i class="pallino ${s.stato}" aria-hidden="true">${simbolo(s.stato)}</i>
      <span><b>${preferite.has(s.id) ? '<span aria-label="preferita">★</span> ' : ""}${esc(s.indirizzo || "Indirizzo non indicato")}</b>
        <small class="tenue">${s.fuori ? "Non nella PUN · " : ""}${esc(s.citta || "")}${s.citta ? " · " : ""}${esc(s.nomeOp)}${s.fuori ? "" : ` · ${s.dc ? "DC" : "AC"} ${numero(s.kw)} kW`}</small>
        <span class="sr-only">${riassunto(s)}</span></span>
      <span class="dist">${d < 10 ? numero(d, 1) : numero(d)} km</span>
    </button></li>`).join("");
}
$("elenco-lista").addEventListener("click", e => {
  const b = e.target.closest(".voce");
  if (b) apri(b.dataset.id);
});

function cambiaVista(v) {
  stato.vista = v;
  $("v-mappa").setAttribute("aria-pressed", String(v === "mappa"));
  $("v-elenco").setAttribute("aria-pressed", String(v === "elenco"));
  $("elenco").hidden = v !== "elenco";
  document.querySelector(".legenda").hidden = v === "elenco";
  if (v === "elenco") { disegnaElenco(); $("elenco-titolo").focus?.(); }
}
$("v-mappa").addEventListener("click", () => cambiaVista("mappa"));
$("v-elenco").addEventListener("click", () => cambiaVista("elenco"));
$("elenco-titolo").tabIndex = -1;
document.querySelector(".salta").addEventListener("click", () => cambiaVista("elenco"));

// ── vicino a me ─────────────────────────────────────────────────────────

let marcatoreIo = null;
function messaggio(testo) {
  $("messaggio").textContent = testo;
  $("messaggio").hidden = !testo;
  if (testo) setTimeout(() => { $("messaggio").hidden = true; }, 6000);
}
$("vicino").addEventListener("click", () => {
  if (!navigator.geolocation) return messaggio("Il tuo browser non permette di trovare la posizione.");
  messaggio("Cerco la tua posizione…");
  navigator.geolocation.getCurrentPosition(p => {
    stato.io = { lat: p.coords.latitude, lon: p.coords.longitude };
    messaggio("");
    if (!marcatoreIo) {
      const el = document.createElement("div");
      el.className = "marcatore-io";
      el.setAttribute("aria-label", "La tua posizione");
      marcatoreIo = new maplibregl.Marker({ element: el });
    }
    marcatoreIo.setLngLat([stato.io.lon, stato.io.lat]).addTo(mappa);
    mappa.flyTo({ center: [stato.io.lon, stato.io.lat], zoom: 13 });
    if (stato.vista === "elenco") disegnaElenco();
  }, () => messaggio("Posizione non disponibile. Controlla i permessi di localizzazione del browser."),
  { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 });
});

// ── scheda di dettaglio ─────────────────────────────────────────────────

const SIMBOLI = { libera: "✓", occupata: "●", guasta: "✕", sconosciuto: "?", fuori: "!" };
const simbolo = st => SIMBOLI[st] || "?";
const statoPresa = p => (SIMBOLI[p.stato] && p.stato !== "fuori" ? p.stato : "sconosciuto");

function riassunto(s) {
  if (s.fuori) return "Non presente nella PUN: stato sconosciuto";
  const reali = s.punti.filter(p => p.tempo_reale);
  if (!reali.length) return "Stato non disponibile in tempo reale";
  if (s.libere) return `${s.libere} ${s.libere === 1 ? "presa libera" : "prese libere"} su ${s.punti.length}`;
  return ETICHETTA_STATO[s.stato] + (s.punti.length > 1 ? ` (tutte le ${s.punti.length} prese)` : "");
}

function oraFascia() {
  const ora = new Date();
  const g = ora.getDay();
  return { fascia: ora.getHours() + (g === 0 || g === 6 ? 24 : 0), ora: ora.getHours(), festivo: g === 0 || g === 6 };
}

function profiloSito(s) {
  const serie = s.punti.map(p => stato.profili[p.id]?.occupata_pct).filter(Boolean);
  const guasti = s.punti.map(p => stato.profili[p.id]?.guasta_pct).filter(v => v != null);
  const { festivo } = oraFascia();
  const base = festivo ? 24 : 0;
  const ore = Array.from({ length: 24 }, (_, h) => {
    const valori = serie.map(v => v[base + h]).filter(v => v != null);
    return valori.length ? valori.reduce((a, b) => a + b, 0) / valori.length : null;
  });
  return {
    ore: serie.length ? ore : null,
    guasta: guasti.length ? guasti.reduce((a, b) => a + b, 0) / guasti.length : null,
  };
}

function htmlProfilo(s) {
  const p = profiloSito(s);
  let html = "";
  if (p.ore && p.ore.some(v => v != null)) {
    const { ora, festivo } = oraFascia();
    const adesso = p.ore[ora];
    const frase = adesso == null ? "Per quest'ora non ci sono ancora abbastanza dati: il grafico si completa con qualche giorno di raccolta."
      : adesso < 15 ? `A quest'ora di solito è libera (occupata il ${numero(adesso)}% del tempo).`
      : adesso < 50 ? `A quest'ora a volte è occupata (il ${numero(adesso)}% del tempo).`
      : `A quest'ora spesso è occupata (il ${numero(adesso)}% del tempo).`;
    html += `<h3>Di solito ${festivo ? "nel fine settimana" : "nei giorni feriali"}</h3>
      <p>${frase}</p>
      <div class="grafico-ore" role="img" aria-label="Percentuale di tempo occupata per ora del giorno">
        ${p.ore.map((v, h) => v == null ? `<span class="vuoto" title="ore ${h}: dati insufficienti"></span>`
          : `<span class="${h === ora ? "ora" : ""}" style="height:${Math.max(3, v)}%" title="ore ${h}: occupata ${numero(v)}%"></span>`).join("")}
      </div>
      <div class="assi-ore" aria-hidden="true"><span>0</span><span>6</span><span>12</span><span>18</span><span>23</span></div>`;
  }
  if (p.guasta != null) {
    html += p.guasta < 1
      ? `<p class="tenue">Quasi mai fuori servizio di recente, secondo i dati PUN.</p>`
      : `<p class="${p.guasta >= 20 ? "" : "tenue"}">Fuori servizio per il <b>${numero(p.guasta)}%</b> del tempo di recente, secondo i dati PUN.</p>`;
  }
  return html;
}

function htmlPrezzi(s) {
  const righe = [];
  const pubblicati = new Map();
  for (const p of s.punti) {
    for (const [tipo, v] of Object.entries(p.tariffe_pun || {})) {
      if (v.energy != null) pubblicati.set(`${tipo}${v.energy}`, { tipo: tipo.toUpperCase(), ...v });
    }
  }
  for (const v of pubblicati.values()) {
    righe.push(`<li><b>≈ ${euro(conIva(v.energy))}/kWh</b> ${v.tipo}${v.time ? ` + ${euro(conIva(v.time))}/min` : ""}${v.activation ? ` + ${euro(conIva(v.activation))} avvio` : ""} <small class="tenue">· IVA inclusa, stimata dal prezzo pubblicato dall'operatore sulla PUN (${euro(v.energy)} senza IVA)</small></li>`);
  }
  const manuali = (stato.prezzi?.rilevati_a_mano || []).filter(r =>
    nomeOperatore(r.operatore) === s.nomeOp || r.operatore.toLowerCase() === (s.operatore || "").toLowerCase());
  for (const r of manuali) {
    if (r.id_colonnina && !s.punti.some(p => p.id === r.id_colonnina)) continue;
    const data = new Date(r.data_rilevazione).toLocaleDateString("it-IT");
    righe.push(`<li><b>${euro(r.prezzo_kwh)}/kWh</b> ${r.tipo}${r.costo_minuto ? ` + ${euro(r.costo_minuto)}/min` : ""}${r.costo_avvio ? ` + ${euro(r.costo_avvio)} avvio` : ""} <small class="tenue">· tariffa a consumo${r.note ? `, ${esc(r.note)}` : ""}, verificata il ${data} (${esc(r.fonte)})</small></li>`);
  }
  if (!righe.length) return `<h3>Prezzo</h3><p class="tenue">Prezzo non ancora rilevato. Controlla l'app dell'operatore. <a href="prezzi.html">Confronta i prezzi</a></p>`;
  return `<h3>Prezzo</h3><ul class="prese">${righe.join("")}</ul><p><small class="tenue">Con abbonamenti o app diverse il prezzo può cambiare. <a href="prezzi.html">Confronta i prezzi</a></small></p>`;
}

// ── altre fonti ─────────────────────────────────────────────────────────

const GIORNI = { Mo: "lun", Tu: "mar", We: "mer", Th: "gio", Fr: "ven", Sa: "sab", Su: "dom", PH: "festivi" };
function orari(testo) {
  if (!testo) return null;
  if (testo.trim() === "24/7") return "Sempre aperta (24 ore su 24)";
  return "Orari: " + testo.replace(/\b(Mo|Tu|We|Th|Fr|Sa|Su|PH)\b/g, g => GIORNI[g])
    .replace(/\boff\b/g, "chiuso").replace(/;\s*/g, " · ");
}
function esitoCommento(e) {
  if (!e) return "";
  if (/^charged/i.test(e)) return `<span class="esito-ok">✓ Ricarica riuscita</span> · `;
  if (/^failed/i.test(e)) return `<span class="esito-ko">✕ Ricarica non riuscita</span> · `;
  return "";
}
const dataIt = d => new Date(d).toLocaleDateString("it-IT", { day: "numeric", month: "short", year: "numeric" });

function datiAltreFonti(s) {
  return {
    o: s.fuori ? s.osmDati : stato.osm?.per_sito?.[s.id],
    m: s.fuori ? s.ocmDati : stato.ocm?.per_sito?.[s.id],
  };
}

function htmlAltreFonti(s) {
  const { o, m } = datiAltreFonti(s);
  if (!o && !m) return "";
  const info = [];
  const h = orari(o?.opening_hours);
  if (h && !(s.h24 && o.opening_hours.trim() === "24/7")) info.push(h);   // già detto dalla PUN
  const posti = +(o?.capacity || m?.posti || 0);
  if (posti) info.push(`${posti} ${posti === 1 ? "posto auto" : "posti auto"}`);
  if (o?.access === "customers") info.push("Riservata ai clienti");
  if (o?.fee === "no") info.push("Segnalata come gratuita");
  if (o?.covered === "yes") info.push("Al coperto");
  let html = `<h3>Dalle altre fonti</h3>`;
  if (info.length) html += `<ul class="etichette">${info.map(x => `<li>${esc(x)}</li>`).join("")}</ul>`;
  if (m?.accesso) html += `<p><small>Come arrivarci, secondo gli utenti: ${esc(m.accesso)}</small></p>`;
  // Solo commenti degli ultimi 3 anni: quelli più vecchi dicono poco sullo stato di oggi.
  const limite = new Date(); limite.setFullYear(limite.getFullYear() - 3);
  const commenti = (m?.ultimi_commenti || []).filter(c => c.data && new Date(c.data) >= limite);
  if (commenti.length) {
    html += `<p style="margin-bottom:0"><b>Cosa dicono gli utenti</b></p><ul class="commenti">${commenti.map(c => `
      <li><small class="tenue">${esitoCommento(c.esito)}${dataIt(c.data)}${c.autore ? ` · ${esc(c.autore)}` : ""}</small>
        <p>${esc(c.testo)}</p></li>`).join("")}</ul>`;
  }
  const fonti = [s.fuori ? null : "PUN (stato in tempo reale)",
    o ? `<a href="https://www.openstreetmap.org/${esc(o.id)}" target="_blank" rel="noopener">OpenStreetMap</a>` : null,
    m ? `<a href="${esc(m.link)}" target="_blank" rel="noopener">Open Charge Map</a>` : null].filter(Boolean);
  html += `<p><small class="tenue">Fonti: ${fonti.join(" · ")}.
    ${o ? "Dati OpenStreetMap © contributori di OpenStreetMap, licenza ODbL." : ""}
    ${m ? `Dati e commenti da Open Charge Map, licenza <a href="https://creativecommons.org/licenses/by/4.0/deed.it" target="_blank" rel="noopener">CC BY 4.0</a>${m.verificata ? `, ultima verifica degli utenti: ${dataIt(m.verificata)}` : ""}.` : ""}</small></p>`;
  return html;
}

function htmlPreseFuori(s) {
  const voci = Object.entries(s.conteggioPrese || {});
  return `<div class="avviso-fuori"><p style="margin:0">Questa colonnina <b>non è nella Piattaforma Unica Nazionale</b>,
    dove gli operatori devono registrare le colonnine pubbliche. È segnalata sia da OpenStreetMap sia da
    Open Charge Map, ma potrebbe essere privata, spostata o smontata: <b>verifica prima di andarci</b>.</p></div>
    ${voci.length ? `<h3>Prese segnalate</h3><ul class="etichette">${voci.map(([k, n]) =>
      `<li>${n} × ${esc(CONNETTORI[k] || k)}</li>`).join("")}</ul>` : ""}`;
}

// ── quanto ci metto e quanto spendo ─────────────────────────────────────
// Stima semplice e prudente (vedi METODO.md, "Stima di tempo e costo"):
//  - AC: la potenza è limitata dal caricatore di bordo dell'auto (11 kW, il più diffuso);
//  - DC: fino all'80% di batteria in media l'80% della potenza utile, oltre l'80% circa il 35%;
//  - perdite di ricarica: 8%. Il risultato è un intervallo (±15%), non un numero preciso.

const AUTO_BASE = { batteria: 60, dcMax: 100 };
function leggiAuto() {
  try { return { ...AUTO_BASE, ...JSON.parse(localStorage.getItem("auto") || "{}") }; } catch { return { ...AUTO_BASE }; }
}
function salvaAuto(a) { try { localStorage.setItem("auto", JSON.stringify(a)); } catch { /* niente */ } }

const tipoTariffa = p => (p.corrente === "DC" ? (p.kw >= 100 ? "HPC" : "DC") : "AC");

function prezzoPer(s, tipo) {
  const manuale = (stato.prezzi?.rilevati_a_mano || []).find(r => r.tipo === tipo &&
    (nomeOperatore(r.operatore) === s.nomeOp || r.operatore.toLowerCase() === (s.operatore || "").toLowerCase()) &&
    (!r.id_colonnina || s.punti.some(p => p.id === r.id_colonnina)));
  if (manuale) return { kwh: manuale.prezzo_kwh, minuto: manuale.costo_minuto, avvio: manuale.costo_avvio,
    fonte: `prezzo a consumo verificato il ${new Date(manuale.data_rilevazione).toLocaleDateString("it-IT")}` };
  for (const p of s.punti) {
    const v = p.tariffe_pun?.[tipo.toLowerCase()];
    if (v?.energy != null) return { kwh: conIva(v.energy), minuto: conIva(v.time), avvio: conIva(v.activation),
      fonte: "prezzo PUN con IVA stimata" };
  }
  return null;
}

function stimaRicarica({ kwPresa, dc, batteria, dcMax, da, a }) {
  const potenza = dc ? Math.min(kwPresa, dcMax) : Math.min(kwPresa, 11);
  const fino80 = Math.max(0, Math.min(a, 80) - da), oltre80 = Math.max(0, a - Math.max(da, 80));
  const kwhBatteria = batteria * (a - da) / 100;
  const ore = dc
    ? (batteria * fino80 / 100) / (potenza * 0.8) + (batteria * oltre80 / 100) / (potenza * 0.35)
    : kwhBatteria / (potenza * 0.92);
  return { minuti: ore * 60, kwhPagati: kwhBatteria / 0.92, potenza };
}

function htmlStima(s) {
  const tipi = [...new Map(s.punti.filter(p => p.kw).map(p =>
    [`${p.corrente}${p.kw}`, p])).values()].sort((x, y) => y.kw - x.kw);
  if (!tipi.length) return "";
  const auto = leggiAuto();
  return `<details class="stima" id="stima">
    <summary>Quanto ci metto e quanto spendo?</summary>
    <div class="griglia-stima">
      <label>Presa <select id="st-presa">${tipi.map((p, i) =>
        `<option value="${i}">${p.corrente} ${numero(p.kw)} kW · ${esc([...new Set(p.connettori.map(c => CONNETTORI[c[0]] || c[0]))].join(", "))}</option>`).join("")}</select></label>
      <label>Batteria dell'auto <select id="st-batteria">${[40, 50, 60, 75, 90, 100].map(v =>
        `<option value="${v}"${v === auto.batteria ? " selected" : ""}>${v} kWh</option>`).join("")}</select></label>
      <label>Potenza massima DC dell'auto <select id="st-dcmax">${[50, 100, 150, 250].map(v =>
        `<option value="${v}"${v === auto.dcMax ? " selected" : ""}>${v} kW</option>`).join("")}</select></label>
      <label>Da (%) <input id="st-da" type="number" min="0" max="99" step="5" value="20" inputmode="numeric"></label>
      <label>A (%) <input id="st-a" type="number" min="1" max="100" step="5" value="80" inputmode="numeric"></label>
    </div>
    <p id="st-risultato" aria-live="polite"></p>
    <p><small class="tenue">Stima indicativa: dipende da auto, temperatura e colonnina. AC limitata a 11 kW
      (caricatore di bordo più diffuso); in DC oltre l'80% la ricarica rallenta molto.</small></p>
  </details>`;
}

function collegaStima(s) {
  const el = $("stima");
  if (!el) return;
  const tipi = [...new Map(s.punti.filter(p => p.kw).map(p => [`${p.corrente}${p.kw}`, p])).values()].sort((x, y) => y.kw - x.kw);
  const calcola = () => {
    const p = tipi[+$("st-presa").value];
    const batteria = +$("st-batteria").value, dcMax = +$("st-dcmax").value;
    const da = Math.max(0, Math.min(99, +$("st-da").value || 0));
    const a = Math.max(da + 1, Math.min(100, +$("st-a").value || 0));
    salvaAuto({ batteria, dcMax });
    const r = stimaRicarica({ kwPresa: p.kw, dc: p.corrente === "DC", batteria, dcMax, da, a });
    const min = Math.max(1, Math.round(r.minuti * 0.85 / 5) * 5), max = Math.max(min + 5, Math.round(r.minuti * 1.15 / 5) * 5);
    const durata = m => (m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60 ? `${m % 60} min` : ""}`.trim());
    const prezzo = prezzoPer(s, tipoTariffa(p));
    let costo = `Prezzo non ancora rilevato per questa colonnina: circa <b>${numero(r.kwhPagati)} kWh</b> da pagare.`;
    if (prezzo) {
      const minuti = (prezzo.minuto || 0) * r.minuti;
      const tot = prezzo.kwh * r.kwhPagati + (prezzo.avvio || 0) + minuti;
      costo = `Circa <b>${euro(tot)}</b> per ${numero(r.kwhPagati)} kWh <small class="tenue">(${esc(prezzo.fonte)}${prezzo.minuto ? ", compreso il costo al minuto" : ""})</small>.`;
    }
    $("st-risultato").innerHTML = `Da ${da}% a ${a}%: <b>${durata(min)} – ${durata(max)}</b>
      <small class="tenue">(potenza utile circa ${numero(r.potenza)} kW)</small>.<br>${costo}`;
  };
  el.addEventListener("input", calcola);
  el.addEventListener("change", calcola);
  calcola();
}

// ── segnala un problema ─────────────────────────────────────────────────
// Apre l'app di posta con un messaggio già compilato: nessun server, nessun dato salvato da noi.

function htmlSegnala(s) {
  if (!CONTATTO.email) {
    return `<p><small class="tenue">Hai notato un errore su questa colonnina? A breve potrai segnalarlo da qui.</small></p>`;
  }
  const pagina = `${location.origin}${location.pathname}#c=${encodeURIComponent(s.id)}`;
  const corpo = [
    "Ciao, segnalo un problema su questa colonnina:",
    "",
    `${s.nomeOp} - ${s.indirizzo || ""}${s.citta ? `, ${s.citta}` : ""}`,
    `Codice: ${s.id}`,
    `Scheda: ${pagina}`,
    "",
    "Cosa non va? (cancella le voci che non c'entrano)",
    "- non funziona / è guasta",
    "- lo stato sul sito è sbagliato",
    "- la posizione sulla mappa è sbagliata",
    "- non esiste più",
    "- il prezzo è diverso",
    "- altro:",
    "",
    "Quando l'hai visto (giorno e ora, circa):",
  ].join("\n");
  const href = `mailto:${CONTATTO.email}?subject=${encodeURIComponent(`Segnalazione colonnina: ${s.indirizzo || s.id}`)}&body=${encodeURIComponent(corpo)}`;
  return `<p><a class="bottone" href="${esc(href)}">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 21V4h11l-1 4h6v9h-9l1-4H4"/></svg>
    Segnala un problema</a>
    <small class="tenue" style="display:block;margin-top:4px">Si apre la tua app di posta con il messaggio già pronto.</small></p>`;
}

function link(s) {
  const d = `${s.lat},${s.lon}`;
  return {
    google: `https://www.google.com/maps/dir/?api=1&destination=${d}&travelmode=driving`,
    apple: `https://maps.apple.com/?daddr=${d}&dirflg=d`,
    waze: `https://waze.com/ul?ll=${d}&navigate=yes`,
  };
}

function apri(id, { aggiornamento = false } = {}) {
  const s = stato.perId.get(id);
  if (!s) return;
  // Aggiornamento automatico della stessa scheda: si conservano i valori della stima.
  const statoStima = aggiornamento && stato.aperto === id && $("stima")
    ? { open: $("stima").open, valori: ["st-presa", "st-da", "st-a"].map(k => $(k).value) } : null;
  stato.aperto = id;
  history.replaceState(null, "", `#c=${encodeURIComponent(id)}`);
  const l = link(s);
  const servizi = (s.servizi || []).map(x => SERVIZI[x] || x.toLowerCase().replace(/_/g, " "));
  const aperta = apertaAdesso(s);
  const extra = [s.h24 ? "Aperta 24 ore su 24" : null,
    s.orari?.length ? `${aperta ? "Aperta adesso" : "Chiusa adesso"} · ${testoOrari(s.orari)}` : null,
    PARCHEGGIO[s.parcheggio]].filter(Boolean);

  $("dettaglio").innerHTML = `
    <div class="maniglia" aria-hidden="true"></div>
    <div class="dettaglio-testa">
      <div>
        <p class="operatore">${esc(s.nomeOp)}</p>
        <h2 id="dettaglio-titolo">${esc(s.indirizzo || "Indirizzo non indicato")}</h2>
        <p class="tenue" style="margin:0">${esc(s.citta || "")}${s.provincia ? ` (${esc(s.provincia)})` : ""}</p>
      </div>
      <button type="button" class="bottone-icona chiudi" id="chiudi-dettaglio" aria-label="Chiudi la scheda">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>
      </button>
    </div>
    <p class="riassunto ${s.stato}"><i class="pallino ${s.stato}" aria-hidden="true">${simbolo(s.stato)}</i>${riassunto(s)}</p>
    ${s.fuori ? "" : `<p><small class="tenue">Stato aggiornato ${tempoFa(stato.aggiornato)}</small></p>`}

    <div class="azioni-dettaglio">
      <button type="button" class="bottone primario" id="portami" aria-expanded="false" aria-controls="navigatori">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><path d="M3 11 21 3l-8 18-2-8z"/></svg>
        Portami qui
      </button>
      <button type="button" class="bottone" id="salva" aria-pressed="${preferite.has(s.id)}">${preferite.has(s.id) ? "★ Salvata" : "☆ Salva"}</button>
      <button type="button" class="bottone" id="condividi">Condividi</button>
    </div>
    <div class="scelta-navigatore" id="navigatori" hidden>
      <a class="bottone" href="${l.google}" target="_blank" rel="noopener">Apri in Google Maps</a>
      <a class="bottone" href="${l.apple}" target="_blank" rel="noopener">Apri in Apple Mappe</a>
      <a class="bottone" href="${l.waze}" target="_blank" rel="noopener">Apri in Waze</a>
    </div>

    ${s.fuori ? htmlPreseFuori(s) : `<h3>Prese</h3>
    <ul class="prese">${s.punti.map(p => `
      <li class="presa">
        <i class="pallino ${p.tempo_reale ? statoPresa(p) : "sconosciuto"}" aria-hidden="true">${simbolo(p.tempo_reale ? statoPresa(p) : "sconosciuto")}</i>
        <span><span class="nome">${p.tempo_reale ? ETICHETTA_STATO[p.stato] : "Stato non in tempo reale"}</span>
          <small class="tenue">${p.corrente || ""} ${numero(p.kw)} kW · ${[...new Set(p.connettori.map(c => CONNETTORI[c[0]] || c[0]))].join(", ")}</small></span>
      </li>`).join("")}
    </ul>
    ${htmlProfilo(s)}
    ${htmlPrezzi(s)}
    ${htmlStima(s)}`}
    ${servizi.length || extra.length ? `<h3>Sul posto</h3><ul class="etichette">${[...extra, ...servizi].map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
    ${htmlAltreFonti(s)}
    ${htmlSegnala(s)}
    <p><small class="tenue">${s.fuori ? "Dati segnalati da volontari, non ufficiali" : "Dati PUN (MASE/GSE) rielaborati, non ufficiali"}: controlla sempre sul posto o nell'app dell'operatore.</small></p>`;
  $("dettaglio").hidden = false;
  if (!aggiornamento) $("dettaglio").focus();

  $("chiudi-dettaglio").addEventListener("click", chiudi);
  $("portami").addEventListener("click", e => {
    const nav = $("navigatori");
    nav.hidden = !nav.hidden;
    e.currentTarget.setAttribute("aria-expanded", String(!nav.hidden));
  });
  if (statoStima && $("stima")) {
    $("stima").open = statoStima.open;
    ["st-presa", "st-da", "st-a"].forEach((k, i) => { $(k).value = statoStima.valori[i]; });
  }
  if (!s.fuori) collegaStima(s);
  $("salva").addEventListener("click", e => {
    if (preferite.has(s.id)) preferite.delete(s.id); else preferite.add(s.id);
    salvaPreferite();
    const si = preferite.has(s.id);
    e.currentTarget.setAttribute("aria-pressed", String(si));
    e.currentTarget.textContent = si ? "★ Salvata" : "☆ Salva";
    messaggio(si ? "Aggiunta alle preferite: la ritrovi con il pulsante ★ Preferite." : "Tolta dalle preferite.");
    if (stato.filtri.preferite) aggiornaMappa();
  });
  $("condividi").addEventListener("click", async () => {
    const url = location.href;
    const testo = `Colonnina ${s.nomeOp}, ${s.indirizzo || ""} ${s.citta || ""}`.trim();
    try {
      if (navigator.share) await navigator.share({ title: testo, url });
      else { await navigator.clipboard.writeText(url); messaggio("Link copiato."); }
    } catch { /* condivisione annullata */ }
  });
  if (!aggiornamento && stato.vista === "mappa") mappa.easeTo({ center: [s.lon, s.lat], zoom: Math.max(mappa.getZoom(), 14), padding: { bottom: 240 } });
}

function chiudi() {
  const id = stato.aperto;
  stato.aperto = null;
  $("dettaglio").hidden = true;
  history.replaceState(null, "", location.pathname);
  if (stato.vista === "elenco" && id) document.querySelector(`.voce[data-id="${CSS.escape(id)}"]`)?.focus();
}
document.addEventListener("keydown", e => {
  if (e.key !== "Escape") return;
  if (!$("pannello-filtri").hidden) { mostraPannello(false); $("apri-filtri").focus(); }
  else if (!$("dettaglio").hidden) chiudi();
});

// ── avvio ───────────────────────────────────────────────────────────────

async function avvio() {
  try {
    const [live, profili, prezzi, osm, ocm] = await Promise.all([
      carica("live.json"),
      carica("profili.json").catch(() => null),
      carica("prezzi.json").catch(() => null),
      carica("osm.json").catch(() => null),
      carica("ocm.json").catch(() => null),
    ]);
    stato.osm = osm; stato.ocm = ocm;
    preparaFuori();
    prepara(live);
    stato.profili = profili?.colonnine || {};
    stato.prezzi = prezzi;
    riempiOperatori();
    if (mappa.isStyleLoaded()) aggiornaMappa(); else mappa.once("load", aggiornaMappa);
    const id = new URLSearchParams(location.hash.slice(1)).get("c");
    if (id) apri(id);
  } catch (err) {
    messaggio("Non riesco a caricare i dati delle colonnine. Riprova tra qualche minuto.");
    console.error(err);
  }
}
avvio();

// I dati si aggiornano da soli ogni 5 minuti, senza ricaricare la pagina.
setInterval(async () => {
  try {
    const live = await carica("live.json");
    if (live.aggiornato === stato.aggiornato) return;
    prepara(live);
    aggiornaMappa();
    if (stato.aperto) apri(stato.aperto, { aggiornamento: true });
  } catch { /* riprova al giro dopo */ }
}, 5 * 60 * 1000);
