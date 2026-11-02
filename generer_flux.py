
import re
from datetime import datetime, timezone
from email.utils import format_datetime
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

SEARCH_URL = (
    "https://choisirleservicepublic.gouv.fr/"
    "nos-offres/filtres/mot-cles/"
    "cartogrpahe%20g%C3%A9omaticien/"
)

SITE = "https://choisirleservicepublic.gouv.fr/"
OUTPUT = "public/feed.xml"

MONTHS = {
    "janvier": 1, "février": 2, "fevrier": 2,
    "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "aout": 8,
    "septembre": 9, "octobre": 10, "novembre": 11,
    "décembre": 12, "decembre": 12,
}


def publication_date(text):
    match = re.search(
        r"En ligne depuis le\s+(\d{1,2})\s+"
        r"([A-Za-zÀ-ÿ]+)\s+(\d{4})",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None

    day, month_name, year = match.groups()
    month = MONTHS.get(month_name.lower())
    if not month:
        return None

    try:
        date = datetime(int(year), month, int(day), tzinfo=timezone.utc)
        return format_datetime(date, usegmt=True)
    except ValueError:
        return None


def main():
    response = requests.get(
        SEARCH_URL,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; VeilleRSS/1.0)"
            )
        },
        timeout=45,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    offers = []
    seen = set()

    # Les offres du site utilisent des URL /offre-emploi/...
    for link in soup.select('a[href*="/offre-emploi/"]'):
        href = urljoin(SITE, link.get("href", ""))
        title = link.get_text(" ", strip=True)

        if not title or href in seen:
            continue

        # Écarte les liens qui ne sont pas des offres du site.
        if not href.startswith(SITE + "offre-emploi/"):
            continue

        seen.add(href)

        # Recherche la date de publication dans le bloc de l'offre.
        card_text = title
        for parent in link.parents:
            if getattr(parent, "name", None) in ("body", "html"):
                break

            text = parent.get_text(" ", strip=True)
            if (
                "En ligne depuis le" in text
                and len(text) < 1800
            ):
                card_text = text
                break

        item = {
            "title": title,
            "link": href,
            "description": card_text[:1200],
        }

        pub_date = publication_date(card_text)
        if pub_date:
            item["pubDate"] = pub_date

        offers.append(item)

    if not offers:
        raise RuntimeError(
            "Aucune offre trouvée. Le site a peut-être changé "
            "sa structure HTML ou bloqué la requête. "
            "Le flux précédent ne sera pas publié."
        )

    # RSS 2.0 : chaque offre devient un élément du flux.
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = (
        "Veille emploi — Cartographe et géomaticien"
    )
    ET.SubElement(channel, "link").text = SEARCH_URL
    ET.SubElement(channel, "description").text = (
        "Offres de Choisir le service public correspondant "
        "à la recherche cartographe et géomaticien."
    )
    ET.SubElement(channel, "language").text = "fr-FR"
    ET.SubElement(channel, "lastBuildDate").text = (
        format_datetime(datetime.now(timezone.utc), usegmt=True)
    )

    for offer in offers:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = offer["title"]
        ET.SubElement(item, "link").text = offer["link"]
        ET.SubElement(item, "guid", {"isPermaLink": "true"}).text = (
            offer["link"]
        )
        ET.SubElement(item, "description").text = (
            offer["description"]
        )
        if offer.get("pubDate"):
            ET.SubElement(item, "pubDate").text = offer["pubDate"]

    import os
    os.makedirs("public", exist_ok=True)

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")
    tree.write(
        OUTPUT,
        encoding="utf-8",
        xml_declaration=True,
    )

    print(f"Flux RSS créé : {OUTPUT}")
    print(f"Nombre d'offres récupérées : {len(offers)}")


if __name__ == "__main__":
    main()
