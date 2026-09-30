from django import template
from wallet.services import money_it
from wallet.services.colors import vivid_category_color

register = template.Library()
register.filter("vivid_color", vivid_category_color)


@register.filter
def euro(value):
    try:
        return money_it(value)
    except Exception:
        return "0,00 €"


@register.filter
def signed_euro(value):
    try:
        return money_it(value)
    except Exception:
        return "0,00 €"


@register.filter
def percent(value):
    try:
        return f"{float(value):.1f}%".replace(".", ",")
    except Exception:
        return "0,0%"


@register.filter
def get_item(mapping, key):
    try:
        return mapping.get(key)
    except Exception:
        return None


@register.simple_tag(takes_context=True)
def query_url(context, **changes):
    params = getattr(context["request"], "wallet_params", context["request"].GET).copy()
    for key, value in changes.items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = str(value)
    return "?" + params.urlencode()
