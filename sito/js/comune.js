// Parti comuni a tutte le pagine: nome del sito, intestazione e menu,
// tema chiaro/scuro, badge "ultimo aggiornamento", nomi degli operatori.

export const NOME_SITO = "Ricarica Sicilia";   // nome provvisorio: si sceglie in Fase 5
// Titolare e contatto mostrati in Privacy, Note legali e Info. L'email è quella dedicata al sito.
export const CONTATTO = { nome: "Manfredi Agnello", email: "" };   // email: da inserire in Fase 5

const ICONE = {
  logo: '<svg viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="9" fill="var(--mare)"/><path d="M4 22c4-3 8 3 12 0s8 3 12 0" fill="none" stroke="var(--su-mare)" stroke-width="2" stroke-linecap="round" opacity=".55"/><path d="M17.5 5 10 17h5.5L14 27l8-13h-5.5z" fill="var(--su-mare)"/></svg>',
  mappa: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2z"/><path d="M9 4v14M15 6v14"/></svg>',
  prezzi: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="M17 6.5A7 7 0 1 0 17 17.5"/><path d="M4 10h9M4 14h9"/></svg>',
  affidabilita: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3 5 6v6c0 4.5 3 7.5 7 9 4-1.5 7-4.5 7-9V6z"/><path d="m9 12 2 2 4-4"/></svg>',
  info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/></svg>',
  tema: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 0 0 16z" fill="currentColor"/></svg>',
};
export { ICONE };

const PAGINE = [
  { id: "mappa", href: "./", nome: "Mappa" },
  { id: "prezzi", href: "prezzi.html", nome: "Prezzi" },
  { id: "affidabilita", href: "affidabilita.html", nome: "Affidabilità" },
  { id: "info", href: "info.html", nome: "Info" },
];

// ── tema ────────────────────────────────────────────────────────────────
function leggiPreferenza(chiave) {
  try { return localStorage.getItem(chiave); } catch { return null; }
}
function salvaPreferenza(chiave, valore) {
  try { valore ? localStorage.setItem(chiave, valore) : localStorage.removeItem(chiave); } catch { /* niente */ }
}
export function temaAttuale() {
  const t = document.documentElement.dataset.tema;
  if (t === "chiaro" || t === "scuro") return t;
  return matchMedia("(prefers-color-scheme: dark)").matches ? "scuro" : "chiaro";
}
function applicaTema(t) {
  if (t) document.documentElement.dataset.tema = t;
  else delete document.documentElement.dataset.tema;
  document.dispatchEvent(new CustomEvent("tema", { detail: temaAttuale() }));
}
applicaTema(leggiPreferenza("tema"));

// ── intestazione e menu ─────────────────────────────────────────────────
export function intestazione(attiva) {
  const testata = document.getElementById("testata");
  const voci = PAGINE.map(p =>
    `<a href="${p.href}"${p.id === attiva ? ' aria-current="page"' : ""}>${p.nome}</a>`).join("");
  testata.className = "testata";
  testata.innerHTML = `
    <a class="marchio" href="./">${ICONE.logo}<span>${NOME_SITO}</span></a>
    <span class="spazio"></span>
    <nav class="nav-alto" aria-label="Sezioni">${voci}</nav>
    <span class="distintivo" id="aggiornamento" role="status">…</span>
    <button class="bottone-icona" id="cambia-tema" type="button">${ICONE.tema}</button>`;
  const basso = document.createElement("nav");
  basso.className = "nav-basso";
  basso.setAttribute("aria-label", "Sezioni");
  basso.innerHTML = PAGINE.map(p =>
    `<a href="${p.href}"${p.id === attiva ? ' aria-current="page"' : ""}>${ICONE[p.id]}<span>${p.nome}</span></a>`).join("");
  document.body.appendChild(basso);

  const bottone = document.getElementById("cambia-tema");
  const etichetta = () => {
    const prossimo = temaAttuale() === "scuro" ? "chiaro" : "scuro";
    bottone.setAttribute("aria-label", `Passa al tema ${prossimo}`);
    bottone.title = `Tema ${prossimo}`;
  };
  etichetta();
  bottone.addEventListener("click", () => {
    const nuovo = temaAttuale() === "scuro" ? "chiaro" : "scuro";
    const sistema = matchMedia("(prefers-color-scheme: dark)").matches ? "scuro" : "chiaro";
    salvaPreferenza("tema", nuovo === sistema ? null : nuovo);   // uguale al sistema: torna automatico
    applicaTema(nuovo === sistema ? null : nuovo);
    etichetta();
  });
  aggiornaDistintivo();
  setInterval(aggiornaDistintivo, 60_000);
  riempiContatti();
}

function riempiContatti() {
  const mail = CONTATTO.email
    ? `<a href="mailto:${esc(CONTATTO.email)}">${esc(CONTATTO.email)}</a>`
    : `<span class="tenue">(indirizzo email in arrivo)</span>`;
  const titolare = document.getElementById("titolare");
  if (titolare) {
    titolare.className = "";
    titolare.innerHTML = `Il sito è curato da <b>${esc(CONTATTO.nome)}</b>, a titolo personale. Contatto: ${mail}.`;
  }
  const legale = document.getElementById("contatto-legale");
  if (legale) {
    legale.className = "";
    legale.innerHTML = `${esc(CONTATTO.nome)} · ${mail}. Per segnalazioni sui dati o richieste dei titolari dei dati e dei marchi.`;
  }
  const info = document.getElementById("contatti");
  if (info) info.innerHTML = `Hai trovato un errore o una colonnina sbagliata? Scrivi a ${mail}.`;
}

// ── dati ────────────────────────────────────────────────────────────────
export async function carica(nome) {
  const r = await fetch(`dati/${nome}`, { cache: "no-cache" });
  if (!r.ok) throw new Error(`${nome}: ${r.status}`);
  return r.json();
}

export function minutiFa(iso) {
  return Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60000));
}
export function tempoFa(iso) {
  const m = minutiFa(iso);
  if (m < 1) return "adesso";
  if (m < 60) return `${m} min fa`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} ${h === 1 ? "ora" : "ore"} fa`;
  return new Date(iso).toLocaleString("it-IT", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

async function aggiornaDistintivo() {
  const el = document.getElementById("aggiornamento");
  if (!el) return;
  try {
    const s = await carica("stato.json");
    const m = minutiFa(s.aggiornato);
    el.className = "distintivo " + (m <= 20 ? "ok" : m <= 60 ? "ritardo" : "fermo");
    el.innerHTML = `<span class="lungo">Aggiornato&nbsp;</span>${tempoFa(s.aggiornato)}`;
    el.title = m > 20
      ? "La raccolta dei dati è in ritardo: gli stati potrebbero non essere attuali."
      : "Dati dalla Piattaforma Unica Nazionale, aggiornati ogni 5 minuti circa.";
  } catch {
    el.className = "distintivo fermo";
    el.textContent = "Dati non disponibili";
  }
}

// ── testi ───────────────────────────────────────────────────────────────
const NOMI = {
  "ENEL X WAY ITALIA SRL": "Enel X Way", "BEC": "BEC", "ENX": "ENX",
  "UAU srl": "UAU", "Plenitude On The Road S.r.l.": "Plenitude",
  "Tesla Italia Srl.": "Tesla", "Repower Vendita Italia SpA": "Repower",
  "DUFERCO MOBILITY SRL": "Duferco", "A2A E.MOBILITY S.R.L.": "A2A",
  "Eurospin Sicilia S.p.a. a Socio Unico": "Eurospin", "Edison Next S.P.A.": "Edison",
  "Go Electric Stations SRLS": "Go Electric Stations",
  "Porsche Sales & Marketplace GmbH": "Porsche", "ACEA ENERGIA": "Acea",
};
export function nomeOperatore(n) {
  if (!n) return "Operatore non indicato";
  if (NOMI[n]) return NOMI[n];
  const pulito = n.replace(/\s*\b(s\.?\s?r\.?\s?l\.?s?|s\.?\s?p\.?\s?a\.?|srls|spa|gmbh|società benefit|societ. benefit|a socio unico)\b\.?/gi, "")
    .replace(/[\s,.-]+$/, "").trim();
  return pulito === pulito.toUpperCase() && pulito.length > 4
    ? pulito.toLowerCase().replace(/\b\p{L}/gu, c => c.toUpperCase()) : pulito;
}

export const ETICHETTA_STATO = {
  libera: "Libera", occupata: "Occupata", guasta: "Fuori servizio",
  sconosciuto: "Stato sconosciuto", in_arrivo: "In arrivo", rimossa: "Rimossa",
};

export const CONNETTORI = {
  IEC_62196_T2: "Tipo 2", IEC_62196_T2_COMBO: "CCS2", CHADEMO: "CHAdeMO",
  IEC_62196_T3A: "Tipo 3A", DOMESTIC_F: "Schuko", TESLA_S: "Tesla",
};

export const numero = (v, cifre = 0) =>
  v == null || Number.isNaN(v) ? "–" : v.toLocaleString("it-IT", { maximumFractionDigits: cifre, minimumFractionDigits: cifre });
// Le tariffe pubblicate sulla PUN risultano SENZA IVA: confrontate con i listini ufficiali
// (Enel X Way, A2A) coincidono una volta aggiunto il 22%. Vedi METODO.md.
export const IVA = 0.22;
export const conIva = v => v == null ? null : Math.round(v * (1 + IVA) * 100) / 100;

export const euro = v => v == null ? "–" :
  v.toLocaleString("it-IT", { style: "currency", currency: "EUR", minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Il sito funziona anche senza connessione (dopo la prima visita).
// In locale (prove sul computer) è spento, salvo con ?sw=1, per vedere subito le modifiche.
const inLocale = ["localhost", "127.0.0.1"].includes(location.hostname) && !location.search.includes("sw=1");
if ("serviceWorker" in navigator && location.protocol !== "file:" && !inLocale) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}
