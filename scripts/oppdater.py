"""
Oppdater modellporteføljen: hent priser, beregn avkastning, skriv CSV-er.
Kjøres daglig (manuelt eller via GitHub Actions).
"""

import pandas as pd
import yfinance as yf
from pathlib import Path

# --- Konfigurasjon ---
BENCHMARK = "OSEBX.OL"
HISTORIKK = "6mo"  # hvor langt tilbake vi henter priser

# Finn stien til data-mappa (uansett hvor scriptet kjøres fra)
ROT = Path(__file__).parent.parent
DATA = ROT / "data"


def les_holdings():
    """Les holdings.csv og konverter datoer."""
    holdings = pd.read_csv(DATA / "holdings.csv")
    holdings["inn_dato"] = pd.to_datetime(holdings["inn_dato"])
    holdings["ut_dato"] = pd.to_datetime(holdings["ut_dato"])
    return holdings


def hent_priser(tickere):
    """Last ned sluttkurser for aksjer + benchmark."""
    alle = tickere + [BENCHMARK]
    priser = yf.download(alle, period=HISTORIKK, auto_adjust=True, progress=False)["Close"]
    priser = priser.ffill()
    return priser


def bygg_eid_matrise(holdings, priser, tickere):
    """Lag en 0/1-matrise: rader = dager, kolonner = tickere, verdi = eid den dagen."""
    eid = pd.DataFrame(0, index=priser.index, columns=tickere)
    
    for _, rad in holdings.iterrows():
        ticker = rad["ticker"]
        inn = rad["inn_dato"]
        ut = rad["ut_dato"] if pd.notna(rad["ut_dato"]) else priser.index[-1]
        
        # Første eierdag = første handelsdag etter inn_dato
        handelsdager_etter = priser.index[priser.index > inn]
        if len(handelsdager_etter) == 0:
            continue
        forste_eierdag = handelsdager_etter[0]
        
        eid.loc[forste_eierdag:ut, ticker] = 1
    
    return eid


def beregn_performance(priser, eid, tickere):
    """Regn ut daglig og kumulativ avkastning for portefølje + benchmark."""
    daglig = priser.pct_change(fill_method=None)
    
    # Portefølje: likevektet snitt av eide aksjer per dag
    aksje_avk = daglig[tickere]
    vektet_sum = (aksje_avk * eid).sum(axis=1)
    antall_eid = eid.sum(axis=1)
    portefolje = vektet_sum / antall_eid
    
    # Sett sammen
    perf = pd.DataFrame({
        "portefolje": portefolje,
        "osebx": daglig[BENCHMARK]
    })
    
    # Klipp fra første eierdag, sett første rad til 0
    forste_eierdag = eid.sum(axis=1).gt(0).idxmax()
    perf = perf.loc[forste_eierdag:].copy()
    perf.iloc[0] = 0
    
    # Legg til kumulativ avkastning (som prosent)
    perf["portefolje_kumulativ"] = ((1 + perf["portefolje"]).cumprod() - 1) * 100
    perf["osebx_kumulativ"] = ((1 + perf["osebx"]).cumprod() - 1) * 100
    
    return perf


def beregn_per_aksje(holdings, priser):
    """Total avkastning + siste ukes avkastning per aksje siden inntak."""
    rader = []
    for _, rad in holdings.iterrows():
        ticker = rad["ticker"]
        inn = rad["inn_dato"]
        ut = rad["ut_dato"] if pd.notna(rad["ut_dato"]) else priser.index[-1]
        
        kjopskurs = priser[ticker].asof(inn)
        sistekurs = priser[ticker].asof(ut)
        total = (sistekurs / kjopskurs - 1) * 100
        
        # Siste ukes avkastning: sluttkurs 5 handelsdager tilbake
        # Vi bruker index-posisjon slik at helger/helligdager håndteres automatisk
        priser_ticker = priser[ticker].dropna()
        priser_frem_til_ut = priser_ticker.loc[:ut]
        
        if len(priser_frem_til_ut) >= 6:
            kurs_uke_siden = priser_frem_til_ut.iloc[-6]
            uke_avk = (sistekurs / kurs_uke_siden - 1) * 100
        else:
            uke_avk = None  # ikke nok historikk (nylig inntatt aksje)
        
        rader.append({
            "ticker": ticker,
            "inn_dato": inn.date(),
            "ut_dato": ut.date() if pd.notna(rad["ut_dato"]) else "",
            "kjopskurs": round(kjopskurs, 2),
            "sistekurs": round(sistekurs, 2),
            "avkastning_pct": round(total, 2),
            "uke_avkastning_pct": round(uke_avk, 2) if uke_avk is not None else ""
        })
    
    return pd.DataFrame(rader)


def main():
    print("Leser holdings...")
    holdings = les_holdings()
    tickere = holdings["ticker"].unique().tolist()
    print(f"  {len(tickere)} tickere: {', '.join(tickere)}")
    
    print("Henter priser fra yfinance...")
    priser = hent_priser(tickere)
    print(f"  {len(priser)} handelsdager, siste: {priser.index[-1].date()}")
    
    print("Bygger eid-matrise...")
    eid = bygg_eid_matrise(holdings, priser, tickere)
    
    print("Beregner performance...")
    perf = beregn_performance(priser, eid, tickere)
    
    print("Beregner per-aksje avkastning...")
    per_aksje = beregn_per_aksje(holdings, priser)
    
    print("Skriver CSV-er...")
    perf.to_csv(DATA / "performance.csv", index_label="dato")
    per_aksje.to_csv(DATA / "per_aksje.csv", index=False)
    
    print("Ferdig.")
    print(f"\nSiste dag portefølje: {perf['portefolje_kumulativ'].iloc[-1]:.2f}%")
    print(f"Siste dag OSEBX:      {perf['osebx_kumulativ'].iloc[-1]:.2f}%")


if __name__ == "__main__":
    main()