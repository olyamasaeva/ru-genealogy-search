"""Проверка файла GEDCOM после правки: синтаксис строк, висячие ссылки, двусторонние связи семей, QUAY, приватность живых.

Запуск: python3 ged_check.py дерево.ged [--strict-privacy]
Код выхода 1, если есть ошибки. С --strict-privacy возможно живые без
RESN privacy/confidential тоже считаются ошибкой — так проверяй файл перед тем,
как кому-то его отдать.
Возможно живой: смерть не подтверждена (нет DEAT с датой, местом или значением Y)
и год рождения (или оценка: любое своё событие, брак минус 15, рождение
ребёнка минус 15, рождение супруга плюс 10) не раньше 1925 года или ничем не
оценивается. Без единой даты человек считается возможно живым — это нарочно.
Если установлен python-gedcom (pip install python-gedcom==1.1.0 в venv), дополнительно
делает строгий разбор; его ошибка — ошибка проверки. --require-strict: без
python-gedcom проверка не проходит.
"""
import re
import sys
from pathlib import Path

LINE = re.compile(r"^(\d+) (@[^@]+@ )?([A-Z0-9_]+)( .*)?$")
LIVING_BORN_AFTER = 1925


def load(path):
    errors, recs, cur = [], {}, None
    prev_level = -1
    for no, raw in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), 1):
        m = LINE.match(raw)
        if not m:
            errors.append(f"строка {no}: не по формату GEDCOM: {raw[:60]}")
            continue
        level, xref, tag, val = int(m[1]), (m[2] or "").strip(), m[3], (m[4] or "").strip()
        if level > prev_level + 1:
            errors.append(f"строка {no}: уровень {level} после {prev_level}")
        prev_level = level
        if level == 0:
            cur = {"type": tag, "lines": [], "no": no}
            if xref:
                if xref in recs:
                    errors.append(f"строка {no}: повтор {xref}")
                recs[xref] = cur
        elif cur is not None:
            cur["lines"].append((no, level, tag, val))
    if not recs or "TRLR" not in Path(path).read_text(encoding="utf-8-sig"):
        errors.append("нет записей или нет TRLR")
    return recs, errors


def refs(rec, tag, level=1):
    return [v for _, lv, t, v in rec["lines"] if t == tag and lv == level]


def check(recs):
    errors, warnings = [], []
    for x, r in recs.items():
        for no, _, tag, val in r["lines"]:
            if re.fullmatch(r"@[^@]+@", val) and val not in recs:
                errors.append(f"{x}: {tag} ссылается на несуществующий {val} (строка {no})")
            if tag == "QUAY" and val not in ("0", "1", "2", "3"):
                errors.append(f"{x}: QUAY {val} вне 0–3 (строка {no})")
        if r["type"] == "INDI":
            for f in refs(r, "FAMC"):
                if f in recs and x not in refs(recs[f], "CHIL"):
                    errors.append(f"{x}: FAMC {f}, но в {f} нет CHIL {x}")
            for f in refs(r, "FAMS"):
                if f in recs and x not in refs(recs[f], "HUSB") + refs(recs[f], "WIFE"):
                    errors.append(f"{x}: FAMS {f}, но в {f} нет HUSB/WIFE {x}")
            birth_years = [int(y) for i, (_, lv, t, v) in enumerate(r["lines"])
                           if t == "DATE" and lv == 2 and _event_of(r["lines"], i) == "BIRT"
                           for y in re.findall(r"\d{4}", v)[:1]]
            resn = {v.lower() for _, lv, t, v in r["lines"] if lv == 1 and t == "RESN"}
            protected = bool(resn & {"privacy", "confidential"})
            estimate = birth_years[0] if birth_years else _estimate_birth(recs, x, r)
            maybe_living = not _death_confirmed(r["lines"]) and (estimate is None or estimate >= LIVING_BORN_AFTER)
            if maybe_living and not protected:
                born = birth_years[0] if birth_years else (f"~{estimate}" if estimate else "?")
                warnings.append(f"{x}: возможно жив (рождение {born}, смерть не подтверждена), а RESN privacy не стоит")
            if not refs(r, "FAMC") and not refs(r, "FAMS"):
                warnings.append(f"{x}: ни с кем не связан")
        if r["type"] == "FAM":
            for role in ("HUSB", "WIFE"):
                for p in refs(r, role):
                    if p in recs and x not in refs(recs[p], "FAMS"):
                        errors.append(f"{x}: {role} {p}, но у {p} нет FAMS {x}")
            for c in refs(r, "CHIL"):
                if c in recs and x not in refs(recs[c], "FAMC"):
                    errors.append(f"{x}: CHIL {c}, но у {c} нет FAMC {x}")
    return errors, warnings


def _years(lines):
    return [int(y) for _, lv, t, v in lines if t == "DATE" for y in re.findall(r"\d{4}", v)[:1]]


def _event_years(lines, event):
    return [int(y) for i, (_, lv, t, v) in enumerate(lines)
            if t == "DATE" and lv == 2 and _event_of(lines, i) == event
            for y in re.findall(r"\d{4}", v)[:1]]


def _estimate_birth(recs, x, r):
    guesses = _years(r["lines"])
    for f in refs(r, "FAMS"):
        fam = recs.get(f)
        if not fam:
            continue
        guesses += [y - 15 for y in _event_years(fam["lines"], "MARR")]
        for spouse in refs(fam, "HUSB") + refs(fam, "WIFE"):
            if spouse != x and spouse in recs:
                guesses += [y + 10 for y in _event_years(recs[spouse]["lines"], "BIRT")]
        for c in refs(fam, "CHIL"):
            if c in recs:
                guesses += [y - 15 for y in _event_years(recs[c]["lines"], "BIRT")]
    return min(guesses) if guesses else None


def _death_confirmed(lines):
    for i, (_, lv, t, v) in enumerate(lines):
        if lv == 1 and t == "DEAT":
            if v.upper() == "Y":
                return True
            following = lines[i + 1:]
            for _, lv2, t2, _ in following:
                if lv2 <= 1:
                    break
                if t2 in ("DATE", "PLAC", "CAUS", "SOUR", "NOTE"):
                    return True
    return False


def _event_of(lines, i):
    for _, lv, t, _ in reversed(lines[:i]):
        if lv == 1:
            return t
    return None


def strict_parse(path, required):
    try:
        from gedcom.parser import Parser
    except ImportError:
        if required:
            return "python-gedcom не установлен", "python-gedcom не установлен, а задан --require-strict"
        return "python-gedcom не установлен — строгий разбор пропущен", None
    try:
        Parser().parse_file(str(path), strict=True)
        return "python-gedcom strict: ok", None
    except Exception as exc:
        return "python-gedcom strict: ошибка", f"строгий разбор: {exc}"


def main():
    path = next(a for a in sys.argv[1:] if not a.startswith("--"))
    strict_privacy = "--strict-privacy" in sys.argv
    recs, errors = load(path)
    more, warnings = check(recs)
    errors += more
    if strict_privacy:
        errors += [w for w in warnings if "возможно жив" in w]
        warnings = [w for w in warnings if "возможно жив" not in w]
    kinds = {}
    for r in recs.values():
        kinds[r["type"]] = kinds.get(r["type"], 0) + 1
    print(f"{path}: " + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items())))
    status, strict_error = strict_parse(path, "--require-strict" in sys.argv)
    print(status)
    if strict_error:
        errors.append(strict_error)
    for e in errors:
        print("ОШИБКА", e)
    for w in warnings:
        print("внимание", w)
    print("итог:", "ошибок нет" if not errors else f"{len(errors)} ошибок", f"/ {len(warnings)} предупреждений")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
