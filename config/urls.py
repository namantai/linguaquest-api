from django.contrib import admin
from django.urls import path
from django.views.generic import TemplateView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from accounts.views import LoginView, MeView, RefreshView, RegisterView
from learning.views import (
    CourseDetailView,
    CourseListView,
    ExerciseListView,
    LessonDetailView,
    LessonListView,
    SubmissionDetailView,
    SubmitAnswerView,
)
from progress.views import ProgressView

urlpatterns = [
    path("", TemplateView.as_view(template_name="index.html"), name="home"),
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("api/v1/auth/register/", RegisterView.as_view(), name="register"),
    path("api/v1/auth/token/", LoginView.as_view(), name="token_obtain_pair"),
    path("api/v1/auth/token/refresh/", RefreshView.as_view(), name="token_refresh"),
    path("api/v1/me/", MeView.as_view(), name="me"),
    path("api/v1/me/progress/", ProgressView.as_view(), name="progress"),
    path("api/v1/courses/", CourseListView.as_view(), name="course-list"),
    path("api/v1/courses/<int:pk>/", CourseDetailView.as_view(), name="course-detail"),
    path(
        "api/v1/courses/<int:pk>/lessons/", LessonListView.as_view(), name="lesson-list"
    ),
    path("api/v1/lessons/<int:pk>/", LessonDetailView.as_view(), name="lesson-detail"),
    path(
        "api/v1/lessons/<int:pk>/exercises/",
        ExerciseListView.as_view(),
        name="exercise-list",
    ),
    path(
        "api/v1/exercises/<int:pk>/submit/",
        SubmitAnswerView.as_view(),
        name="submit-answer",
    ),
    path(
        "api/v1/submissions/<int:pk>/",
        SubmissionDetailView.as_view(),
        name="submission-detail",
    ),
]
