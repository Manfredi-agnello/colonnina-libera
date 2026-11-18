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
  filtri: { libere: false, rapide: false, potenza: 0, presa: "", operatore: "", fuori: false },
  vista: "mappa", io: null, aperto: null,
};

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
  if (s.fuori && !f.fuori) return false;
  if (f.libere && s.stato !== "libera") return false;
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
interruttore("f-rapide", "rapide");

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
    `${mostrati.length} più vicine ${stato.io ? "a te" : "al centro della mappa"}, su ${tutti.length} che rispettano i filtri.`;
  $("elenco-lista").innerHTML = mostrati.map(({ s, d }) => `
    <li><button type="button" class="voce" data-id="${esc(s.id)}">
      <i class="pallino ${s.stato}" aria-hidden="true">${simbolo(s.stato)}</i>
      <span><b>${esc(s.indirizzo || "Indirizzo non indicato")}</b>
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
    righe.push(`<li><b>${euro(r.prezzo_kwh)}/kWh</b> ${r.tipo}${r.costo_minuto ? ` + ${euro(r.costo_minuto)}/min` : ""}${r.costo_avvio ? ` + ${euro(r.costo_avvio)} avvio` : ""} <small class="tenue">· tariffa a consumo, verificata il ${data} (${esc(r.fonte)})</small></li>`);
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
  stato.aperto = id;
  history.replaceState(null, "", `#c=${encodeURIComponent(id)}`);
  const l = link(s);
  const servizi = (s.servizi || []).map(x => SERVIZI[x] || x.toLowerCase().replace(/_/g, " "));
  const extra = [s.h24 ? "Aperta 24 ore su 24" : null, PARCHEGGIO[s.parcheggio]].filter(Boolean);

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
    ${htmlPrezzi(s)}`}
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
