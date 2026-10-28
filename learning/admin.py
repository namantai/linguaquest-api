from django.contrib import admin

from .models import Course, Exercise, Lesson, Submission


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ["title", "level", "is_published"]
    list_filter = ["level", "is_published"]
    search_fields = ["title"]


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ["title", "course", "order"]
    list_filter = ["course"]
    list_select_related = ["course"]


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    list_display = ["id", "lesson", "kind", "order", "xp_reward"]
    list_filter = ["kind", "lesson__course"]
    list_select_related = ["lesson"]


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "exercise", "status", "provider", "xp_awarded"]
    list_filter = ["status", "provider"]
    list_select_related = ["user", "exercise__lesson"]
    readonly_fields = [field.name for field in Submission._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
