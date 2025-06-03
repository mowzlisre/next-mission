import json
from channels.generic.websocket import AsyncWebsocketConsumer
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import os
import requests
from dotenv import load_dotenv
from rest_framework_simplejwt.backends import TokenBackend
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.conf import settings
from asgiref.sync import sync_to_async

User = get_user_model()


# Load environment variables
load_dotenv()


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
                '$push': {'conversation': {'role': 'user', 'message': user_question}},
                '$set': {'updated_at': datetime.utcnow()},
                '$setOnInsert': {'created_at': datetime.utcnow()}
            },
            upsert=True
        )

        chat_history = await self.get_chat_history(self.fingerprint)
        profile_data = await self.get_user_profile(self.fingerprint)


        prompt = self.build_prompt(profile_data, chat_history, user_question)
        reply = await self.ask_llama(prompt)

        # Store bot reply
        await db.chat_history.update_one(
            {'user_id': self.fingerprint},
            {
                '$push': {'conversation': {'role': 'bot', 'message': reply}},
                '$set': {'updated_at': datetime.utcnow()}
            },
            upsert=True
        )

        await self.send(json.dumps({"response": reply}))



    async def get_user_profile(self, user_id):
        for col_name in ['dd214', 'jst', 'dd2586']:
            doc = await db[col_name].find_one({'user_id': user_id})
            if doc:
                doc['_id'] = str(doc['_id']) 
                return doc
        return None

    async def get_chat_history(self, user_id, limit=20):
        doc = await db.chat_history.find_one({'user_id': user_id})
        if doc and 'conversation' in doc:
            return doc['conversation'][-limit:]
        return []

    def build_prompt(self, user_profile, chat_history, user_question, knowledge_base=None):
        prompt = (
            "You are a helpful assistant for U.S. military veterans. "
            "You have access to the user's profile (below) and the conversation history. "
            "Use this information, and the knowledge base if provided, to answer the user's question. "
            "If the question is about benefits, jobs, or transition, personalize the answer using the user's profile. "
            "If you don't know, say so honestly.\n\n"
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