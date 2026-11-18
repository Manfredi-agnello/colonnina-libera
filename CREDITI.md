# Crediti e licenze

## Codice
Licenza [WTFPL versione 2](LICENSE), la stessa del progetto originale.

Questo progetto parte da:
- [PalermoHub/evcharginglogsicilia](https://github.com/PalermoHub/evcharginglogsicilia) (EV Charging Log Sicilia), WTFPL;
- che a sua volta deriva da [napo/evcharginglogtrento](https://github.com/napo/evcharginglogtrento) di Maurizio Napolitano, WTFPL;
- il metodo di accesso all'API della PUN è stato ricostruito anche grazie ad [AgID/cruscotto-italia](https://github.com/AgID/cruscotto-italia).

Il codice è stato riscritto in buona parte (raccolta, analisi, sito), ma l'idea, il metodo di accesso ai dati
e parte delle scelte (filtro per area, semantica di `real_time` e dello stato CHARGING) vengono da lì.

## Dati
- Punti di ricarica: **Piattaforma Unica Nazionale (PUN)**, promossa dal MASE e gestita dal GSE con RSE.
  Nessuna licenza dichiarata: si applica il principio di riuso dell'art. 52 del CAD, citando la fonte.
  Dati rielaborati, non ufficiali, senza garanzia di completezza o correttezza.
- Orari, posti e altri dettagli: [OpenStreetMap](https://www.openstreetmap.org/), © contributori di
  OpenStreetMap, [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/). Scaricati una volta al giorno
  tramite Overpass e pubblicati in un file separato (`dati/osm.json`).
- Commenti degli utenti e dettagli: [Open Charge Map](https://openchargemap.org/), CC BY 4.0
  (autore e data indicati per ogni commento). File separato `dati/ocm.json`.
- Mappa: [OpenFreeMap](https://openfreemap.org) © [OpenMapTiles](https://openmaptiles.org/),
  dati © [contributori di OpenStreetMap](https://www.openstreetmap.org/copyright), ODbL.

## Librerie e caratteri inclusi nel sito
| Componente | Versione | Licenza | File |
|---|---|---|---|
| MapLibre GL JS | 6.16.0 | BSD 3 clausole | [sito/vendor/maplibre/LICENSE.txt](sito/vendor/maplibre/LICENSE.txt) |
| Fraunces (variabile) | 5.3.0 (Fontsource) | SIL OFL 1.1 | [sito/vendor/fraunces/LICENSE](sito/vendor/fraunces/LICENSE) |

## Librerie Python
boto3 e botocore (Apache 2.0), requests (Apache 2.0), pandas (BSD 3), pyarrow (Apache 2.0), tzdata (Apache 2.0).
