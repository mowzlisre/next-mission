from django.shortcuts import render
from rest_framework.views import APIView
from django.http import JsonResponse


class StatView(APIView):
    def get(self, request):
        return JsonResponse({}, safe=False)


def chatbot_view(request):
    user_id = request.user.id if request.user.is_authenticated else "guest"
    return render(request, "app/chatbot.html", {"user_id": user_id})