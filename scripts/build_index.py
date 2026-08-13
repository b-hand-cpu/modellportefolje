"""
Bygger index.html for modellportefoljen.
Leser stocks/*.md, henter nøkkeltall fra yfinance,
renderer én forside med accordion per aksje.
"""
from pathlib import Path
import yaml
import markdown

STOCKS_DIR = Path("stocks")


def parse_stock_file(path: Path) -> dict:
    """
    Leser en .md-fil med YAML-frontmatter og markdown-body.
    Returnerer dict med metadata + rendret HTML.
    """
    text = path.read_text(encoding="utf-8")

    # Frontmatter ligger mellom to '---' på starten av fila
    if not text.startswith("---"):
        raise ValueError(f"{path} mangler frontmatter")

    _, frontmatter_raw, body = text.split("---", 2)
    metadata = yaml.safe_load(frontmatter_raw)
    body_html = markdown.markdown(body.strip())

    return {
        **metadata,
        "body_html": body_html,
    }


import yfinance as yf


FALLBACK_STATS = {
    "kurs": "—",
    "markedsverdi": "—",
    "pe": "—",
    "dividend_yield": "—",
    "hoy_52u": "—",
    "lav_52u": "—",
}


def fetch_key_stats(ticker: str, retries: int = 2) -> dict:
    """
    Henter nøkkeltall fra yfinance for én ticker.
    Returnerer dict med felt formatert som strings (klar for HTML).
    Manglende felt, timeout eller andre yfinance-feil gir graceful
    fallback til '—' i stedet for å krasje hele pipelinen.
    """
    info = None
    for attempt in range(1, retries + 1):
        try:
            info = yf.Ticker(ticker).info
            break
        except Exception as e:
            print(f"  Advarsel: feil ved henting av {ticker} (forsøk {attempt}/{retries}): {e}")

    if not info:
        print(f"  Fikk ikke data for {ticker}, bruker '—' for alle nøkkeltall.")
        return dict(FALLBACK_STATS)

    def get(key, fmt=None):
        val = info.get(key)
        if val is None:
            return "—"
        try:
            if fmt == "price":
                return f"{val:.2f}"
            if fmt == "pct":
                return f"{val:.2f} %"
            if fmt == "mcap":
                # Markedsverdi i milliarder NOK
                return f"{val / 1e9:.1f} mrd"
            return str(val)
        except (TypeError, ValueError):
            return "—"

    return {
        "kurs": get("currentPrice", "price"),
        "markedsverdi": get("marketCap", "mcap"),
        "pe": get("trailingPE", "price"),
        "dividend_yield": get("dividendYield", "pct"),
        "hoy_52u": get("fiftyTwoWeekHigh", "price"),
        "lav_52u": get("fiftyTwoWeekLow", "price"),
    }


from datetime import datetime
from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = Path("templates")
OUTPUT_FILE = Path("index.html")


def build_all() -> None:
    """Leser alle stocks/*.md, henter tall, renderer index.html."""
    stock_files = sorted(STOCKS_DIR.glob("*.md"))
    stocks = []
    for path in stock_files:
        print(f"Prosesserer {path.name}...")
        stock = parse_stock_file(path)
        stock["stats"] = fetch_key_stats(stock["ticker"])
        stocks.append(stock)

    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
    template = env.get_template("index.html.j2")
    html = template.render(
        stocks=stocks,
        build_time=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )

    OUTPUT_FILE.write_text(html, encoding="utf-8")
    print(f"\nSkrev {OUTPUT_FILE} med {len(stocks)} aksjer.")


if __name__ == "__main__":
    build_all()