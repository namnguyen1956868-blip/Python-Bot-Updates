"""Conservative exact JAN / EAN match for product alerts."""
import re

_PATTERN = re.compile(r'(?<![0-9])(?:[0-9]{8}|[0-9]{13}|[0-9]{14})(?![0-9])')

def extract_jan(message):
    return set(_PATTERN.findall(str(message)))

def matches_tasks(message, tasks):
    codes = extract_jan(message)
    return [t for t in tasks if t.get('enabled', True) and str(t.get('jan', '')).strip() in codes and t.get('jan')]
