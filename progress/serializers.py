from rest_framework import serializers


class ProgressSerializer(serializers.Serializer):
    total_xp = serializers.IntegerField()
    completed_exercise_ids = serializers.ListField(child=serializers.IntegerField())
    completed_lesson_ids = serializers.ListField(child=serializers.IntegerField())
    completed_exercise_count = serializers.IntegerField()
    completed_lesson_count = serializers.IntegerField()
