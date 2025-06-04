from django.urls import path
from .api import RegisterView, LoginView, LogoutView, DocumentUploadView, UpdateUserData
urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('onboard/doc/upload', DocumentUploadView.as_view(), name='document-upload'),
    path('update/user/data', UpdateUserData.as_view())
]