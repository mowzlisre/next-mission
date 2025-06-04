from django.shortcuts import render
from rest_framework.views import APIView
from django.http import JsonResponse
from django.conf import settings
import httpx
from users.crypt import encrypt_with_fingerprint, decrypt_with_fingerprint
from pymongo import MongoClient
from datetime import datetime
import os
import json

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

class BookmarkMessage(APIView):
    def post(self, request):
        fingerprint = request.data.get("fingerprint")
        message = request.data.get("message")

        if not fingerprint or not message:
            return JsonResponse({"error": "Missing fingerprint or message"}, status=400)

        try:
            # Encrypt the message
            data_to_encrypt = {"message": message}
            encrypted_message = encrypt_with_fingerprint(data_to_encrypt, fingerprint)["message"]

            # Connect to MongoDB
            client = MongoClient(settings.MONGO_URI)
            db = client[settings.MONGO_DB_NAME]
            bookmarks = db["bookmarks"]

            # Check for duplicate
            exists = bookmarks.find_one({
                "fingerprint": fingerprint,
                "message": encrypted_message
            })

            if exists:
                return JsonResponse({"error": "This bookmark already exists."}, status=409)

            # Insert new bookmark
            bookmarks.insert_one({
                "fingerprint": fingerprint,
                "message": encrypted_message,
                "created_at": datetime.utcnow()
            })

            return JsonResponse({"message": "Bookmark saved successfully"}, status=201)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
        

class BookmarkedChats(APIView):
    def get(self, request):
        fingerprint = request.data.get('fingerprint')
        if not fingerprint:
            return JsonResponse({"error": "Missing 'fingerprint' in query parameters."}, status=400, safe=False)

        client = MongoClient(settings.MONGO_URI)
        db = client[settings.MONGO_DB_NAME]
        bookmarks = db["bookmarks"]

        # Fetch and convert cursor to list
        chats = list(bookmarks.find({"fingerprint": fingerprint}))

        # Optional: remove ObjectId for JSON serialization
        for chat in chats:
            chat["_id"] = str(chat["_id"])
            chat["message"] = decrypt_with_fingerprint({"message": chat["message"]}, fingerprint)["message"]
            del chat["fingerprint"]
        
        return JsonResponse(chats, safe=False)

class VeteranJobSearchView(APIView):
    async def post(self, request):
        # 1. Load dummy profile and MOS database
        dummy_path = os.path.join(os.path.dirname(__file__), 'utils', 'data', 'dummy.json')
        mos_db_path = os.path.join(os.path.dirname(__file__), 'utils', 'data', 'mos_database.json')
        with open(dummy_path, 'r') as f:
            profile = json.load(f)
        with open(mos_db_path, 'r') as f:
            mos_db = json.load(f)

        # 2. Enrich MOS codes with title/desc
        for mos in profile['form_data'].get('mos_history', []):
            code = mos.get('code')
            mos_info = mos_db.get(code, {})
            mos['title'] = mos_info.get('title', mos.get('title'))
            mos['description'] = mos_info.get('description', '')

        # 3. Generate civilian summary & keywords with Llama
        llama_prompt = (
            "You are an expert at translating military experience to civilian terms. "
            "Given the following profile, summarize it for a civilian audience and generate a list of relevant skills/keywords for job search. "
            "Return a JSON object with 'summary' and 'keywords' (array of strings).\n"
            f"Profile: {json.dumps(profile['form_data'], indent=2)}"
        )
        llama_data = {
            "model": "meta-llama/llama-4-scout-17b-16e-instruct",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant for U.S. military veterans."},
                {"role": "user", "content": llama_prompt}
            ]
        }
        async with httpx.AsyncClient() as client:
            try:
                llama_resp = await client.post(settings.GROQ_API_URL, json=llama_data, headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"}, timeout=60)
                llama_resp.raise_for_status()
                llama_json = llama_resp.json()["choices"][0]["message"]["content"]
                # Try to parse JSON from Llama output
                try:
                    import re
                    match = re.search(r'\{.*\}', llama_json, re.DOTALL)
                    if match:
                        summary_keywords = json.loads(match.group(0))
                    else:
                        summary_keywords = json.loads(llama_json)
                except Exception:
                    summary_keywords = {"summary": "", "keywords": []}
            except Exception as e:
                return JsonResponse({"error": f"Llama failed: {str(e)}"}, status=500)

        keywords = summary_keywords.get('keywords', [])
        if not keywords:
            keywords = [mos.get('title', '') for mos in profile['form_data'].get('mos_history', [])]

        # 4. Search jobs from SERPAPI (LinkedIn) and USAJOBS
        serpapi_key = getattr(settings, 'SERPAPI_KEY', None)
        usajobs_key = getattr(settings, 'USAJOBS_API_KEY', None)
        jobs = []
        # SERPAPI LinkedIn
        if serpapi_key:
            params = {
                'q': ' '.join(keywords),
                'api_key': serpapi_key,
                'engine': 'linkedin_jobs',
                'location': 'United States',
                'date_posted': 'past_48_hours',
                'num': 25
            }
            try:
                serp_resp = await client.get('https://serpapi.com/search', params=params, timeout=20)
                serp_resp.raise_for_status()
                serp_data = serp_resp.json()
                for item in serp_data.get('jobs_results', [])[:25]:
                    jobs.append({
                        'company_logo': item.get('company_logo_url'),
                        'company_name': item.get('company_name'),
                        'job_title': item.get('title'),
                        'location': item.get('location'),
                        'job_tags': item.get('job_types', None),
                        'posted_time': item.get('posted_at'),
                        'applicants': item.get('applicants', None),
                        'alumni': item.get('alumni', None),
                        'url': item.get('job_url'),
                        'description': item.get('description', None)
                    })
            except Exception:
                pass
        # USAJOBS
        if usajobs_key:
            headers = {'Authorization-Key': usajobs_key, 'User-Agent': 'next-mission-app'}
            params = {
                'Keyword': ' '.join(keywords),
                'LocationName': 'United States',
                'ResultsPerPage': 25,
                'DatePosted': 2  # last 48 hours
            }
            try:
                usajobs_resp = await client.get('https://data.usajobs.gov/api/search', params=params, headers=headers, timeout=20)
                usajobs_resp.raise_for_status()
                usajobs_data = usajobs_resp.json()
                for item in usajobs_data.get('SearchResult', {}).get('SearchResultItems', [])[:25]:
                    pos = item.get('MatchedObjectDescriptor', {})
                    jobs.append({
                        'company_logo': None,
                        'company_name': pos.get('OrganizationName'),
                        'job_title': pos.get('PositionTitle'),
                        'location': pos.get('PositionLocationDisplay'),
                        'job_tags': pos.get('PositionSchedule', None),
                        'posted_time': pos.get('PublicationStartDate'),
                        'applicants': None,
                        'alumni': None,
                        'url': pos.get('PositionURI'),
                        'description': pos.get('UserArea', {}).get('Details', {}).get('JobSummary', None)
                    })
            except Exception:
                pass

        # 5. Score and rank jobs with Llama
        scored_jobs = []
        for job in jobs:
            job_prompt = (
                "Given the following veteran profile and job posting, score how well the job matches the profile on a scale of 0-100. "
                "Return a JSON object with 'score' (int) and 'label' (string: GOOD MATCH, OK MATCH, LOW MATCH).\n"
                f"Profile: {json.dumps(profile['form_data'], indent=2)}\n"
                f"Job: {json.dumps(job, indent=2)}"
            )
            job_data = {
                "model": "meta-llama/llama-4-scout-17b-16e-instruct",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant for U.S. military veterans."},
                    {"role": "user", "content": job_prompt}
                ]
            }
            try:
                job_resp = await client.post(settings.GROQ_API_URL, json=job_data, headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"}, timeout=30)
                job_resp.raise_for_status()
                job_json = job_resp.json()["choices"][0]["message"]["content"]
                import re
                match = re.search(r'\{.*\}', job_json, re.DOTALL)
                if match:
                    score_label = json.loads(match.group(0))
                else:
                    score_label = json.loads(job_json)
                job['matching_score'] = score_label.get('score', None)
                job['matching_label'] = score_label.get('label', None)
            except Exception:
                job['matching_score'] = None
                job['matching_label'] = None
            scored_jobs.append(job)

        # 6. Sort by matching_score descending
        scored_jobs.sort(key=lambda x: (x['matching_score'] is not None, x['matching_score']), reverse=True)

        return JsonResponse(scored_jobs, safe=False)