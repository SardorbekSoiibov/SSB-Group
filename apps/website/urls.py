from django.urls import path

from . import views

app_name = "website"

urlpatterns = [
    path("", views.home, name="home"),
    path("biz-haqimizda/", views.about, name="about"),
    path("xizmatlar/", views.services, name="services"),
    path("xizmatlar/<slug:slug>/", views.service_detail, name="service_detail"),
    path("portfolio/", views.portfolio, name="portfolio"),
    path("portfolio/<slug:slug>/", views.project_detail, name="project_detail"),
    path("jamoa/", views.team, name="team"),
    path("aloqa/", views.contact, name="contact"),
    path("aloqa/rahmat/", views.contact_done, name="contact_done"),
    path("maxfiylik/", views.privacy, name="privacy"),
]
