from django import template

register = template.Library()


@register.filter
def split_list(value, sep=","):
    """'Python, Django' -> ['Python', 'Django'] for rendering as chips."""
    return [p.strip() for p in (value or "").split(sep) if p.strip()]


@register.simple_tag
def fill_span(count, cols=3):
    """Column span for the last grid item so the final row has no empty cell."""
    rest = count % cols
    return "" if rest == 0 else f"lg:col-span-{cols - rest + 1}"
