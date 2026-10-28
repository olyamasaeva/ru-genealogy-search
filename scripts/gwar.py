"""«Памяти героев Великой войны 1914–1918» (gwar.mil.ru): поиск карточек потерь, госпиталей, наград.

Запуск:
  python3 gwar.py person --surname Фамилия [--given Имя] [--patronymic Отчество] [--gubernia Губерния]
  python3 gwar.py volost --volost Волость --gubernia Губерния [--grep РЕГЕКС]
Общие ключи: --out выдача.json (сырые карточки), --max N (по умолчанию 3000).

volost выгружает все карточки волости: так находятся фамилии, искажённые писарем или индексатором,
которые поиск по фамилии пропускает. --grep фильтрует напечатанные строки, выдача в --out полная.
Строка: ФИО | место | часть | дата и событие | код места | ссылка на карточку.
Если деревня в карточке пустая, сравни код места с карточками, где деревня записана.
Скан открывается с карточки кнопкой «Перейти к просмотру дела/ящика».
"""
import argparse
import http.cookiejar
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://gwar.mil.ru"
KINDS = ["chelovek_donesenie", "chelovek_gospital", "chelovek_nagrazhdenie"]
PAGE_SIZE = 1000
PAUSE_SECONDS = 2
CA_DIR = Path(__file__).resolve().parent / "ca"


def opener():
    context = ssl.create_default_context()
    for pem in sorted(CA_DIR.glob("*.pem")):
        context.load_verify_locations(cafile=str(pem))
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        urllib.request.HTTPSHandler(context=context),
    )


def post(client, fields, offset, size):
    body = {"indices": ["gwar"], "entities": KINDS, "queryFields": fields, "filterFields": {},
            "facetField": None, "from": offset, "size": size, "builderType": "Heroes"}
    request = urllib.request.Request(
        BASE + "/gt_data/?builder=Heroes", data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "Mozilla/5.0",
                 "Referer": BASE + "/heroes/", "Origin": BASE})
    text = client.open(request, timeout=60).read().decode("utf-8")
    if text.lstrip().startswith("<"):
        raise RuntimeError("вместо данных пришла веб-страница: капча или защита, остановись и ищи в браузере")
    data = json.loads(text)
    box = data.get("response", data).get("hits", {})
    total = box.get("total")
    return box.get("hits", []), total.get("value") if isinstance(total, dict) else total


def collect(fields, limit):
    client = opener()
    client.open(urllib.request.Request(BASE + "/heroes/", headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()
    hits, total = [], None
    while total is None or len(hits) < min(total, limit):
        page, total = post(client, fields, len(hits), min(PAGE_SIZE, limit - len(hits)))
        if not page:
            break
        hits.extend(page)
        time.sleep(PAUSE_SECONDS)
    return hits, total


def place(card):
    parts = [card.get("birth_place_gubernia"), card.get("birth_place_uezd"), card.get("birth_place_volost")]
    return card.get("birth_place") or ", ".join(p for p in parts if p) or "—"


def line(hit):
    card = hit["_source"]
    name = " ".join(str(card.get(k) or "") for k in ("last_name", "first_name", "middle_name")).strip()
    when = card.get("vibitie_date_from") or card.get("event_date_from") or card.get("document_date") or ""
    event = " ".join(str(v) for v in (when, card.get("vibitie_prichina"), card.get("vibitie_mesto") or card.get("event_place")) if v)
    place_id = card.get("birth_place_id")
    return " | ".join([name, place(card), str(card.get("military_unit_name") or "—"), event or "—",
                       f"место#{place_id}" if place_id else "—", f"{BASE}/heroes/{hit['_type']}{hit['_id']}/"])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    person = commands.add_parser("person")
    person.add_argument("--surname", required=True)
    person.add_argument("--given")
    person.add_argument("--patronymic")
    person.add_argument("--gubernia")
    volost = commands.add_parser("volost")
    volost.add_argument("--volost", required=True)
    volost.add_argument("--gubernia", required=True)
    for command in (person, volost):
        command.add_argument("--grep")
        command.add_argument("--out")
        command.add_argument("--max", type=int, default=3000)
    args = parser.parse_args()
    if args.command == "person":
        names = {"last_name": args.surname, "first_name": args.given, "middle_name": args.patronymic,
                 "birth_place_gubernia": args.gubernia}
        fields = {k: v for k, v in names.items() if v}
    else:
        fields = {"birth_place_volost": args.volost, "birth_place_gubernia": args.gubernia}
    try:
        hits, total = collect(fields, args.max)
    except (urllib.error.URLError, RuntimeError, ValueError) as error:
        print(f"error: {error}")
        return 1
    if args.out:
        Path(args.out).write_text(json.dumps({"query": fields, "total": total, "hits": hits}, ensure_ascii=False, indent=1), encoding="utf-8")
    pattern = re.compile(args.grep, re.I) if args.grep else None
    shown = [text for text in map(line, hits) if not pattern or pattern.search(text)]
    print("\n".join(shown))
    status = "complete" if total is not None and len(hits) >= total else "truncated: подними --max"
    print(f"== {len(hits)} из {total} карточек, показано {len(shown)}, {status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
