# app.py
from typing import Optional, List, Dict, Any

import requests
from fastapi import FastAPI, Query, HTTPException

app = FastAPI(title="Broker Accelerator API")

# --- BRREG ---
BRREG_ENHETER_URL = "https://data.brreg.no/enhetsregisteret/api/enheter"

# --- Finanstilsynet ---
FINANSTILSYNET_REGISTRY_URL = "https://api.finanstilsynet.no/registry/api/v2/entities"


# ======================
# BRREG – Enhetsregisteret
# ======================
def fetch_enhetsregisteret(
    name: str,
    kommunenummer: Optional[str] = None,
    size: int = 20,
) -> List[Dict[str, Any]]:
    """
    Search Enhetsregisteret by name (or orgnr string) and return
    a compact, broker‑friendly structure.
    """
    params: Dict[str, Any] = {"navn": name, "size": size}
    if kommunenummer:
        params["kommunenummer"] = kommunenummer

    resp = requests.get(BRREG_ENHETER_URL, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    enheter = (data.get("_embedded") or {}).get("enheter", [])
    results: List[Dict[str, Any]] = []

    for e in enheter:
        addr = e.get("forretningsadresse") or {}
        orgform = e.get("organisasjonsform") or {}
        naeringskode1 = e.get("naeringskode1") or {}

        results.append(
            {
                "orgnr": e.get("organisasjonsnummer"),
                "navn": e.get("navn"),
                "organisasjonsform": orgform.get("beskrivelse"),
                "organisasjonsform_kode": orgform.get("kode"),
                "kommune": addr.get("kommune"),
                "postnummer": addr.get("postnummer"),
                "land": addr.get("land"),
                "naeringskode1": naeringskode1.get("kode"),
                "naeringskode1_beskrivelse": naeringskode1.get("beskrivelse"),
            }
        )

    return results


def fetch_enhet_by_orgnr(orgnr: str) -> Optional[Dict[str, Any]]:
    """
    Lookup a single organisation by orgnr via the Enhetsregisteret API.
    """
    params = {"organisasjonsnummer": orgnr}
    resp = requests.get(BRREG_ENHETER_URL, params=params, timeout=10)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    data = resp.json()
    enheter = (data.get("_embedded") or {}).get("enheter", [])
    if not enheter:
        return None

    e = enheter[0]
    addr = e.get("forretningsadresse") or {}
    orgform = e.get("organisasjonsform") or {}
    naeringskode1 = e.get("naeringskode1") or {}

    return {
        "orgnr": e.get("organisasjonsnummer"),
        "navn": e.get("navn"),
        "organisasjonsform": orgform.get("beskrivelse"),
        "organisasjonsform_kode": orgform.get("kode"),
        "kommune": addr.get("kommune"),
        "postnummer": addr.get("postnummer"),
        "land": addr.get("land"),
        "naeringskode1": naeringskode1.get("kode"),
        "naeringskode1_beskrivelse": naeringskode1.get("beskrivelse"),
    }


# ======================
# BRREG – Regnskapsregisteret (åpen del, siste år)
# ======================
def fetch_regnskap_keyfigures(orgnr: str) -> Dict[str, Any]:
    """
    Hent (nesten) alle tilgjengelige nøkkeltall fra Regnskapsregisteret (åpen del)
    for siste regnskapsår.
    """
    url = f"https://data.brreg.no/regnskapsregisteret/regnskap/{orgnr}"
    resp = requests.get(url, timeout=10)

    if resp.status_code == 404:
        return {}

    resp.raise_for_status()
    data = resp.json()

    regnskaper = data if isinstance(data, list) else [data]
    if not regnskaper:
        return {}

    # velg siste år basert på regnskapsperiode.tilDato
    def year_key(r: Dict[str, Any]) -> int:
        periode = r.get("regnskapsperiode") or {}
        til_dato = periode.get("tilDato")
        if isinstance(til_dato, str) and len(til_dato) >= 4:
            try:
                return int(til_dato[:4])
            except ValueError:
                pass
        return 0

    chosen = sorted(regnskaper, key=year_key)[-1]

    # --- metadata / periode ---
    periode = chosen.get("regnskapsperiode") or {}
    periode_år = None
    til_dato = periode.get("tilDato")
    if isinstance(til_dato, str) and len(til_dato) >= 4:
        try:
            periode_år = int(til_dato[:4])
        except ValueError:
            pass

    # --- resultatregnskap ---
    resultat = chosen.get("resultatregnskapResultat") or {}
    driftsres = resultat.get("driftsresultat") or {}
    driftsinntekter = driftsres.get("driftsinntekter") or {}
    driftskostnad = driftsres.get("driftskostnad") or {}

    finansres = resultat.get("finansresultat") or {}
    finansinntekt = finansres.get("finansinntekt") or {}
    finanskostnad = finansres.get("finanskostnad") or {}

    # --- balanse: egenkapital og gjeld ---
    balanse = chosen.get("egenkapitalGjeld") or {}
    egenkapital_obj = balanse.get("egenkapital") or {}
    innskutt_ek = egenkapital_obj.get("innskuttEgenkapital") or {}
    opptjent_ek = egenkapital_obj.get("opptjentEgenkapital") or {}

    gjeld_oversikt = balanse.get("gjeldOversikt") or {}
    kortsiktig = gjeld_oversikt.get("kortsiktigGjeld") or {}
    langsiktig = gjeld_oversikt.get("langsiktigGjeld") or {}

    # --- eiendeler ---
    eiendeler_obj = chosen.get("eiendeler") or {}
    omloepsmidler = eiendeler_obj.get("omloepsmidler") or {}
    anleggsmidler = eiendeler_obj.get("anleggsmidler") or {}

    virksomhet = chosen.get("virksomhet") or {}
    regnskapsprinsipper = chosen.get("regnkapsprinsipper") or chosen.get(
        "regnskapsprinsipper"
    ) or {}

    return {
        # Metadata
        "regnskapsår": periode_år,
        "fra_dato": periode.get("fraDato"),
        "til_dato": periode.get("tilDato"),
        "valuta": chosen.get("valuta"),
        "oppstillingsplan": chosen.get("oppstillingsplan"),
        "avviklingsregnskap": chosen.get("avviklingsregnskap"),
        "regnskapstype": chosen.get("regnskapstype"),
        "id": chosen.get("id"),
        "journalnr": chosen.get("journalnr"),

        # Virksomhet / prinsipper
        "virksomhet_organisasjonsnummer": virksomhet.get("organisasjonsnummer"),
        "virksomhet_organisasjonsform": virksomhet.get("organisasjonsform"),
        "virksomhet_morselskap": virksomhet.get("morselskap"),
        "antall_ansatte": virksomhet.get("antallAnsatte"),
        "smaa_foretak": regnskapsprinsipper.get("smaaForetak"),
        "regnskapsregler": regnskapsprinsipper.get("regnskapsregler"),

        # Resultatregnskap – drift
        "salgsinntekter": driftsinntekter.get("salgsinntekter"),
        "sum_driftsinntekter": driftsinntekter.get("sumDriftsinntekter"),
        "loennskostnad": driftskostnad.get("loennskostnad"),
        "sum_driftskostnad": driftskostnad.get("sumDriftskostnad"),
        "driftsresultat": driftsres.get("driftsresultat"),

        # Resultatregnskap – finans
        "sum_finansinntekt": finansinntekt.get("sumFinansinntekter"),
        "rentekostnad_samme_konsern": finanskostnad.get("rentekostnadSammeKonsern"),
        "annen_rentekostnad": finanskostnad.get("annenRentekostnad"),
        "sum_finanskostnad": finanskostnad.get("sumFinanskostnad"),
        "netto_finans": finansres.get("nettoFinans"),

        # Resultatregnskap – resultatnivåer
        "ordinaert_resultat_foer_skattekostnad": resultat.get(
            "ordinaertResultatFoerSkattekostnad"
        ),
        "ordinaert_resultat_skattekostnad": resultat.get(
            "ordinaertResultatSkattekostnad"
        ),
        "ekstraordinaere_poster": resultat.get("ekstraordinaerePoster"),
        "skattekostnad_ekstraord_resultat": resultat.get(
            "skattekostnadEkstraordinaertResultat"
        ),
        "aarsresultat": resultat.get("aarsresultat"),
        "totalresultat": resultat.get("totalresultat"),

        # Balanse – egenkapital
        "sum_egenkapital_gjeld": balanse.get("sumEgenkapitalGjeld"),
        "sum_egenkapital": egenkapital_obj.get("sumEgenkapital"),
        "sum_innskutt_egenkapital": innskutt_ek.get("sumInnskuttEgenkaptial"),
        "sum_opptjent_egenkapital": opptjent_ek.get("sumOpptjentEgenkapital"),

        # Balanse – gjeld
        "sum_gjeld": gjeld_oversikt.get("sumGjeld"),
        "sum_kortsiktig_gjeld": kortsiktig.get("sumKortsiktigGjeld"),
        "sum_langsiktig_gjeld": langsiktig.get("sumLangsiktigGjeld"),

        # Eiendeler
        "sum_eiendeler": eiendeler_obj.get("sumEiendeler"),
        "sum_omloepsmidler": omloepsmidler.get("sumOmloepsmidler"),
        "sum_anleggsmidler": anleggsmidler.get("sumAnleggsmidler"),
        "sum_varer": eiendeler_obj.get("sumVarer"),
        "sum_fordringer": eiendeler_obj.get("sumFordringer"),
        "sum_investeringer": eiendeler_obj.get("sumInvesteringer"),
        "sum_bankinnskudd_og_kontanter": eiendeler_obj.get(
            "sumBankinnskuddOgKontanter"
        ),
        "goodwill": eiendeler_obj.get("goodwill"),
    }


def derive_simple_risk(org: Dict[str, Any], regn: Dict[str, Any]) -> Dict[str, Any]:
    """
    Veldig enkel risikomodell – kan raffineres senere.
    Bruker nå 'sum_eiendeler' og 'sum_egenkapital' fra det utvidede settet.
    """
    score = 0
    reasons: List[str] = []

    # Org form – enkel bump for AS/ASA
    if org.get("organisasjonsform_kode") in {"AS", "ASA"}:
        score += 1
        reasons.append("Limited liability company (AS/ASA)")

    # Omsetning (størrelse)
    driftsinntekter = regn.get("sum_driftsinntekter") or 0
    if driftsinntekter > 100_000_000:
        score += 2
        reasons.append("High turnover (>100 MNOK)")
    elif driftsinntekter > 10_000_000:
        score += 1
        reasons.append("Medium turnover (>10 MNOK)")

    # Egenkapitalandel
    egenkapital = regn.get("sum_egenkapital") or 0
    sum_eiendeler = regn.get("sum_eiendeler") or 0
    eq_ratio = None
    if sum_eiendeler:
        eq_ratio = egenkapital / sum_eiendeler
        if eq_ratio < 0:
            score += 2
            reasons.append("Negative equity")
        elif eq_ratio < 0.2:
            score += 1
            reasons.append("Low equity ratio (<20%)")

    return {
        "score": score,
        "reasons": reasons,
        "equity_ratio": eq_ratio,
    }


# ======================
# Finanstilsynet – registry
# ======================
def fetch_finanstilsynet_licenses(orgnr: str) -> List[Dict[str, Any]]:
    """
    Look up licences for a legal entity in Finanstilsynet's registry.
    orgnr must be 9-digit Norwegian organisation number as string.
    """
    params = {
        "organizationNumber": orgnr,
        "pageSize": 100,
        "pageIndex": 0,
    }
    resp = requests.get(FINANSTILSYNET_REGISTRY_URL, params=params, timeout=10)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    data = resp.json()

    entities = data.get("entities") or data.get("items") or []
    results: List[Dict[str, Any]] = []

    for e in entities:
        name = e.get("name")
        orgno = e.get("organizationNumber") or orgnr
        country = e.get("country")
        entity_type = e.get("entityType")

        for lic in e.get("licenses", []):
            results.append(
                {
                    "orgnr": orgno,
                    "name": name,
                    "country": country,
                    "entity_type": entity_type,
                    "license_id": lic.get("id"),
                    "license_type": lic.get("type"),
                    "license_status": lic.get("status"),
                    "license_from": lic.get("validFrom"),
                    "license_to": lic.get("validTo"),
                    "license_description": lic.get("description"),
                }
            )

    return results


# ======================
# FastAPI endpoints
# ======================
@app.get("/ping")
def ping():
    return {"status": "ok"}


@app.get("/search")
def search_orgs(
    name: str = Query(..., min_length=2),
    kommunenummer: Optional[str] = None,
    size: int = Query(20, ge=1, le=100),
):
    """
    Broker search endpoint: type name, get list of candidates (BRREG).
    """
    try:
        return fetch_enhetsregisteret(name=name, kommunenummer=kommunenummer, size=size)
    except requests.HTTPError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/org/{orgnr}")
def get_org_profile(orgnr: str):
    """
    Combined profile:
    - BRREG basic info
    - Regnskapsregisteret extended key figures (last year)
    - Simple derived risk
    """
    try:
        org = fetch_enhet_by_orgnr(orgnr)
    except requests.HTTPError as e:
        raise HTTPException(status_code=502, detail=str(e))

    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    try:
        regn: Dict[str, Any] = fetch_regnskap_keyfigures(orgnr)
    except requests.HTTPError:
        regn = {}

    risk = derive_simple_risk(org, regn) if regn else None

    return {
        "org": org,
        "regnskap": regn or None,
        "risk": risk,
    }


@app.get("/org/{orgnr}/licenses")
def get_org_licenses(orgnr: str):
    """
    Finanstilsynet licences for this organisation (if any).
    """
    try:
        licenses = fetch_finanstilsynet_licenses(orgnr)
    except requests.HTTPError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return {
        "orgnr": orgnr,
        "licenses": licenses,
    }
