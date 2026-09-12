#!/usr/bin/env python3
"""
Planet El Margen — agregador de feeds RSS/Atom autoalojado.

Lee una lista de feeds desde feeds.txt, descarga la entrada más reciente
de cada uno y genera una página HTML estática (output/index.html) al
estilo del widget "Lista de blogs" de Blogger.

Uso:
    python3 planet.py

Pensado para ejecutarse periódicamente vía cron o systemd timer.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import feedparser
from jinja2 import Environment, FileSystemLoader

BASE_DIR = Path(__file__).resolve().parent
FEEDS_FILE = BASE_DIR / "feeds.txt"
TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_FILE = OUTPUT_DIR / "index.html"

SITE_TITLE = "El Margen"
SITE_TAGLINE = "Conspiraciones. Contrainformación. Paranoias..."
ENTRIES_PER_FEED = 1       # cuántas entradas mostrar de cada blog seguido
MAX_TOTAL_ENTRIES = 80     # límite total de entradas en la página

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("planet")


@dataclass
class Entry:
    feed_title: str
    site_url: str
    title: str
    link: str
    summary: str
    published: dt.datetime


def read_feed_list(path: Path) -> list[str]:
    if not path.exists():
        log.error("No encuentro %s — crea el archivo con un feed por línea.", path)
        sys.exit(1)
    urls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def favicon_url(site_url: str) -> str:
    domain = urlparse(site_url).netloc or site_url
    return f"https://www.google.com/s2/favicons?sz=32&domain={domain}"


def to_datetime(entry) -> dt.datetime:
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            return dt.datetime(*value[:6], tzinfo=dt.timezone.utc)
    return dt.datetime.now(dt.timezone.utc)


def clean_summary(raw: str, max_chars: int = 220) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + "…"
    return text


def fetch_feed(url: str) -> list[Entry]:
    parsed = feedparser.parse(url, request_headers={"User-Agent": "PlanetElMargen/1.0"})
    if parsed.bozo and not parsed.entries:
        log.warning("Feed con problemas, lo salto: %s (%s)", url, parsed.bozo_exception)
        return []

    feed_title = parsed.feed.get("title", url)
    site_url = parsed.feed.get("link", url)

    entries = []
    for raw_entry in parsed.entries[:ENTRIES_PER_FEED]:
        entries.append(
            Entry(
                feed_title=feed_title,
                site_url=site_url,
                title=raw_entry.get("title", "(sin título)"),
                link=raw_entry.get("link", site_url),
                summary=clean_summary(raw_entry.get("summary", "")),
                published=to_datetime(raw_entry),
            )
        )
    return entries


def relative_spanish(published: dt.datetime, now: dt.datetime) -> str:
    delta = now - published
    seconds = delta.total_seconds()
    if seconds < 3600:
        return "Hace unos minutos"
    if seconds < 86400:
        hours = int(seconds // 3600)
        return "Hace 1 hora" if hours == 1 else f"Hace {hours} horas"
    days = delta.days
    if days < 7:
        return "Hace 1 día" if days == 1 else f"Hace {days} días"
    if days < 30:
        weeks = days // 7
        return "Hace 1 semana" if weeks == 1 else f"Hace {weeks} semanas"
    if days < 365:
        months = days // 30
        return "Hace 1 mes" if months == 1 else f"Hace {months} meses"
    years = days // 365
    return "Hace 1 año" if years == 1 else f"Hace {years} años"


def build_site(entries: list[Entry]) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    entries.sort(key=lambda e: e.published, reverse=True)
    entries = entries[:MAX_TOTAL_ENTRIES]

    view = [
        {
            "feed_title": e.feed_title,
            "title": e.title,
            "link": e.link,
            "summary": e.summary,
            "favicon": favicon_url(e.site_url),
            "relative_time": relative_spanish(e.published, now),
        }
        for e in entries
    ]

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    template = env.get_template("index.html.jinja")
    html = template.render(
        site_title=SITE_TITLE,
        site_tagline=SITE_TAGLINE,
        entries=view,
        generated_at=now.strftime("%d/%m/%Y %H:%M UTC"),
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(html, encoding="utf-8")

    if STATIC_DIR.exists():
        shutil.copy(STATIC_DIR / "style.css", OUTPUT_DIR / "style.css")

    log.info("Generado %s con %d entradas.", OUTPUT_FILE, len(view))


def main() -> None:
    urls = read_feed_list(FEEDS_FILE)
    log.info("Leyendo %d feeds...", len(urls))
    all_entries: list[Entry] = []
    for url in urls:
        try:
            all_entries.extend(fetch_feed(url))
        except Exception as exc:  # no queremos que un feed roto tumbe todo el proceso
            log.warning("Error en %s: %s", url, exc)
    build_site(all_entries)


if __name__ == "__main__":
    main()
