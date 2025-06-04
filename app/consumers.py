import json
from channels.generic.websocket import AsyncWebsocketConsumer
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import os
import requests
from django.contrib.auth import get_user_model
from django.conf import settings
from asgiref.sync import sync_to_async
import httpx
from users.crypt import encrypt_with_fingerprint, decrypt_with_fingerprint
import asyncio
User = get_user_model()




# MongoDB setup
mongo = AsyncIOMotorClient(settings.MONGO_URI)
db = mongo.veteran_docs

# WebSocket Consumer
class ChatConsumer(AsyncWebsocketConsumer):
    from asgiref.sync import sync_to_async

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        try:
            self.user_id = int(self.scope['url_route']['kwargs']['user_id'])
            self.user = await sync_to_async(User.objects.get)(id=self.user_id)
            self.fingerprint = self.user.fingerprint
            await self.accept()
        except User.DoesNotExist:
            await self.close()

    async def disconnect(self, close_code):
        pass

    async def receive(self, text_data):
        data = json.loads(text_data)
        user_question = data.get("message")

        # Store user message
        await db.chat_history.update_one(
            {'user_id': self.fingerprint},
            {
                '$push': {'conversation': encrypt_with_fingerprint({'role': 'user', 'message': user_question}, self.fingerprint)},
                '$set': {'updated_at': datetime.utcnow()},
                '$setOnInsert': {'created_at': datetime.utcnow()}
            },
            upsert=True
        )

        chat_history = await self.get_chat_history(self.fingerprint)
        profile_data = await self.get_user_profile(self.fingerprint)

        # Always perform web search first (internal, not via API)
        mcp_results = await self.perform_web_search(user_question)
        print(f"[DEBUG] MCP results: {mcp_results}")  # Debug: log MCP results

        # Build prompt with web results always included
        prompt = self.build_prompt(
            profile_data, chat_history, user_question,
            knowledge_base=json.dumps(mcp_results, indent=2)
        )
        reply = await self.ask_llama_async(prompt)
        print(f"[DEBUG] Llama reply: {reply}")  # Debug: log Llama's response

        # Validate links in actions (if any)
        cleaned_reply = await self.clean_actions_links(reply)

        # Store bot reply
        await db.chat_history.update_one(
            {'user_id': self.fingerprint},
            {
                '$push': {'conversation': encrypt_with_fingerprint({'role': 'bot', 'message': cleaned_reply}, self.fingerprint)},
                '$set': {'updated_at': datetime.utcnow()}
            },
            upsert=True
        )

        await self.send(json.dumps({"response": cleaned_reply}))

    async def get_user_profile(self, fingerprint):
        doc = await db["user_data"].find_one({'fingerprint': fingerprint})
        if doc:
            try:
                decrypted_doc = decrypt_with_fingerprint(doc, fingerprint)
                decrypted_doc['_id'] = str(doc['_id'])  # keep the original MongoDB ID
                return decrypted_doc
            except Exception as e:
                # You might want to log this
                return {"error": f"Decryption failed: {str(e)}"}
        return None

    async def get_chat_history(self, user_id, limit=20):
        doc = await db.chat_history.find_one({'user_id': user_id})
        if doc and 'conversation' in doc:
            encrypted_conversation = doc['conversation'][-limit:]
            decrypted_conversation = [
                decrypt_with_fingerprint(item, self.fingerprint) for item in encrypted_conversation
            ]
            return decrypted_conversation
        return []

    def build_prompt(self, user_profile, chat_history, user_question, knowledge_base=None):
        prompt = (
            "You are a helpful assistant for U.S. military veterans. "
            "You have access to the user's profile (below) and the conversation history. "
            "If you need information not in the user's profile or chat history, you can use a web search tool. "
            "If you use the tool, you will be provided with search results to help answer the user's question. "
            "Always return your answer in the following JSON format, where \"message\" is your reply (can be a paragraph, steps, or bullet points), "
            "and \"actions\" is an array of interactive elements (links, phone numbers, comments) only when available:\n\n"
            "[\n"
            "  {\n"
            "    \"message\": \"Your main reply to the user.\",\n"
            "    \"actions\": [\n"
            "      { \"action\": \"link\", \"do\": \"https://example.com\", \"help_text\": \"Description of the link\" },\n"
            "      { \"action\": \"phone\", \"do\": \"+1-800-123-4567\", \"help_text\": \"Description of the phone number\" },\n"
            "      { \"action\": \"comment\", \"do\": \"Any extra comment or fact.\", \"help_text\": \"Description of the comment\" }\n"
            "    ]\n"
            "  }\n"
            "]\n\n"
            "Make sure your output is valid JSON using double quotes (\"), not single quotes.\n"
            "If you need to use the tool, respond with: TOOL_CALL: <query>. Otherwise, answer directly.\n\n"
            f"User Profile (JSON):\n{json.dumps(user_profile, indent=2)}\n\n"
            f"Conversation History (most recent last):\n"
        )

        for msg in chat_history:
            prompt += f"{msg['role'].capitalize()}: {msg['message']}\n"
        prompt += f"\nUser's Current Question: {user_question}\n"
        if knowledge_base:
            prompt += f"\nKnowledge Base:\n{knowledge_base}\n"
        prompt += "\nAnswer as helpfully and concisely as possible."
        # Add behavioral instructions for allowed topics, web search, and mental health
        prompt += (
            "\n\nIMPORTANT INSTRUCTIONS:\n"
            "- Only respond to questions related to: resume reviews, career path suggestions, benefits information, education opportunities, business (if veteran-related), connection building (if veteran-related), veteran mental health and wellness, and housing transition.\n"
            "- If the user's question is not related to these areas, politely decline to answer and state that you are focused on supporting veterans in these areas.\n"
            "- If the user's question is about housing, housing transition, rental assistance, home buying, or veteran housing programs, you MUST answer and provide resources or guidance.\n"
            "- Use the web search tool (TOOL_CALL) only for career, education, education gap, education transfer, housing transition, and similar veteran-related queries. Do NOT use web search for unrelated topics.\n"
            "- For mental health topics, act as a mentor: listen empathetically, provide supportive and encouraging responses, promote wellness and peer support, and encourage seeking professional help if needed (but do not give medical advice).\n"
            "- Always use the user's profile and chat history for context.\n"
            "- Focus on service navigation (healthcare, education, employment, housing, housing transition), transition support (resume, job training, mentorship), and mental health/wellness (stress management, counseling, peer support).\n"
            "\nExample allowed questions for housing topics:\n"
            "- 'Can you help me find veteran housing?'\n"
            "- 'What are my options for housing transition?'\n"
            "- 'How do I get rental assistance as a veteran?'\n"
        )
        return prompt

    async def ask_llama(self, prompt):
        headers = {'Authorization': f'Bearer {settings.GROQ_API_KEY}'}
        data = {
            "model": "meta-llama/llama-4-scout-17b-16e-instruct",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant for U.S. military veterans."},
                {"role": "user", "content": prompt}
            ]
        }
        try:
            response = requests.post(settings.GROQ_API_URL, json=data, headers=headers)
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            return f"[Error contacting Llama 4: {str(e)}]"

    async def ask_llama_async(self, prompt):
        headers = {'Authorization': f'Bearer {settings.GROQ_API_KEY}'}
        data = {
            "model": "meta-llama/llama-4-scout-17b-16e-instruct",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant for U.S. military veterans."},
                {"role": "user", "content": prompt}
            ],
            "stream": True
        }
        async with httpx.AsyncClient() as client:
            try:
                async with client.stream("POST", settings.GROQ_API_URL, json=data, headers=headers, timeout=60) as response:
                    response.raise_for_status()
                    content = ""
                    async for chunk in response.aiter_text():
                        content += chunk
                    return content
            except Exception as e:
                return f"[Error contacting Llama 4: {str(e)}]"

    async def clean_actions_links(self, reply):
        import httpx
        try:
            # Try to parse the reply as JSON array
            parsed = json.loads(reply)
            if not isinstance(parsed, list):
                return reply
            # Only process if 'actions' is present
            for msg in parsed:
                if 'actions' in msg and isinstance(msg['actions'], list):
                    actions = msg['actions']
                    # Validate all links asynchronously
                    valid_actions = []
                    async with httpx.AsyncClient() as client:
                        tasks = []
                        for action in actions:
                            if action.get('action') == 'link' and action.get('do'):
                                url = action['do']
                                tasks.append(self.check_link_valid(client, url, action))
                            else:
                                valid_actions.append(action)
                        checked = await asyncio.gather(*tasks)
                        valid_actions.extend([a for a in checked if a])
                    msg['actions'] = valid_actions
            return json.dumps(parsed)
        except Exception as e:
            print(f"[DEBUG] clean_actions_links error: {e}")
            return reply

    async def check_link_valid(self, client, url, action):
        try:
            resp = await client.head(url, timeout=5, follow_redirects=True)
            if resp.status_code == 200:
                # Some servers return 200 for soft 404s, so check content
                get_resp = await client.get(url, timeout=5, follow_redirects=True)
                if get_resp.status_code == 200:
                    html = get_resp.text.lower()
                    # Common soft 404 phrases
                    not_found_phrases = [
                        'sorry — we can\'t find that page',
                        'sorry, we can\'t find that page',
                        '404',
                        'page not found',
                        'not found',
                        'error 404',
                        'this page does not exist',
                        'the page you requested could not be found',
                        'no longer exists',
                        'does not exist',
                        'cannot be found',
                        'gone',
                        'dead link',
                        'broken link'
                    ]
                    if any(phrase in html for phrase in not_found_phrases):
                        print(f"[DEBUG] Soft 404 detected for {url}")
                        return None
                    return action
            # Some servers don't support HEAD, fallback to GET
            resp = await client.get(url, timeout=5, follow_redirects=True)
            if resp.status_code == 200:
                html = resp.text.lower()
                not_found_phrases = [
                    'sorry — we can\'t find that page',
                    'sorry, we can\'t find that page',
                    '404',
                    'page not found',
                    'not found',
                    'error 404',
                    'this page does not exist',
                    'the page you requested could not be found',
                    'no longer exists',
                    'does not exist',
                    'cannot be found',
                    'gone',
                    'dead link',
                    'broken link'
                ]
                if any(phrase in html for phrase in not_found_phrases):
                    print(f"[DEBUG] Soft 404 detected for {url}")
                    return None
                return action
        except Exception as e:
            print(f"[DEBUG] Link check failed for {url}: {e}")
        return None

    async def perform_web_search(self, query):
        import re
        import httpx
        from django.conf import settings
        serpapi_key = getattr(settings, 'SERPAPI_KEY', None)
        if not serpapi_key:
            return []
        params = {
            'q': query,
            'api_key': serpapi_key,
            'engine': 'google',
            'num': 3
        }
        results = []
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get('https://serpapi.com/search', params=params, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                for item in data.get('organic_results', [])[:3]:
                    results.append({
                        'title': self.clean_text(item.get('title')),
                        'snippet': self.clean_text(item.get('snippet')),
                        'link': item.get('link'),
                        'source': item.get('displayed_link') or item.get('link')
                    })
            except Exception as e:
                print(f"[DEBUG] Web search error: {e}")
        return results

    def clean_text(self, text):
        import re
        if not text:
            return ""
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()