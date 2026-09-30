"""Real browser acceptance test. Run only against a disposable demo database.

WALLET_BASE_URL, DJANGO_SUPERUSER_USERNAME and DJANGO_SUPERUSER_PASSWORD configure
an existing server. --start-server starts and stops Django in this process.
WALLET_DB_PATH must then explicitly point to a separate test database.
"""

import argparse
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo
import re
import atexit
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("WALLET_BASE_URL", "http://127.0.0.1:8000")
OUT = Path(os.environ.get("WALLET_SCREENSHOT_DIR", "test-results"))


def assert_bar_tooltip(page, name, screenshot):
    chart = page.locator(f'[data-chart="{name}"]')
    chart.scroll_into_view_if_needed()
    point = chart.evaluate("""el => {
        for (const path of el.querySelectorAll('.barlayer .point path')) {
            const r = path.getBoundingClientRect();
            if (r.width > 2 && r.height > 2 && r.y >= 0 && r.bottom < innerHeight)
                return {x:r.x+r.width/2, y:r.y+r.height/2};
        }
    }""")
    assert point, f"No visible bar in {name}"
    page.mouse.move(point["x"], point["y"])
    tip = chart.locator("..").locator(".bar-tooltip")
    expect(tip).to_be_visible()
    expect(tip.locator("dt")).to_have_text(["Mese", "Importo"])
    actual = tip.locator("dd").all_text_contents()
    expected = chart.evaluate("""el => {
        const tip=el.parentElement.querySelector('.bar-tooltip');
        const trace=el.data.find(t=>t.name===tip.querySelector('strong').textContent);
        const month=tip.querySelector('dd').textContent;
        return [month, trace.customdata[trace.x.indexOf(month)]];
    }""")
    assert actual == expected
    assert (
        tip.evaluate("el=>getComputedStyle(el).backgroundColor") == "rgb(255, 255, 255)"
    )
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=str(OUT / screenshot))
    page.mouse.move(0, 0)
    expect(tip).not_to_be_visible()


def amount(text):
    return Decimal(
        text.replace("€", "")
        .replace(".", "")
        .replace(",", ".")
        .replace("−", "-")
        .strip()
    )


def assert_balance_tooltip(page, screenshot):
    chart = page.locator('[data-chart="daily"]')
    chart.scroll_into_view_if_needed()
    page.wait_for_function(
        "el => Math.abs(el.querySelector('.main-svg').getBoundingClientRect().width - el.clientWidth) < 2",
        arg=chart.element_handle(),
    )
    point = chart.evaluate("""el => {
        el.on('plotly_hover', event => {
            const point = event.points[0];
            el.walletTestHover = {index: point.pointNumber, curve: point.curveNumber};
        });
        const path = el.querySelector('.scatterlayer .js-line');
        const point = path.getPointAtLength(path.getTotalLength()/2);
        const screen = new DOMPoint(point.x, point.y).matrixTransform(path.getScreenCTM());
        return {x:screen.x, y:screen.y};
    }""")
    page.mouse.move(point["x"], point["y"])
    tip = chart.locator("..").locator(".line-tooltip")
    expect(tip).to_be_visible()
    expect(tip.locator("strong")).to_have_text("Saldo")
    expect(tip.locator("dt")).to_have_text(["Data", "Saldo"])
    expected = chart.evaluate("""el => {
        const {index, curve} = el.walletTestHover;
        const trace = el.data[curve];
        return [trace.x[index].split('-').reverse().join('/'), trace.customdata[index]];
    }""")
    assert tip.locator("dd").all_text_contents() == expected
    spike = chart.locator(".spikeline").last
    expect(spike).to_be_attached()
    assert spike.get_attribute("x1") == spike.get_attribute("x2")
    assert float(spike.get_attribute("y2")) > float(spike.get_attribute("y1"))
    expected_x = chart.evaluate("""el => {
        const {index, curve} = el.walletTestHover;
        const axis = el._fullLayout.xaxis;
        return el.getBoundingClientRect().x + axis._offset + axis.d2p(el.data[curve].x[index]);
    }""")
    assert abs(spike.bounding_box()["x"] - expected_x) < 2
    assert (
        tip.evaluate("el=>getComputedStyle(el).backgroundColor") == "rgb(255, 255, 255)"
    )
    box = tip.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= page.viewport_size["width"]
    page.screenshot(path=str(OUT / screenshot))
    page.mouse.move(0, 0)
    expect(tip).not_to_be_visible()
    expect(chart.locator(".spikeline")).to_have_count(0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-server", action="store_true")
    args = parser.parse_args()
    username = os.environ["DJANGO_SUPERUSER_USERNAME"]
    password = os.environ["DJANGO_SUPERUSER_PASSWORD"]
    if args.start_server:
        if os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URI"):
            raise RuntimeError(
                "Rimuovi DATABASE_URL e POSTGRES_URI prima di avviare il database SQLite di test."
            )
        selected = os.environ.get("WALLET_DB_PATH")
        if (
            not selected
            or Path(selected).resolve() == (ROOT / "wallet.sqlite3").resolve()
        ):
            raise RuntimeError(
                "Seleziona un database di test separato con WALLET_DB_PATH."
            )
        OUT.mkdir(parents=True, exist_ok=True)
        log = (OUT / "server.log").open("w")
        server = subprocess.Popen(
            [sys.executable, "manage.py", "runserver", "127.0.0.1:8000", "--noreload"],
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        atexit.register(server.terminate)
        for _ in range(50):
            try:
                urllib.request.urlopen(BASE + "/healthz/", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        else:
            raise RuntimeError("Il server di test non risponde.")
    OUT.mkdir(parents=True, exist_ok=True)
    errors = []
    failed = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on(
            "response",
            lambda r: failed.append(f"{r.status} {r.url}") if r.status >= 400 else None,
        )
        page.goto(BASE + "/accedi/")
        page.get_by_label("Nome utente").fill(username)
        page.get_by_label("Password", exact=True).fill(password)
        page.get_by_role("button", name="Mostra password", exact=True).click()
        expect(page.locator("#id_password")).to_have_attribute("type", "text")
        page.get_by_role("button", name="Nascondi password", exact=True).click()
        expect(page.locator("#id_password")).to_have_attribute("type", "password")
        # Capture the empty form, without credentials in the screenshot.
        page.get_by_label("Nome utente").fill("")
        page.get_by_label("Password", exact=True).fill("")
        for width in [1440, 390, 360]:
            page.set_viewport_size({"width": width, "height": 900})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(OUT / f"login-{width}.png"), full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.get_by_label("Nome utente").fill(username)
        page.get_by_label("Password", exact=True).fill(password)
        page.get_by_role("button", name="Accedi", exact=True).click()
        expect(page).to_have_url(BASE + "/dashboard/")
        page.wait_for_load_state("load")
        for width, nav in [(1440, ".main-nav"), (390, ".mobile-bottom-navigation")]:
            page.set_viewport_size({"width": width, "height": 1000})
            for label, route in [
                ("Overview", "/overview/"),
                ("Dashboard", "/dashboard/"),
            ]:
                page.locator(nav).get_by_role("link", name=label, exact=True).click()
                expect(page).to_have_url(BASE + route)
                expect(page.locator("h1")).to_have_text(label)
                expect(page.locator(nav + ' [aria-current="page"]')).to_have_text(label)
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.goto(BASE + "/?periodo=tutto&conto=tutti")
        expect(page).to_have_url(BASE + "/dashboard/?periodo=tutto&conto=tutti")
        expect(page.locator("#daily-chart .js-line")).to_have_count(1)
        assert (
            page.locator("#daily-chart .main-svg").first.bounding_box()["width"] > 800
        ), "Plotly SVG clipped by CSS"
        page.screenshot(path=str(OUT / "dashboard-desktop.png"), full_page=True)
        for width in [1440, 390]:
            page.set_viewport_size({"width": width, "height": 1000})
            assert_balance_tooltip(page, f"balance-tooltip-{width}.png")
        page.set_viewport_size({"width": 1440, "height": 1000})
        assert page.evaluate("""() => {
            const hero = document.querySelector('.balance-card');
            const filters = document.querySelector('#page-filters');
            const kpis = document.querySelector('.kpi-grid');
            return hero.compareDocumentPosition(filters) & Node.DOCUMENT_POSITION_FOLLOWING
                && filters.compareDocumentPosition(kpis) & Node.DOCUMENT_POSITION_FOLLOWING;
        }""")
        expect(page.locator(".owner-chip")).to_have_count(0)
        expect(page.locator(".topbar .brand")).to_have_text("Wallet")
        earliest = page.locator('[name="inizio"]').input_value()
        today = datetime.now(ZoneInfo("Europe/Rome")).strftime("%d/%m/%Y")
        page.locator('[data-filter-group="period"] > summary').click()
        page.locator('[name="inizio"]').fill(today)
        page.locator('[name="fine"]').fill(today)
        page.get_by_role("heading", name="Dashboard", exact=True).click()
        expect(page).to_have_url(re.compile("periodo=custom"))
        page.locator('[data-filter-group="period"] > summary').click()
        page.locator('[data-period="tutto"]').click()
        expect(page.locator('[name="inizio"]')).to_have_value(earliest)
        expect(page.locator('[name="fine"]')).to_have_value(today)
        expect(page.locator("[data-period-field]")).to_have_value("tutto")
        page.locator('[data-filter-group="account"] > summary').click()
        page.screenshot(path=str(OUT / "filters-desktop.png"), full_page=True)
        expect(
            page.get_by_role("button", name="Applica filtri", exact=True)
        ).to_have_count(0)
        page.get_by_role("button", name="Nessuno", exact=True).click()
        expect(page.locator('[name="conto"][type="checkbox"]:checked')).to_have_count(0)
        expect(page.locator(".balance-card strong")).to_have_text("0,00 €")
        expect(
            page.locator('[data-filter-group="account"] .filter-caption strong')
        ).to_have_text("Nessuno")
        page.reload()
        expect(page.locator('[name="conto"][type="checkbox"]:checked')).to_have_count(0)
        page.locator('[data-filter-group="account"] > summary').click()
        page.get_by_role("button", name="Tutti", exact=True).click()
        expect(
            page.locator('[name="conto"][type="checkbox"]:not(:checked)')
        ).to_have_count(0)
        # Closing a panel during a pending automatic update must not reopen it.
        account_id = page.locator(
            '[name="conto"][type="checkbox"]'
        ).first.get_attribute("value")
        page.evaluate(
            "() => { window.realFetch = window.fetch; window.fetch = (...args) => new Promise(resolve => setTimeout(() => resolve(window.realFetch(...args)), 300)); }"
        )
        page.locator('[name="conto"][type="checkbox"]').first.uncheck()
        page.get_by_role("heading", name="Dashboard", exact=True).click()
        page.wait_for_function(
            "id => !new URL(location.href).searchParams.getAll('conto').includes(id)",
            arg=account_id,
        )
        expect(page.locator("[data-filter-form] details[open]")).to_have_count(0)
        page.evaluate("() => { window.fetch = window.realFetch; }")
        page.get_by_role("link", name="Ripristina", exact=True).click()
        expect(
            page.locator('[name="conto"][type="checkbox"]:not(:checked)')
        ).to_have_count(0)
        page.locator('[data-filter-group="period"] > summary').click()
        page.locator('[name="inizio"]').fill(earliest)
        page.locator('[name="fine"]').fill(today)
        page.locator('[name="fine"]').press("Enter")
        expect(page).to_have_url(re.compile("periodo=custom"))
        expect(page.locator('[name="inizio"]')).to_have_value(earliest)
        expect(page.locator('[name="fine"]')).to_have_value(today)
        expect(page.locator("[data-period-field]")).to_have_value("custom")
        page.locator('[data-period="1m"]').click()
        expect(page).to_have_url(re.compile("periodo=1m"))
        page.locator('[data-global-period="3m"]').click()
        expect(page).to_have_url(re.compile("periodo=3m"))
        expect(page.locator("[data-period-field]")).to_have_value("3m")
        # All modes preserve exactly the same accounting totals.
        series = page.evaluate(
            'JSON.parse(document.querySelector("#chart-data").textContent).flows'
        )
        for traces in series.values():
            assert all(trace["type"] == "bar" for trace in traces)
        assert_bar_tooltip(page, "flows", "histogram-total-tooltip.png")
        assert_bar_tooltip(page, "net", "histogram-net-tooltip.png")
        expect(
            page.locator('[data-chart="net"]')
            .locator("..")
            .locator("..")
            .locator(".panel-heading .badge")
        ).to_have_count(0)
        for mode in ["tipo", "categoria"]:
            page.locator(f'[data-flow="{mode}"]').click()
            actual = page.locator('[data-chart="flows"]').evaluate(
                "(el)=>el.data.length"
            )
            assert actual == len(series[mode])
            assert_bar_tooltip(page, "flows", f"histogram-{mode}-tooltip.png")
        page.locator("[data-new-movement]").click()
        expect(page.locator("dialog")).to_be_visible()
        page.keyboard.press("Escape")
        expect(page.locator("dialog")).not_to_be_visible()
        page.locator("[data-new-movement]").click()
        page.locator("dialog a").filter(has_text="Entrata").click()
        expect(page.get_by_role("heading", name="Nuova entrata")).to_be_visible()
        page.locator("[name=account]").select_option(label="Conto principale")
        page.get_by_role("radio", name="Entrate", exact=True).click()
        page.get_by_role("radio", name="Stipendio", exact=True).click()
        page.locator("[name=amount]").fill("1.234,56")
        page.locator("[name=description]").fill("Verifica browser movimento")
        page.get_by_role("button", name="Salva movimento", exact=True).click()
        expect(page).to_have_url(BASE + "/movimenti/")
        page.locator("[name=q]").fill("Verifica browser movimento")
        expect(page.locator(".movement-table tbody tr")).to_have_count(1)
        expect(page.locator(".movement-table")).to_contain_text("1.234,56")
        with page.expect_download() as download:
            page.get_by_role("link", name="↓ CSV", exact=True).click()
        assert download.value.suggested_filename == "movimenti_wallet.csv"
        page.locator(".row-actions a").click()
        page.locator("[name=amount]").fill("1.200,00")
        page.get_by_role("button", name="Salva movimento", exact=True).click()
        page.goto(BASE + "/movimenti/?q=Verifica+browser+movimento")

        def accept_dialog(dialog):
            dialog.accept()

        page.on("dialog", accept_dialog)
        page.get_by_role("button", name="Elimina Verifica browser movimento").click()
        page.goto(BASE + "/movimenti/nuovo/?flusso=uscita")
        page.locator('[name="account"]').select_option(label="Conto principale")
        page.get_by_role("radio", name="Supermercati", exact=True).click()
        page.get_by_role("radio", name="Supermercato", exact=True).click()
        expect(page.get_by_role("radio", name="Necessaria", exact=True)).to_be_checked()
        page.get_by_role("radio", name="Extra", exact=True).check()
        page.locator('[name="amount"]').fill("25,30")
        page.locator('[name="description"]').fill("Verifica tipo personale")
        for width in [1440, 390, 360]:
            page.set_viewport_size(
                {"width": width, "height": 1000 if width == 1440 else 844}
            )
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(OUT / f"new-expense-{width}.png"), full_page=True)
        page.get_by_role("button", name="Salva movimento", exact=True).click()
        page.goto(BASE + "/movimenti/?q=Verifica+tipo+personale")
        expect(page.locator(".movement-table tbody")).to_contain_text("Uscita extra")
        page.locator(".row-actions a").click()
        expect(page.get_by_role("radio", name="Extra", exact=True)).to_be_checked()
        page.get_by_role("button", name="Salva movimento", exact=True).click()
        page.goto(BASE + "/movimenti/?q=Verifica+tipo+personale")
        page.get_by_role("button", name="Elimina Verifica tipo personale").click()
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.goto(BASE + "/giroconti/")
        page.locator("[name=source]").select_option(label="Conto principale")
        page.locator("[name=destination]").select_option(label="Carta quotidiana")
        page.locator("[name=amount]").fill("20,10")
        page.locator("[name=description]").fill("Verifica browser giroconto")
        page.get_by_role("button", name="Salva giroconto").click()
        page.goto(BASE + "/movimenti/?q=Verifica+browser+giroconto")
        expect(page.locator(".movement-table tbody tr")).to_have_count(2)
        page.locator(".row-actions a").first.click()
        page.locator("[name=amount]").fill("25,10")
        page.get_by_role("button", name="Salva giroconto").click()
        page.goto(BASE + "/movimenti/?q=Verifica+browser+giroconto")
        expect(page.locator(".movement-table")).to_contain_text("25,10")
        with page.expect_download() as transfer_download:
            page.get_by_role("link", name="↓ CSV", exact=True).click()
        transfer_csv = OUT / "roundtrip-wallet.csv"
        transfer_download.value.save_as(transfer_csv)
        page.goto(BASE + "/movimenti/?q=Verifica+browser+giroconto&vista=lista")
        expect(page.locator(".movement-list-view")).to_contain_text(
            "Giroconto · Trasferimento in entrata"
        )
        expect(page.locator(".movement-list-view")).to_contain_text(
            "Giroconto · Trasferimento in uscita"
        )
        expect(page.locator(".movement-value small")).to_have_count(0)
        page.goto(BASE + "/movimenti/?q=Verifica+browser+giroconto")
        page.get_by_role(
            "button", name="Elimina Verifica browser giroconto"
        ).first.click()
        page.goto(BASE + "/importa/")
        page.locator('input[type="file"]').set_input_files(transfer_csv)
        page.locator("form").filter(has=page.locator('input[type="file"]')).locator(
            'button[type="submit"]'
        ).click()
        expect(
            page.get_by_role("heading", name="Controlla le operazioni")
        ).to_be_visible()
        for width in [1440, 390, 360]:
            page.set_viewport_size(
                {"width": width, "height": 1000 if width == 1440 else 844}
            )
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth"
            ), f"CSV review overflow: {width}"
            page.screenshot(path=str(OUT / f"csv-review-{width}.png"), full_page=True)
        page.get_by_role("button", name="Conferma importazione", exact=True).click()
        expect(
            page.get_by_role("heading", name="Riepilogo importazione")
        ).to_be_visible()
        page.goto(BASE + "/movimenti/?q=Verifica+browser+giroconto")
        expect(page.locator(".movement-table tbody tr")).to_have_count(2)
        page.get_by_role(
            "button", name="Elimina Verifica browser giroconto"
        ).first.click()
        print(
            "OK CSV giroconto: esportazione, anteprima responsive e reimportazione",
            flush=True,
        )
        # Visually verify each actual screen, including forms and authentication.
        routes = [
            ("/dashboard/?periodo=tutto&conto=tutti", "dashboard"),
            ("/overview/?periodo=tutto&conto=tutti", "overview"),
            ("/movimenti/", "movimenti"),
            ("/movimenti/?vista=lista", "lista"),
            ("/budget/", "budget"),
            ("/configurazione/", "account"),
            ("/categorie/", "categorie"),
            ("/importa/", "import"),
            ("/backup/", "backup"),
            ("/giroconti/", "giroconto"),
            ("/movimenti/nuovo/?flusso=uscita", "nuova-uscita"),
            ("/password/cambia/", "password"),
        ]
        for route, name in routes:
            page.goto(BASE + route)
            page.wait_for_load_state("load")
            if page.locator("[data-chart]").count():
                expect(page.locator("[data-chart] .main-svg").first).to_be_attached()
            for width in [1440, 390, 360]:
                page.set_viewport_size(
                    {"width": width, "height": 1000 if width == 1440 else 844}
                )
                page.wait_for_timeout(120)
                if not page.evaluate(
                    "document.documentElement.scrollWidth<=innerWidth"
                ):
                    page.screenshot(
                        path=str(OUT / f"overflow-{name}-{width}.png"), full_page=True
                    )
                    print(
                        page.evaluate(
                            """() => ({width:innerWidth, scroll:document.documentElement.scrollWidth,
                        x:scrollX, elements:[...document.querySelectorAll('body *')].filter(el =>
                        el.getBoundingClientRect().right > innerWidth && !el.closest('.table-wrap')).map(el =>
                        ({tag:el.tagName, cls:el.className, rect:el.getBoundingClientRect().toJSON()})).slice(0,25)})"""
                        ),
                        flush=True,
                    )
                    raise AssertionError(f"Horizontal overflow: {name}/{width}")
                if width < 761:
                    expect(page.locator(".mobile-bottom-navigation a")).to_have_count(5)
                if name == "dashboard":
                    button = page.locator("[data-new-movement]")
                    assert (
                        button.evaluate("el => getComputedStyle(el).position")
                        == "static"
                    )
                    page.evaluate("scrollTo({top: 600, behavior: 'instant'})")
                    assert button.bounding_box()["y"] < 0
                    page.evaluate("scrollTo({top: 0, behavior: 'instant'})")
                if name in ["account", "categorie", "import", "backup", "password"]:
                    expect(page.locator("h1")).to_have_text("Account e impostazioni")
                    assert page.evaluate(
                        "document.querySelector('.settings-tabs').compareDocumentPosition(document.querySelector('.section-heading')) & Node.DOCUMENT_POSITION_FOLLOWING"
                    )
                if name == "budget":
                    expect(page.locator(".budget-kpis .kpi")).to_have_count(5)
                    expect(page.locator(".scope-badge")).to_have_text("Tutti i conti")
                if name == "movimenti":
                    assert page.locator(".movement-table").evaluate(
                        "el => getComputedStyle(el).fontFamily === getComputedStyle(document.body).fontFamily"
                    )
                    expect(page.locator(".movement-table thead th")).to_have_count(8)
                    expect(page.locator(".movement-table thead")).to_be_visible()
                    assert (
                        page.locator(".movement-table").evaluate(
                            "el => getComputedStyle(el).display"
                        )
                        == "table"
                    )
                    expect(
                        page.locator('[data-label="Categoria"] .dot').first
                    ).to_be_visible()
                    expect(page.locator('[data-label="Tipo"] .badge')).to_have_count(0)
                    if width < 761:
                        assert page.locator(".movement-table-view").evaluate(
                            "el => el.scrollWidth > el.clientWidth"
                        )
                if name == "lista":
                    expect(page.locator(".month-summary").first).not_to_contain_text(
                        "Netto"
                    )
                    expect(page.locator(".day-heading").first).not_to_contain_text(
                        "Netto"
                    )
                    assert page.evaluate(
                        "getComputedStyle(document.querySelector('.month-summary')).backgroundColor === getComputedStyle(document.querySelector('.day-heading')).backgroundColor"
                    )
                    expect(page.locator(".day-heading time").first).to_have_text(
                        re.compile(r"^[A-ZÀ-Üa-zà-ü]+, \d{1,2} [a-z]+$")
                    )
                    expect(page.locator(".movement-value small")).to_have_count(0)
                if (
                    name
                    in [
                        "dashboard",
                        "overview",
                        "budget",
                        "lista",
                        "movimenti",
                        "account",
                        "categorie",
                        "import",
                        "backup",
                        "password",
                    ]
                    and width != 360
                ):
                    page.screenshot(
                        path=str(OUT / f"{name}-{width}.png"), full_page=True
                    )
            print(f"OK {name}", flush=True)
        page.goto(BASE + "/movimenti/")
        page.locator("[data-sort-control]").select_option("amount")
        expect(page).to_have_url(re.compile("sort=amount"))
        expect(page.locator("[data-sort-control]")).to_have_value("amount")
        page.goto(BASE + "/overview/?periodo=tutto&conto=tutti")
        page.set_viewport_size({"width": 1440, "height": 1000})
        expect(page.get_by_role("heading", name="Overview", exact=True)).to_be_visible()
        page.get_by_role("link", name="Sottocategoria", exact=True).click()
        expect(
            page.get_by_role("heading", name="Riepilogo per sottocategoria")
        ).to_be_visible()
        page.locator('[data-filter-group="classification"] > summary').click()
        page.locator('[data-persist="categories-filter"] > summary').click()
        category_id = page.locator(
            '[name="categoria"][type="checkbox"]'
        ).first.get_attribute("value")
        page.locator('[name="categoria"][type="checkbox"]').first.uncheck()
        page.wait_for_function(
            "id => !new URL(location.href).searchParams.getAll('categoria').includes(id)",
            arg=category_id,
        )
        expect(page).to_have_url(re.compile("dettaglio=sottocategoria"))
        page.screenshot(path=str(OUT / "overview-choices.png"), full_page=True)
        page.get_by_role("heading", name="Overview", exact=True).click()
        expect(page.locator("[data-filter-form] details[open]")).to_have_count(0)
        page.get_by_role("link", name="Ripristina", exact=True).click()
        expect(
            page.locator('[name="categoria"][type="checkbox"]:not(:checked)')
        ).to_have_count(0)
        page.locator('[data-chart="donut"]').scroll_into_view_if_needed()
        point = page.locator('[data-chart="donut"] .pielayer').evaluate("""el => {
            const box=el.getBoundingClientRect(), cx=box.x+box.width/2, cy=box.y+box.height/2;
            for(let angle=0; angle<6.28; angle+=.1) {
                const x=cx+Math.cos(angle)*box.width*.44, y=cy+Math.sin(angle)*box.height*.44;
                if(document.elementFromPoint(x,y)?.closest('.slice')) return {x,y};
            }
        }""")
        assert point, "No donut slice found for hover"
        page.mouse.move(point["x"], point["y"])
        tooltip = page.locator(".donut-tooltip")
        expect(tooltip).to_be_visible()
        expect(tooltip.locator("dt")).to_have_text(
            ["Importo", "Percentuale", "Movimenti"]
        )
        # Check the values themselves, not only the labels or background color.
        expected = page.locator('[data-chart="donut"]').evaluate("""el => {
            const title = document.querySelector('.donut-tooltip > strong').textContent;
            return el.data[0].customdata[el.data[0].labels.indexOf(title)].map(String);
        }""")
        expect(tooltip.locator("dd")).to_have_text(expected)
        assert (
            tooltip.evaluate("el=>getComputedStyle(el).backgroundColor")
            == "rgb(255, 255, 255)"
        )
        page.screenshot(path=str(OUT / "overview-tooltip.png"))
        page.mouse.move(0, 0)
        expect(tooltip).not_to_be_visible()
        assert_bar_tooltip(page, "spending", "histogram-subcategories-tooltip.png")
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(200)
        assert_bar_tooltip(page, "spending", "histogram-mobile-tooltip.png")
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.locator("[data-month-picker]").select_option(index=1)
        expect(page).to_have_url(re.compile("periodo=mese"))
        page.locator(".chart-series summary").click()
        checkbox = page.locator(".series-options input").first
        checkbox.uncheck()
        assert (
            page.locator('[data-chart="spending"]').evaluate("(el)=>el.data[0].visible")
            == "legendonly"
        )
        page.goto(BASE + "/dashboard/?periodo=tutto&conto=tutti")
        page.locator('[data-flow="categoria"]').click()
        traces = page.locator('[data-chart="flows"]').evaluate(
            "el=>el.data.map(trace=>({name:trace.name,side:trace.offsetgroup}))"
        )
        assert all(
            not re.search(r" · (entrate|uscite)$", trace["name"]) for trace in traces
        )
        assert {trace["side"] for trace in traces} == {"income", "outgoing"}
        page.goto(BASE + "/budget/?mese=2026-09")
        expect(page.locator(".budget-period-bar strong")).to_have_text("Settembre 2026")
        expect(page.locator("tfoot th")).to_have_text("TOT")
        group = page.locator("[data-budget-group]").filter(
            has=page.locator(".budget-category strong", has_text=re.compile("^Casa$"))
        )
        group.locator("summary").click()
        original = group.locator("[data-budget-manual] input").input_value()
        original_total = amount(page.locator("[data-budget-grand-total]").inner_text())
        original_limit = amount(group.locator("[data-budget-total]").inner_text())
        original_remaining = amount(
            page.locator("[data-budget-remaining]").inner_text()
        )
        table = (
            page.locator("section.panel")
            .filter(has=page.get_by_role("heading", name="Spese per tipo", exact=True))
            .locator("table")
        )
        expect(table.locator("thead th")).to_have_text(
            ["Tipo", "Spesa", "Sulle entrate"]
        )
        expect(table.locator("tfoot tr > *")).to_have_count(3)
        expect(page.locator("[data-budget-unsaved]")).to_be_hidden()
        group.get_by_label("Per sottocategoria", exact=True).check()
        parts = group.locator("[data-budget-parts] input")
        rows = group.locator("[data-budget-subcategory]")
        expense_row = next(
            rows.nth(i)
            for i in range(rows.count())
            if Decimal(rows.nth(i).get_attribute("data-budget-spent")) > 0
        )
        expense_input = expense_row.locator("input")
        sub_progress = expense_row.locator(".budget-sub-progress")
        spent_sub = Decimal(expense_row.get_attribute("data-budget-spent"))
        for limit, label, state, width in [
            (spent_sub * 2, "50% · Regolare", "steady", "50%"),
            (
                (spent_sub / Decimal("0.9")).quantize(Decimal("0.01")),
                "90% · Vicino al limite",
                "near",
                None,
            ),
            (spent_sub / 2, "200% · Superato", "over", "100%"),
            (Decimal(0), "Limite zero · Superato", "over", "100%"),
        ]:
            expense_input.fill(f"{limit:.2f}".replace(".", ","))
            expect(sub_progress.locator("[data-budget-status]")).to_have_text(label)
            expect(sub_progress.locator(".progress-track")).to_have_class(
                re.compile(rf"\b{state}\b")
            )
            if width:
                assert (
                    sub_progress.locator(".progress-track > span").evaluate(
                        "el=>el.style.width"
                    )
                    == width
                )
        expense_input.fill("")
        expect(sub_progress.locator("[data-budget-status]")).to_have_text(
            "Nessun limite"
        )
        assert (
            sub_progress.locator(".progress-track > span").evaluate(
                "el=>el.style.width"
            )
            == "0%"
        )
        expense_input.fill("1,2345")
        expect(sub_progress.locator("[data-budget-status]")).to_have_text(
            "Controlla gli importi"
        )
        for index in range(parts.count()):
            parts.nth(index).fill("")
        parts.nth(0).fill("200,10")
        expense_input.fill("100,20")
        expect(group.locator("[data-budget-parts-total]")).to_have_text("300,30 €")
        expect(group.locator("[data-budget-total]")).to_have_text("300,30 €")
        expect(group.locator("[data-budget-source]")).to_have_text(
            "Somma sottocategorie"
        )
        assert amount(
            page.locator("[data-budget-grand-total]").inner_text()
        ) == original_total - original_limit + Decimal("300.30")
        spent = Decimal(group.get_attribute("data-budget-spent"))
        expect(group.locator(".budget-summary [data-budget-status]")).to_contain_text(
            "Superato"
            if spent > Decimal("300.30")
            else "Regolare" if spent < Decimal("255.255") else "Vicino al limite"
        )
        expected_remaining = abs(Decimal("300.30") - spent)
        assert (
            amount(
                group.locator("[data-budget-balance]")
                .inner_text()
                .split(" · ")[1]
                .split(" ", 1)[1]
            )
            == expected_remaining
        )
        expect(page.locator("[data-budget-unsaved]")).to_be_visible()
        group.locator("summary").click()
        expect(group.locator("[data-budget-total]")).to_have_text("300,30 €")
        group.locator("summary").click()
        expense_input.fill("1,2345")
        expect(group.locator("[data-budget-total]")).to_have_text(
            "Controlla gli importi"
        )
        expect(page.locator("[data-budget-grand-total]")).to_have_text("Da verificare")
        expect(page.locator("[data-budget-remaining]")).to_have_text("—")
        parts.nth(0).fill("")
        expense_input.fill("0")
        expect(group.locator("[data-budget-total]")).to_have_text("0,00 €")
        expect(group.locator(".budget-summary [data-budget-status]")).to_contain_text(
            "Limite zero"
        )
        expense_input.fill("")
        expect(group.locator("[data-budget-total]")).to_have_text("Non impostato")
        expect(group.locator(".budget-summary [data-budget-status]")).to_have_text(
            "Nessun limite"
        )
        parts.nth(0).fill("200,10")
        expense_input.fill("100,20")
        for width in [1440, 390, 360]:
            page.set_viewport_size(
                {"width": width, "height": 1000 if width == 1440 else 844}
            )
            group.scroll_into_view_if_needed()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(OUT / f"budget-allocation-{width}.png"))
        page.get_by_role("button", name="Salva budget del mese", exact=True).click()
        expect(group.locator("[data-budget-total]")).to_have_text("300,30 €")
        expect(page.locator("[data-budget-unsaved]")).to_be_hidden()
        page.reload()
        expect(group.locator("[data-budget-total]")).to_have_text("300,30 €")
        group.locator("summary").click()
        expect(group.get_by_label("Per sottocategoria", exact=True)).to_be_checked()
        expect(group.locator("[data-budget-parts] input").nth(0)).to_have_value(
            "200,10"
        )
        group.get_by_label("Limite unico", exact=True).check()
        group.locator("[data-budget-manual] input").fill(original)
        assert (
            amount(page.locator("[data-budget-grand-total]").inner_text())
            == original_total
        )
        assert (
            amount(page.locator("[data-budget-remaining]").inner_text())
            == original_remaining
        )
        page.get_by_role("button", name="Salva budget del mese", exact=True).click()
        page.locator("#budget-month").fill("2026-08")
        page.get_by_role("button", name="Mostra", exact=True).click()
        expect(page.locator(".budget-period-bar strong")).to_have_text("Agosto 2026")
        page.goto(BASE + "/budget/?mese=2026-09")
        group.locator("summary").click()
        expect(group.get_by_label("Limite unico", exact=True)).to_be_checked()
        expect(group.locator("[data-budget-manual] input")).to_have_value(original)
        print("OK nuovi filtri, istogrammi e budget per sottocategoria", flush=True)
        page.goto(BASE + "/configurazione/")
        page.remove_listener("dialog", accept_dialog)
        page.once("dialog", lambda dialog: dialog.dismiss())
        page.get_by_role("button", name="Esci", exact=True).click()
        expect(page).to_have_url(BASE + "/configurazione/")
        page.once("dialog", lambda dialog: dialog.accept())
        page.get_by_role("button", name="Esci", exact=True).click()
        expect(page).to_have_url(BASE + "/accedi/")
        assert not errors, errors
        assert not failed, failed
        browser.close()
    print(
        "Browser acceptance: OK; no JavaScript errors, missing assets or viewport overflow.",
        flush=True,
    )


if __name__ == "__main__":
    main()
