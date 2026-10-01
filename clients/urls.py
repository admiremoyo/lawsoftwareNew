from django.urls import path

from . import views

urlpatterns = [
    path("", views.ClientList.as_view(), name="client_list"),
    path("new/", views.ClientCreate.as_view(), name="client_create"),
    path("<int:pk>/", views.ClientDetail.as_view(), name="client_detail"),
    path("<int:pk>/edit/", views.ClientUpdate.as_view(), name="client_edit"),
]
