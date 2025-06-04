from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.response import Response
from rest_framework import status, views, generics, permissions
from .serializers import RegisterSerializer, LoginSerializer, UserSerializer
from rest_framework.parsers import MultiPartParser, FormParser
from .llama_utils import *
from jsonschema import validate, ValidationError
import pdfplumber
from PIL import Image
import pytesseract
import io
from .models import User
from .crypt import encrypt_with_fingerprint

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

    def extract_file(self, file_obj):
        file_name = file_obj.name
        file_text = ""

        if file_name.endswith(".pdf"):
            with pdfplumber.open(file_obj) as pdf:
                file_text = "\n".join([page.extract_text() or "" for page in pdf.pages])
        elif file_name.endswith(('.jpg', '.jpeg', '.png')):
            image = Image.open(file_obj)
            file_text = pytesseract.image_to_string(image)
        else:
            raise ValueError("Unsupported file type. Only PDF and image files are supported.")

        if not file_text.strip():
            raise ValueError("Failed to extract text from file.")

        return file_text

    def post(self, request, format=None):
        file_obj = request.FILES.get('file_obj')
        try:
            extracted_text = self.extract_file(file_obj)
        except ValueError as ve:
            return Response({'error': str(ve)}, status=400)
        except Exception as e:
            print(e)
            return Response({'error': f'Text extraction failed: {str(e)}'}, status=500)

        user_id = request.data.get('user_id')
        document_type = request.data.get('document_type').upper()
        ALLOWED_DOC_TYPES = ['DD214', 'JST', 'DD2586']

        if not file_obj or not user_id or not document_type:
            return Response({'error': 'Missing required fields.'}, status=status.HTTP_400_BAD_REQUEST)
        if document_type not in ALLOWED_DOC_TYPES:
            return Response({'error': 'Invalid document_type.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(request.FILES) != 1:
            return Response({'error': 'You must upload exactly one file.'}, status=status.HTTP_400_BAD_REQUEST)

        file_name = file_obj.name

        # Load the document schema
        schema_path = settings.SCHEMA_PATHS[document_type]
        try:
            with open(schema_path, 'r') as f:
                form_schema = json.load(f)
        except Exception as e:
            return Response({'error': f'Failed to load schema: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Build LLM prompt
        prompt = (
            f"You are an expert in extracting structured data from U.S. military documents.\n"
            f"The user has uploaded a {document_type} file named '{file_name}'.\n"
            f"Using the extracted text below,:\n\n"
            f"`form_data`: Match the structure defined by this JSON schema:\n{json.dumps(form_schema, indent=2)}\n\n"
            f"Respond ONLY with a valid JSON object, wrapped between special tokens:\n"
            f"Start your output with `[[[JSON]]]` and end it with `[[[/JSON]]]`.\n"
            f"Do not include any explanations or text outside the tokens.\n"
            f"The expected structure is:\n"
            f"[[[JSON]]]\n{{\n  \"form_data\": {{ ... }}}}\n[[[/JSON]]]\n\n"
            f"----- BEGIN EXTRACTED TEXT -----\n{extracted_text[:10000]}\n----- END EXTRACTED TEXT -----"
        )



        # Prepare payload for Groq API
        data = {
            "model": "meta-llama/llama-4-scout-17b-16e-instruct",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant that extracts structured data from military documents and infers user profile data."},
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
            try:
                extracted_data = json.loads(content)
                extracted_data["fingerprint"] = User.objects.get(id=user_id).fingerprint
            except json.JSONDecodeError:
                import re
                match = re.search(r'\[\[\[JSON\]\]\](.*?)\[\[\[/JSON\]\]\]', content, re.DOTALL)
                if not match:
                    raise ValueError("Special JSON markers not found in LLaMA response.")

                extracted_data = json.loads(match.group(1).strip())
                extracted_data["fingerprint"] = User.objects.get(id=user_id).fingerprint


        except Exception as e:
            return Response({'error': f'LLama extraction failed: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # # Enrich and validate form_data
        # form_data = extracted_data
        # form_data = enrich_mos_codes(document_type, form_data)
        # profile_summary = generate_profile_summary(form_data)
        # form_data['profile_summary'] = profile_summary

        # try:
        #     validate(instance=form_data, schema=form_schema)
        # except ValidationError as ve:
        #     return Response({'error': f'Schema validation failed: {ve.message}'}, status=status.HTTP_400_BAD_REQUEST)

        # # Insert to MongoDB
        # try:
        #     form_data['user_id'] = user_id
        #     form_data['document_type'] = document_type
        #     insert_document(document_type, form_data)
        # except Exception as e:
        #     return Response({'error': f'MongoDB insert failed: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # # Return combined data
        # form_data.pop('profile_summary', None)
        return Response(extracted_data, status=status.HTTP_200_OK)


class UpdateUserData(views.APIView):
    def post(self, request, *args, **kwargs):
        form_data = request.data.get("form_data")
        fingerprint = request.data.get("fingerprint")

        if form_data:
            try:
                encrypted_form_data = encrypt_with_fingerprint(form_data, fingerprint)

                client = MongoClient(settings.MONGO_URI)()
                db = client[settings.MONGO_DB_NAME]
                db["user_data"].insert_one(encrypted_form_data)
            except Exception as e:
                return Response({"error": f"Failed to save form data: {str(e)}"}, status=500)

        return Response({
            "message": "User data saved successfully.",
        }, status=200)