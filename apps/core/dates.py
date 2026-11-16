"""Date parsing shared by application filters, independent of dashboard pages."""
from django.utils.dateparse import parse_date


def parse_filter_date(value):
    try:
        return parse_date(value) if value else None
    except (TypeError, ValueError):
        return None
