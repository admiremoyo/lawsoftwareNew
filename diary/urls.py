from django.urls import path

from . import views

urlpatterns = [
    path("", views.diary, name="diary"),
    path("new/", views.entry_form, name="diary_create"),
    path("<int:pk>/", views.entry_form, name="diary_edit"),
    path("<int:pk>/toggle/", views.entry_toggle, name="diary_toggle"),
    path("<int:pk>/delete/", views.entry_delete, name="diary_delete"),
]
