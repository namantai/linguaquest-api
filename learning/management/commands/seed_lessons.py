from django.core.management.base import BaseCommand
from django.db import transaction

from learning.models import Course, Exercise, Lesson


class Command(BaseCommand):
    help = "Create a small A1 course. Safe to rerun; existing content is preserved."

    @transaction.atomic
    def handle(self, *args, **options):
        course, _ = Course.objects.get_or_create(
            title="Everyday English",
            level="A1",
            defaults={
                "description": "Practice introductions, daily routines and writing.",
                "is_published": True,
            },
        )
        basics, _ = Lesson.objects.get_or_create(
            course=course,
            order=1,
            defaults={
                "title": "Introductions and daily routines",
                "description": "Use am with I. Use goes with he or she.",
            },
        )
        writing, _ = Lesson.objects.get_or_create(
            course=course,
            order=2,
            defaults={
                "title": "Write about your day",
                "description": "Write short sentences and get AI grammar feedback.",
            },
        )
        examples = [
            (
                basics,
                1,
                {
                    "kind": Exercise.Kind.MULTIPLE_CHOICE,
                    "prompt": "She ___ to university every morning.",
                    "options": {"a": "go", "b": "goes", "c": "going"},
                    "correct_answer": "b",
                    "xp_reward": 10,
                },
            ),
            (
                basics,
                2,
                {
                    "kind": Exercise.Kind.TEXT,
                    "prompt": "Complete the sentence with one word: I ___ a student.",
                    "correct_answer": "am",
                    "xp_reward": 10,
                },
            ),
            (
                writing,
                1,
                {
                    "kind": Exercise.Kind.WRITING,
                    "prompt": "Write two English sentences about your daily routine.",
                    "xp_reward": 20,
                },
            ),
        ]
        for lesson, order, defaults in examples:
            exercise, _ = Exercise.objects.get_or_create(
                lesson=lesson, order=order, defaults=defaults
            )
            exercise.full_clean()
        self.stdout.write(
            self.style.SUCCESS(
                f"Course ready: {course.pk}. Lessons: {basics.pk}, {writing.pk}."
            )
        )
