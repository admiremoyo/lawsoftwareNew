from django.urls import path

from . import views

urlpatterns = [
    path("", views.MatterList.as_view(), name="matter_list"),
    path("new/", views.MatterCreate.as_view(), name="matter_create"),
    path("<int:pk>/", views.matter_detail, name="matter_detail"),
    path("<int:pk>/edit/", views.MatterUpdate.as_view(), name="matter_edit"),
    path("<int:pk>/notes/add/", views.add_file_note, name="file_note_add"),
    path("<int:pk>/documents/upload/", views.upload_document, name="document_upload"),
    path("<int:pk>/documents/generate/", views.generate_document, name="document_generate"),
    path("documents/<int:pk>/download/", views.download_document, name="document_download"),
    path("documents/<int:pk>/delete/", views.delete_document, name="document_delete"),
    path("<int:pk>/tasks/add/", views.task_add, name="task_add"),
    path("<int:pk>/tasks/apply/", views.apply_workflow, name="apply_workflow"),
    path("tasks/<int:pk>/toggle/", views.task_toggle, name="task_toggle"),
    path("tasks/<int:pk>/delete/", views.task_delete, name="task_delete"),
    path("workflows/", views.workflow_list, name="workflow_list"),
    path("workflows/new/", views.workflow_form, name="workflow_create"),
    path("workflows/<int:pk>/", views.workflow_form, name="workflow_edit"),
    path("templates/", views.TemplateList.as_view(), name="template_list"),
    path("templates/new/", views.TemplateCreate.as_view(), name="template_create"),
    path("templates/<int:pk>/edit/", views.TemplateUpdate.as_view(), name="template_edit"),
]
