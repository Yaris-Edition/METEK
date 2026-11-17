"""
Импорт прайса бухгалтерии (xlsx или ods) в site/prices.json.

Формат входного файла (как «Товар.ods»):
  колонка A — наименование; строка без цифр и без цены = заголовок вида товара
    («Арматура», «Лист Г/К», «Шкаф») — новые виды появляются на сайте автоматически;
  колонка B — цена в рублях; пусто = «Уточняйте у менеджера».

Правила устойчивости:
  - заголовок группы, под которым лежат позиции другого профиля (в исходнике
    встречается «Уголок» перед швеллерами), переименовывается по большинству
    первых слов позиций — с пометкой в отчёте;
  - цена принимает «61 500», «61500,50», «61500 ₽» и просто число;
  - файл не похож на прайс (нет групп, мало позиций, имена без размеров) —
    ImportFormatError, публикация не происходит.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

MSK = timezone(timedelta(hours=3))

TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


class ImportFormatError(Exception):
    """Файл не удалось разобрать как прайс."""


def slugify(name: str) -> str:
    out = []
    for ch in name.lower():
        if ch in TRANSLIT:
            out.append(TRANSLIT[ch])
        elif ch.isalnum() and ch.isascii():
            out.append(ch)
        else:
            out.append("-")
    slug = re.sub(r"-+", "-", "".join(out)).strip("-")
    return slug or "gruppa"


def _parse_price(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            if value != value:  # NaN
                return None
        except Exception:
            return None
        return float(value) if value > 0 else None
    s = str(value).strip()
    if not s:
        return None
    s = s.replace("\u00a0", "").replace(" ", "").replace("₽", "").replace("р.", "")
    s = s.replace(",", ".")
    try:
        num = float(s)
    except ValueError:
        return None
    return num if num > 0 else None


def _read_rows(path: Path) -> list[tuple[str | None, object]]:
    suffix = path.suffix.lower()
    rows: list[tuple[str | None, object]] = []
    if suffix == ".xlsx":
        from openpyxl import load_workbook
        try:
            wb = load_workbook(path, read_only=True, data_only=True)
        except Exception as e:
            raise ImportFormatError(f"Не удалось открыть xlsx: {e}") from e
        ws = wb.active
        for row in ws.iter_rows(values_only=True):
            name = row[0] if len(row) > 0 else None
            price = row[1] if len(row) > 1 else None
            rows.append((None if name is None else str(name), price))
        wb.close()
    elif suffix == ".ods":
        try:
            import pandas as pd
            df = pd.read_excel(path, engine="odf", header=None)
        except Exception as e:
            raise ImportFormatError(f"Не удалось открыть ods: {e}") from e
        for _, row in df.iterrows():
            name = row.iloc[0] if len(row) > 0 else None
            price = row.iloc[1] if len(row) > 1 else None
            if name is not None and name != name:  # NaN
                name = None
            rows.append((None if name is None else str(name), price))
    else:
        raise ImportFormatError(f"Неподдерживаемый формат: {suffix} (нужен .xlsx или .ods)")
    return rows


def parse_price_file(path: Path) -> tuple[dict, list[str]]:
    """Возвращает (структура prices.json, список предупреждений)."""
    rows = _read_rows(Path(path))
    warnings: list[str] = []
    groups: list[dict] = []
    current: dict | None = None

    for name_raw, price_raw in rows:
        if name_raw is None:
            continue
        name = " ".join(str(name_raw).split())
        if not name or name.lower() in ("цена", "наименование"):
            continue
        price_val = _parse_price(price_raw)
        # заголовок вида товара: строка без цифр и без цены («Арматура», «Шкаф»);
        # позиция: есть размер (цифры) или указана цена («Шкаф навесной белый | 12 500»)
        is_header = not re.search(r"\d", name) and price_val is None
        if is_header:
            current = {"slug": slugify(name), "name": name.rstrip("-").strip(), "items": []}
            groups.append(current)
            continue
        if current is None:
            current = {"slug": "prochee", "name": "Прочее", "items": []}
            groups.append(current)
            warnings.append("Позиции до первого заголовка сложены в «Прочее»")
        current["items"].append({
            "sku": slugify(name)[:60],
            "name": name,
            "stock": "Сочи",
            "price": price_val,
        })

    groups = [g for g in groups if g["items"]]

    # автопочинка заголовка, не совпадающего со своими позициями
    for g in groups:
        first_words = Counter(it["name"].split()[0].lower() for it in g["items"])
        top_word, top_count = first_words.most_common(1)[0]
        header_word = g["name"].split()[0].lower()
        if top_count >= max(2, int(0.8 * len(g["items"]))) and not top_word.startswith(header_word[:4]):
            fixed = top_word.capitalize()
            warnings.append(f"Группа «{g['name']}» переименована в «{fixed}» по содержимому")
            g["name"] = fixed
            g["slug"] = slugify(fixed)

    # уникальность слагов
    seen: dict[str, int] = {}
    for g in groups:
        if g["slug"] in seen:
            seen[g["slug"]] += 1
            g["slug"] = f"{g['slug']}-{seen[g['slug']]}"
        else:
            seen[g["slug"]] = 1

    total_items = sum(len(g["items"]) for g in groups)
    with_digits = sum(
        1 for g in groups for it in g["items"] if re.search(r"\d", it["name"])
    )
    if not groups or total_items < 10:
        raise ImportFormatError("В файле не нашлось групп и позиций прайса")
    with_price = sum(1 for g in groups for it in g["items"] if it["price"] is not None)
    if with_digits + with_price < total_items * 0.5:
        raise ImportFormatError("Названия позиций не похожи на прайс (нет размеров и цен)")

    data = {
        "updated_at": datetime.now(MSK).isoformat(timespec="seconds"),
        "source": Path(path).name,
        "currency": "RUB",
        "unit": "т",
        "groups": groups,
    }
    return data, warnings


def publish(data: dict, prices_path: Path, backups_dir: Path, keep: int = 5) -> None:
    """Атомарная запись prices.json + бэкап предыдущей версии."""
    prices_path = Path(prices_path)
    backups_dir = Path(backups_dir)
    backups_dir.mkdir(parents=True, exist_ok=True)

    if prices_path.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        (backups_dir / f"prices-{stamp}.json").write_bytes(prices_path.read_bytes())
        old = sorted(backups_dir.glob("prices-*.json"),
                     key=lambda p: p.stat().st_mtime, reverse=True)
        for f in old[keep:]:
            f.unlink()

    fd, tmp = tempfile.mkstemp(dir=str(prices_path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, prices_path)  # атомарно
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise
