import os
import json
from pymongo import MongoClient
from dotenv import load_dotenv
import requests
from datetime import datetime

# Load environment variables
load_dotenv()
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
MONGO_DB_NAME = os.getenv('MONGO_DB_NAME', 'veteran_docs')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]

print("GROQ_API_KEY:", GROQ_API_KEY)
print("MONGO_URI:", MONGO_URI)
print("MONGO_DB_NAME:", MONGO_DB_NAME)

# --- Chat History Helpers ---
def get_chat_history(user_id, limit=20):
    doc = db.chat_history.find_one({'user_id': user_id})
    if doc and 'conversation' in doc:
        return doc['conversation'][-limit:]
    return []

def append_chat_history(user_id, role, message):
    now = datetime.utcnow()
    db.chat_history.update_one(
        {'user_id': user_id},
        {'$push': {'conversation': {'role': role, 'message': message}},
         '$set': {'updated_at': now},
         '$setOnInsert': {'created_at': now}},
        upsert=True
    )

# --- User Profile Helper ---
def get_user_profile(user_id):
    # Try all collections for a profile (DD214, JST, DD2586)
    for col in ['dd214', 'jst', 'dd2586']:
        doc = db[col].find_one({'user_id': user_id})
        if doc:
            return doc
    return None

# --- Prompt Builder ---
def build_prompt(user_profile, chat_history, user_question, knowledge_base=None):
    # Remove or convert _id if present
    if '_id' in user_profile:
        user_profile['_id'] = str(user_profile['_id'])
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

# --- Llama 4 Chat API Call ---
def ask_llama(prompt):
    headers = {'Authorization': f'Bearer {GROQ_API_KEY}'}
    data = {
        "model": "meta-llama/llama-4-scout-17b-16e-instruct",  # Updated to working Groq model
        "messages": [
            {"role": "system", "content": "You are a helpful assistant for U.S. military veterans."},
            {"role": "user", "content": prompt}
        ]
    }
    try:
        response = requests.post(GROQ_API_URL, json=data, headers=headers)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[Error contacting Llama 4: {str(e)}]"

# --- Main Chatbot Logic ---
def chatbot_ask(user_id, user_question, knowledge_base=None):
    user_profile = get_user_profile(user_id)
    if not user_profile:
        return "Sorry, I couldn't find your profile. Please upload your document first."
    chat_history = get_chat_history(user_id)
    prompt = build_prompt(user_profile, chat_history, user_question, knowledge_base)
    answer = ask_llama(prompt)
    append_chat_history(user_id, 'user', user_question)
    append_chat_history(user_id, 'bot', answer)
    return answer

def insert_dummy_profile(user_id, doc_type='dd214'):
    dummy_profile = {
        'user_id': user_id,
        'document_type': doc_type.upper(),
        'uploaded_at': datetime.utcnow().isoformat(),
        'full_name': 'Jane Doe',
        'branch_of_service': 'Army',
        'pay_grade': 'E-5',
        'service_start_date': '2010-01-01',
        'service_end_date': '2020-01-01',
        'character_of_service': 'Honorable',
        'mos_history': [
            {
                'code': '11B',
                'title': 'Infantryman',
                'start_date': '2010-01-01',
                'end_date': '2020-01-01',
                'source': doc_type.upper()
            }
        ],
        'awards': [
            {
                'name': 'Army Achievement Medal',
                'date_awarded': '2015-05-01',
                'description': 'For meritorious service',
                'source': doc_type.upper()
            }
        ],
        'training_courses': [
            {
                'name': 'Basic Combat Training',
                'description': 'Initial entry training',
                'completion_date': '2010-03-01',
                'source': doc_type.upper()
            }
        ],
        'profile_summary': 'Jane Doe served 10 years as an Infantryman (MOS 11B) in the Army. She is eligible for a range of veteran benefits and has strong leadership and tactical skills.'
    }
    db[doc_type].replace_one({'user_id': user_id}, dummy_profile, upsert=True)
    return True

if __name__ == "__main__":
    user_id = "test_user_1"
    insert_dummy_profile(user_id, doc_type='dd214')
    print("Type 'exit' or 'quit' to end the chat.\n")
    while True:
        question = input("You: ")
        if question.strip().lower() in ["exit", "quit"]:
            break
        answer = chatbot_ask(user_id, question)
        print("Bot:", answer)
    # After chat, print the chat history for this user
    print("\n--- Chat History ---")
    history = get_chat_history(user_id, limit=100)
    for msg in history:
        print(f"{msg['role'].capitalize()}: {msg['message']}") 