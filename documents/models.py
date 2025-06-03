from django.db import models
from django.conf import settings
from pymongo import MongoClient
import os

# Create your models here.

# MongoDB connection setup using environment variables
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
MONGO_DB_NAME = os.getenv('MONGO_DB_NAME', 'veteran_docs')

client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]

def insert_document(collection_name, document):
    """
    Insert a document into the specified MongoDB collection.
    """
    collection = db[collection_name]
    result = collection.insert_one(document)
    return result.inserted_id
