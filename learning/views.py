from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Course, Exercise, Lesson, Submission
from .serializers import (
    CourseSerializer,
    ExerciseSerializer,
    LessonSerializer,
    SubmissionSerializer,
    SubmitAnswerSerializer,
)
from .services import submit_answer


class CourseListView(generics.ListAPIView):
    queryset = Course.objects.filter(is_published=True)
    serializer_class = CourseSerializer
    permission_classes = [AllowAny]


class CourseDetailView(generics.RetrieveAPIView):
    queryset = Course.objects.filter(is_published=True)
    serializer_class = CourseSerializer
    permission_classes = [AllowAny]


class LessonListView(generics.ListAPIView):
    serializer_class = LessonSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Lesson.objects.none()
        course = get_object_or_404(Course, pk=self.kwargs["pk"], is_published=True)
        return course.lessons.all()


class LessonDetailView(generics.RetrieveAPIView):
    queryset = Lesson.objects.filter(course__is_published=True)
    serializer_class = LessonSerializer
    permission_classes = [AllowAny]


class ExerciseListView(generics.ListAPIView):
    serializer_class = ExerciseSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Exercise.objects.none()
        lesson = get_object_or_404(
            Lesson, pk=self.kwargs["pk"], course__is_published=True
        )
        return lesson.exercises.all()


class SubmitAnswerView(APIView):
    throttle_scope = "submissions"

    @extend_schema(
        request=SubmitAnswerSerializer,
        responses={201: SubmissionSerializer, 202: SubmissionSerializer},
        examples=[
            OpenApiExample("Multiple choice", value={"answer": "b"}, request_only=True),
            OpenApiExample(
                "Writing",
                value={"answer": "I study English every day."},
                request_only=True,
            ),
        ],
        description=(
            "Returns 201 for graded/unavailable submissions; 202 for queued AI. "
            "Poll /api/v1/submissions/{id}/. A correct exercise earns XP only once."
        ),
    )
    def post(self, request, pk):
        exercise = get_object_or_404(Exercise, pk=pk, lesson__course__is_published=True)
        serializer = SubmitAnswerSerializer(
            data=request.data, context={"exercise": exercise}
        )
        serializer.is_valid(raise_exception=True)
        submission = submit_answer(
            user=request.user,
            exercise=exercise,
            answer=serializer.validated_data["answer"],
        )
        submission.refresh_from_db()  # Includes broker failures from on_commit.
        pending = submission.status in {
            Submission.Status.PENDING,
            Submission.Status.PROCESSING,
            Submission.Status.RETRYING,
        }
        return Response(
            SubmissionSerializer(submission).data,
            status=status.HTTP_202_ACCEPTED if pending else status.HTTP_201_CREATED,
            headers={"Location": f"/api/v1/submissions/{submission.pk}/"},
        )


class SubmissionDetailView(generics.RetrieveAPIView):
    serializer_class = SubmissionSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Submission.objects.none()
        return Submission.objects.filter(user=self.request.user)
