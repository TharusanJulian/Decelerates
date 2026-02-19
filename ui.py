# ui.py
import requests
import streamlit as st
import pandas as pd

API_BASE = "http://127.0.0.1:8000"

st.title("Broker Accelerator UI")

# --- Search section ---
st.subheader("Search organisation")
name = st.text_input("Name (or orgnr)", value="DNB")
kommune = st.text_input("Kommunenummer (optional)", value="")
size = st.slider("Max results", 5, 50, 20)

if "search_results" not in st.session_state:
    st.session_state["search_results"] = []
if "selected_orgnr" not in st.session_state:
    st.session_state["selected_orgnr"] = None

if st.button("Search"):
    params = {"name": name, "size": size}
    if kommune:
        params["kommunenummer"] = kommune

    try:
        resp = requests.get(f"{API_BASE}/search", params=params, timeout=10)
        resp.raise_for_status()
        st.session_state["search_results"] = resp.json()
    except Exception as e:
        st.error(f"Failed to call backend: {e}")

results = st.session_state["search_results"]
st.write(f"Found {len(results)} results")

for r in results:
    line = (
        f"{r['orgnr']} - {r['navn']} "
        f"({r['organisasjonsform']}) "
        f"[{r['kommune']}, {r['postnummer']}] "
        f"– {r['naeringskode1']} {r['naeringskode1_beskrivelse']}"
    )
    st.write(line)
    if st.button("View profile", key=f"view-{r['orgnr']}"):
        st.session_state["selected_orgnr"] = r["orgnr"]

# --- Profile section ---
selected_orgnr = st.session_state["selected_orgnr"]
if selected_orgnr:
    st.markdown("---")
    st.subheader(f"Profile for {selected_orgnr}")

    # Hent profil
    prof = None
    try:
        prof_resp = requests.get(f"{API_BASE}/org/{selected_orgnr}", timeout=10)
        prof_resp.raise_for_status()
        prof = prof_resp.json()
    except Exception as e:
        st.error(f"Failed to fetch org profile: {e}")

    # Hent lisenser
    lic = None
    try:
        lic_resp = requests.get(
            f"{API_BASE}/org/{selected_orgnr}/licenses", timeout=10
        )
        lic_resp.raise_for_status()
        lic = lic_resp.json()
    except Exception as e:
        st.error(f"Failed to fetch licences: {e}")

    if prof:
        org = prof.get("org") or {}
        regn = prof.get("regnskap") or {}
        risk = prof.get("risk") or {}

        # -----------------------
        # 1) Organisasjonsinfo
        # -----------------------
        st.markdown("### Organisation")
        st.write(
            f"**{org.get('navn', 'N/A')}** "
            f"({org.get('organisasjonsform', 'N/A')}) – "
            f"orgnr {org.get('orgnr', 'N/A')}"
        )
        st.write(
            f"{org.get('kommune', 'N/A')} {org.get('postnummer', '')}, "
            f"{org.get('land', 'N/A')}"
        )
        st.write(
            f"Næringskode: {org.get('naeringskode1', 'N/A')} "
            f"{org.get('naeringskode1_beskrivelse', '')}"
        )

        # -----------------------
        # 2) Nøkkeltall (metrics)
        # -----------------------
        def fmt_mnok(value):
            if value is None:
                return "–"
            try:
                return f"{value/1_000_000:,.1f} MNOK".replace(",", " ")
            except Exception:
                return str(value)

        if regn and regn.get("regnskapsår") is not None:
            year = regn.get("regnskapsår")

            st.markdown(f"### Key figures ({year})")

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric(
                    label="Turnover",
                    value=fmt_mnok(regn.get("sum_driftsinntekter")),
                )

            with col2:
                st.metric(
                    label="Net result",
                    value=fmt_mnok(regn.get("aarsresultat")),
                )

            with col3:
                st.metric(
                    label="Equity",
                    value=fmt_mnok(regn.get("sum_egenkapital")),
                )

            with col4:
                eq_ratio = risk.get("equity_ratio")
                eq_val = (
                    "–"
                    if eq_ratio is None
                    else f"{eq_ratio*100:,.1f} %".replace(",", " ")
                )
                st.metric(label="Equity ratio", value=eq_val)

            # -----------------------
            # 3) Resultat & balanse-tabeller
            # -----------------------
            st.markdown("#### Profit and loss")

            pl_data = {
                "Metric": [
                    "Sales revenue",
                    "Total operating income",
                    "Wage costs",
                    "Total operating costs",
                    "Operating result",
                    "Financial income",
                    "Financial costs",
                    "Net financials",
                    "Ordinary result before tax",
                    "Tax cost (ordinary)",
                    "Extraordinary items",
                    "Tax on extraordinary result",
                    "Annual result",
                    "Total result",
                ],
                "Value": [
                    fmt_mnok(regn.get("salgsinntekter")),
                    fmt_mnok(regn.get("sum_driftsinntekter")),
                    fmt_mnok(regn.get("loennskostnad")),
                    fmt_mnok(regn.get("sum_driftskostnad")),
                    fmt_mnok(regn.get("driftsresultat")),
                    fmt_mnok(regn.get("sum_finansinntekt")),
                    fmt_mnok(regn.get("sum_finanskostnad")),
                    fmt_mnok(regn.get("netto_finans")),
                    fmt_mnok(regn.get("ordinaert_resultat_foer_skattekostnad")),
                    fmt_mnok(regn.get("ordinaert_resultat_skattekostnad")),
                    fmt_mnok(regn.get("ekstraordinaere_poster")),
                    fmt_mnok(regn.get("skattekostnad_ekstraord_resultat")),
                    fmt_mnok(regn.get("aarsresultat")),
                    fmt_mnok(regn.get("totalresultat")),
                ],
            }
            st.table(pd.DataFrame(pl_data))  # statisk tabell [web:50][web:53]

            st.markdown("#### Balance sheet")

            bal_data = {
                "Metric": [
                    "Total assets",
                    "Current assets",
                    "Fixed assets",
                    "Inventory",
                    "Receivables",
                    "Investments",
                    "Cash and bank",
                    "Goodwill",
                    "Equity",
                    "Paid-in equity",
                    "Retained earnings",
                    "Total debt",
                    "Short-term debt",
                    "Long-term debt",
                ],
                "Value": [
                    fmt_mnok(regn.get("sum_eiendeler")),
                    fmt_mnok(regn.get("sum_omloepsmidler")),
                    fmt_mnok(regn.get("sum_anleggsmidler")),
                    fmt_mnok(regn.get("sum_varer")),
                    fmt_mnok(regn.get("sum_fordringer")),
                    fmt_mnok(regn.get("sum_investeringer")),
                    fmt_mnok(regn.get("sum_bankinnskudd_og_kontanter")),
                    fmt_mnok(regn.get("goodwill")),
                    fmt_mnok(regn.get("sum_egenkapital")),
                    fmt_mnok(regn.get("sum_innskutt_egenkapital")),
                    fmt_mnok(regn.get("sum_opptjent_egenkapital")),
                    fmt_mnok(regn.get("sum_gjeld")),
                    fmt_mnok(regn.get("sum_kortsiktig_gjeld")),
                    fmt_mnok(regn.get("sum_langsiktig_gjeld")),
                ],
            }
            st.table(pd.DataFrame(bal_data))

            # -----------------------
            # 4) Enkel risikovurdering
            # -----------------------
            st.markdown("### Simple risk assessment")
            st.write(f"Score: **{risk.get('score', 0)}**")
            reasons = risk.get("reasons") or []
            if reasons:
                for r in reasons:
                    st.write(f"- {r}")
            else:
                st.write("No specific risk factors identified by the simple model.")
        else:
            st.info("No open financial statements available for this organisation.")

        # -----------------------
        # 5) Rå JSON (debug)
        # -----------------------
        st.markdown("### Raw /org response")
        st.json(prof)

        st.markdown("### Raw /org/{orgnr}/licenses response")
        st.json(lic or {"orgnr": selected_orgnr, "licenses": []})
