from django.urls import path
from . import views

app_name = 'chat'
urlpatterns = [
    path('', views.index, name='index'),
    path('api/contacts/', views.contacts, name='contacts'),
    path('api/<int:pk>/messages/', views.messages, name='messages'),
    path('api/<int:pk>/read/', views.read, name='read'),
    path('api/<int:pk>/forward/', views.forward, name='forward'),
    path('api/<int:pk>/typing/', views.typing, name='typing'),
    path('api/messages/<int:mid>/', views.message_detail, name='message'),
    path('api/messages/<int:mid>/react/', views.react, name='react'),
    path('api/messages/<int:mid>/pin/', views.pin, name='pin'),
    path('api/messages/<int:mid>/file/', views.attachment, name='file'),
    path('<int:pk>/', views.index, name='conversation'),
]
