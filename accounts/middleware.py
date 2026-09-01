from django.utils.cache import add_never_cache_headers


class NoStoreAuthenticatedPagesMiddleware:
    """Keep pages containing account actions out of browser/proxy caches."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.user.is_authenticated and request.method == "GET":
            add_never_cache_headers(response)
            response["Pragma"] = "no-cache"
        return response
