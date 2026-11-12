# Metodo di calcolo

Questo documento spiega in italiano semplice come vengono calcolati i numeri,
sia quelli del sito pubblico sia quelli del report privato della zona hub.
Le ipotesi modificabili sono in [`config/ipotesi_analisi.json`](config/ipotesi_analisi.json).
I calcoli sono controllati da test automatici con dati inventati dal risultato
noto ([`tests/test_analisi.py`](tests/test_analisi.py)):

```bash
python -m unittest discover -s tests -v
```

## 1. Da dove vengono i dati

Ogni ~5 minuti si legge dalla Piattaforma Unica Nazionale (PUN, MASE/GSE) lo
stato di ogni presa siciliana. La PUN usa questi stati, che raggruppiamo così:

| Stato PUN | Per noi |
|---|---|
| AVAILABLE | libera |
| CHARGING, RESERVED | occupata |
| OUTOFORDER, INOPERATIVE, BLOCKED | fuori servizio |
| UNKNOWN, PLANNED, REMOVED | non utile (escluso dai conti) |

Una **presa** (EVSE) è un punto dove si collega un'auto. Una colonnina ha di
solito 2 prese; un **sito** è un parcheggio con una o più colonnine.

## 2. Archivio privato della zona hub

Si salvano solo i **cambi di stato** (`eventi/`), più un **registro dei giri**
(`cicli/`: quando la raccolta ha funzionato) e una **fotografia completa al
giorno** (`anagrafica/`: operatore, potenza, coordinate di ogni presa).

Un giro è **completo** se ha letto almeno il 95% delle colonnine siciliane.
Le **letture** di una presa sono gli istanti dei giri completi più gli istanti
dei suoi cambi di stato, solo nei giorni in cui la presa compare nella
fotografia giornaliera.

## 3. Regola di base: il cambio avviene a metà

Se alle 10:00 una presa è libera e alle 10:05 è occupata, non sappiamo quando
sia arrivata l'auto: assumiamo **a metà, alle 10:02:30**. In pratica ogni
minuto prende lo stato della lettura più vicina.

**Buchi**: se due letture distano più di **15 minuti**, il tempo in mezzo è
**non osservato** e non entra in nessun conto (né come libera né come occupata).

## 4. Sessioni di ricarica

Una sessione è una serie di letture consecutive "occupata" della stessa presa.

- **Inizio**: a metà tra l'ultima lettura non occupata e la prima occupata.
- **Fine**: a metà tra l'ultima lettura occupata e la successiva.
- **Durata**: fine − inizio, **meno il tempo non osservato** nei buchi interni.
- **Incerta**: se l'inizio o la fine cadono in un buco, o se c'è un buco
  dentro la sessione. In quel caso la durata è un **valore minimo**.
- **Scartata (breve)**: sessione certa più corta di 3 minuti (probabile errore
  di comunicazione). Le incerte non si scartano mai.
- **Lunga (segnalata, non scartata)**: oltre 3 ore in DC, oltre 14 ore in AC.

Limite: con letture ogni 5 minuti una ricarica di 2-3 minuti può sfuggire.

## 5. Occupazione e fuori servizio

Per ogni presa e ogni ora (ora italiana) si contano i minuti libera / occupata /
fuori servizio.

- **Occupazione %** = minuti occupata ÷ minuti osservati.
  Si calcola solo per le prese **"in tempo reale"** il cui operatore ha
  segnalato almeno una volta lo stato "in carica". Alcuni operatori dicono solo
  se la presa funziona, mai se è occupata: includerli abbasserebbe la media a torto.
- **Fuori servizio %** = minuti fuori servizio ÷ minuti osservati (tutte le prese).

**Classi di potenza**: AC (tutte) · DC fino a 99 kW · DC da 100 kW in su.

## 6. Energia stimata (kWh)

Non si usa durata × potenza nominale, che sovrastima. Si usa una **potenza
effettiva** prudente:

- **DC**: 55% della potenza nominale della presa (la potenza cala man mano che
  la batteria si riempie). Esempio: 50 kW → 27,5 kW.
- **AC**: il valore minore tra la potenza della presa e **7,4 kW** (il
  caricatore di bordo di molte auto). Esempio: presa da 22 kW → 7,4 kW.
- **Tetto**: al massimo **80 kWh** per sessione.

Due stime, entrambe nel report:

1. **Dalle sessioni viste** = Σ durata × potenza effettiva. È un **minimo**:
   non conta le ricariche avvenute durante i buchi della raccolta.
2. **Dall'occupazione (stima principale)** = per ogni presa,
   minuti occupati × potenza effettiva, poi riportato all'intero periodo:
   `kWh osservati × minuti del periodo ÷ minuti osservati`.
   Esempio: 10 kWh in 6 ore osservate su 24 → 40 kWh nella giornata.
   Regge i buchi, purché le ore osservate siano rappresentative.

Con la raccolta completa (nessun buco) le due stime coincidono.

**Attenzione AC**: in AC "occupata" non vuol dire "sta caricando": molte auto
restano collegate a ricarica finita. Le stime AC sono quindi probabilmente per
eccesso.

## 7. Dati pubblici del sito

- **"Di solito libera a quest'ora?"** e **"fuori servizio X%"** per colonnina:
  contatori per fascia oraria (24 ore feriali + 24 ore del fine settimana) che
  perdono peso ogni giorno (×0,967: un dato di 21 giorni fa vale metà). Una
  fascia con meno di 3 osservazioni è "dati insufficienti".
- **Affidabilità degli operatori**: % del tempo osservato con prese fuori
  servizio, pesata sul tempo.
- **Prezzi**: rilevati a mano (`prezzi/prezzi.csv`, con data e fonte, IVA inclusa) più le
  tariffe che alcuni operatori pubblicano sulla PUN (circa 64 prese su 3.480 in Sicilia).
  **Le tariffe PUN risultano senza IVA**: verifica del 12/11/2026 sui listini ufficiali.
  Enel X Way dichiara alla PUN 0,54 (AC) e 0,67 (HPC) €/kWh; il suo listino a consumo
  è 0,67 e 0,83, cioè gli stessi valori × 1,22. A2A dichiara 0,63 e 0,69; i listini
  riportati da terzi sono 0,77 e 0,84 (= × 1,22). Il sito quindi mostra prezzo PUN × 1,22,
  con il simbolo ≈ e il valore originale. Altri valori PUN (es. Enel X HPC 0,43) non
  corrispondono a nessun listino: probabilmente vecchi o promozionali.
