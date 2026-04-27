# Symulator Inwestycji Walutowej (NBP)

Zadanie rekrutacyjne — automatyzacja analizy inwestycji w trzy waluty na danych historycznych z API NBP. Aplikacja wycenia portfel buy-and-hold dzień po dniu, liczy KPI ryzyka (drawdown, zmienność), generuje raport jednostronicowy oraz zapisuje audit-trail każdego uruchomienia.

## Stos

- **Python 3.10+**
- `pandas` — szeregi czasowe i wycena
- `requests` — klient HTTP do NBP (HTTPS, timeout, retry z backoffem)
- `plotly` — wykresy (rangeslider, crosshair, waterfall attribution)
- `streamlit` — interaktywny dashboard
- `openpyxl` — eksport Excel
- `pytest` + `ruff` + `mypy` — testy, lint, typecheck
- `Docker` — kontener gotowy do deployu

## Instalacja

```bash
python3 -m pip install -r requirements.txt          # tylko runtime
python3 -m pip install -e ".[dev,report]"           # + testy, lint, eksport PNG/PDF
```

## Uruchomienie

**Dashboard interaktywny:**

```bash
streamlit run dashboard.py
# albo:
python3 main.py
# albo (Docker):
docker build -t portfolio-sim . && docker run -p 8501:8501 portfolio-sim
```

**CLI — generowanie raportu jednostronicowego + audit record:**

```bash
python3 -m portfolio_sim \
    --amount 1000 \
    --start 2026-03-03 \
    --allocation USD:30,EUR:40,HUF:30 \
    --days 30 \
    --output report.png
```

`--output` akceptuje rozszerzenia `.png`, `.pdf`, `.svg` (wymaga `kaleido`) lub `.html` (zawsze).
Każde uruchomienie zapisuje JSON manifest do `runs/{timestamp}_{hash}.json` (wyłącz flagą `--no-audit`).

**Testy i jakość kodu:**

```bash
make test           # pytest + coverage
make lint           # ruff
make typecheck      # mypy --strict
```

## Architektura

```
portfolio_sim/
├── allocation.py     # Allocation — frozen dataclass z walidacją
├── nbp_client.py     # NBPClient — HTTPS, retry, timeout
├── portfolio.py      # PortfolioSimulator — pipeline fetch → align → price → enrich
├── metrics.py        # PortfolioMetrics + compute_metrics()
├── visualizer.py     # buildery wykresów Plotly
├── report.py         # raport jednostronicowy (PNG/PDF/SVG/HTML)
├── audit.py          # zapis JSON manifestu każdego uruchomienia
└── __main__.py       # CLI (argparse)

dashboard.py          # warstwa Streamlit
main.py               # wrapper uruchamiający dashboard
Dockerfile            # obraz produkcyjny (non-root, healthcheck)
runs/                 # audit-trail JSON (tworzone przy uruchomieniu)
tests/                # 51 testów jednostkowych (97% coverage)
```

Pipeline jest świadomie podzielony na cztery niezależne kroki w `PortfolioSimulator`:

1. **`_fetch_basket`** — pobiera kursy dla każdej waluty.
2. **`_align_to_calendar`** — dolewa kalendarz dzienny i forward-fillem łata weekendy/święta.
3. **`_price_holdings`** — przelicza alokację PLN na jednostki walut po kursie z dnia 1 i wycenia każdy kolejny dzień.
4. **`_enrich_with_metrics`** — dokleja kolumny `total_value`, `cumulative_pnl`, `daily_change`, `drawdown_pct`.

Każdy krok jest `@staticmethod` bez stanu, co czyni je trywialnie testowalnymi w izolacji.

## UX wykresów

Wszystkie wykresy czasowe mają:

- **Crosshair** (spike lines) na obu osiach — łatwy odczyt wartości w danym dniu
- **Custom hover template** z formatowaniem PLN (`1,015.32 PLN` zamiast `1015.32`)
- **Annotacje best/worst day** strzałkami na głównym wykresie wartości
- **Modebar** Plotly: zoom prostokątem, pan, reset, eksport PNG (skala 2x)
- **Spójna typografia** (system font stack) i lekka siatka (`#ECECEC`)

Dodatkowo:

- **Waterfall attribution** — pokazuje wkład każdej waluty w łączny P&L portfela
- **Donut** z 55% otworem i białymi separatorami — czytelny rozkład alokacji na dzień 1 i N
- **Download CSV / Excel** w UI — surowe dane dla zespołu reportowego

## Decyzje projektowe

- **Forward-fill na weekendy.** NBP nie publikuje kursów w soboty/niedziele i święta. Przyjęto konwencję rynkową: portfel utrzymuje wycenę z ostatniego dnia roboczego. `BUSINESS_DAY_LOOKBACK = 7` w `NBPClient` gwarantuje, że nawet inwestycja rozpoczęta w sobotę po długim weekendzie znajdzie kurs odniesienia.
- **30 dni kalendarzowych, nie sesyjnych.** Spec mówi *„przechowywane przez okres 30 dni"* — interpretowane dosłownie jako kalendarz.
- **Volatility nie jest annualizowana.** Próbka 30-dniowa nie uzasadnia skalowania `√252`. Raportowana jest surowa zmienność dziennych stóp zwrotu w oknie obserwacji.
- **`daily_change` w dniu 1 to NaN, nie 0.** Brak poprzedniej obserwacji = brak zmiany. Zerowanie sztucznie zaburzało statystyki best/worst day.
- **Retry z back-offem** na kodach 429/5xx — zewnętrzne API potrafi mrugnąć.
- **HTTPS** zamiast HTTP, timeout `10s` na każdym requeście.
- **Cache `@st.cache_data`** w dashboardzie — historia NBP jest niezmienna.
- **Audit trail z deterministycznym hashem inputów** — dwa identyczne uruchomienia dają identyczny hash, co pozwala wykryć duplikaty i daje audytorom stabilny identyfikator każdej symulacji.
- **Docker non-root + healthcheck** — gotowe do deploymentu w środowisku konteneryzowanym (Kubernetes, ECS).

## Spełnienie wymagań zadania

| Wymaganie z PDF | Realizacja |
|---|---|
| Kwota i data jako parametr | `--amount`, `--start` (CLI) + sidebar (UI) |
| Procentowy podział walut jako parametr | `--allocation USD:30,EUR:40,HUF:30` + number inputs + presety w UI |
| 1000 PLN na 3 waluty, 30 dni hold | Wartości domyślne |
| Średni kurs (bez bid/ask) | NBP table A — `mid` |
| Dashboard z wykresami | 6 wykresów Plotly + 12 KPI + audit reference |
| Procentowy rozkład start/koniec | Wykresy kołowe „Day 1" vs „Day N" |
| Saldo narastająco + zmiana dzienna | `total_value` + `daily_change` + drawdown + attribution |
| Raport 1 strona / 1 slajd | `python -m portfolio_sim --output report.pdf` |

### KPI ryzyka (banking-grade)

Poza standardowymi miarami zwrotu liczone są metryki ryzyka stosowane na biurkach FX:

- **Sharpe ratio** (raw, daily, rf=0) — zwrot na jednostkę zmienności całkowitej.
- **Sortino ratio** — jak Sharpe, ale w mianowniku tylko odchylenie strat (downside deviation), zgodnie z konwencją CFA.
- **VaR 95% (1d, historyczna)** — empirycznie wyznaczony 5-procentowy kwantyl strat dziennych. Raportowany jako dodatnia kwota PLN (banking convention).
- **CVaR 95% / Expected Shortfall** — średnia ze strat poniżej progu VaR. Basel III FRTB zastąpiło VaR przez ES jako miarę kapitału na ryzyko rynkowe (sub-addytywność, lepsze ujęcie tail risk).

Sharpe i Sortino świadomie **nie są annualizowane** — okno 30-dniowe jest zbyt krótkie, by skalowanie `√252` było statystycznie sensowne. To samo dotyczy zmienności.

## Testy

58 testów jednostkowych pokrywających 96% kodu pakietu:

- walidację `Allocation` (suma, ujemne wagi, niepoprawne kody, `FrozenInstanceError`)
- klienta NBP (parsing JSON, retry/timeout, błędy 404/sieć/pusty payload, walidacja okna)
- pipeline portfela (forward-fill weekendów, poprawność wyceny, drawdown, NaN w dniu 1)
- KPI (drawdown, volatility nieannualizowana, best/worst day pomijające dzień 1)
- audit trail (deterministyczny hash, JSON well-formed, tworzenie zagnieżdżonych katalogów)
- buildery wykresów Plotly (struktura figur, liczba traces, anotacje best/worst)
- raport jednostronicowy (4 panele 2×2, eksport HTML, tworzenie katalogów)
- CLI (full pipeline z stub NBP, exit codes na błędach, parsery argumentów)

```bash
$ make test
============================== 58 passed in 0.32s ==============================
```

## CI

`.github/workflows/ci.yml` uruchamia na każdym pushu/PR:

- `ruff check` — lint
- `mypy --strict` — typecheck
- `pytest` z coverage (próg 80%)
- Matrix: Python 3.10, 3.11, 3.12

## Audit trail — przykładowy manifest

```json
{
  "schema_version": 1,
  "recorded_at_utc": "2026-04-25T23:16:14.497547+00:00",
  "input_hash": "f1f600ce8b16",
  "inputs": {
    "initial_amount_pln": 1000.0,
    "allocation": { "USD": 0.3, "EUR": 0.4, "HUF": 0.3 },
    "start_date": "2026-03-03",
    "end_date": "2026-04-02",
    "holding_days": 30
  },
  "metrics": {
    "final_value": 1006.61,
    "total_return_pct": 0.66,
    "best_day": "2026-03-31",
    "worst_day": "2026-03-09",
    "max_drawdown_pct": -0.51,
    "realized_volatility_pct": 0.13
  }
}
```
