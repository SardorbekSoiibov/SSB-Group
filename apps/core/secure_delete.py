"""Second step of every permanent deletion: the person's own password, checked on the server."""
from django.contrib import messages

from .ratelimit import hit, is_limited, reset

LIMIT = (5, 900)
SCOPE = 'delete-password'


def confirm_delete_password(request):
    ident = str(request.user.pk)
    if is_limited(SCOPE, ident, LIMIT):
        messages.error(request, 'Juda ko‘p noto‘g‘ri urinish. 15 daqiqadan keyin qayta urinib ko‘ring. Hech narsa o‘chirilmadi.')
        return False
    if not request.user.check_password(request.POST.get('confirm_password', '')):
        hit(SCOPE, ident, LIMIT)
        messages.error(request, 'Parol noto‘g‘ri. Hech narsa o‘chirilmadi.')
        return False
    reset(SCOPE, ident)
    return True
