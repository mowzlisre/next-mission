from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.response import Response
from rest_framework import status, views, generics, permissions
from .serializers import RegisterSerializer, LoginSerializer, UserSerializer
from rest_framework.parsers import MultiPartParser, FormParser
from .llama_utils import *
from jsonschema import validate, ValidationError

class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer

class LoginView(views.APIView):
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        })

class LogoutView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data["refresh"]
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(status=status.HTTP_205_RESET_CONTENT)
        except Exception:
            return Response(status=status.HTTP_400_BAD_REQUEST)

class DocumentUploadView(views.APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, format=None):
        file_obj = request.FILES.get('file_obj')
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
        schema_path = settings.SCHEMA_PATHS[document_type]
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
            'Authorization': f'Bearer {settings.GROQ_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        try:
            llama_response = requests.post(settings.GROQ_API_URL, json=data, headers=headers)
            llama_response.raise_for_status()
            result = llama_response.json()
            content = result["choices"][0]["message"]["content"]
            if settings.DEBUG:
                print("Raw LLaMA output:", content)
            # Improved JSON parsing
            try:
                extracted_data = json.loads(content)
            except json.JSONDecodeError:
                import re
                match = re.search(r'(\{(?:[^{}]|(?1))*\})', content, re.DOTALL)
                if match:
                    extracted_data = json.loads(match.group(0))
                else:
                    import ast
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