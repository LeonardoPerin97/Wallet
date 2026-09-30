"""One interpretation of dates and selections for pages, charts and CSV."""

import calendar
from dataclasses import dataclass
from datetime import date

from django.db.models import Q
from django.utils import timezone

from ..models import Account, Category, Subcategory, Transaction, Transfer
from .formatting import parse_date

PERIODS = [("1m", "1M"), ("3m", "3M"), ("6m", "6M"), ("1y", "1A"), ("tutto", "Tutto")]
TRANSFER_IN = "Trasferimento in entrata"
TRANSFER_OUT = "Trasferimento in uscita"
MONTH_NAMES = [
    "Gennaio",
    "Febbraio",
    "Marzo",
    "Aprile",
    "Maggio",
    "Giugno",
    "Luglio",
    "Agosto",
    "Settembre",
    "Ottobre",
    "Novembre",
    "Dicembre",
]


def italian_month_label(day):
    return f"{MONTH_NAMES[day.month - 1]} {day.year}"


def first_ledger_date():
    days = [
        Transaction.objects.order_by("date").values_list("date", flat=True).first(),
        Transfer.objects.order_by("date").values_list("date", flat=True).first(),
    ]
    return min([timezone.localdate()] + [d for d in days if d])


def values(params, key):
    return (
        params.getlist(key)
        if hasattr(params, "getlist")
        else [params[key]] if key in params else []
    )


def select_ids(params, key, available):
    raw = values(params, key)
    if not raw or "tutti" in raw:
        return set(available)
    return {int(v) for v in raw if str(v).isdigit()} & set(available)


def compact(names, all_selected=False, all_label="Tutti"):
    if all_selected:
        return all_label
    return (
        (names[0] + (f" + {len(names)-1}" if len(names) > 1 else ""))
        if names
        else "Nessuno"
    )


@dataclass
class Filters:
    start: date
    end: date
    today: date
    earliest: date
    period: str
    accounts: list
    categories: list
    subcategories: list
    account_ids: set
    category_ids: set
    subcategory_ids: set
    kinds: set
    include_transfers: bool
    query: str = ""
    error: str = ""

    @classmethod
    def parse(cls, params, *, categories=True):
        today, earliest = timezone.localdate(), first_ledger_date()
        start, end, period, error = earliest, today, params.get("periodo", "tutto"), ""
        try:
            if period.startswith("mese:"):
                year, month = map(int, period[5:].split("-"))
                start = date(year, month, 1)
                end = date(year, month, calendar.monthrange(year, month)[1])
            elif period in {"1m", "3m", "6m", "1y"}:
                offset = {"1m": 1, "3m": 3, "6m": 6, "1y": 12}[period]
                index = today.year * 12 + today.month - 1 - offset
                year, month = index // 12, index % 12 + 1
                start = date(
                    year, month, min(today.day, calendar.monthrange(year, month)[1])
                )
            elif period == "tutto" and "periodo" in params:
                # Explicit All overrides dates left by the previous selection.
                start, end = earliest, today
            elif params.get("inizio") or params.get("fine"):
                start = (
                    parse_date(params["inizio"]) if params.get("inizio") else earliest
                )
                end = parse_date(params["fine"]) if params.get("fine") else today
                period = "custom"
            else:
                period = "tutto"
            if start > end:
                raise ValueError("La data iniziale deve precedere la data finale.")
        except (ValueError, TypeError):
            start, end, period = earliest, today, "tutto"
            error = "Intervallo non valido: è stato ripristinato tutto lo storico."
        accounts = list(Account.objects.all())
        cats = list(Category.objects.all())
        subs = list(Subcategory.objects.select_related("category"))
        account_ids = select_ids(params, "conto", [a.id for a in accounts])
        category_ids = (
            select_ids(params, "categoria", [c.id for c in cats])
            if categories
            else {c.id for c in cats}
        )
        sub_ids = (
            select_ids(params, "sottocategoria", [s.id for s in subs])
            if categories
            else {s.id for s in subs}
        )
        sub_ids &= {s.id for s in subs if s.category_id in category_ids}
        all_kinds = {v for v, _ in Transaction._meta.get_field("kind").choices} | {
            TRANSFER_IN,
            TRANSFER_OUT,
        }
        kinds = (
            set(values(params, "tipo"))
            if categories and "tipo" in params
            else all_kinds
        )
        if "Trasferimento" in kinds:
            kinds.update({TRANSFER_IN, TRANSFER_OUT})
        include_transfers = not categories or (
            "categoria" not in params
            or "giroconto" in values(params, "categoria")
            or "1" in values(params, "giroconti")
        )
        if categories and params.get("giroconti") == "0":
            include_transfers = False
        if (
            categories
            and "sottocategoria" in params
            and sub_ids != {s.id for s in subs if s.category_id in category_ids}
        ):
            include_transfers = False
        return cls(
            start,
            end,
            today,
            earliest,
            period,
            accounts,
            cats,
            subs,
            account_ids,
            category_ids,
            sub_ids,
            kinds & all_kinds,
            include_transfers,
            params.get("q", "").strip() if categories else "",
            error,
        )

    def transactions(self):
        qs = Transaction.objects.select_related(
            "account", "subcategory__category"
        ).filter(
            date__range=(self.start, self.end),
            account_id__in=self.account_ids,
            subcategory_id__in=self.subcategory_ids,
            kind__in=self.kinds,
        )
        if self.query:
            qs = qs.filter(
                Q(description__icontains=self.query)
                | Q(external_id__icontains=self.query)
                | Q(subcategory__name__icontains=self.query)
                | Q(subcategory__category__name__icontains=self.query)
            )
        return qs

    def transfers(self):
        if not self.include_transfers:
            return Transfer.objects.none()
        qs = (
            Transfer.objects.select_related("source", "destination")
            .filter(date__range=(self.start, self.end))
            .filter(
                Q(source_id__in=self.account_ids)
                | Q(destination_id__in=self.account_ids)
            )
        )
        if self.query:
            qs = qs.filter(
                Q(description__icontains=self.query)
                | Q(source__name__icontains=self.query)
                | Q(destination__name__icontains=self.query)
            )
        return qs

    def context(self):
        all_accounts = self.account_ids == {a.id for a in self.accounts}
        account_label = compact(
            [a.name for a in self.accounts if a.id in self.account_ids],
            all_accounts,
            "Tutti i conti",
        )
        period_label = {
            "tutto": "Tutto lo storico",
            "1m": "Ultimo mese",
            "3m": "Ultimi 3 mesi",
            "6m": "Ultimi 6 mesi",
            "1y": "Ultimo anno",
        }.get(self.period, f"{self.start:%d/%m/%Y} – {self.end:%d/%m/%Y}")
        cat_names = [c.name for c in self.categories if c.id in self.category_ids]
        if self.include_transfers:
            cat_names.append("Giroconto")
        category_label = compact(
            cat_names,
            len(self.category_ids) == len(self.categories) and self.include_transfers,
            "Tutte le categorie",
        )
        available_subs = [
            s for s in self.subcategories if s.category_id in self.category_ids
        ]
        subcategory_label = compact(
            [s.name for s in available_subs if s.id in self.subcategory_ids],
            bool(available_subs) and len(self.subcategory_ids) == len(available_subs),
            "Tutte le sottocategorie",
        )
        kind_choices = list(Transaction._meta.get_field("kind").choices) + [
            (TRANSFER_IN, TRANSFER_IN),
            (TRANSFER_OUT, TRANSFER_OUT),
        ]
        return {
            "filters": self,
            "accounts": self.accounts,
            "categories": self.categories,
            "subcategories": self.subcategories,
            "selected_account_ids": self.account_ids,
            "selected_category_ids": self.category_ids,
            "selected_subcategory_ids": self.subcategory_ids,
            "selected_kinds": self.kinds,
            "selected_giroconti": self.include_transfers,
            "period": self.period,
            "periods": PERIODS,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "earliest": self.earliest.isoformat(),
            "start_display": self.start.strftime("%d/%m/%Y"),
            "end_display": self.end.strftime("%d/%m/%Y"),
            "account_label": account_label,
            "account_filter_summary": account_label,
            "period_filter_summary": period_label,
            "category_filter_summary": category_label,
            "subcategory_filter_summary": subcategory_label,
            "kind_filter_summary": compact(
                [label for val, label in kind_choices if val in self.kinds],
                len(self.kinds) == len(kind_choices),
                "Tutti i tipi",
            ),
            "filter_summary": f"{period_label} · {account_label}",
            "selected_account": (
                next(iter(self.account_ids)) if len(self.account_ids) == 1 else None
            ),
            "kind_choices": kind_choices,
        }
