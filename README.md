# Colonnina Libera

Sito gratuito e senza pubblicità per chi guida un'auto elettrica in **Sicilia**: mostra quali colonnine di
ricarica sono libere, occupate o fuori servizio, aggiornate ogni 5 minuti circa, con le informazioni utili
per decidere dove andare.

**Dati:** [Piattaforma Unica Nazionale dei punti di ricarica (PUN)](https://www.piattaformaunicanazionale.it/),
MASE/GSE, rielaborati: dati **non ufficiali**, senza garanzia di completezza o correttezza. In più, per orari e
commenti degli utenti, [OpenStreetMap](https://www.openstreetmap.org/copyright) (ODbL) e
[Open Charge Map](https://openchargemap.org/) (CC BY 4.0). Dettagli in [CREDITI.md](CREDITI.md).

## Cosa fa il sito
- **Mappa ed elenco** di tutte le colonnine siciliane con lo stato in tempo reale, filtri (libere, rapide,
  aperte adesso, potenza, presa, operatore) e "Vicino a me".
- **Scheda di ogni colonnina:** prese e stato, "di solito libera a quest'ora?", quanto spesso è fuori servizio,
  prezzo, orari, stima di **tempo e costo** della ricarica, commenti recenti degli utenti,
  "Portami qui" con Google Maps, Apple Mappe o Waze, condivisione, preferite, "Segnala un problema".
- Pagine **Prezzi** (con calcolatrice), **Affidabilità**, **Info**, **Privacy**, **Note legali**.
- Si può **installare sul telefono** come un'app e funziona anche con poca connessione.
- Niente cookie, niente statistiche sulle visite, niente pubblicità.

Come vengono calcolati i numeri: [METODO.md](METODO.md).

## Come funziona, in breve

```
 cron-job.org ──ogni 5 min──▶ GitHub Actions (workflow "raccolta")
                                 │ 1. legge la PUN (solo colonnine siciliane)
                                 │ 2. una volta al giorno: OpenStreetMap e Open Charge Map
                                 │ 3. scrive i file JSON del sito
                                 ▼
                              GitHub Pages ──▶ il sito (HTML + JavaScript, nessun server)
```

- I file che servono tra un giro e l'altro (elenco colonnine, contatori orari) stanno nel branch **`stato`**,
  che viene **sovrascritto** ogni volta: il repository non cresce.
- Facoltativo: un **archivio privato** dei cambi di stato di una zona a scelta, scritto in un repository
  privato separato (segreti `HUB_*`). Nei log pubblici non compare mai nessun dato di quella zona.

## Cartelle

| Cartella | Contenuto |
|---|---|
| `raccolta/` | Programma di raccolta: PUN (`pun.py`), file del sito (`sito.py`), profili orari, prezzi, altre fonti (`osm.py`, `ocm.py`, `incrocio.py`, `fonti.py`), archivio privato (`hub.py`) |
| `sito/` | Il sito: pagine HTML, `css/`, `js/`, icone, librerie incluse (`vendor/`) |
| `prezzi/prezzi.csv` | Prezzi rilevati a mano (si modifica con Excel) |
| `config/` | Area (`area.json`), ipotesi delle analisi; i file `*.local.json` sono privati ed esclusi da Git |
| `analisi/` | Analisi dell'archivio privato (sessioni, occupazione, kWh) con report HTML |
| `strumenti/` | Server di prova in locale, confronti tra fonti |
| `tests/` | Test automatici |
| `modelli/` | Workflow da copiare nel repository privato |

## Compiti di manutenzione

### Aggiornare i prezzi
1. Apri `prezzi/prezzi.csv` con Excel o con un editor di testo.
2. Una riga per operatore e tipo di ricarica: `operatore;tipo;prezzo_kwh;costo_minuto;costo_avvio;id_colonnina;data_rilevazione;fonte;note`
   - `tipo`: `AC`, `DC` (fino a 99 kW) oppure `HPC` (da 100 kW).
   - prezzi **IVA inclusa**, come li mostra l'app; va bene `0,69` o `0.69`.
   - `data_rilevazione` nel formato `AAAA-MM-GG`; `fonte` obbligatoria (es. "app Enel X Way").
   - nelle note **non usare il punto e virgola**: usa la virgola.
3. Controlla il file: `python -m raccolta.prezzi` (dice quali righe hanno errori).
4. Fai commit e push: al giro successivo il sito si aggiorna.

### Cambiare l'area
Modifica `config/area.json`: rettangolo (`bbox`), intervallo di CAP e nomi della regione.
Il rettangolo di OpenStreetMap e Open Charge Map è in `raccolta/osm.py` e `raccolta/ocm.py`.

### Se la raccolta si ferma
L'etichetta in alto nel sito diventa **arancione** (oltre 20 minuti) o **rossa** (oltre un'ora).
1. Su GitHub apri **Actions → raccolta**: l'ultimo giro è rosso? Apri il log e leggi il messaggio.
2. Controlla che la sveglia su **cron-job.org** sia attiva (la riserva di GitHub parte solo ogni 10 minuti
   circa, e non sempre).
3. Errori ripetuti con la PUN: probabilmente il sito della PUN è cambiato o non risponde. Il sito continua a
   mostrare l'ultimo dato buono con l'etichetta rossa; il registro degli errori è nel branch `stato`
   (`registro_errori.jsonl`).
4. Per fermare tutto: **Actions → raccolta → ⋯ → Disable workflow** (e metti in pausa la sveglia).

### Segreti (Settings → Secrets and variables → Actions)
| Segreto | Serve per | Obbligatorio |
|---|---|---|
| `OCM_CHIAVE` | chiave gratuita di Open Charge Map | no |
| `HUB_TOKEN`, `HUB_REPO` | scrivere nel repository privato dell'archivio | no |
| `HUB_LAT`, `HUB_LON`, `HUB_RAGGIO_KM` | centro e raggio della zona dell'archivio privato | solo con `HUB_TOKEN` |

Senza segreti il sito funziona lo stesso (senza Open Charge Map e senza archivio privato).

## Provarlo sul proprio computer

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt          # su Mac/Linux: .venv/bin/pip
.venv/Scripts/python -m raccolta --stato stato --sito out/sito
.venv/Scripts/python -m raccolta.fonti --stato stato --sito out/sito
cp out/sito/*.json sito/dati/
.venv/Scripts/python strumenti/server_locale.py        # poi apri http://localhost:8080
```

Dal telefono sulla stessa Wi-Fi: `strumenti/server_locale.py --rete`. Test: `python -m unittest`.

## Crediti e licenza
Il progetto parte da [PalermoHub/evcharginglogsicilia](https://github.com/PalermoHub/evcharginglogsicilia),
a sua volta derivato da [napo/evcharginglogtrento](https://github.com/napo/evcharginglogtrento).
Codice con licenza [WTFPL](LICENSE), come gli originali. Mappa [OpenFreeMap](https://openfreemap.org/),
dati © contributori di OpenStreetMap. Elenco completo in [CREDITI.md](CREDITI.md).

Sito indipendente e non commerciale, non collegato a MASE, GSE o agli operatori di ricarica.
Segnalazioni e richieste: vedi la pagina [Note legali](sito/note-legali.html) del sito.
