from django.shortcuts import render
from rest_framework.views import APIView
from django.http import JsonResponse
from django.conf import settings
import httpx


class StatView(APIView):
    def get(self, request):
        return JsonResponse({}, safe=False)


def chatbot_view(request):
    user_id = request.user.id if request.user.is_authenticated else "guest"
    return render(request, "app/chatbot.html", {"user_id": user_id})


class MCPInternetSearchView(APIView):
    async def post(self, request):
        query = request.data.get('query')
        if not query:
            return JsonResponse({'error': 'Missing query parameter.'}, status=400)
        serpapi_key = getattr(settings, 'SERPAPI_KEY', None)
        if not serpapi_key:
            return JsonResponse({'error': 'SERPAPI_KEY not configured.'}, status=500)
        params = {
            'q': query,
            'api_key': serpapi_key,
            'engine': 'google',
            'num': 3
        }
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get('https://serpapi.com/search', params=params, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                results = []
                for item in data.get('organic_results', [])[:3]:
                    results.append({
                        'title': item.get('title'),
                        'snippet': item.get('snippet'),
                        'link': item.get('link'),
                        'source': item.get('displayed_link') or item.get('link')
                    })
                return JsonResponse({'results': results}, status=200)
            except Exception as e:
                return JsonResponse({'error': f'Internet search failed: {str(e)}'}, status=500)