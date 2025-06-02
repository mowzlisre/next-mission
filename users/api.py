from django.shortcuts import render
from rest_framework.views import APIView
from django.http import JsonResponse

class StatUserView(APIView):
    def get(self, request):
        return JsonResponse({}, safe=False)