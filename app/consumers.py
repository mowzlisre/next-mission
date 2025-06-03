import json
from channels.generic.websocket import AsyncWebsocketConsumer
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime

mongo = AsyncIOMotorClient("mongodb://localhost:27017/")
db = mongo.chatbot
messages = db.messages

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user_id = self.scope['url_route']['kwargs']['user_id']
        await self.accept()

    async def disconnect(self, close_code):
        pass

    async def receive(self, text_data):
        data = json.loads(text_data)
        msg = data.get("message")

        await messages.insert_one({
            "user_id": self.user_id,
            "role": "user",
            "content": msg,
            "timestamp": datetime.utcnow()
        })

        # Replace with real LLM logic
        reply = f"Echo: {msg} 1 2 3 4 5"
        await messages.insert_one({
            "user_id": self.user_id,
            "role": "bot",
            "content": reply,
            "timestamp": datetime.utcnow()
        })

        await self.send(json.dumps({"response": reply}))
