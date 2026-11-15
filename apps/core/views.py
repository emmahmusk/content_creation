from django.http import HttpResponse, JsonResponse
from django.shortcuts import render

def home(request):
    return render(request, "home.html")

def health(request):
    return JsonResponse({"status": "ok"})

def api_docs(request):
    return render(request, "core/api_docs.html")

def robots_txt(request):
    sitemap_url = request.build_absolute_uri("/sitemap.xml")
    body = "\n".join((
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /accounts/profile/",
        "Disallow: /orders/",
        "Disallow: /credits/wallet/",
        "Disallow: /credits/payment/",
        "Disallow: /credits/buy/",
        "Disallow: /music/",
        "Disallow: /intelligence/",
        "Disallow: /api/",
        "Disallow: /api-auth/",
        f"Sitemap: {sitemap_url}",
        "",
    ))
    return HttpResponse(body, content_type="text/plain; charset=utf-8")

def sitemap_xml(request):
    urls = ("/", "/credits/", "/developers/api/")
    entries = "".join(
        f"<url><loc>{request.build_absolute_uri(path)}</loc></url>"
        for path in urls
    )
    return HttpResponse(
        f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{entries}</urlset>',
        content_type="application/xml; charset=utf-8",
    )
