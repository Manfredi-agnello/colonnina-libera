"""Accesso all'API della Piattaforma Unica Nazionale (PUN, GSE/MASE).

Come funziona (ricostruito dal progetto originale PalermoHub/evcharginglogsicilia,
a sua volta derivato da napo/evcharginglogtrento e AgID/cruscotto-italia):

  1. dal sito della PUN si legge /config.json, che contiene la "regione" AWS e
     l'identificativo del pool Cognito;
  2. Cognito rilascia credenziali "ospite" temporanee (valgono 1 ora,
     nessun account richiesto);
  3. POST /v1/chargepoints/public/map/search  -> elenco di tutti i punti di
     ricarica d'Italia (solo id, coordinate e stato), a pagine da 1000;
  4. POST /v1/chargepoints/group              -> dettagli completi, a gruppi di 100 id.

Rispetto della fonte: pause tra le richieste, nuovi tentativi distanziati,
l'elenco nazionale (la richiesta pesante) si scarica al massimo una volta al giorno.
"""
from __future__ import annotations

import json
import logging
import re
import time

import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials
from botocore.exceptions import BotoCoreError, ClientError

log = logging.getLogger("raccolta.pun")

SITO_PUN = "https://www.piattaformaunicanazionale.it"
API_PUN = "https://api.pun.piattaformaunicanazionale.it"
# Valori noti (novembre 2026): usati solo se /config.json non è leggibile.
REGIONE_RISERVA = "eu-south-1"
POOL_RISERVA = "eu-south-1:e3b2ab05-2046-43dd-8ed0-c0f14c69d507"

USER_AGENT = "colonnine-sicilia/0.1 (sito informativo non commerciale)"
TIMEOUT_S = 30
PAUSA_TRA_RICHIESTE_S = 0.5
ATTESE_TENTATIVI_S = (5, 30, 120)   # 3 nuovi tentativi, sempre più distanziati
DIMENSIONE_PAGINA = 1000
DIMENSIONE_GRUPPO = 100
GRUPPI_FALLITI_DI_FILA_MAX = 2      # poi si smette: probabilmente manca la rete o la PUN è giù


class ErrorePUN(Exception):
    """Errore definitivo verso la PUN (dopo tutti i tentativi)."""


def _leggi_config_pun() -> tuple[str, str]:
    try:
        r = requests.get(f"{SITO_PUN}/config.json",
                         headers={"User-Agent": USER_AGENT}, timeout=15)
        r.raise_for_status()
        testo = json.dumps(r.json())
        pool = re.search(r"([a-z]{2}-[a-z]+-\d:[0-9a-f-]{36})", testo)
        pool_id = pool.group(1) if pool else POOL_RISERVA
        return pool_id.split(":")[0], pool_id
    except (requests.RequestException, ValueError) as e:
        log.warning("config.json della PUN non leggibile (%s): uso i valori di riserva", e)
        return REGIONE_RISERVA, POOL_RISERVA


class SessionePUN:
    """Gestisce credenziali ospite, firma delle richieste e nuovi tentativi."""

    def __init__(self, tempo_massimo_s: float = 360):
        # Oltre questo tempo non si fanno più nuovi tentativi: un giro non deve
        # mai sovrapporsi al successivo (ne parte uno ogni 5 minuti).
        self.scadenza_giro = time.time() + tempo_massimo_s
        self.regione, self.pool_id = _leggi_config_pun()
        self._cognito = boto3.client("cognito-identity", region_name=self.regione,
                                     aws_access_key_id="", aws_secret_access_key="")
        self._cred: Credentials | None = None
        self._scadenza = 0.0
        self._http = requests.Session()
        self._http.headers["User-Agent"] = USER_AGENT
        self.richieste = 0
        self.tentativi_ripetuti = 0

    def _credenziali(self) -> Credentials:
        if self._cred is None or time.time() > self._scadenza - 120:
            iid = self._cognito.get_id(IdentityPoolId=self.pool_id)["IdentityId"]
            c = self._cognito.get_credentials_for_identity(IdentityId=iid)["Credentials"]
            self._cred = Credentials(c["AccessKeyId"], c["SecretKey"], c["SessionToken"])
            self._scadenza = c["Expiration"].timestamp()
        return self._cred

    def _post_una_volta(self, percorso: str, corpo) -> object:
        url = f"{API_PUN}{percorso}"
        dati = json.dumps(corpo)
        req = AWSRequest(method="POST", url=url, data=dati,
                         headers={"Content-Type": "application/json"})
        SigV4Auth(self._credenziali(), "execute-api", self.regione).add_auth(req)
        self.richieste += 1
        r = self._http.post(url, data=dati, headers=dict(req.headers), timeout=TIMEOUT_S)
        if r.status_code in (401, 403):
            self._cred = None          # credenziali scadute: al prossimo tentativo si rinnovano
        r.raise_for_status()
        return r.json()

    def post(self, percorso: str, corpo) -> object:
        """POST con nuovi tentativi. Errori 4xx diversi da 401/403/429 non si ripetono."""
        for n, attesa in enumerate((*ATTESE_TENTATIVI_S, None)):
            try:
                return self._post_una_volta(percorso, corpo)
            except requests.HTTPError as e:
                codice = e.response.status_code if e.response is not None else 0
                ripetibile = codice in (401, 403, 429) or codice >= 500
                errore = f"HTTP {codice}"
            except (requests.RequestException, ValueError, BotoCoreError, ClientError) as e:
                ripetibile, errore = True, f"{type(e).__name__}: {e}"
            if not ripetibile or attesa is None:
                raise ErrorePUN(f"{percorso}: {errore} (dopo {n + 1} tentativi)")
            if time.time() + attesa > self.scadenza_giro:
                raise ErrorePUN(f"{percorso}: {errore} (tempo massimo del giro superato)")
            self.tentativi_ripetuti += 1
            log.warning("%s: %s, nuovo tentativo tra %ss", percorso, errore, attesa)
            time.sleep(attesa)

    # ── richieste ad alto livello ──────────────────────────────────────────

    def elenco_nazionale(self) -> list[dict]:
        """Tutti i punti di ricarica d'Italia (id, coordinate, stato). Pesante: ~82 pagine."""
        voci, pagina = [], 0
        while True:
            d = self.post("/v1/chargepoints/public/map/search",
                          {"page": pagina, "size": DIMENSIONE_PAGINA})
            voci.extend(d.get("content", []))
            if d.get("last", True) or not d.get("content"):
                return voci
            pagina += 1
            time.sleep(PAUSA_TRA_RICHIESTE_S)

    def dettagli(self, id_evse: list[str]) -> tuple[list[dict], list[str]]:
        """Dettagli completi a gruppi di 100. Ritorna (record, errori).
        Un gruppo isolato che fallisce non blocca gli altri; due di fila sì."""
        record, errori, di_fila = [], [], 0
        for i in range(0, len(id_evse), DIMENSIONE_GRUPPO):
            try:
                record.extend(self.post("/v1/chargepoints/group",
                                        id_evse[i:i + DIMENSIONE_GRUPPO]))
                di_fila = 0
            except ErrorePUN as e:
                errori.append(str(e))
                di_fila += 1
                if di_fila >= GRUPPI_FALLITI_DI_FILA_MAX or time.time() > self.scadenza_giro:
                    rimasti = len(id_evse) - i - DIMENSIONE_GRUPPO
                    if rimasti > 0:
                        errori.append(f"giro interrotto, {rimasti} colonnine non richieste")
                    break
            time.sleep(PAUSA_TRA_RICHIESTE_S)
        return record, errori
