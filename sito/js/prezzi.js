import { intestazione, carica, nomeOperatore, euro, esc } from "./comune.js";

intestazione("prezzi");
const $ = id => document.getElementById(id);
let voci = [];

function altri(v) {
  return [v.costo_minuto ? `${euro(v.costo_minuto)}/min` : null,
          v.costo_avvio ? `${euro(v.costo_avvio)} all'avvio` : null].filter(Boolean).join(" · ") || "–";
}

function calcola() {
  const kwh = Math.min(150, Math.max(1, Number($("kwh").value) || 0));
  const tipo = $("tipo-calc").value;
  const scelte = voci.filter(v => v.tipo === tipo && v.prezzo_kwh != null)
    .map(v => ({ ...v, totale: v.prezzo_kwh * kwh + (v.costo_avvio || 0) }))
    .sort((a, b) => a.totale - b.totale);
  if (!scelte.length) {
    $("calcolo").innerHTML = `<p style="margin:1rem 0 0">Nessun prezzo disponibile per questo tipo di ricarica.</p>`;
    return;
  }
  $("calcolo").innerHTML = `<ul style="list-style:none;padding:0;margin:1rem 0 0;display:grid;gap:6px">${scelte.slice(0, 8).map(v =>
    `<li style="display:flex;justify-content:space-between;gap:12px;border-bottom:1px solid var(--bordo);padding:6px 0">
      <span>${esc(nomeOperatore(v.operatore))}${v.costo_minuto ? ' <small class="tenue">(+ costo al minuto)</small>' : ""}</span>
      <b style="font-variant-numeric:tabular-nums">${euro(v.totale)}</b></li>`).join("")}</ul>`;
}

async function avvio() {
  let dati;
  try { dati = await carica("prezzi.json"); }
  catch { $("righe").innerHTML = `<tr><td colspan="5">Prezzi non disponibili al momento.</td></tr>`; return; }

  const manuali = dati.rilevati_a_mano.map(r => ({ ...r, fonte: `${r.fonte}, verificato il ${new Date(r.data_rilevazione).toLocaleDateString("it-IT")}` }));
  const pun = dati.pubblicati_su_pun.map(r => ({ ...r, fonte: `Pubblicato sulla PUN (${r.colonnine} ${r.colonnine === 1 ? "presa" : "prese"})` }));
  voci = [...manuali, ...pun].sort((a, b) =>
    ["AC", "DC", "HPC"].indexOf(a.tipo) - ["AC", "DC", "HPC"].indexOf(b.tipo) || a.prezzo_kwh - b.prezzo_kwh);

  $("ultima").textContent = dati.ultima_verifica_manuale
    ? `Ultima verifica manuale: ${new Date(dati.ultima_verifica_manuale).toLocaleDateString("it-IT", { day: "numeric", month: "long", year: "numeric" })}.`
    : "Le rilevazioni manuali dalle app degli operatori sono in corso: per ora vedi solo le tariffe pubblicate sulla PUN.";
  $("righe").innerHTML = voci.length ? voci.map(v => `<tr>
      <td>${esc(nomeOperatore(v.operatore))}</td><td>${v.tipo}</td>
      <td class="num"><b>${euro(v.prezzo_kwh)}</b></td><td>${altri(v)}</td><td><small>${esc(v.fonte)}</small></td></tr>`).join("")
    : `<tr><td colspan="5">Nessun prezzo disponibile.</td></tr>`;
  calcola();
}

$("kwh").addEventListener("input", calcola);
$("tipo-calc").addEventListener("change", calcola);
avvio();
