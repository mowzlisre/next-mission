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
    permission_classes = [IsAuthenticated]

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
            "   - Accept ranges like '$80k-$100k', '$85,000/year', or 'up to $95,000'\n"
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
        user = request.user
        # 1. Load dummy profile and MOS DB
        client = MongoClient(settings.MONGO_URI)
        db = client[settings.MONGO_DB_NAME]
        user_collection = db["user_data"]
        user_doc = user_collection.find_one({'fingerprint': user.fingerprint})
        user_doc = decrypt_with_fingerprint(user_doc, user.fingerprint)
        if not user_doc:
            return JsonResponse({'error': 'User profile not found.'}, status=404)
        profile = user_doc
        del profile["_id"]

        # Fetch MOS DB
        mos_doc = db["mos_doc"]
        mos_docs = mos_doc.find({})
        mos_db_list = list(mos_docs)
        if not mos_db_list:
            # Load local JSON file and insert into MongoDB
            base_dir = os.path.dirname(__file__)
            json_path = os.path.join(base_dir, 'utils/data/mos_database.json')

            try:
                with open(json_path, 'r') as f:
                    mos_data = json.load(f)
                    if isinstance(mos_data, list):
                        mos_doc.insert_many(mos_data)
                        mos_db_list = mos_data  # use directly for downstream logic
                    else:
                        return JsonResponse({'error': 'Invalid format in mos_database.json'}, status=500)
            except Exception as e:
                return JsonResponse({'error': f'Failed to load mos_database.json: {str(e)}'}, status=500)

        mos_db = {item['code']: item for item in mos_db_list}
            
        # Enrich MOS history
        for mos in profile.get('mos_history', []):
            code = mos.get('code')
            if not code:
                continue
            mos_info = mos_db.get(code, {})
            mos['title'] = mos_info.get('title', mos.get('title'))
            mos['description'] = mos_info.get('description', '')

        # 2. Generate summary + keywords with LLaMA
        prompt = (
            "You are an expert at translating military experience to civilian terms. "
            "Given the following profile, summarize it for a civilian audience and generate a list of relevant skills/keywords for job search. "
            "Return a JSON object with 'summary' and 'keywords' (array of strings).\n"
            f"Profile: {json.dumps(profile, indent=2)}"
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
            mos.get('title', '') for mos in profile.get('mos_history', [])
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
                        critical_fields = [
                            structured.get("company_name"),
                            structured.get("job_title"),
                            structured.get("location"),
                            structured.get("description"),
                            structured.get("salary"),
                            structured.get("employment_type"),
                            structured.get("work_mode"),
                        ]
                        null_count = sum(1 for field in critical_fields if field in [None, '', [], {}])

                        if null_count < 3:
                            jobs.append({
                                "company_name": structured.get("company_name"),
                                "job_title": structured.get("job_title"),
                                "location": structured.get("location"),
                                "job_tags": structured.get("job_tags", []),
                                "posted_time": structured.get("posted_time"),
                                "applicants": structured.get("applicants"),
                                "salary": structured.get("salary"),
                                "employment_type": structured.get("employment_type"),
                                "work_mode": structured.get("work_mode"),
                                "url": url,
                                "description": structured.get("description"),
                            })
                        else:
                            print(f"Job skipped due to too many null fields: {url}")
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
                f"Profile:\n{json.dumps(profile, indent=2)}\n\n"
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

        from copy import deepcopy
        response_jobs = deepcopy(scored_jobs)

        client = MongoClient(settings.MONGO_URI)
        db = client[settings.MONGO_DB_NAME]
        cache_db = db["cache_job_db"]

        for job in scored_jobs:
            job["scraped_at"] = datetime.utcnow().isoformat()
            job["fingerprint"] = user.fingerprint
            if not cache_db.find_one({"url": job["url"], "fingerprint": user.fingerprint}):
                cache_db.insert_one(job)
        return JsonResponse(response_jobs, safe=False)

    
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
            del chat["_id"]
        
        return JsonResponse(chats, safe=False)

class FetchRelJobs(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        fingerprint = getattr(user, 'fingerprint', None)

        if not fingerprint:
            return JsonResponse({'error': 'User fingerprint not found.'}, status=400)

        try:
            # Connect to MongoDB
            client = MongoClient(settings.MONGO_URI)
            db = client[settings.MONGO_DB_NAME]
            cache_collection = db["cache_job_db"]

            # Fetch jobs related to the user
            job_docs = list(cache_collection.find({"fingerprint": fingerprint}, {'_id': 0}))

            return JsonResponse(job_docs, safe=False, status=200)

        except Exception as e:
            return JsonResponse({'error': f'Failed to fetch jobs: {str(e)}'}, status=500)

class VeteranMentorSearchView(APIView):
    permission_classes = [IsAuthenticated]

    def extract_structured_mentor_info(self, visible_text, keywords):
        prompt = (
            "You are a structured data extractor that parses plain text professional profiles. "
            "Given a mentor or professional's plain text content, return a JSON object with the following normalized fields:\n\n"
            "- `name`: string\n"
            "- `title`: string (e.g., 'Senior Software Engineer', 'Career Coach')\n"
            "- `expertise`: array of up to 5 keywords/skills/areas of guidance\n"
            "- `profile_url`: string (if available)\n"
            "- `summary`: a short 2-3 line bio written in **third person**, not in first person (avoid 'I', 'my', 'me').\n\n"
            "Return only the JSON object. If data is missing, set values to `null` or an empty list.\n\n"
            "Profile text:\n"
            f"{visible_text}"
        )
        llama_data = {
            "model": "meta-llama/llama-4-scout-17b-16e-instruct",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant that extracts structured mentor info from HTML."},
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
            print(f"Failed to extract structured mentor info: {e}")
            return {
                "name": None,
                "title": None,
                "expertise": [],
                "profile_url": None,
                "summary": None
            }

    def post(self, request):
        user = request.user
        # 1. Load user profile
        client = MongoClient(settings.MONGO_URI)
        db = client[settings.MONGO_DB_NAME]
        user_collection = db["user_data"]
        user_doc = user_collection.find_one({'fingerprint': user.fingerprint})
        user_doc = decrypt_with_fingerprint(user_doc, user.fingerprint)
        if not user_doc:
            return JsonResponse({'error': 'User profile not found.'}, status=404)
        profile = user_doc
        del profile["_id"]

        # 2. Generate summary + keywords with LLaMA
        prompt = (
            "You are an expert at translating military experience to civilian terms. "
            "Given the following profile, summarize it for a civilian audience and generate a list of relevant skills/keywords for mentorship search. "
            "Return a JSON object with 'summary' and 'keywords' (array of strings).\n"
            f"Profile: {json.dumps(profile, indent=2)}"
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
            mos.get('title', '') for mos in profile.get('mos_history', [])
        ]

        # 3. Search for mentors via SerpAPI (LinkedIn, etc.)
        serpapi_key = getattr(settings, 'SERPAPI_KEY', None)
        mentors = []
        if serpapi_key:
            query = ' '.join(keywords[:3]) + 'veteran' if keywords else 'veteran mentor'
            params = {
                'engine': 'google',
                'q': query + ' site:linkedin.com/in',
                'api_key': serpapi_key,
                'num': 20
            }
            try:
                serp_resp = requests.get('https://serpapi.com/search', params=params, timeout=20)
                serp_resp.raise_for_status()
                serp_data = serp_resp.json()
                for item in serp_data.get('organic_results', []):
                    url = item.get("link")
                    snippet = item.get("snippet", "")
                    title = item.get("title", "")
                    name, _, role = title.partition(" - ")

                    mentors.append({
                        "name": name.strip() if name else None,
                        "title": role.strip() if role else None,
                        "expertise": keywords[:5],
                        "profile_url": url,
                        "summary": snippet.strip() if snippet else None,
                    })
            except Exception as e:
                print(f"SerpAPI error: {e}")

            from copy import deepcopy
            response_mentors = deepcopy(mentors)

            client = MongoClient(settings.MONGO_URI)
            db = client[settings.MONGO_DB_NAME]
            cache_db = db["cache_mentor_db"]

            for job in mentors:
                job["scraped_at"] = datetime.utcnow().isoformat()
                job["fingerprint"] = user.fingerprint
                if not cache_db.find_one({"url": job["profile_url"], "fingerprint": user.fingerprint}):
                    cache_db.insert_one(job)
        return JsonResponse(response_mentors, safe=False)

class FetchRelMentors(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        fingerprint = getattr(user, 'fingerprint', None)

        if not fingerprint:
            return JsonResponse({'error': 'User fingerprint not found.'}, status=400)

        try:
            # Connect to MongoDB
            client = MongoClient(settings.MONGO_URI)
            db = client[settings.MONGO_DB_NAME]
            cache_collection = db["cache_mentor_db"]

            # Fetch jobs related to the user
            job_docs = list(cache_collection.find({"fingerprint": fingerprint}, {'_id': 0}))

            return JsonResponse(job_docs, safe=False, status=200)

        except Exception as e:
            return JsonResponse({'error': f'Failed to fetch jobs: {str(e)}'}, status=500)
        
class VeteranCommunitySearchView(APIView):
    permission_classes = [IsAuthenticated]

    def extract_structured_event_info(self, visible_text):
        prompt = (
            "You are a structured data extractor that parses plain text about community events and services for veterans. "
            "Return a JSON object with these normalized fields:\n"
            "- `name`: string (event/service name)\n"
            "- `description`: 2-3 line summary\n"
            "- `type`: one of ['Event', 'Support Service', 'benefit_program']\n"
            "- `location`: string (city/state or Online) if available\n"
            "- `date`: ISO format YYYY-MM-DD if available\n"
            "- `time`: starting HH:MM am/pm if available. No need ending\n"
            "- `contact`: string (email, phone) if available\n"
            "- `audience`: string (e.g., 'All veterans', 'Female veterans', etc.)\n"
            "- `tags`: array of up to 3 relevant keywords\n"
            "Return only the JSON object.\n\n"
            f"Content:\n{visible_text}"
        )
        llama_data = {
            "model": "meta-llama/llama-4-scout-17b-16e-instruct",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant that extracts structured event data for veterans."},
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
            print(f"Failed to extract structured community info: {e}")
            return {}

    def post(self, request):
        user = request.user

        # Load user profile
        client = MongoClient(settings.MONGO_URI)
        db = client[settings.MONGO_DB_NAME]
        user_collection = db["user_data"]
        user_doc = user_collection.find_one({'fingerprint': user.fingerprint})
        user_doc = decrypt_with_fingerprint(user_doc, user.fingerprint)
        if not user_doc:
            return JsonResponse({'error': 'User profile not found.'}, status=404)
        profile = user_doc
        del profile["_id"]

        keywords = [mos.get('title', '') for mos in profile.get('mos_history', [])] or ["veteran"]

        # Search via SerpAPI
        serpapi_key = getattr(settings, 'SERPAPI_KEY', None)
        results = []
        if serpapi_key:
            query = ' '.join(keywords[:3]) + ' veteran services events 2024'
            params = {
                'engine': 'google',
                'q': query,
                'api_key': serpapi_key,
                'num': 15
            }
            try:
                serp_resp = requests.get('https://serpapi.com/search', params=params, timeout=20)
                serp_resp.raise_for_status()
                serp_data = serp_resp.json()
                for item in serp_data.get('organic_results', []):
                    url = item.get("link")
                    snippet = item.get("snippet", "")
                    title = item.get("title", "")
                    visible_text = f"Title: {title}\nSnippet: {snippet}\nURL: {url}"
                    structured = self.extract_structured_event_info(visible_text)
                    structured["link"] = url
                    results.append(structured)
            except Exception as e:
                print(f"SerpAPI error: {e}")
            from copy import deepcopy
            response_results = deepcopy(results)
            # Cache in DB
            community_db = db["cache_community_db"]
            for result in results:
                result["fingerprint"] = user.fingerprint
                result["scraped_at"] = datetime.utcnow().isoformat()
                if not community_db.find_one({"link": result["link"], "fingerprint": user.fingerprint}):
                    community_db.insert_one(result)

        return JsonResponse(response_results, safe=False)

class FetchRelEvents(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        fingerprint = getattr(user, 'fingerprint', None)

        if not fingerprint:
            return JsonResponse({'error': 'User fingerprint not found.'}, status=400)

        try:
            # Connect to MongoDB
            client = MongoClient(settings.MONGO_URI)
            db = client[settings.MONGO_DB_NAME]
            cache_collection = db["cache_community_db"]

            # Fetch jobs related to the user
            job_docs = list(cache_collection.find({"fingerprint": fingerprint}, {'_id': 0}))

            return JsonResponse(job_docs, safe=False, status=200)

        except Exception as e:
            return JsonResponse({'error': f'Failed to fetch jobs: {str(e)}'}, status=500)
        
class VeteranBioDataView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user

        # 1. Load user profile
        client = MongoClient(settings.MONGO_URI)
        db = client[settings.MONGO_DB_NAME]
        user_collection = db["user_data"]
        user_doc = user_collection.find_one({'fingerprint': user.fingerprint})
        user_doc = decrypt_with_fingerprint(user_doc, user.fingerprint)
        if not user_doc:
            return JsonResponse({'error': 'User profile not found.'}, status=404)

        profile = user_doc
        del profile["_id"]

        # 2. Construct prompt for LLaMA to generate enriched civilian bio-data
        prompt = (
            "You are an expert career assistant helping U.S. military veterans transition to civilian careers. "
            "Given the military background and personal profile below, write a JSON resume summary. "
            "Translate the experience into clear civilian terms and provide a well-structured biography.\n"
            "Include these fields in the JSON response:\n"
            "- `full_name`: string\n"
            "- `headline`: string (short title or role summary)\n"
            "- `summary`: string (3-5 line bio in third person)\n"
            "- `skills`: array of key skills (4-5)\n"
            "- `education`: string (school and degree if known)\n"
            "- `experience_summary`: string (overview of work history)\n"
            "- `experience_details`: array of experience objects with `role`, `organization`, `duration`, and `description`\n"
            "- `achievements`: array of notable achievements or recognitions\n"
            "- `certifications`: array of any known certifications (if mentioned)\n"
            "- `volunteer_experience`: string (if relevant)\n"
            "Return only the JSON object.\n\n"
            f"Veteran Profile:\n{json.dumps(profile, indent=2)}"
        )

        llama_data = {
            "model": "meta-llama/llama-4-scout-17b-16e-instruct",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant that generates enriched bios for veterans."},
                {"role": "user", "content": prompt}
            ]
        }

        try:
            resp = requests.post(settings.GROQ_API_URL,
                                 json=llama_data,
                                 headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                                 timeout=60)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            match = re.search(r'\{.*\}', content, re.DOTALL)
            biodata = json.loads(match.group(0)) if match else json.loads(content)
        except Exception as e:
            print(f"Bio generation failed: {e}")
            return JsonResponse({'error': 'Failed to generate bio-data.'}, status=500)

        # 3. Save to MongoDB collection bio_data
        bio_collection = db["bio_data"]
        biodata["fingerprint"] = user.fingerprint
        biodata["created_at"] = datetime.utcnow().isoformat()
        bio_collection.replace_one({"fingerprint": user.fingerprint}, biodata, upsert=True)

        return JsonResponse(biodata, safe=False)


from django.template.loader import render_to_string
from weasyprint import HTML
from django.http import HttpResponse

class VeteranBioPDFView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user

        # 1. Load bio-data from MongoDB using fingerprint
        client = MongoClient(settings.MONGO_URI)
        db = client[settings.MONGO_DB_NAME]
        bio_collection = db["bio_data"]
        biodata = bio_collection.find_one({"fingerprint": user.fingerprint})

        if not biodata:
            return JsonResponse({'error': 'Bio-data not found. Please generate it first.'}, status=404)

        # Remove internal fields for rendering
        biodata.pop("_id", None)
        biodata.pop("fingerprint", None)
        biodata.pop("created_at", None)

        # 2. Render HTML and convert to PDF
        html_string = render_to_string("biodata.html", biodata)
        pdf_file = HTML(string=html_string).write_pdf()

        # 3. Serve PDF response
        response = HttpResponse(pdf_file, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="veteran_biodata.pdf"'
        return response
