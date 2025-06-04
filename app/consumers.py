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

        prompt = self.build_prompt(profile_data, chat_history, user_question)
        reply = await self.ask_llama_async(prompt)

        # Tool-calling logic: If Llama requests a tool call, call MCP, then re-ask Llama with results
        if isinstance(reply, str) and reply.strip().startswith("TOOL_CALL:"):
            tool_query = reply.strip().split("TOOL_CALL:", 1)[1].strip()
            # Call MCP endpoint
            async with httpx.AsyncClient() as client:
                try:
                    mcp_resp = await client.post(
                        f"http://localhost:8000/app/mcp/search/",  # Adjust if running on a different host/port
                        json={"query": tool_query},
                        timeout=30
                    )
                    mcp_resp.raise_for_status()
                    mcp_results = mcp_resp.json().get('results', [])
                except Exception as e:
                    mcp_results = []
            # Build a new prompt for Llama with the tool results
            tool_prompt = self.build_prompt(
                profile_data, chat_history, user_question,
                knowledge_base=json.dumps(mcp_results, indent=2)
            )
            reply = await self.ask_llama_async(tool_prompt)

        # Store bot reply
        await db.chat_history.update_one(
            {'user_id': self.fingerprint},
            {
                '$push': {'conversation': encrypt_with_fingerprint({'role': 'bot', 'message': reply}, self.fingerprint)},
                '$set': {'updated_at': datetime.utcnow()}
            },
            upsert=True
        )

        await self.send(json.dumps({"response": reply}))

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
            ]
        }
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(settings.GROQ_API_URL, json=data, timeout=60, headers=headers)
                response.raise_for_status()
                result = response.json()
                return result["choices"][0]["message"]["content"]
            except Exception as e:
                return f"[Error contacting Llama 4: {str(e)}]"