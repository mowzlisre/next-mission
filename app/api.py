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
    def post(self, request):
        # 1. Load dummy profile and MOS database
        dummy_path = os.path.join(os.path.dirname(__file__), 'utils', 'data', 'dummy.json')
        mos_db_path = os.path.join(os.path.dirname(__file__), 'utils', 'data', 'mos_database.json')
        with open(dummy_path, 'r') as f:
            profile = json.load(f)
        with open(mos_db_path, 'r') as f:
            mos_db_list = json.load(f)
        mos_db = {item['code']: item for item in mos_db_list}

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
        try:
            llama_resp = requests.post(settings.GROQ_API_URL, json=llama_data, headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"}, timeout=60)
            llama_resp.raise_for_status()
            llama_json = llama_resp.json()["choices"][0]["message"]["content"]
            # Try to parse JSON from Llama output
            match = re.search(r'\{.*\}', llama_json, re.DOTALL)
            if match:
                summary_keywords = json.loads(match.group(0))
            else:
                summary_keywords = json.loads(llama_json)
        except Exception:
            summary_keywords = {"summary": "", "keywords": []}

        keywords = summary_keywords.get('keywords', [])
        if not keywords:
            keywords = [mos.get('title', '') for mos in profile['form_data'].get('mos_history', [])]

        print("Keywords used:", keywords)

        # 4. Search jobs from SERPAPI (LinkedIn) and USAJOBS
        serpapi_key = getattr(settings, 'SERPAPI_KEY', None)
        usajobs_key = getattr(settings, 'USAJOBS_API_KEY', None)
        jobs = []
        # SERPAPI Google Search for Jobs (now only LinkedIn)
        if serpapi_key:
            # Use the first 3 keywords to build the query
            query = ' '.join(keywords[:3]) if keywords else ''
            params = {
                'engine': 'google',
                'q': query + ' jobs site:linkedin.com',  # Restrict to LinkedIn
                'api_key': serpapi_key,
                'num': 20
            }
            try:
                serp_resp = requests.get('https://serpapi.com/search', params=params, timeout=20)
                serp_resp.raise_for_status()
                serp_data = serp_resp.json()
                print("SERPAPI response:", serp_data)
                linkedin_jobs = [item for item in serp_data.get('organic_results', []) if item.get('link') and 'linkedin.com' in item.get('link')]
                for item in linkedin_jobs[:10]:  # Only LinkedIn jobs, max 10
                    url = item.get('link', None)
                    domain = None
                    company_name = None
                    if url:
                        parsed = urlparse(url)
                        domain = parsed.netloc if parsed.netloc else None
                    # Crawl the job page
                    job_title = item.get('title', '')
                    snippet = item.get('snippet', '')
                    location = extract_location(job_title) or extract_location(snippet) or None
                    description = None
                    company_logo = None
                    tags = set()
                    try:
                        if url:
                            page = requests.get(url, timeout=10)
                            # Detect anti-bot/Cloudflare protection
                            if 'window._cf_chl_opt' in page.text or 'cf-browser-verification' in page.text or 'Cloudflare' in page.text:
                                raise Exception('Blocked by anti-bot protection')
                            soup = BeautifulSoup(page.content, 'html.parser')
                            # Try to extract job title
                            h1 = soup.find('h1')
                            if h1 and len(h1.text) > 5:
                                job_title = h1.text.strip()
                            # Try to extract company name from meta or prominent HTML
                            meta_company = soup.find('meta', {'property': 'og:site_name'})
                            if meta_company and meta_company.get('content'):
                                company_name = meta_company['content']
                            else:
                                # Try to find company name in a span/div with 'company' in class or id
                                company_tag = soup.find(lambda tag: tag.name in ['span', 'div'] and tag.get('class') and any('company' in c for c in tag.get('class')))
                                if company_tag and company_tag.text:
                                    company_name = company_tag.text.strip()
                            # Try to extract location again from HTML
                            loc_tag = soup.find(string=lambda t: t and ('location' in t.lower() or 'Location' in t))
                            if loc_tag:
                                loc = extract_location(loc_tag)
                                if loc:
                                    location = loc
                            # Try to extract description
                            desc_tag = soup.find('meta', {'name': 'description'})
                            if desc_tag and desc_tag.get('content'):
                                description = desc_tag['content']
                            else:
                                # Fallback: use first large <p> or <div>
                                p = soup.find('p')
                                if p and len(p.text) > 30:
                                    description = p.text.strip()
                            # Try to extract logo
                            logo_tag = soup.find('img', {'class': 'company-logo'})
                            if logo_tag and logo_tag.get('src'):
                                company_logo = logo_tag['src']
                            # Extract tags/skills from description
                            desc_text = (description or '') + ' ' + (snippet or '')
                            for k in keywords:
                                if k.lower() in desc_text.lower():
                                    tags.add(k)
                    except Exception as e:
                        print(f"Error crawling {url}: {e}")
                        # fallback to snippet as description, and do not use HTML fields
                        description = snippet
                        company_name = None
                        company_logo = None
                        tags = set([k for k in keywords if k.lower() in snippet.lower()])
                    # Fallbacks
                    if not company_name:
                        company_name = domain
                    # Fallback for description if too short or generic
                    if not description or len(description) < 20:
                        description = snippet
                    jobs.append({
                        'company_logo': company_logo,
                        'company_name': company_name,
                        'job_title': job_title if job_title else None,
                        'location': location,
                        'job_tags': list(tags),
                        'posted_time': None,
                        'applicants': None,
                        'alumni': None,
                        'url': url,
                        'description': description if description else snippet
                    })
                    time.sleep(1)  # Be polite to job boards
                print("LinkedIn jobs found:", len(jobs))
            except Exception as e:
                print("SERPAPI error:", e)
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
                usajobs_resp = requests.get('https://data.usajobs.gov/api/search', params=params, headers=headers, timeout=20)
                usajobs_resp.raise_for_status()
                usajobs_data = usajobs_resp.json()
                print("USAJOBS response:", usajobs_data)
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
                print("Jobs found so far:", len(jobs))
            except Exception as e:
                print("USAJOBS error:", e)

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
                job_resp = requests.post(settings.GROQ_API_URL, json=job_data, headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"}, timeout=30)
                job_resp.raise_for_status()
                job_json = job_resp.json()["choices"][0]["message"]["content"]
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
