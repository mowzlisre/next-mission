from django.shortcuts import render
from rest_framework.views import APIView
from django.http import JsonResponse


class StatView(APIView):
    def get(self, request):
        return JsonResponse({}, safe=False)