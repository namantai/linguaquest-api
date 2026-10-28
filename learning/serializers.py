from rest_framework import serializers

from .models import Course, Exercise, Lesson, Submission


class CourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ["id", "title", "description", "level"]


class LessonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lesson
        fields = ["id", "course", "title", "description", "order"]


class ExerciseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Exercise
        # Explicit allowlist: never serialize correct_answer.
        fields = ["id", "lesson", "kind", "prompt", "options", "xp_reward", "order"]


class SubmitAnswerSerializer(serializers.Serializer):
    answer = serializers.CharField(
        max_length=2000, allow_blank=False, trim_whitespace=True
    )

    def validate_answer(self, value):
        exercise = self.context["exercise"]
        if (
            exercise.kind == Exercise.Kind.MULTIPLE_CHOICE
            and value not in exercise.options
        ):
            raise serializers.ValidationError("Submit one of the option keys.")
        return value


class FeedbackSerializer(serializers.Serializer):
    score = serializers.IntegerField(min_value=0, max_value=100)
    corrections = serializers.ListField(child=serializers.CharField())
    explanation = serializers.CharField()


class SubmissionSerializer(serializers.ModelSerializer):
    feedback = FeedbackSerializer(read_only=True, allow_null=True)

    class Meta:
        model = Submission
        fields = [
            "id",
            "exercise",
            "answer",
            "status",
            "is_correct",
            "xp_awarded",
            "feedback",
            "provider",
            "error_code",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
