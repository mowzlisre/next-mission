import os
import glob
import json
from django.conf import settings
import requests
from pymongo import MongoClient

client = MongoClient(settings.MONGO_URI)
db_veteran = client['veteran_docs']

def insert_document(collection_name, document):
    """
    Insert a document into the specified MongoDB collection.
    """
    collection = db_veteran[collection_name]
    result = collection.insert_one(document)
    return result.inserted_id


MOS_DATA = {}
def load_all_mos_data():
    global MOS_DATA
    mos_dir = os.path.join(os.path.dirname(__file__), 'mos_data')
    for path in glob.glob(os.path.join(mos_dir, '*_mos.json')):
        service = os.path.basename(path).split('_')[0]
        with open(path, 'r') as f:
            MOS_DATA[service] = {item['code']: item for item in json.load(f)}
load_all_mos_data()

def enrich_mos_codes(document_type, extracted_data):
    # Try to enrich MOS codes in the extracted data
    service = document_type.replace(' ', '_')  # crude mapping
    mos_list = extracted_data.get('mos_history', [])
    if service in MOS_DATA:
        for mos in mos_list:
            code = mos.get('code')
            if code and code in MOS_DATA[service]:
                mos_info = MOS_DATA[service][code]
                mos['title'] = mos_info.get('title', mos.get('title'))
                mos['description'] = mos_info.get('description', '')
    return extracted_data

def generate_profile_summary(extracted_data):
    mos_descriptions = []
    for mos in extracted_data.get('mos_history', []):
        desc = mos.get('description')
        if desc:
            mos_descriptions.append(f"{mos.get('code', '')}: {desc}")
    mos_desc_text = '\n'.join(mos_descriptions)
    prompt = (
        "You are an expert at summarizing U.S. military veterans' experience for civilian audiences. "
        "Given the following extracted profile data and MOS code descriptions, write a detailed profile summary. "
        "The summary should highlight the veteran's skills, experience, and potential civilian career paths. "
        "Include a list of skills based on the MOS descriptions.\n\n"
        f"Extracted Data (JSON):\n{json.dumps(extracted_data, indent=2)}\n\n"
        f"MOS Code Descriptions:\n{mos_desc_text}\n\n"
        "Profile Summary:"
    )
    headers = {'Authorization': f'Bearer {settings.GROQ_API_KEY}', 'Content-Type': 'application/json'}
    data = {
        "model": "meta-llama/llama-4-scout-17b-16e-instruct",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that summarizes veteran profiles for civilian use."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 512
    }

    try:
        response = requests.post(settings.GROQ_API_URL, json=data, headers=headers)
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        return content.strip()
    except Exception as e:
        return f"[Error generating profile summary: {str(e)}]"