from django import template

register = template.Library()


@register.filter
def display_title(value):
    """Replace em dashes in visible titles without changing stored data."""
    if not isinstance(value, str):
        return value
    return value.replace(" \u2014 ", ": ").replace("\u2014", ":")
