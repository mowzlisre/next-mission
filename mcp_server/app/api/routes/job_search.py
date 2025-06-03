from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from app.services.linkedin_service import LinkedInService
from app.config import settings
from datetime import datetime

router = APIRouter()
linkedin_service = LinkedInService(settings.SERPAPI_KEY)

class JobSearchRequest(BaseModel):
    skills: List[str]
    job_roles: Optional[List[str]] = None
    location: Optional[str] = None
    experience_level: Optional[str] = None
    max_results: Optional[int] = 10

class JobListing(BaseModel):
    title: str
    company: str
    location: str
    description: str
    url: str
    posted_date: Optional[str]
    salary: Optional[str]

# Dummy profile for demonstration (replace with DB lookup in production)
dummy_profile = {
    'user_id': 'test_user_1',
    'document_type': 'DD214',
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
            'source': 'DD214'
        }
    ],
    'awards': [
        {
            'name': 'Army Achievement Medal',
            'date_awarded': '2015-05-01',
            'description': 'For meritorious service',
            'source': 'DD214'
        }
    ],
    'training_courses': [
        {
            'name': 'Basic Combat Training',
            'description': 'Initial entry training',
            'completion_date': '2010-03-01',
            'source': 'DD214'
        }
    ],
    'profile_summary': 'Jane Doe served 10 years as an Infantryman (MOS 11B) in the Army. She is eligible for a range of veteran benefits and has strong leadership and tactical skills.'
}

@router.post("/search", response_model=List[JobListing])
async def search_jobs(request: JobSearchRequest):
    try:
        results = await linkedin_service.search_jobs(
            skills=request.skills,
            job_roles=request.job_roles,
            location=request.location,
            experience_level=request.experience_level,
            max_results=request.max_results
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def health_check():
    return {"status": "healthy"}

@router.get("/by_profile", response_model=List[JobListing])
async def jobs_by_profile():
    # In production, load the user profile from DB using user_id (e.g., from JWT or query param)
    profile = dummy_profile
    # Extract skills and job roles from profile
    skills = [mos['title'] for mos in profile.get('mos_history', [])]
    job_roles = skills  # For demo, use MOS titles as job roles
    location = "United States"  # Default location; in production, use user preference or profile
    experience_level = None  # Could be inferred from pay_grade or years of service
    max_results = 5
    try:
        results = await linkedin_service.search_jobs(
            skills=skills,
            job_roles=job_roles,
            location=location,
            experience_level=experience_level,
            max_results=max_results
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 