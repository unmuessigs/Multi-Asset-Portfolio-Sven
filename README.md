# ⬢ ATLAS Terminal

**Multi-Asset Portfolio & Derivatives Analytics Platform**

Eine modulare, institutionell anmutende Risk-Management-Plattform (Python + Streamlit +
Plotly) für Aktien, ETFs, Futures, Optionen, Anleihen und Cash. Dark-Mode-Terminal-UI
mit großen KPI-Karten, Heatmaps und interaktiven Charts — inspiriert von Bloomberg,
TradingView, Interactive Brokers und BlackRock Aladdin.

---

## Schnellstart

```bash
# 1. (optional) virtuelles Environment
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. Abhängigkeiten installieren
pip install -r requirements.txt

# 3. App starten
streamlit run app.py
```

Beim ersten Start wird automatisch ein diversifiziertes **Demo-Portfolio** geladen, damit
alle Dashboards sofort gefüllt sind. Über die Sidebar lässt sich zwischen **Live-Daten
(yfinance)** und **Simulationsdaten (offline)** umschalten, das Portfolio leeren oder das
Demo neu laden.

---

## Dashboards

| # | Dashboard | Inhalt |
|---|-----------|--------|
| 1 | **Portfolio Overview** (`app.py`) | Gesamtwert, Tages-P&L, Gesamtrendite, Volatilität, Asset Allocation (Donut), Value-over-Time, Performance, Positionstabelle |
| 2 | **Risk Analytics** | Portfolio-Greeks (Δ Γ V Θ ρ), VaR (parametrisch & historisch), CVaR/Expected Shortfall, Beta, Sharpe, Greeks-Heatmap, Risk-Contribution, VaR-Verteilung |
| 3 | **Options Analytics** | Black-Scholes-Preis, Implied Volatility, alle Greeks, Payoff-/P&L-Diagramm, Vola-Sensitivität, Time-Decay, 3D-Greeks-Surface |
| 4 | **Scenario Analysis** | Stress-Shocks (Markt ±%, Vola, Zinsen, Zeitablauf), neuer Wert, Greek-Änderungen, VaR-Änderung, P&L-Sweep, Preset-Stresstests |
| 5 | **Bond Analytics** | Duration, Modified Duration, Convexity, YTM, Current Yield, Yield-Curve, Duration-Contribution, Zins-Sensitivität, DV01 |
| 6 | **Portfolio Builder** | GUI zum Hinzufügen/Entfernen von Positionen je Assetklasse, professionelle Portfolio-Tabelle |

---

## Projektstruktur

```
Multi_Asset-Portfolio/
├── app.py                     # Entry-Point + Dashboard 1 (Overview)
├── requirements.txt
├── .streamlit/config.toml     # Dark-Theme
├── pages/                     # Streamlit-Multipage-Dashboards 2–6
│   ├── 2_Risk_Analytics.py
│   ├── 3_Options_Analytics.py
│   ├── 4_Scenario_Analysis.py
│   ├── 5_Bond_Analytics.py
│   └── 6_Portfolio_Builder.py
├── src/
│   ├── config.py              # Farbschema, Konstanten, Plotly-Layout
│   ├── state.py               # Streamlit-Session-State + Demo-Portfolio + Sidebar
│   ├── pricing/               # Finanzmathematik
│   │   ├── black_scholes.py   #   BSM-Preis, Greeks, Implied Vol
│   │   └── bond_math.py       #   Duration, Convexity, YTM
│   ├── instruments/           # OOP-Klassenhierarchie
│   │   ├── base.py            #   Instrument (ABC), Position, MarketContext
│   │   ├── equity.py          #   Equity, ETF
│   │   ├── option.py          #   Option (Call/Put)
│   │   ├── future.py · bond.py · cash.py
│   ├── data/market_data.py    # yfinance + deterministischer Offline-Fallback
│   ├── portfolio/portfolio.py # Aggregation, Bewertung, Historie
│   ├── analytics/             # risk.py (VaR/CVaR/Beta/Sharpe), scenario.py
│   └── ui/                    # theme.py, components.py (KPI-Karten), charts.py
└── tests/                     # Unit- & Integrationstests
```

## Architektur in einem Satz

`Instrument` weiß, wie sich **eine** Einheit bewertet → `Position` kapselt Menge/Seite/
Einstand → `Portfolio` aggregiert über alle Positionen und baut den `MarketContext` (inkl.
Szenario-Shocks) → `analytics` und `ui` konsumieren das Portfolio. Saubere Trennung von
Bewertung, Daten und Darstellung.

---

## Finanzmodelle (Kurzreferenz)

**Black-Scholes-Merton** (europäische Optionen, mit Dividendenrendite *q*):
Preis und Greeks in Praktiker-Konvention — Vega pro 1 Vol-Punkt, Theta pro Kalendertag,
Rho pro 1 Zinspunkt. Implied Volatility via Brent-Verfahren. Siehe `black_scholes.py`.

**Fixed Income:** Barwert diskontierter Cashflows; Macaulay-/Modified Duration, Convexity,
YTM (Nullstellensuche), Current Yield; Preisänderung als Taylor-2.-Ordnung
(`-ModDur·Δy + ½·Convexity·Δy²`). Siehe `bond_math.py`.

**Risiko:** parametrischer (Varianz-Kovarianz) und historischer VaR, Expected Shortfall,
Beta (Regression auf S&P 500), annualisierter Sharpe, Risk-Contribution aus der
Kovarianzmatrix der Positions-P&L. Siehe `risk.py`.

> **Hinweis QuantLib:** Die Plattform nutzt bewusst eigene, dokumentierte Engines
> (keine harte QuantLib-Abhängigkeit) für maximale Portabilität. QuantLib kann optional
> installiert werden, um Bewertungen gegenzuprüfen (siehe `requirements.txt`).

---

## Tests

```bash
python -m pytest tests/ -q
```

Abgedeckt: BS-Referenzwert (10.4506), Put-Call-Parität, IV-Roundtrip, Bond-Par/YTM/
Duration (inkl. Zero-Coupon = Maturity) sowie Portfolio-, Risiko- und Szenario-Integration
auf deterministischen Offline-Daten.

---

## Daten & Offline-Betrieb

`MarketData` zieht Live-Kurse über **yfinance**. Fällt das Netz aus oder ist ein Symbol
nicht auflösbar, wird transparent auf eine **deterministische GBM-Simulation** (seedbar pro
Ticker) umgeschaltet, sodass die gesamte Plattform offline und in Demos voll funktionsfähig
bleibt. Betroffene Symbole werden in der Sidebar als Simulationsdaten markiert.
```
