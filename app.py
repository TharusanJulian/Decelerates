from typing import Optional, List, Dict, Any

import requests
from fastapi import FastAPI, Query, HTTPException, Depends
from sqlalchemy.orm import Session

from db import SessionLocal, Company, init_db

app = FastAPI(title="Broker Accelerator API")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
def on_startup():
    init_db()


# --- BRREG ---
BRREG_ENHETER_URL = "https://data.brreg.no/enhetsregisteret/api/enheter"

# --- Finanstilsynet ---
FINANSTILSYNET_REGISTRY_URL = "https://api.finanstilsynet.no/registry/api/v2/entities"

# --- OpenSanctions (PEP/sanctions) ---
OPENSANCTIONS_SEARCH_URL = "https://api.opensanctions.org/search/peps"


# ======================
# BRREG – Enhetsregisteret
# ======================
def fetch_enhetsregisteret(
    name: str,
    kommunenummer: Optional[str] = None,
    size: int = 20,
) -> List[Dict[str, Any]]:
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
    url = f"https://data.brreg.no/regnskapsregisteret/regnskap/{orgnr}"
    resp = requests.get(url, timeout=10)

    if resp.status_code == 404:
        return {}

    resp.raise_for_status()
    data = resp.json()

    regnskaper = data if isinstance(data, list) else [data]
    if not regnskaper:
        return {}

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

    periode = chosen.get("regnskapsperiode") or {}
    periode_år = None
    til_dato = periode.get("tilDato")
    if isinstance(til_dato, str) and len(til_dato) >= 4:
        try:
            periode_år = int(til_dato[:4])
        except ValueError:
            pass

    resultat = chosen.get("resultatregnskapResultat") or {}
    driftsres = resultat.get("driftsresultat") or {}
    driftsinntekter = driftsres.get("driftsinntekter") or {}
    driftskostnad = driftsres.get("driftskostnad") or {}

    finansres = resultat.get("finansresultat") or {}
    finansinntekt = finansres.get("finansinntekt") or {}
    finanskostnad = finansres.get("finanskostnad") or {}

    balanse = chosen.get("egenkapitalGjeld") or {}
    egenkapital_obj = balanse.get("egenkapital") or {}
    innskutt_ek = egenkapital_obj.get("innskuttEgenkapital") or {}
    opptjent_ek = egenkapital_obj.get("opptjentEgenkapital") or {}

    gjeld_oversikt = balanse.get("gjeldOversikt") or {}
    kortsiktig = gjeld_oversikt.get("kortsiktigGjeld") or {}
    langsiktig = gjeld_oversikt.get("langsiktigGjeld") or {}

    eiendeler_obj = chosen.get("eiendeler") or {}
    omloepsmidler = eiendeler_obj.get("omloepsmidler") or {}
    anleggsmidler = eiendeler_obj.get("anleggsmidler") or {}

    virksomhet = chosen.get("virksomhet") or {}
    regnskapsprinsipper = chosen.get("regnkapsprinsipper") or chosen.get(
        "regnskapsprinsipper"
    ) or {}

    return {
        "regnskapsår": periode_år,
        "fra_dato": periode.get("fraDato"),
        "til_dato": periode.get("tilDato"),
        "valuta": chosen.get("valuta"),
        "oppstillingsplan": chosen.get("oppstillingsplan"),
        "avviklingsregnskap": chosen.get("avviklingsregnskap"),
        "regnskapstype": chosen.get("regnskapstype"),
        "id": chosen.get("id"),
        "journalnr": chosen.get("journalnr"),

        "virksomhet_organisasjonsnummer": virksomhet.get("organisasjonsnummer"),
        "virksomhet_organisasjonsform": virksomhet.get("organisasjonsform"),
        "virksomhet_morselskap": virksomhet.get("morselskap"),
        "antall_ansatte": virksomhet.get("antallAnsatte"),
        "smaa_foretak": regnskapsprinsipper.get("smaaForetak"),
        "regnskapsregler": regnskapsprinsipper.get("regnskapsregler"),

        "salgsinntekter": driftsinntekter.get("salgsinntekter"),
        "sum_driftsinntekter": driftsinntekter.get("sumDriftsinntekter"),
        "loennskostnad": driftskostnad.get("loennskostnad"),
        "sum_driftskostnad": driftskostnad.get("sumDriftskostnad"),
        "driftsresultat": driftsres.get("driftsresultat"),

        "sum_finansinntekt": finansinntekt.get("sumFinansinntekter"),
        "rentekostnad_samme_konsern": finanskostnad.get("rentekostnadSammeKonsern"),
        "annen_rentekostnad": finanskostnad.get("annenRentekostnad"),
        "sum_finanskostnad": finanskostnad.get("sumFinanskostnad"),
        "netto_finans": finansres.get("nettoFinans"),

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

        "sum_egenkapital_gjeld": balanse.get("sumEgenkapitalGjeld"),
        "sum_egenkapital": egenkapital_obj.get("sumEgenkapital"),
        "sum_innskutt_egenkapital": innskutt_ek.get("sumInnskuttEgenkaptial"),
        "sum_opptjent_egenkapital": opptjent_ek.get("sumOpptjentEgenkapital"),

        "sum_gjeld": gjeld_oversikt.get("sumGjeld"),
        "sum_kortsiktig_gjeld": kortsiktig.get("sumKortsiktigGjeld"),
        "sum_langsiktig_gjeld": langsiktig.get("sumLangsiktigGjeld"),

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
    score = 0
    reasons: List[str] = []

    if org.get("organisasjonsform_kode") in {"AS", "ASA"}:
        score += 1
        reasons.append("Limited liability company (AS/ASA)")

    driftsinntekter = regn.get("sum_driftsinntekter") or 0
    if driftsinntekter > 100_000_000:
        score += 2
        reasons.append("High turnover (>100 MNOK)")
    elif driftsinntekter > 10_000_000:
        score += 1
        reasons.append("Medium turnover (>10 MNOK)")

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


def build_risk_summary(
    org: Dict[str, Any],
    regn: Dict[str, Any],
    risk: Dict[str, Any],
    pep: Dict[str, Any],
) -> Dict[str, Any]:
    omsetning = regn.get("sum_driftsinntekter")
    aarsresultat = regn.get("aarsresultat")
    antall_ansatte = regn.get("antall_ansatte")
    equity_ratio = risk.get("egenkapitalandel") if risk else None
    risk_flags = risk.get("reasons") if risk else []
    pep_hits = pep.get("hit_count", 0) if pep else 0

    return {
        "orgnr": org.get("orgnr"),
        "navn": org.get("navn"),
        "organisasjonsform": org.get("organisasjonsform"),
        "organisasjonsform_kode": org.get("organisasjonsform_kode"),
        "kommune": org.get("kommune"),
        "land": org.get("land"),
        "naeringskode1": org.get("naeringskode1"),
        "naeringskode1_beskrivelse": org.get("naeringskode1_beskrivelse"),

        "regnskapsår": regn.get("regnskapsår"),
        "omsetning": omsetning,
        "aarsresultat": aarsresultat,
        "antall_ansatte": antall_ansatte,
        "sum_eiendeler": regn.get("sum_eiendeler"),
        "sum_egenkapital": regn.get("sum_egenkapital"),
        "egenkapitalandel": equity_ratio,

        "risk_score": risk.get("score") if risk else None,
        "risk_flags": risk_flags,
        "pep_hits": pep_hits,
    }


# ======================
# OpenSanctions – PEP / sanctions screening
# ======================
def pep_screen_name(name: str) -> Optional[Dict[str, Any]]:
    if not name:
        return None

    params = {"q": name, "limit": 5}
    resp = requests.get(OPENSANCTIONS_SEARCH_URL, params=params, timeout=10)

    if resp.status_code == 404:
        return None

    resp.raise_for_status()
    data = resp.json()

    results = data.get("results") or data.get("entities") or []
    hits: List[Dict[str, Any]] = []

    for m in results:
        hits.append(
            {
                "id": m.get("id"),
                "name": m.get("name"),
                "schema": m.get("schema"),
                "datasets": m.get("datasets"),
                "topics": m.get("topics"),
            }
        )

    return {"query": name, "hit_count": len(hits), "hits": hits}


# ======================
# Finanstilsynet – registry
# ======================
def fetch_finanstilsynet_licenses(orgnr: str) -> List[Dict[str, Any]]:
    params = {"organizationNumber": orgnr, "pageSize": 100, "pageIndex": 0}
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
    try:
        return fetch_enhetsregisteret(name=name, kommunenummer=kommunenummer, size=size)
    except requests.HTTPError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/org/{orgnr}")
def get_org_profile(orgnr: str, db: Session = Depends(get_db)):
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

    pep = None
    try:
        pep = pep_screen_name(org.get("navn", ""))
    except requests.HTTPError:
        pep = None

    # upsert i DB
    db_obj = db.query(Company).filter(Company.orgnr == orgnr).first()
    if not db_obj:
        db_obj = Company(orgnr=orgnr)
        db.add(db_obj)

    db_obj.navn = org.get("navn")
    db_obj.organisasjonsform_kode = org.get("organisasjonsform_kode")
    db_obj.kommune = org.get("kommune")
    db_obj.land = org.get("land")
    db_obj.naeringskode1 = org.get("naeringskode1")
    db_obj.naeringskode1_beskrivelse = org.get("naeringskode1_beskrivelse")

    if regn:
        db_obj.regnskapsår = regn.get("regnskapsår")
        db_obj.sum_driftsinntekter = regn.get("sum_driftsinntekter")
        db_obj.sum_egenkapital = regn.get("sum_egenkapital")
        db_obj.sum_eiendeler = regn.get("sum_eiendeler")
        if risk:
            db_obj.equity_ratio = risk.get("equity_ratio")
            db_obj.risk_score = risk.get("score")
        db_obj.regnskap_raw = regn

    if pep:
        db_obj.pep_raw = pep

    db.commit()

    risk_summary = build_risk_summary(org, regn or {}, risk or {}, pep or {})

    return {
        "org": org,
        "regnskap": regn or None,
        "risk": risk,
        "pep": pep,
        "risk_summary": risk_summary,
    }


@app.get("/org/{orgnr}/licenses")
def get_org_licenses(orgnr: str):
    try:
        licenses = fetch_finanstilsynet_licenses(orgnr)
    except requests.HTTPError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return {"orgnr": orgnr, "licenses": licenses}


@app.get("/companies")
def list_companies(
    limit: int = Query(50, ge=1, le=500),
    kommune: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Company)
    if kommune:
        q = q.filter(Company.kommune == kommune)

    rows = q.order_by(Company.id.desc()).limit(limit).all()

    return [
        {
            "id": c.id,
            "orgnr": c.orgnr,
            "navn": c.navn,
            "organisasjonsform_kode": c.organisasjonsform_kode,
            "kommune": c.kommune,
            "land": c.land,
            "naeringskode1": c.naeringskode1,
            "naeringskode1_beskrivelse": c.naeringskode1_beskrivelse,
            "regnskapsår": c.regnskapsår,
            "omsetning": c.sum_driftsinntekter,
            "sum_eiendeler": c.sum_eiendeler,
            "sum_egenkapital": c.sum_egenkapital,
            "egenkapitalandel": c.equity_ratio,
            "risk_score": c.risk_score,
        }
        for c in rows
    ]


@app.get("/org-by-name")
def get_org_by_name(
    name: str = Query(..., min_length=2),
    kommunenummer: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Søk på navn, ta første treff, og returner samme som /org/{orgnr}.
    Brukes som komfort-endepunkt (ikke perfekt matching).
    """
    candidates = fetch_enhetsregisteret(name=name, kommunenummer=kommunenummer, size=1)
    if not candidates:
        raise HTTPException(status_code=404, detail="No organisation found for name")

    orgnr = candidates[0]["orgnr"]
    return get_org_profile(orgnr=orgnr, db=db)
