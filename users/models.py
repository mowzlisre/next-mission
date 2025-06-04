from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from django.utils import timezone
import hashlib

EMPLOYMENT_CHOICES = [
    ('employed', 'Employed'),
    ('unemployed', 'Unemployed'),
    ('student', 'Student'),
    ('retired', 'Retired'),
]

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    employment_status = models.CharField(max_length=20, choices=EMPLOYMENT_CHOICES, blank=True)
    interests = models.TextField(blank=True)
    onboarded = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name", "date_of_birth", "city", "state"]

    fingerprint = models.CharField(max_length=64, editable=False, blank=True)

    objects = UserManager()

    def __str__(self):
        return self.email
    
    def generate_fingerprint(self) -> str:
        """
        Generate a unique fingerprint hash from a list of user-specific strings.
        """
        user_data = [self.first_name, self.last_name, self.city, self.state, self.date_of_birth.isoformat()]
        combined = "|".join(sorted(user_data))  # Ensure consistent order
        fingerprint = hashlib.sha256(combined.encode()).hexdigest()
        return fingerprint
    
    def save(self, *args, **kwargs):
        self.fingerprint = self.generate_fingerprint()
        super().save(*args, **kwargs)
