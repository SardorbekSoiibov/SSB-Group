from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from .models import PortfolioProject, Service


class StaticSitemap(Sitemap):
    changefreq = "monthly"

    def items(self):
        return ["website:home", "website:about", "website:services", "website:portfolio", "website:team", "website:contact"]

    def location(self, item):
        return reverse(item)


class ServiceSitemap(Sitemap):
    def items(self):
        return Service.objects.published()

    def lastmod(self, obj):
        return obj.updated_at


class PortfolioSitemap(Sitemap):
    def items(self):
        return PortfolioProject.objects.published()

    def lastmod(self, obj):
        return obj.updated_at


SITEMAPS = {"static": StaticSitemap, "services": ServiceSitemap, "portfolio": PortfolioSitemap}
