"""Fixed-window rate limiter on the Django cache (use Redis in production so workers share counts)."""

import hashlib

from django.core.cache import cache


def client_ip(request):
    return request.META.get("REMOTE_ADDR", "")


def _key(scope, ident):
    return "rl:%s:%s" % (scope, hashlib.sha256(ident.encode()).hexdigest()[:32])


def is_limited(scope, ident, limit):
    max_hits, _ = limit
    return cache.get(_key(scope, ident), 0) >= max_hits


def hit(scope, ident, limit):
    _, window = limit
    key = _key(scope, ident)
    if cache.add(key, 1, window):
        return
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, window)


def reset(scope, ident):
    cache.delete(_key(scope, ident))
