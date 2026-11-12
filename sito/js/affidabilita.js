import { intestazione, carica, nomeOperatore, numero, esc, tempoFa } from "./comune.js";

intestazione("affidabilita");
const $ = id => document.getElementById(id);
const pct = (a, b) => b ? `${numero(100 * a / b)}%` : "–";

async function avvio() {
  try {
    const live = await carica("live.json");
    const prese = live.siti.flatMap(s => s.punti.filter(p => p.tempo_reale && p.stato !== "rimossa")
      .map(p => ({ ...p, provincia: s.provincia || "Non indicata" })));
    const conta = (lista, st) => lista.filter(p => p.stato === st).length;
    const tot = prese.length;
    $("numeri").innerHTML = [
      [numero(live.siti.length), "luoghi di ricarica"],
      [numero(tot), "prese con stato in tempo reale"],
      [pct(conta(prese, "libera"), tot), "libere adesso"],
      [pct(conta(prese, "occupata"), tot), "occupate adesso"],
      [pct(conta(prese, "guasta"), tot), "fuori servizio adesso"],
    ].map(([n, t]) => `<div class="numero"><b>${n}</b><span>${t}</span></div>`).join("");
    $("nota-adesso").textContent = `Situazione di ${tempoFa(live.aggiornato)}. Le percentuali contano solo le prese che comunicano lo stato in tempo reale.`;

    const perProv = new Map();
    for (const p of prese) {
      if (!perProv.has(p.provincia)) perProv.set(p.provincia, []);
      perProv.get(p.provincia).push(p);
    }
    $("province").innerHTML = [...perProv].filter(([, l]) => l.length >= 5)
      .sort((a, b) => b[1].length - a[1].length)
      .map(([prov, l]) => `<tr><th scope="row">${esc(prov)}</th><td class="num">${numero(l.length)}</td>
        <td class="num">${pct(conta(l, "libera"), l.length)}</td><td class="num">${pct(conta(l, "occupata"), l.length)}</td>
        <td class="num">${pct(conta(l, "guasta"), l.length)}</td></tr>`).join("");
  } catch {
    $("numeri").innerHTML = `<p>Dati non disponibili al momento.</p>`;
  }

  try {
    const op = await carica("operatori.json");
    $("operatori").innerHTML = op.filter(o => o.prese >= 10).map(o => `<tr>
      <th scope="row">${esc(nomeOperatore(o.operatore))}</th><td class="num">${numero(o.prese)}</td>
      <td class="num">${numero(o.guasta_pct)}%</td>
      <td><div class="barra-pct" aria-hidden="true"><span style="width:${Math.min(100, o.guasta_pct)}%"></span></div></td>
      <td>${o.segnala_occupazione ? "Sì" : "No, solo se funziona"}</td></tr>`).join("");
  } catch {
    $("operatori").innerHTML = `<tr><td colspan="5">Dati non disponibili al momento.</td></tr>`;
  }
}
avvio();
