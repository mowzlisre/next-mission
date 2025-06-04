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
from rest_framework.permissions import IsAuthenticated
import requests
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import time
import re

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
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        message = request.data.get("message")

        if not user.fingerprint or not message:
            return JsonResponse({"error": "Missing fingerprint or message"}, status=400)

        try:
            # Encrypt the message
            data_to_encrypt = {"message": message}
            encrypted_message = encrypt_with_fingerprint(data_to_encrypt, user.fingerprint)["message"]

            # Connect to MongoDB
            client = MongoClient(settings.MONGO_URI)
            db = client[settings.MONGO_DB_NAME]
            bookmarks = db["bookmarks"]

            # Check for duplicate
            exists = bookmarks.find_one({
                "fingerprint": user.fingerprint,
                "message": encrypted_message
            })

            if exists:
                return JsonResponse({"error": "This bookmark already exists."}, status=409)

            # Insert new bookmark
            bookmarks.insert_one({
                "fingerprint": user.fingerprint,
                "message": encrypted_message,
                "created_at": datetime.utcnow()
            })

            return JsonResponse({"message": "Bookmark saved successfully"}, status=201)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
        

class BookmarkedChats(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user

        if not user.fingerprint:
            return JsonResponse({"error": "Missing 'fingerprint' in query parameters."}, status=400, safe=False)

        client = MongoClient(settings.MONGO_URI)
        db = client[settings.MONGO_DB_NAME]
        bookmarks = db["bookmarks"]

        # Fetch and convert cursor to list
        chats = list(bookmarks.find({"fingerprint": user.fingerprint}))

        # Optional: remove ObjectId for JSON serialization
        for chat in chats:
            chat["_id"] = str(chat["_id"])
            chat["message"] = decrypt_with_fingerprint({"message": chat["message"]}, user.fingerprint)["message"]
            del chat["fingerprint"]
        
        return JsonResponse(chats, safe=False)


class VeteranJobSearchView(APIView):
    def extract_structured_job_info(self, visible_text, keywords):
        prompt = (
            "You are a structured data extractor that parses plain text job descriptions. "
            "Given a job posting's plain text content, return a JSON object with the following normalized fields:\n\n"
            "- `company_name`: string\n"
            "- `job_title`: string\n"
            "- `location`: string\n"
            "- `description`: a short 2-3 line summary\n"
            "- `job_tags`: array of up to 5 keywords/skills\n"
            "- `posted_time`: ISO date format (`YYYY-MM-DD`) if mentioned\n"
            "- `applicants`: integer (e.g., `18` from '18 applicants')\n"
            "- `salary`: normalized object like `{ \"from\": 85000, \"to\": 100000 }` in **USD per year**\n"
            "   - If only one value is mentioned, use it for both `from` and `to`\n"
            "   - Accept ranges like '$80k–$100k', '$85,000/year', or 'up to $95,000'\n"
            "- `employment_type`: string like 'Full-time', 'Part-time', etc.\n"
            "- `work_mode`: one of `Remote`, `Hybrid`, or `On-site`\n\n"
            "Return only the JSON object. If data is missing, set values to `null` or an empty list.\n\n"
            "Job text:\n"
            f"{visible_text}"
        )
        llama_data = {
            "model": "meta-llama/llama-4-scout-17b-16e-instruct",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant that extracts structured job info from HTML."},
                {"role": "user", "content": prompt}
            ]
        }
        try:
            resp = requests.post(
                settings.GROQ_API_URL,
                json=llama_data,
                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                timeout=60
            )
            resp.raise_for_status()
            output = resp.json()["choices"][0]["message"]["content"]
            match = re.search(r'\{.*\}', output, re.DOTALL)
            return json.loads(match.group(0)) if match else json.loads(output)
        except Exception as e:
            print(f"Failed to extract structured job info: {e}")
            return {
                "company_name": None,
                "job_title": None,
                "location": None,
                "description": None,
                "job_tags": []
            }

    def post(self, request):
        # 1. Load dummy profile and MOS DB
        base_dir = os.path.dirname(__file__)
        with open(os.path.join(base_dir, 'utils/data/dummy.json'), 'r') as f:
            profile = json.load(f)
        with open(os.path.join(base_dir, 'utils/data/mos_database.json'), 'r') as f:
            mos_db_list = json.load(f)
        mos_db = {item['code']: item for item in mos_db_list}

        for mos in profile['form_data'].get('mos_history', []):
            code = mos.get('code')
            mos_info = mos_db.get(code, {})
            mos['title'] = mos_info.get('title', mos.get('title'))
            mos['description'] = mos_info.get('description', '')

        # 2. Generate summary + keywords with LLaMA
        prompt = (
            "You are an expert at translating military experience to civilian terms. "
            "Given the following profile, summarize it for a civilian audience and generate a list of relevant skills/keywords for job search. "
            "Return a JSON object with 'summary' and 'keywords' (array of strings).\n"
            f"Profile: {json.dumps(profile['form_data'], indent=2)}"
        )
        llama_data = {
            "model": "meta-llama/llama-4-scout-17b-16e-instruct",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant for U.S. military veterans."},
                {"role": "user", "content": prompt}
            ]
        }

        try:
            resp = requests.post(settings.GROQ_API_URL, json=llama_data,
                                 headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"}, timeout=60)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            match = re.search(r'\{.*\}', content, re.DOTALL)
            summary_keywords = json.loads(match.group(0)) if match else json.loads(content)
        except Exception:
            summary_keywords = {"summary": "", "keywords": []}

        keywords = summary_keywords.get('keywords') or [
            mos.get('title', '') for mos in profile['form_data'].get('mos_history', [])
        ]

        # 3. Search via SerpAPI (LinkedIn only)
        serpapi_key = getattr(settings, 'SERPAPI_KEY', None)
        jobs = []

        if serpapi_key:
            query = ' '.join(keywords[:3]) if keywords else ''
            params = {
                'engine': 'google',
                'q': query + ' jobs site:linkedin.com',
                'api_key': serpapi_key,
                'num': 10
            }
            try:
                serp_resp = requests.get('https://serpapi.com/search', params=params, timeout=20)
                serp_resp.raise_for_status()
                serp_data = serp_resp.json()
                linkedin_jobs = [
                    item for item in serp_data.get('organic_results', [])
                    if 'linkedin.com/jobs/view/' in item.get('link', '')
                ]

                for item in linkedin_jobs:
                    url = item.get('link')
                    if not url:
                        continue
                    try:
                        html = requests.get(url, timeout=10).text
                        if 'Cloudflare' in html:
                            raise Exception("Blocked by bot protection")
                        soup = BeautifulSoup(html, 'html.parser')
                        visible_text = soup.get_text(separator='\n', strip=True)
                        if len(visible_text) > 20000:
                            visible_text = visible_text[:20000]
                        structured = self.extract_structured_job_info(visible_text, keywords)
                        jobs.append({
                            "company_name": structured.get("company_name"),
                            "job_title": structured.get("job_title"),
                            "location": structured.get("location"),
                            "job_tags": structured.get("job_tags", []),
                            "posted_time": structured.get("posted_time"),  # e.g., "2025-06-01"
                            "applicants": structured.get("applicants"),     # e.g., 18
                            "salary": structured.get("salary"),             # e.g., {"from": 85000, "to": 100000}
                            "employment_type": structured.get("employment_type"),  # e.g., "Full-time"
                            "work_mode": structured.get("work_mode"),       # e.g., "remote", "on-site"
                            "url": url,
                            "description": structured.get("description"),    # Short 2–3 line summary
                        })
                    except Exception as e:
                        print(f"Error crawling {url}: {e}")
            except Exception as e:
                print(f"SerpAPI error: {e}")

        # 4. Score and rank with LLaMA
        scored_jobs = []
        for job in jobs:
            job_prompt = (
                "Given the following veteran profile and job posting, evaluate how well the job matches the profile. "
                "Return a JSON object with:\n"
                "- `score`: a numeric value between 0 and 100 (e.g., 87, but not multiples of 5), based on relevance\n"
                "- `label`: one of `GOOD MATCH`, `OK MATCH`, or `LOW MATCH`, based on the score\n\n"
                "Scoring scale:\n"
                "- 80 and above → GOOD MATCH\n"
                "- 50 to 79.9 → OK MATCH\n"
                "- below 50 → LOW MATCH\n\n"
                f"Profile:\n{json.dumps(profile['form_data'], indent=2)}\n\n"
                f"Job:\n{json.dumps(job, indent=2)}"
            )

            job_data = {
                "model": "meta-llama/llama-4-scout-17b-16e-instruct",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant for U.S. military veterans."},
                    {"role": "user", "content": job_prompt}
                ]
            }
            try:
                match_resp = requests.post(settings.GROQ_API_URL, json=job_data,
                                           headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"}, timeout=30)
                match_resp.raise_for_status()
                match_json = match_resp.json()["choices"][0]["message"]["content"]
                match = re.search(r'\{.*\}', match_json, re.DOTALL)
                match_data = json.loads(match.group(0)) if match else json.loads(match_json)
                job['matching_score'] = match_data.get('score')
                job['matching_label'] = match_data.get('label')
            except Exception:
                job['matching_score'] = None
                job['matching_label'] = None
            scored_jobs.append(job)

        # 5. Sort and return
        scored_jobs.sort(key=lambda x: (x['matching_score'] is not None, x['matching_score']), reverse=True)
        return JsonResponse(scored_jobs, safe=False)

    
class FetchChats(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        client = MongoClient(settings.MONGO_URI)
        db = client[settings.MONGO_DB_NAME]
        chats_db = db["chat_history"]

        # Fetch and convert cursor to list
        chats = list(chats_db.find({"user_id": user.fingerprint}))
        for chat in chats:
            chat["created_at"] = chat["created_at"].isoformat()
            chat["updated_at"] = chat["updated_at"].isoformat()
            chat["conversation"] = decrypt_with_fingerprint(chat["conversation"][0], user.fingerprint)
            print(chat["conversation"])
            del chat["_id"]
        
        return JsonResponse(chats, safe=False)

# Helper to extract location
def extract_location(text):
    if not text:
        return None
    # Look for city, state, or country patterns
    match = re.search(r'([A-Za-z .,-]+, [A-Z]{2,}|[A-Za-z .,-]+, [A-Za-z .,-]+|United States|Remote)', text)
    if match:
        loc = match.group(1).strip()
        # Ignore generic or overly long locations
        if loc.lower() not in ['location or remote', 'exact location'] and len(loc) < 50:
            return loc
    return None
