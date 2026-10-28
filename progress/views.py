from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import ProgressSerializer
from .services import get_progress


class ProgressView(APIView):
    @extend_schema(responses=ProgressSerializer)
    def get(self, request):
        return Response(ProgressSerializer(get_progress(request.user)).data)
