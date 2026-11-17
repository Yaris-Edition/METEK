#!/usr/bin/env python3
"""Генерирует страницы сайта МЕТЭК Сочи. Запуск: python3 gen_pages.py"""
import re
from pathlib import Path

SITE = Path(__file__).parent / "site"

ADDR = "г. Сочи, ул. Гастелло, д. 42, к. 1"
PHONE = "+7 (862) 291-00-33"
PHONE_HREF = "tel:+78622910033"
EMAIL = "info@meteksochi.ru"
YA_OID = "70607898709"
YA_ORG_URL = "https://yandex.ru/maps/-/CTDgIUMV"
YA_LL = "39.919593,43.451371"  # точка компании из карточки Яндекса
# только метка, без открытой карточки; pm2rdm — красная метка
YA_EMBED = f"https://yandex.ru/map-widget/v1/?ll={YA_LL}&z=17&pt={YA_LL},pm2rdm"
GIS_URL = "https://go.2gis.com/e7QJU"

NAV = [
    ("index.html", "Главная"),
    ("katalog.html", "Каталог проката"),
    ("proizvodstvo.html", "Производство"),
    ("uslugi.html", "Услуги"),
    ("otzyvy.html", "Отзывы"),
    ("kontakty.html", "Контакты"),
]

HEAD = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="icon" href="assets/favicon.ico" sizes="32x32">
<link rel="icon" type="image/png" href="assets/favicon.png">
<link rel="stylesheet" href="assets/style.css">
</head>
<body>
<div class="topbar">
  <div class="wrap">
    <span>ООО «МЕТЭК Сочи» · Собственный склад и производство · Работаем с НДС</span>
    <span>Пн–Пт 8:00–17:00 · <a href="mailto:{email}">{email}</a> · <a href="{phone_href}">{phone}</a></span>
  </div>
</div>
<header>
  <div class="wrap nav-row">
    <a class="logo" href="index.html"><img src="assets/logo_new.png" alt="МЕТЭК Сочи" width="153" height="66"></a>
    <div class="hscroll nav-scroll">
      <button class="hs-btn" type="button" data-dir="-1" aria-label="Прокрутить меню влево"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 3 5 8l5 5"/></svg></button>
      <nav class="tabs-nav" aria-label="Основная навигация">
{nav}
      </nav>
      <button class="hs-btn" type="button" data-dir="1" aria-label="Прокрутить меню вправо"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="m6 3 5 5-5 5"/></svg></button>
    </div>
    <a class="btn header-cta" href="kontakty.html#zvonok">Обратный звонок</a>
  </div>
</header>
"""

FOOT = """<footer>
  <div class="wrap">
    <div class="foot">
      <div>
        <p class="flogo">МЕТЭК <em>Сочи</em></p>
        <p style="margin-top:10px">Металлопрокат, изготовление металлоизделий, лазерная резка и сверление.</p>
      </div>
      <div>
        <h3>Контакты</h3>
        <p><a href="{phone_href}">{phone}</a><br>
        <a href="mailto:{email}">{email}</a><br>
        {addr}</p>
      </div>
      <div>
        <h3>Разделы</h3>
        <p><a href="katalog.html">Каталог проката</a><br>
        <a href="proizvodstvo.html">Производство</a><br>
        <a href="uslugi.html">Услуги</a><br>
        <a href="otzyvy.html">Отзывы</a></p>
      </div>
      <div>
        <h3>Режим работы</h3>
        <p>Пн–Пт: 8:00–17:00</p>
      </div>
    </div>
    <p class="req">© 2026 ООО «МЕТЭК Сочи» · ОГРН 1232300075292 · ИНН 2367035393 · <a href="privacy.html">Политика конфиденциальности</a><a class="lk" href="/upload" rel="nofollow">Личный кабинет</a></p>
  </div>
</footer>
<script src="assets/site.js"></script>
</body>
</html>
""".format(phone=PHONE, phone_href=PHONE_HREF, email=EMAIL, addr=ADDR)


PREPS = r"(в|во|с|со|и|а|но|на|по|до|от|за|из|о|об|к|у|не|под|при|для|без|над|же|ли|бы)"


def nbsp_preps(html: str) -> str:
    """«Цены за тонну с НДС» → предлог не остаётся в конце строки."""
    def fix(m):
        text = m.group(1)
        text = re.sub(r"(?<![\w-])" + PREPS + r" (?=[\wА-Яа-яЁё«(])", lambda mm: mm.group(1) + "\u00a0", text)
        return ">" + text + "<"
    return re.sub(r">([^<>]+)<", fix, html)


def clean_urls(html: str) -> str:
    """index.html -> /, katalog.html#x -> /katalog#x, assets/x -> /assets/x (без .html в адресе)."""
    html = re.sub(r'(href|action)="index\.html([#?]?[^"]*)"', r'\1="/\2"', html)
    html = re.sub(r'(href|action)="([a-z0-9\-]+)\.html([#?]?[^"]*)"', r'\1="/\2\3"', html)
    html = re.sub(r'(href|src)="assets/', r'\1="/assets/', html)
    # Sprint 1: ссылки на виды проката ведут на серверные маршруты PostgreSQL, а не hash.
    html = re.sub(r'href="/katalog#([a-z0-9-]+)"', r'href="/katalog/\1"', html)
    return html


def page(fname, title, desc, body):
    nav = "\n".join(
        '      <a href="{f}"{cls}>{label}</a>'.format(
            f=f, label=label,
            cls=' class="active"' if f == fname or (fname in SERVICE_FILES and f == "uslugi.html") else "")
        for f, label in NAV
    )
    html = HEAD.format(title=title, desc=desc, nav=nav,
                       phone=PHONE, phone_href=PHONE_HREF, email=EMAIL) + body + FOOT
    html = nbsp_preps(clean_urls(html))
    (SITE / fname).write_text(html, encoding="utf-8")
    print("wrote", fname)


def by_sentence(text: str) -> str:
    """«А. Б.» → «А.<br>Б.» — каждое предложение подзаголовка с новой строки."""
    return re.sub(r"([.!?])\s+(?=[А-ЯЁA-Z«])", r"\1<br>", text.strip())


def page_head(crumb, h1, sub):
    sub = by_sentence(sub)
    return f"""<div class="page-head">
  <div class="wrap">
    <p class="crumbs"><a href="index.html">Главная</a> / {crumb}</p>
    <h1>{h1}</h1>
    <p>{sub}</p>
  </div>
</div>
"""


SEARCH_FORM = """<form class="search" action="katalog.html" method="get" data-search>
      <input name="q" placeholder="Поиск по каталогу: труба, арматура, лист..." autocomplete="off"
             aria-label="Поиск по каталогу" maxlength="80">
      <button class="btn" type="submit">Открыть каталог</button>
      <div class="sug" hidden></div>
    </form>"""

INDEX = f"""<div class="hero">
  <div class="wrap">
    <p class="kicker">Сочи · Краснодарский край</p>
    <h1 class="sr-only">Металлопрокат и металлоизделия в Сочи</h1>
    <div class="hero-split">
      <div class="hero-title t1" aria-hidden="true">Металлопрокат</div>
      <p class="p1">Собственный склад в Сочи более 1000&nbsp;м².<br>
        Всегда в наличии весь ассортимент чёрного металлопроката: арматура А500С, двутавр (балка),
        труба профильная, труба круглая, лист, швеллер, уголок, полоса, ПВЛ, сетка и&nbsp;т.&nbsp;д.</p>
      <div class="hero-title accent t2" aria-hidden="true">металлоизделия</div>
      <p class="p2">Лазерная резка на станке ЧПУ 6&nbsp;кВт — лист до 30&nbsp;мм.<br>
        Производство металлоизделий на собственном оборудовании: анкерные шайбы, закладные изделия,
        П-образные и Н-образные детали, анкерные болты и другое.</p>
    </div>
    {SEARCH_FORM}
    <p class="popular">Популярное:
      <a href="katalog.html#truba-profilnaya">Труба профильная</a>
      <a href="katalog.html?q=А500С">Арматура А500С</a>
      <a href="lazernaya-rezka.html">Лазерная резка</a>
      <a href="izgotovlenie-izdeliy.html">Анкерные шайбы</a>
      <a href="proizvodstvo.html">Свайные каркасы</a>
    </p>
    <div class="facts">
      <div><b>до 30 мм</b><span>лазерная резка листа</span></div>
      <div><b>до 75 мм</b><span>сверление отверстий</span></div>
      <div><b>296</b><span>позиций проката на складе</span></div>
    </div>
  </div>
</div>

<section id="sklad">
  <div class="wrap">
    <div class="sec-head">
      <span class="tag">Каталог</span>
      <h2>Металлопрокат <em>со склада в Сочи</em></h2>
      <span class="stamp" style="margin-left:auto">Любые размеры и диаметры · оптом и в розницу</span>
    </div>
    <div class="tiles">
      <a class="tile" href="katalog.html#list-g-k">
        <div class="photo">фото — заменим</div>
        <h3>Лист</h3>
        <div class="chips"><span class="chip">горячекатаный</span><span class="chip">оцинкованный</span><span class="chip">ПВЛ</span><span class="chip">рифлёный</span><span class="chip">холоднокатаный</span></div>
        <span class="go">Цены и наличие →</span>
      </a>
      <a class="tile" href="katalog.html#truba-profilnaya">
        <div class="photo">фото — заменим</div>
        <h3>Труба</h3>
        <div class="chips"><span class="chip">бесшовная</span><span class="chip">ВГП / ЭСВ</span><span class="chip">круглая</span><span class="chip">профильная</span></div>
        <span class="go">Цены и наличие →</span>
      </a>
      <a class="tile" href="katalog.html#armatura">
        <div class="photo">фото — заменим</div>
        <h3>Арматура</h3>
        <div class="chips"><span class="chip">А1</span><span class="chip">А3</span><span class="chip">гладкая</span><span class="chip">рифлёная</span></div>
        <span class="go">Цены и наличие →</span>
      </a>
      <a class="tile cta" href="kontakty.html#zvonok">
        <h3>Нужна позиция, которой нет в списке?</h3>
        <p>Привезём под заказ. Назовите марку и сечение — найдём и посчитаем.</p>
        <span class="go">Запросить позицию →</span>
      </a>
      <a class="tile" href="katalog.html#dvutavr">
        <div class="photo">фото — заменим</div>
        <h3>Фасонный прокат</h3>
        <div class="chips"><span class="chip">двутавр</span><span class="chip">уголок</span><span class="chip">швеллер</span></div>
        <span class="go">Цены и наличие →</span>
      </a>
      <a class="tile" href="katalog.html?q=сетка">
        <div class="photo">фото — заменим</div>
        <h3>Сетка сварная</h3>
        <div class="chips"><span class="chip">дорожная</span><span class="chip">кладочная</span></div>
        <span class="go">Цены и наличие →</span>
      </a>
      <a class="tile" href="proizvodstvo.html">
        <div class="photo">фото — заменим</div>
        <h3>Закладные детали</h3>
        <div class="chips"><span class="chip">анкерные группы</span><span class="chip">анкерные шайбы</span><span class="chip">болт фундаментный</span><span class="chip">П-образные детали</span></div>
        <span class="go">Смотреть изделия →</span>
      </a>
      <a class="tile" href="katalog.html#kvadrat">
        <div class="photo">фото — заменим</div>
        <h3>Сортовой прокат</h3>
        <div class="chips"><span class="chip">квадрат</span><span class="chip">круг</span><span class="chip">полоса</span><span class="chip">шестигранник</span></div>
        <span class="go">Цены и наличие →</span>
      </a>
    </div>
  </div>
</section>

<section class="cards-dark">
  <div class="wrap">
    <div class="sec-head"><span class="tag">Производство</span><h2>Изготовление металлоизделий</h2></div>
    <div class="cards">
      <div class="card"><h3>Анкерные шайбы</h3><p>Толщина до 30&nbsp;мм, по чертежу и по образцу.</p><span class="ph">фото — заменим</span></div>
      <div class="card"><h3>П-образные детали</h3><p>Детали под блок, серийно и штучно.</p><span class="ph">фото — заменим</span></div>
      <div class="card"><h3>Н-образные детали</h3><p>По вашим размерам, с покраской.</p><span class="ph">фото — заменим</span></div>
      <div class="card"><h3>Анкерные болты</h3><p>Тип 1–7 по ГОСТ 24379, с резьбой и гайками.</p><span class="ph">фото — заменим</span></div>
      <div class="card"><h3>Изделия по чертежам</h3><p>Нестандартные металлоизделия по вашим DXF/DWG.</p><span class="ph">фото — заменим</span></div>
    </div>
    <p class="price-note" style="color:#9aa39e">Все изделия — на странице <a href="proizvodstvo.html" style="color:#fff">Производство</a>.</p>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="sec-head"><span class="tag">Услуги</span><h2>Обработка металла на своём производстве</h2></div>
    <div class="svc">
      <article><h3>Лазерная резка</h3><ul><li>Листовой прокат до 30 мм</li><li>Работа по чертежам DXF/DWG</li></ul>
        <p style="margin-top:10px"><a href="lazernaya-rezka.html">Подробнее об услуге →</a></p></article>
      <article><h3>Гибка листового металла</h3><ul><li>Листогиб BEKE, длина гиба до 3,2 м</li><li>Сложные гибы по чертежу</li></ul>
        <p style="margin-top:10px"><a href="gibka.html">Подробнее об услуге →</a></p></article>
      <article><h3>Металлоконструкции на заказ</h3><ul><li>Конструкции, площадки, лестницы</li><li>Закладные детали, анкерные группы</li></ul>
        <p style="margin-top:10px"><a href="metallokonstrukcii.html">Подробнее об услуге →</a></p></article>
    </div>
    <div class="price-cta">
      <a class="btn" href="uslugi.html">Все услуги</a>
      <a class="btn ghost" href="kontakty.html#zvonok">Заказать обратный звонок</a>
    </div>
  </div>
</section>
"""

KATALOG = page_head("Каталог проката", "Каталог металлопроката в Сочи",
                    "Широкий ассортимент металлопроката в наличии и под заказ. Цены за тонну с НДС — обновляются вместе с прайсом склада.") + f"""
<section id="katalog" style="padding-top:40px">
  <div class="wrap">
    <div style="margin-bottom:26px">{SEARCH_FORM.replace('Открыть каталог', 'Найти')}</div>
    <div class="sec-head">
      <span class="tag">Прайс-лист</span>
      <h2>Цены <em>со склада в Сочи</em></h2>
      <span class="stamp" id="priceStamp"><span class="dot"></span><span id="stampText">загружаем прайс…</span></span>
    </div>
    <div class="search-info" id="searchInfo" hidden></div>
    <div class="gtabs" id="groupTabs" role="tablist" aria-label="Группы металлопроката"></div>
    <div class="selected" id="selectedGroups" hidden></div>
    <div class="table-scroll">
    <table class="price-table" aria-describedby="priceNote">
      <thead><tr><th scope="col">Наименование</th><th scope="col" style="text-align:right">Цена, ₽/т</th></tr></thead>
      <tbody id="priceBody"><tr><td colspan="2" style="color:var(--muted)">Загружаем актуальные цены…</td></tr></tbody>
    </table>
    </div>
    <p class="price-note" id="priceNote">Цены за тонну с НДС. Позиции «уточняйте у менеджера» посчитаем по телефону. Резка в размер и доставка — по согласованию.</p>
    <div class="price-cta">
      <a class="btn" href="kontakty.html#zvonok">Запросить расчёт</a>
      <a class="btn ghost" href="{PHONE_HREF}">{PHONE}</a>
    </div>
  </div>
</section>
"""

USLUGI = page_head("Услуги", "Обработка металла на своём производстве",
                   "Стоимость считаем по задаче. Пришлите чертёж или опишите деталь — перезвоним с расчётом.") + """
<section style="padding-top:44px">
  <div class="wrap">
    <div class="svc">
      <article>
        <h3>Лазерная резка металла</h3>
        <div class="photo">фото — заменим</div>
        <p style="font-size:14px;color:var(--muted)">Листовой прокат до 30 мм. Идеальные края, минимальные отходы, любые металлы, высокая скорость.</p>
        <a class="more" href="lazernaya-rezka.html">Подробнее об услуге →</a>
      </article>
      <article>
        <h3>Изготовление металлоизделий</h3>
        <div class="photo">фото — заменим</div>
        <p style="font-size:14px;color:var(--muted)">Анкерные шайбы, П-образные детали под блок, Н-образные детали — по чертежу и по образцу.</p>
        <a class="more" href="izgotovlenie-izdeliy.html">Подробнее об услуге →</a>
      </article>
      <article>
        <h3>Гибка листового металла</h3>
        <div class="photo">фото — заменим</div>
        <p style="font-size:14px;color:var(--muted)">Листогиб BEKE, длина гиба до 3,2 м. Сложные гибы по чертежу, точность углов и повторяемость серии.</p>
        <a class="more" href="gibka.html">Подробнее об услуге →</a>
      </article>
      <article>
        <h3>Металлоконструкции на заказ</h3>
        <div class="photo">фото — заменим</div>
        <p style="font-size:14px;color:var(--muted)">Строительные конструкции, площадки, лестницы. Закладные детали и анкерные группы.</p>
        <a class="more" href="metallokonstrukcii.html">Подробнее об услуге →</a>
      </article>
      <article>
        <h3>Сверление отверстий</h3>
        <div class="photo">фото — заменим</div>
        <p style="font-size:14px;color:var(--muted)">Диаметр до 75 мм. Сверлильный станок, серийные партии, работа по чертежу.</p>
        <a class="more" href="sverlenie.html">Подробнее об услуге →</a>
      </article>
      <article style="background:var(--navy);border-color:var(--navy)">
        <h3 style="color:#fff">Не нашли нужную услугу?</h3>
        <p style="color:#c9c8de;font-size:14px">Оставьте заявку — менеджер свяжется с вами, поможет решить ваш вопрос.</p>
        <p style="margin-top:16px"><a class="btn" href="kontakty.html#zvonok">Оставить заявку</a></p>
      </article>
    </div>
    <p class="price-note">Цен на услуги на сайте нет намеренно: каждая задача считается индивидуально.</p>
  </div>
</section>
"""

STEPS = """<section>
  <div class="wrap">
    <div class="sec-head"><span class="tag">Порядок работы</span><h2>Как мы работаем</h2></div>
    <div class="steps">
      <article><h3>Присылаете задачу</h3><p>Чертёж DXF, DWG, PDF или эскиз от руки на {email}</p></article>
      <article><h3>Считаем стоимость и сроки</h3><p>Менеджер перезвонит с расчётом и уточнит детали</p></article>
      <article><h3>{do}</h3><p>{do_sub}</p></article>
      <article><h3>Отгружаем</h3><p>Самовывоз со склада в Сочи или доставка по согласованию</p></article>
    </div>
  </div>
</section>"""

CTA_BAND = """<div class="cta-band">
  <div class="wrap">
    <h2>Оставьте заявку — менеджер свяжется с вами</h2>
    <p>Поможет подобрать материал, посчитает стоимость работы и ответит на вопросы по срокам.</p>
    <a class="btn" href="kontakty.html#zvonok">Оставить заявку</a>
  </div>
</div>"""

METAL_CLOUD = """<section>
  <div class="wrap">
    <div class="sec-head"><span class="tag">Материал</span><h2>Металл для работы — со своего склада</h2></div>
    <p style="color:var(--muted);max-width:60ch;margin-bottom:18px">Свой металл везти не обязательно: подберём
    со склада и посчитаем одним счётом вместе с работой.</p>
    <div class="linkcloud">
      <a href="katalog.html#list-g-k">Лист</a><a href="katalog.html#truba-profilnaya">Труба профильная</a>
      <a href="katalog.html#truba-elsv">Труба ЭлСв</a><a href="katalog.html#truba-vgp">Труба ВГП</a>
      <a href="katalog.html#armatura">Арматура</a><a href="katalog.html#dvutavr">Двутавр</a>
      <a href="katalog.html#shveller">Швеллер</a><a href="katalog.html#ugolok">Уголок</a>
      <a href="katalog.html#kvadrat">Квадрат</a><a href="katalog.html#polosa">Полоса</a>
      <a href="katalog.html">Весь каталог</a>
    </div>
  </div>
</section>"""


def service_page(h1, sub, facts, about_title, about_html, faq, do, do_sub):
    facts_html = "".join(f"<div><b>{b}</b><span>{s}</span></div>" for b, s in facts)
    faq_html = "".join(f"<details><summary>{q}</summary><p>{a}</p></details>" for q, a in faq)
    return f"""<div class="page-head">
  <div class="wrap">
    <p class="crumbs"><a href="index.html">Главная</a> / <a href="uslugi.html">Услуги</a> / {h1}</p>
    <h1>{h1}</h1>
    <p>{by_sentence(sub)}</p>
    <div class="facts-row">{facts_html}</div>
  </div>
</div>
{STEPS.format(email=EMAIL, do=do, do_sub=do_sub)}
<section style="padding-top:0">
  <div class="wrap doc">
    <div class="sec-head"><span class="tag">Об услуге</span><h2>{about_title}</h2></div>
    {about_html}
  </div>
</section>
{METAL_CLOUD}
<section style="padding-top:0">
  <div class="wrap">
    <div class="sec-head"><span class="tag">FAQ</span><h2>Частые вопросы</h2></div>
    <div class="faq">{faq_html}</div>
  </div>
</section>
{CTA_BAND}
"""


SERVICES = {
    "lazernaya-rezka.html": dict(
        title="Лазерная резка металла в Сочи — МЕТЭК Сочи",
        desc="Лазерная резка листового проката до 30 мм в Сочи. Работа по чертежам DXF/DWG, от одной детали. Расчёт по заявке.",
        h1="Лазерная резка металла",
        sub="Режем листовой прокат до 30 мм по вашим чертежам. Чистая кромка, минимум отходов, от одной детали.",
        facts=[("до 30 мм", "толщина листа"), ("DXF / DWG", "форматы чертежей"), ("от 1 шт", "минимальная партия")],
        do="Режем", do_sub="Деталь после станка сразу готова к гибке или сварке",
        about_title="Лазерная резка — что важно знать",
        about_html="""<p>Лазерная резка даёт узкий рез и чистую кромку, которую в большинстве случаев не нужно
дорабатывать: деталь после станка сразу идёт на гибку, сверление или сварку. Режем по вашему чертежу
или эскизу — если файла нет, менеджер поможет оформить размеры.</p>
<p>Работаем с листовым прокатом толщиной до 30 мм. Сложность контура влияет на время реза: много мелких
отверстий и острых углов удлиняют работу, поэтому ажурная деталь считается дороже простого прямоугольника
той же площади — точную стоимость менеджер назовёт после просмотра чертежа.</p>
<p>Металл можно взять с нашего склада — тогда не придётся привозить свой лист и согласовывать приёмку,
а работа и материал попадут в один счёт.</p>""",
        faq=[
            ("Какой минимальный заказ?", "Режем от одной детали. Единичные заказы считаем индивидуально."),
            ("В каком формате присылать чертёж?", "Оптимально DXF. Принимаем DWG и PDF; если чертежа нет — пришлите эскиз с размерами, менеджер оформит."),
            ("Можно приехать со своим металлом?", "Да, примем ваш лист и порежем по чертежу. Если металла нет — подберём со склада."),
            ("Работаете с юридическими лицами?", "Да, работаем с НДС и даём полный комплект закрывающих документов."),
        ],
    ),
    "izgotovlenie-izdeliy.html": dict(
        title="Изготовление металлоизделий в Сочи — МЕТЭК Сочи",
        desc="Изготовление металлоизделий в Сочи: анкерные шайбы, П-образные детали под блок, Н-образные детали. По чертежу и образцу.",
        h1="Изготовление металлоизделий",
        sub="Анкерные шайбы, П-образные детали под блок, Н-образные детали. По чертежу и по образцу, серийно и штучно.",
        facts=[("до 30 мм", "толщина заготовки"), ("по образцу", "работаем и без чертежа"), ("серия / штучно", "любые партии")],
        do="Изготавливаем", do_sub="Раскрой, сверление, сварка и покраска на одной площадке",
        about_title="Изделия, которые делаем чаще всего",
        about_html="""<p>Основная номенклатура — крепёжные и закладные изделия для строительства: анкерные шайбы
толщиной до 30 мм, П-образные детали под блок и Н-образные детали по размерам заказчика. Делаем как
серийные партии, так и единичные позиции.</p>
<p>Если чертежа нет, работаем по образцу: привезите деталь, снимем размеры и повторим. Готовые изделия
по запросу красим и комплектуем метизами.</p>
<p>Полный список изделий — на странице <a href="proizvodstvo.html">Производство</a>.</p>""",
        faq=[
            ("Можно заказать без чертежа?", "Да, работаем по образцу: привезите деталь или пришлите фото с размерами."),
            ("Красите изделия?", "Да, по запросу — грунт или покраска, обсуждается при расчёте."),
            ("Какая минимальная партия?", "От одной штуки. Серийные партии считаются выгоднее."),
        ],
    ),
    "gibka.html": dict(
        title="Гибка листового металла в Сочи — МЕТЭК Сочи",
        desc="Гибка листового металла в Сочи на листогибе BEKE: длина гиба до 3,2 м, сложные гибы по чертежу, повторяемость серии.",
        h1="Гибка листового металла",
        sub="Листогиб BEKE с длиной гиба до 3,2 м. Сложные гибы по чертежу, точность углов и повторяемость серии.",
        facts=[("до 3,2 м", "длина гиба"), ("BEKE", "листогиб"), ("серия", "повторяемость углов")],
        do="Гнём", do_sub="Выдерживаем углы по чертежу на всей серии",
        about_title="Гибка — что важно знать",
        about_html="""<p>Гнём листовой металл на листогибе BEKE с длиной гиба до 3,2 метра. Станок держит угол
по всей длине детали, поэтому серийные партии выходят одинаковыми — это важно для коробов, кассет,
отливов и корпусных деталей.</p>
<p>Сложные профили с несколькими гибами считаем по чертежу: менеджер проверит последовательность гибки
и минимальные полки, чтобы деталь можно было согнуть, и предупредит, если что-то нужно поправить
в размерах.</p>
<p>Раскрой под гибку делаем здесь же на лазере — деталь проходит обе операции на одной площадке.</p>""",
        faq=[
            ("Какая максимальная длина гиба?", "3,2 метра за один гиб."),
            ("Гнёте по эскизу?", "Да. Пришлите эскиз с размерами и углами — оформим чертёж и посчитаем."),
            ("Можно с вашим металлом?", "Да, подберём лист со склада и посчитаем одним счётом с работой."),
        ],
    ),
    "metallokonstrukcii.html": dict(
        title="Металлоконструкции на заказ в Сочи — МЕТЭК Сочи",
        desc="Металлоконструкции на заказ в Сочи: строительные конструкции, площадки, лестницы, закладные детали, анкерные группы.",
        h1="Металлоконструкции на заказ",
        sub="Строительные конструкции, площадки, лестницы. Закладные детали и анкерные группы под ваш проект.",
        facts=[("свои посты", "аттестованные сварщики"), ("по проекту", "работа с вашей документацией"), ("НДС", "полный комплект документов")],
        do="Варим и собираем", do_sub="Аттестованные сварочные посты, контроль геометрии",
        about_title="Металлоконструкции — что делаем",
        about_html="""<p>Изготавливаем строительные металлоконструкции: колонны, балки, связи, площадки и лестницы,
а также закладные детали и анкерные группы под опоры и оборудование. Работаем по вашей проектной
документации.</p>
<p>Сварка — на аттестованных постах, с контролем геометрии. По запросу конструкции грунтуем и красим,
комплектуем метизами и маркируем для монтажа.</p>
<p>Материал берём со своего склада — прокат, лист и метизы попадают в один счёт с работой, а сроки
не зависят от сторонних поставок.</p>""",
        faq=[
            ("Работаете по нашим чертежам КМ/КМД?", "Да, работаем с вашей проектной документацией."),
            ("Красите конструкции?", "Да — грунт или покраска по запросу, обсуждается при расчёте."),
            ("Доставляете на объект?", "Самовывоз со склада в Сочи, доставка — по согласованию."),
        ],
    ),
    "sverlenie.html": dict(
        title="Сверление отверстий в металле до 75 мм в Сочи — МЕТЭК Сочи",
        desc="Сверление отверстий в металлопрокате до 75 мм в Сочи. Сверлильный станок, серийные партии, работа по чертежу.",
        h1="Сверление отверстий",
        sub="Сверлим отверстия диаметром до 75 мм в листе и прокате. Серийные партии на сверлильном станке.",
        facts=[("до 75 мм", "диаметр отверстия"), ("станок", "стабильная геометрия"), ("серия", "партии любых объёмов")],
        do="Сверлим", do_sub="Разметка по чертежу, контроль диаметров",
        about_title="Сверление — что важно знать",
        about_html="""<p>Сверлим отверстия диаметром до 75 мм в листовом и профильном прокате: под болтовые
соединения, анкерные группы, фланцы и закладные. Станок держит перпендикулярность и диаметр, поэтому
серийные детали получаются одинаковыми.</p>
<p>Разметку делаем по вашему чертежу. Если отверстий много и они мелкие — предложим лазерный раскрой,
это быстрее и дешевле; менеджер подскажет оптимальный вариант при расчёте.</p>""",
        faq=[
            ("Какой максимальный диаметр?", "75 мм."),
            ("Сверлите металл заказчика?", "Да, примем ваш прокат. Или подберём со склада — одним счётом."),
            ("Что прислать для расчёта?", "Чертёж или эскиз с диаметрами и координатами отверстий."),
        ],
    ),
}
SERVICE_FILES = set(SERVICES.keys())

PROD_TILES = [
    ("Строительные металлоконструкции", "Колонны, балки, фермы, связи. Сварка по ГОСТ, разработка КМД."),
    ("Закладные детали", "По сериям и чертежам заказчика, с антикоррозийной обработкой."),
    ("Опоры трубопровода", "Неподвижные и скользящие опоры под любые диаметры труб."),
    ("Анкерные (фундаментные) болты", "Тип 1–7 по ГОСТ 24379, с резьбой и гайками в комплекте."),
    ("Анкерные группы", "Болтовые группы в сборе под опоры и оборудование."),
    ("Закладные канализационные тип МС", "Изделия типа МС для колодцев и камер."),
    ("Зенкованные пластины", "Пластины с зенковкой под крепёж, лазерный раскрой."),
    ("Каркасы буронабивных свай", "Арматурные каркасы под сваи любого диаметра и длины."),
    ("Изделия по чертежам", "Нестандартные металлоизделия по вашим DXF/DWG."),
    ("Опоры освещения", "Гранёные и трубчатые опоры с закладными под фундамент."),
    ("Закладные МС для кирпичной кладки и газоблока", "Гибкие связи и закладные под кладку."),
    ("Кронштейны крепления кондиционера", "Усиленные кронштейны под любые типоразмеры блоков."),
]
_prod_tiles_html = "\n".join(
    f"""      <a class="tile" href="kontakty.html#zvonok">
        <div class="photo">фото — заменим</div>
        <h3>{t}</h3><p>{d}</p>
        <span class="go">Рассчитать изделие →</span>
      </a>""" for t, d in sorted(PROD_TILES, key=lambda x: x[0].lower()))

PROIZVODSTVO = page_head("Производство", "Что мы изготавливаем",
                         "Собственная площадка в Сочи. Изделия по чертежу и образцу — серийно и штучно.") + f"""
<section style="padding-top:44px">
  <div class="wrap">
    <div class="tiles">
{_prod_tiles_html}
    </div>
  </div>
</section>

<section class="cards-dark">
  <div class="wrap">
    <div class="sec-head"><span class="tag">Оборудование</span><h2>Как работаем</h2></div>
    <div class="cards">
      <div class="card"><h3>Лазерный комплекс</h3><p>Раскрой листа до 30 мм, чистый рез, файлы DXF/DWG или эскиз.</p></div>
      <div class="card"><h3>Листогиб BEKE</h3><p>Длина гиба до 3,2 м, сложные гибы по чертежу.</p></div>
      <div class="card"><h3>Сверлильный станок</h3><p>Отверстия до 75 мм, серийные партии.</p></div>
      <div class="card"><h3>Сварочные посты</h3><p>Металлоконструкции и закладные, аттестованные сварщики.</p></div>
    </div>
  </div>
</section>
{CTA_BAND}
"""

OTZYVY = page_head("Отзывы", "Отзывы клиентов",
                   "Оценки клиентов с Яндекс Карт — прямо с карточки организации.") + f"""
<section style="padding-top:44px">
  <div class="wrap">
    <div class="rev-grid">
      <iframe class="reviews-embed" title="Отзывы о МЕТЭК Сочи на Яндекс.Картах"
        src="https://yandex.ru/maps-reviews-widget/{YA_OID}?comments" loading="lazy" frameborder="0"></iframe>
      <aside class="rev-side">
        <h3>Оценка 4,9 на Яндекс Картах</h3>
        <p>Отзывы подтягиваются напрямую с карточки организации — их нельзя отредактировать или отфильтровать на сайте.</p>
        <div class="map-links" style="margin-top:0">
          <a href="{YA_ORG_URL}" target="_blank" rel="noopener"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 22s7-6.2 7-12a7 7 0 0 0-14 0c0 5.8 7 12 7 12z"/><circle cx="12" cy="10" r="2.6"/></svg>Яндекс Карты</a>
          <a href="{GIS_URL}" target="_blank" rel="noopener"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 22s7-6.2 7-12a7 7 0 0 0-14 0c0 5.8 7 12 7 12z"/><circle cx="12" cy="10" r="2.6"/></svg>2ГИС</a>
        </div>
        <p style="margin-top:22px">Работали с нами? Оценка занимает минуту и помогает другим клиентам.</p>
        <a class="btn" href="kontakty.html#zvonok">Стать нашим клиентом</a>
      </aside>
    </div>
  </div>
</section>
"""

KONTAKTY = page_head("Контакты", "Контакты",
                     "Склад и производство в Сочи. Звоните в рабочее время или оставьте заявку — перезвоним сами.") + f"""
<section style="padding-top:44px;padding-bottom:24px">
  <div class="wrap">
    <div class="svc">
      <article><h3>Телефон</h3><ul><li><a href="{PHONE_HREF}">{PHONE}</a></li><li>Пн–Пт: 8:00–17:00</li></ul></article>
      <article><h3>Почта</h3><ul><li><a href="mailto:{EMAIL}">{EMAIL}</a></li><li>Заявки и чертежи</li></ul></article>
      <article><h3>Адрес</h3><ul><li>{ADDR}</li><li>Самовывоз по согласованию</li></ul></article>
    </div>
  </div>
</section>

<section style="padding-top:0;padding-bottom:24px">
  <div class="wrap">
    <iframe class="map-embed" title="МЕТЭК Сочи на карте" src="{YA_EMBED}"
      loading="lazy" allowfullscreen frameborder="0"></iframe>
    <div class="map-links">
      <a href="{YA_ORG_URL}" target="_blank" rel="noopener" title="Открыть в Яндекс Картах"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 22s7-6.2 7-12a7 7 0 0 0-14 0c0 5.8 7 12 7 12z"/><circle cx="12" cy="10" r="2.6"/></svg>Яндекс Карты</a>
      <a href="{GIS_URL}" target="_blank" rel="noopener" title="Открыть в 2ГИС"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 22s7-6.2 7-12a7 7 0 0 0-14 0c0 5.8 7 12 7 12z"/><circle cx="12" cy="10" r="2.6"/></svg>2ГИС</a>
    </div>
  </div>
</section>

<section id="zvonok" style="background:#fff;border-top:1px solid var(--line);border-bottom:1px solid var(--line)">
  <div class="wrap call">
    <div>
      <div class="sec-head" style="margin-bottom:14px">
        <span class="tag">Заявка</span>
        <h2>Оставьте заявку для обратного звонка</h2>
      </div>
      <p style="color:var(--muted);max-width:46ch">Данные с формы уходят менеджеру на почту —
         он перезвонит, поможет подобрать позиции и посчитает стоимость.</p>
    </div>
    <form id="callForm" novalidate>
      <div>
        <label for="cfName">Ваше имя</label>
        <input id="cfName" name="name" autocomplete="name" maxlength="60" required>
      </div>
      <div>
        <label for="cfPhone">Телефон</label>
        <input id="cfPhone" name="phone" type="tel" autocomplete="tel" inputmode="tel" placeholder="+7" maxlength="20" required>
      </div>
      <div class="hp" aria-hidden="true">
        <label for="cfSite">Не заполняйте это поле</label>
        <input id="cfSite" name="website" tabindex="-1" autocomplete="off">
      </div>
      <button class="btn" type="submit">Заказать обратный звонок</button>
      <p class="form-msg" id="formMsg" role="status"></p>
      <p class="consent">Нажимая кнопку, вы соглашаетесь с <a href="privacy.html">политикой конфиденциальности</a>.</p>
    </form>
  </div>
</section>
"""

SITE_URL = "https://meteksochi.ru"

PRIVACY = page_head("Политика конфиденциальности", "Политика конфиденциальности",
                    "Обработка персональных данных пользователей сайта ООО «МЕТЭК Сочи».") + f"""
<section style="padding-top:44px">
  <div class="wrap doc">
    <p>Настоящая Политика определяет порядок, условия обработки персональных данных пользователей
    Интернет-сайта <a href="{SITE_URL}">{SITE_URL}</a> (далее — Сайт) и устанавливает требования
    по обеспечению безопасности персональных данных пользователей Администрацией Сайта.</p>
    <p>Политика разработана и реализуется в соответствии с действующим национальным законодательством
    в сфере персональных данных.</p>

    <h2>Определения</h2>
    <p><b>Персональные данные</b> — любая информация, относящаяся к прямо или косвенно определённому
    или определяемому физическому лицу (гражданину). К такой информации могут относиться: Ф.И.О., год,
    месяц, дата и место рождения, почтовый адрес, адрес электронной почты, номер телефона, сведения
    о семейном, социальном, имущественном положении, сведения об образовании, профессии, доходах,
    сведения о состоянии здоровья, а также другая информация.</p>
    <p><b>Обработка персональных данных</b> — любое действие с персональными данными, совершаемое
    с использованием средств автоматизации или без использования таких средств. К таким действиям могут
    относиться: сбор, получение, запись, систематизация, накопление, хранение, обновление, изменение,
    извлечение, использование, передача (распространение, предоставление, доступ), обезличивание,
    блокирование, удаление, уничтожение персональных данных.</p>
    <p><b>Пользователь</b> — физическое лицо, получающее доступ к функционалу Сайта.</p>
    <p><b>Администрация Сайта/Компания</b> — компания ООО «МЕТЭК Сочи». Адрес: Россия,
    Краснодарский край, г. Сочи, ул. Гастелло, д. 42, к. 1.</p>

    <h2>Принципы обработки</h2>
    <p>Обработка персональных данных пользователей Сайта производится с соблюдением следующих принципов:</p>
    <ul>
      <li>законности;</li>
      <li>ограничения обработки персональных данных достижением конкретных, заранее определённых и законных целей;</li>
      <li>недопущения обработки персональных данных, несовместимой с целями сбора персональных данных;</li>
      <li>недопущения объединения баз данных, содержащих персональные данные, обработка которых осуществляется в целях, несовместимых между собой.</li>
    </ul>
    <p>В процессе обработки персональных данных пользователей со стороны Администрации Сайта
    предпринимаются необходимые и достаточные правовые, организационные и технические меры для защиты
    персональных данных от неправомерного или случайного доступа к ним, уничтожения, изменения,
    блокирования, копирования, предоставления, распространения персональных данных, а также от иных
    неправомерных действий в отношении персональных данных.</p>
    <p>При обработке персональных данных пользователей используются технические средства
    и технологические решения, направленные на обезличивание субъектов персональных данных при доступе
    к содержащей персональные данные информации лиц, непосредственно задействованных в процессе
    обработки персональных данных.</p>
    <p>Персональные данные пользователей хранятся на собственных серверах Компании в полном соответствии
    с правовыми и нормативно-техническими требованиями, установленными действующим законодательством.</p>
    <p>Администрация Сайта не осуществляет обработку биометрических и специальных категорий персональных
    данных пользователей.</p>
    <p>При изменении своих персональных данных пользователь соглашается, что такое изменение происходит
    на тех же условиях, что и первоначальное предоставление им своих персональных данных, не требует
    оформления дополнительного согласия, и изменённые персональные данные обрабатываются в том же порядке,
    что и первоначально предоставленные персональные данные.</p>
    <p>Администрация Сайта гарантирует и обеспечивает полную конфиденциальность персональных данных
    пользователей, обрабатываемых при предоставлении доступа к функционалу Сайта, за исключением случаев,
    прямо предусмотренных настоящей Политикой или действующим законодательством.</p>

    <h2>Какие данные обрабатываются и для чего</h2>
    <p>Администрация Сайта осуществляет обработку только тех персональных данных, которые необходимы
    для доставки товаров пользователю, оказания услуг пользователю, а также для надлежащего исполнения
    договоров, заключаемых с пользователями:</p>
    <ul>
      <li><b>Фамилия, имя, отчество (при наличии)</b> — для целей идентификации пользователя при заключении договора купли-продажи.</li>
      <li><b>Телефонный номер</b> — для цели осуществления оперативной связи с пользователем по вопросам, связанным с обработкой заказов, доставкой товаров, приобретённых пользователем на Сайте, информированием по вопросам работы Сайта.</li>
      <li><b>Адрес электронной почты</b> — для целей направления пользователю чеков и иных документов и информации, связанных с приобретением товаров на Сайте и необходимых для подтверждения факта заключения договора купли-продажи и получения приобретённых товаров в пунктах выдачи заказов службы доставки, а также для цели осуществления информационных, новостных и рекламных рассылок в адрес пользователя.</li>
      <li><b>Почтовый адрес</b> — только в случаях доставки пользователям товаров, приобретённых ими на Сайте.</li>
    </ul>
    <p>Осуществление информационных, новостных и рекламных рассылок в адрес пользователя производится
    Администрацией Сайта только в том случае, если имеется согласие пользователя на получение таких
    рассылок. Пользователь в любой момент может отказаться от любых рассылок, на которые он был подписан
    или иным образом давал своё согласие.</p>

    <h2>Передача данных третьим лицам</h2>
    <p>Администрация Сайта вправе передавать персональные данные пользователей третьим лицам в следующих случаях:</p>
    <ul>
      <li>Пользователь явно выразил своё согласие на такие действия.</li>
      <li>Передача необходима для исполнения договора, заключённого с пользователем.</li>
      <li>Передача предусмотрена действующим законодательством.</li>
    </ul>
    <p>Пользователь имеет право в любой момент потребовать от Администрации Сайта прекращения обработки
    его персональных данных.</p>

    <h2>Cookie и статистика</h2>
    <p>Для целей статистической обработки информации, оптимизации и дальнейшего развития функционала Сайта
    создаются и используются файлы «cookie», фиксируются сведения о сетевых адресах, с которых
    пользователями производится регистрация и авторизация на Сайте, а также может сохраняться информация
    о действиях пользователей, совершаемых ими в процессе использования функционала Сайта, в том числе
    с помощью специализированных программных средств (Яндекс.Метрика, top.mail.ru, LiveInternet,
    VK Реклама).</p>

    <h2>Сроки обработки</h2>
    <p>Персональные данные пользователей обрабатываются в течение 5 лет с момента заключения последнего
    договора с пользователем для целей осуществления бухгалтерского и налогового учёта в соответствии
    со ст. 23 Налогового кодекса Российской Федерации, ст. 29 Федерального закона «О бухгалтерском
    учёте» №402-ФЗ.</p>
    <p>По окончании срока обработки, в том числе по требованию пользователя, персональные данные
    пользователей удаляются из информационных систем Администрации Сайта.</p>

    <h2>Реквизиты Администрации Сайта</h2>
    <p>ООО «МЕТЭК Сочи» · ОГРН 1232300075292 · ИНН 2367035393<br>
    {ADDR}<br>
    Телефон: <a href="{PHONE_HREF}">{PHONE}</a> · E-mail: <a href="mailto:{EMAIL}">{EMAIL}</a></p>
  </div>
</section>
"""

page("index.html", "МЕТЭК Сочи — металлопрокат и металлоизделия со склада в Сочи",
     "Металлопрокат в наличии и под заказ в Сочи: труба, арматура, лист, двутавр, швеллер. Лазерная резка до 30 мм и производство изделий. Цены за тонну с НДС.", INDEX)
page("katalog.html", "Каталог металлопроката в Сочи — цены за тонну с НДС | МЕТЭК Сочи",
     "Прайс на металлопрокат со склада в Сочи: арматура, труба, лист, швеллер, уголок. Цены за тонну с НДС, обновляются вместе с прайсом склада.", KATALOG)
page("uslugi.html", "Услуги металлообработки в Сочи — МЕТЭК Сочи",
     "Обработка металла на своём производстве в Сочи: лазерная резка до 30 мм, гибка до 3,2 м, сверление до 75 мм, металлоконструкции.", USLUGI)
for fname, s in SERVICES.items():
    page(fname, s["title"], s["desc"],
         service_page(s["h1"], s["sub"], s["facts"], s["about_title"], s["about_html"], s["faq"], s["do"], s["do_sub"]))
page("proizvodstvo.html", "Производство металлоизделий в Сочи — МЕТЭК Сочи",
     "Изготовление металлоизделий в Сочи: металлоконструкции, закладные, анкерные болты и группы, опоры, каркасы свай.", PROIZVODSTVO)
page("otzyvy.html", "Отзывы клиентов — МЕТЭК Сочи",
     "Отзывы клиентов МЕТЭК Сочи с Яндекс.Карт и 2ГИС.", OTZYVY)
page("kontakty.html", "Контакты — МЕТЭК Сочи",
     f"Контакты МЕТЭК Сочи: {PHONE}, {EMAIL}, {ADDR}.", KONTAKTY)
page("privacy.html", "Политика конфиденциальности — МЕТЭК Сочи",
     "Политика обработки персональных данных сайта МЕТЭК Сочи.", PRIVACY)
