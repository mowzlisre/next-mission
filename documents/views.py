from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from .models import insert_document
import requests
import os
from dotenv import load_dotenv
import json
from jsonschema import validate, ValidationError
import glob

# Load environment variables
load_dotenv()
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
GROQ_API_URL = os.getenv('GROQ_API_URL', 'https://api.groq.com/v1/llama-extract')  # Example endpoint

# Map document types to schema file paths
SCHEMA_PATHS = {
    'DD214': 'schemas/dd214.schema.json',
    'JST': 'schemas/jst.schema.json',
    'DD2586': 'schemas/dd2586.schema.json',
}

# Helper to load MOS data for all services
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
    service = document_type.lower().replace(' ', '_')  # crude mapping
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
    headers = {'Authorization': f'Bearer {GROQ_API_KEY}', 'Content-Type': 'application/json'}
    data = {
        "model": "meta-llama/llama-4-scout-17b-16e-instruct",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that summarizes veteran profiles for civilian use."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 512
    }
    GROQ_API_URL = 'https://api.groq.com/openai/v1/chat/completions'
    try:
        response = requests.post(GROQ_API_URL, json=data, headers=headers)
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        return content.strip()
    except Exception as e:
        return f"[Error generating profile summary: {str(e)}]"

# Create your views here.

class DocumentUploadView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, format=None):
        file_obj = request.FILES.get('file')
        user_id = request.data.get('user_id')
        document_type = request.data.get('document_type')
        ALLOWED_DOC_TYPES = ['DD214', 'JST', 'DD2586']

        if not file_obj or not user_id or not document_type:
            return Response({'error': 'Missing required fields.'}, status=status.HTTP_400_BAD_REQUEST)
        if document_type not in ALLOWED_DOC_TYPES:
            return Response({'error': 'Invalid document_type.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(request.FILES) != 1:
            return Response({'error': 'You must upload exactly one file.'}, status=status.HTTP_400_BAD_REQUEST)

        # Read file content as base64 for Llama prompt
        import base64
        file_content = base64.b64encode(file_obj.read()).decode('utf-8')
        file_name = file_obj.name

        # Build prompt for Llama
        prompt = (
            f"You are an expert at extracting structured data from U.S. military documents. "
            f"The user has uploaded a {document_type} file named '{file_name}'. "
            f"Extract all relevant fields as per the following JSON schema: "
        )
        schema_path = SCHEMA_PATHS[document_type]
        try:
            with open(schema_path, 'r') as f:
                schema = json.load(f)
        except Exception as e:
            return Response({'error': f'Failed to load schema: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        prompt += json.dumps(schema, indent=2)
        prompt += (f"\nReturn the extracted data as a JSON object. "
                   f"If a field is missing, use null. "
                   f"If there are MOS codes, include them as a list of objects with code, title, and description if possible.\n"
                   f"The file content is base64-encoded below.\nFILE_BASE64:\n{file_content}")

        # Prepare OpenAI-compatible payload
        data = {
            "model": "meta-llama/llama-4-scout-17b-16e-instruct",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant that extracts structured data from military documents."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 2048
        }
        headers = {
            'Authorization': f'Bearer {GROQ_API_KEY}',
            'Content-Type': 'application/json'
        }
        GROQ_API_URL = 'https://api.groq.com/openai/v1/chat/completions'

        # Call Groq API (Llama 4)
        try:
            llama_response = requests.post(GROQ_API_URL, json=data, headers=headers)
            llama_response.raise_for_status()
            result = llama_response.json()
            # Try to parse the JSON from the assistant's message
            import re
            import ast
            content = result["choices"][0]["message"]["content"]
            # Try to extract JSON from the response
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                extracted_data = json.loads(match.group(0))
            else:
                # fallback: try ast.literal_eval
                extracted_data = ast.literal_eval(content)
        except Exception as e:
            return Response({'error': f'LLama extraction failed: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Enrich MOS codes
        extracted_data = enrich_mos_codes(document_type, extracted_data)

        # Generate profile summary (backend only)
        profile_summary = generate_profile_summary(extracted_data)
        extracted_data['profile_summary'] = profile_summary

        # Validate extracted data
        try:
            validate(instance=extracted_data, schema=schema)
        except ValidationError as ve:
            return Response({'error': f'Schema validation failed: {ve.message}'}, status=status.HTTP_400_BAD_REQUEST)

        # Insert into MongoDB
        try:
            collection_name = document_type.lower()  # e.g., 'dd214', 'jst', 'dd2586'
            extracted_data['user_id'] = user_id
            extracted_data['document_type'] = document_type
            inserted_id = insert_document(collection_name, extracted_data)
        except Exception as e:
            return Response({'error': f'MongoDB insert failed: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Remove profile_summary before sending to frontend
        extracted_data.pop('profile_summary', None)

        return Response({'message': 'File processed and data extracted.', 'data': extracted_data}, status=status.HTTP_200_OK)
