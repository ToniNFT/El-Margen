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
import json
import logging
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, urlparse

import feedparser
import requests
from jinja2 import Environment, FileSystemLoader

BASE_DIR = Path(__file__).resolve().parent
FEEDS_FILE = BASE_DIR / "feeds.txt"
TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_FILE = OUTPUT_DIR / "index.html"
OEMBED_CACHE_FILE = BASE_DIR / ".oembed_cache.json"

SITE_TITLE = "El Margen"
SITE_TAGLINE = "Conspiraciones. Contrainformación. Paranoias..."
ENTRIES_PER_FEED = 1       # cuántas entradas mostrar de cada blog seguido
MAX_TOTAL_ENTRIES = 300     # límite total de entradas en la página
OEMBED_TIMEOUT = 8         # segundos
OEMBED_CACHE_DAYS = 14     # cuánto confiar en un resultado de oEmbed guardado

# Plataformas reconocidas vía oEmbed: (fragmento de dominio, endpoint, tipo)
# "cualquier plataforma de vídeo/audio" que hable oEmbed se puede añadir aquí.
OEMBED_PROVIDERS: list[tuple[str, str, str]] = [
    ("youtube.com", "https://www.youtube.com/oembed?format=json&url={url}", "video"),
    ("youtu.be", "https://www.youtube.com/oembed?format=json&url={url}", "video"),
    ("vimeo.com", "https://vimeo.com/api/oembed.json?url={url}", "video"),
    ("dailymotion.com", "https://www.dailymotion.com/services/oembed?url={url}", "video"),
    ("ivoox.com", "https://www.ivoox.com/services/oembed.json?url={url}", "audio"),
    ("soundcloud.com", "https://soundcloud.com/oembed?format=json&url={url}", "audio"),
    ("spotify.com", "https://open.spotify.com/oembed?url={url}", "audio"),
]

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
    media_kind: str = "none"          # "video" | "audio" | "image" | "none"
    media_src: str | None = None      # URL del iframe, para vídeo/audio
    media_height: int | None = None   # alto sugerido por el proveedor (audio)
    media_image: str | None = None    # URL de imagen, para el resto de feeds


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


def load_oembed_cache() -> dict:
    if OEMBED_CACHE_FILE.exists():
        try:
            return json.loads(OEMBED_CACHE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            log.warning("Caché de oEmbed ilegible, empiezo de cero.")
    return {}


def save_oembed_cache(cache: dict) -> None:
    try:
        OEMBED_CACHE_FILE.write_text(json.dumps(cache), encoding="utf-8")
    except OSError as exc:
        log.warning("No pude guardar la caché de oEmbed: %s", exc)


def fetch_oembed(entry_link: str, endpoint_template: str) -> tuple[str | None, int | None]:
    api_url = endpoint_template.format(url=quote(entry_link, safe=""))
    try:
        resp = requests.get(api_url, timeout=OEMBED_TIMEOUT, headers={"User-Agent": "PlanetElMargen/1.0"})
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        log.warning("oEmbed falló para %s: %s", entry_link, exc)
        return None, None

    html = data.get("html", "")
    match = re.search(r'src="([^"]+)"', html)
    if not match or not match.group(1).startswith("https://"):
        return None, None
    return match.group(1), data.get("height")


def get_media_via_oembed(entry_link: str, endpoint_template: str, cache: dict) -> tuple[str | None, int | None]:
    now = dt.datetime.now(dt.timezone.utc)
    cached = cache.get(entry_link)
    if cached:
        fetched_at = dt.datetime.fromisoformat(cached["fetched"])
        if now - fetched_at < dt.timedelta(days=OEMBED_CACHE_DAYS):
            return cached.get("src"), cached.get("height")

    src, height = fetch_oembed(entry_link, endpoint_template)
    cache[entry_link] = {"src": src, "height": height, "fetched": now.isoformat()}
    return src, height


def extract_thumbnail(raw_entry) -> str | None:
    media_thumb = raw_entry.get("media_thumbnail")
    if media_thumb:
        return media_thumb[0].get("url")

    for media in raw_entry.get("media_content", []):
        if media.get("medium") == "image" or media.get("type", "").startswith("image"):
            return media.get("url")

    for link_info in raw_entry.get("links", []):
        if link_info.get("rel") == "enclosure" and link_info.get("type", "").startswith("image"):
            return link_info.get("href")

    html_source = raw_entry.get("summary", "")
    if not html_source and raw_entry.get("content"):
        html_source = raw_entry["content"][0].get("value", "")
    match = re.search(r'<img[^>]+src="([^"]+)"', html_source)
    return match.group(1) if match else None


def detect_media(entry_link: str, raw_entry, cache: dict) -> tuple[str, str | None, int | None, str | None]:
    domain = urlparse(entry_link).netloc.lower()

    for provider_domain, endpoint, kind in OEMBED_PROVIDERS:
        if provider_domain in domain:
            src, height = get_media_via_oembed(entry_link, endpoint, cache)
            if src:
                return kind, src, height, None
            break  # es una plataforma reconocida pero el oEmbed falló: no seguimos probando

    image = extract_thumbnail(raw_entry)
    if image:
        return "image", None, None, image

    return "none", None, None, None


def fetch_feed(url: str, cache: dict) -> list[Entry]:
    parsed = feedparser.parse(url, request_headers={"User-Agent": "PlanetElMargen/1.0"})
    if parsed.bozo and not parsed.entries:
        log.warning("Feed con problemas, lo salto: %s (%s)", url, parsed.bozo_exception)
        return []

    feed_title = parsed.feed.get("title", url)
    site_url = parsed.feed.get("link", url)

    entries = []
    for raw_entry in parsed.entries[:ENTRIES_PER_FEED]:
        link = raw_entry.get("link", site_url)
        media_kind, media_src, media_height, media_image = detect_media(link, raw_entry, cache)
        entries.append(
            Entry(
                feed_title=feed_title,
                site_url=site_url,
                title=raw_entry.get("title", "(sin título)"),
                link=link,
                summary=clean_summary(raw_entry.get("summary", "")),
                published=to_datetime(raw_entry),
                media_kind=media_kind,
                media_src=media_src,
                media_height=media_height,
                media_image=media_image,
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
            "media_kind": e.media_kind,
            "media_src": e.media_src,
            "media_height": e.media_height,
            "media_image": e.media_image,
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
    cache = load_oembed_cache()
    all_entries: list[Entry] = []
    for url in urls:
        try:
            all_entries.extend(fetch_feed(url, cache))
        except Exception as exc:  # no queremos que un feed roto tumbe todo el proceso
            log.warning("Error en %s: %s", url, exc)
    save_oembed_cache(cache)
    build_site(all_entries)


if __name__ == "__main__":
    main()

