def unread(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not request.path.startswith("/management/"):
        return {}
    return {"unread_count": user.notifications.filter(read_at__isnull=True).count()}
