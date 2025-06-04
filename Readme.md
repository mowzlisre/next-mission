### Base Url
- http://10.75.254.124:9005/

### Base routes
- For Application API - baseUrl/api/v1/*
- For Authentication API - baseUrl/api/auth/*

### Login
**POST** `baseUrl/api/auth/login/`

```json
{
  "email": "user@example.com",
  "password": "your_password"
}
```
test
- email: test@test.com
- password: pass

Response

```json
{
  "access": "ACCESS_TOKEN",
  "refresh": "REFRESH_TOKEN"
}
```

save the access and refresh token in browser session or local storage. Use it later as Bearer in Authorization header for every API requests Eg:

Authorization: Bearer ACCESS_TOKEN

### Registration
**POST** 'baseUrl/api/auth/register

```json
{
  "email": "user@example.com",
  "first_name": "John",
  "last_name": "Doe",
  "password": "your_password",
  "city" : "city",
  "state" : "state",
  "date_of_birth" : "YYYY-MM-DD",
}
```

all fields are mandatory

does not return anything except status code. 

### Refresh JWT
**POST** 'baseUrl/api/auth/token/refresh

```json
{
  "refresh": "REFRESH_TOKEN"
}
```

Send the refresh token to get a new token. Old token is blacklisted by default

Response
```json
{
  "access": "NEW_ACCESS_TOKEN"
}
```

Save the new access token. Do not replace the refresh token. When refresh token expires, user will be logged out. New authentication will give new tokens to the user


### Logout
**POST** 'baseUrl/api/auth/logout

Make sure the access token is in Bearer of Authrization Header with refresh token in the body. This will blacklist and prevent further request from the same token.


# 🧵 Forum API – Base URL

```
/api/v1/forum/
```

---

### 📝 Create a Post

**POST** `/api/v1/forum/create/`

Creates a new post with optional image upload.

**Headers:**
- `Authorization: Bearer <access_token>`
- `Content-Type: multipart/form-data`

**Body:**
- `content` (string, required) – Post text
- `image` (file, optional) – Image file to attach

**Example Request (form-data):**
```
content=This is my new post!
image=[optional file upload]
```

**Response:**
```json
{
  "id": 12,
  "content": "This is my new post!",
  "image": "http://localhost:8000/media/post_images/photo.jpg",
  "created_at": "2025-06-02T15:12:00Z",
  "author_email": "john@example.com",
  "author_first_name": "John",
  "author_last_name": "Doe",
  "reactions": {},
  "reaction_count": 0,
  "comment_count": 0,
  "comments": []
}
```

**Notes:**
- You must be authenticated.
- Image is optional.
- Returns full post object including author and reaction/comment summaries.

## 📄 Fetch All Posts

**GET** `/api/v1/forum/`

Returns all posts (latest first).

---

## 📄 Fetch a Specific Post

**GET** `/api/v1/forum/<post_id>/`

Returns:
- Post details
- Reaction summary
- Top 2 comments (each with replies)

---

## 💬 Get All Comments for a Post (Paginated)

**GET** `/api/v1/forum/<post_id>/comments/all/?page=1&page_size=10`

Returns:
- All comments for the post
- Each comment includes flat replies

---

## 👍 React to a Post

**POST** `/api/v1/forum/<post_id>/react/`

**Body:**
```json
{
  "type": "like"  // Options: like, love, laugh, sad, angry
}
```

---

## 💬 Comment on a Post

**POST** `/api/v1/forum/<post_id>/comments/`

**Body:**
```json
{
  "content": "Great post!"
}
```

---

## 💬 Reply to a Comment (1-Level Only)

**POST** `/api/v1/forum/comments/<comment_id>/replies/`

**Body:**
```json
{
  "content": "Agreed!"
}
```

⚠️ Replies can only be added to **comments**, not to other replies.

---

## 🚫 Reply to a Reply (Not Allowed)

There is **no endpoint** to reply to a reply.

If attempted:

```
POST /api/v1/forum/comments/<reply_id>/replies/
```

→ This should return a 400 or custom error like:
```json
{
  "error": "Cannot reply to a reply. Only one reply level is allowed."
}
```


```markdown


# Document Upload API

**Endpoint:** `/api/auth/onboard/doc/upload`  
**Method:** `POST`  
**Content-Type:** `multipart/form-data`  
**Authentication:** Not required (unless you apply permission classes)

## Description

Uploads a single military document (PDF or image), performs OCR if needed, and extracts structured data using the Groq LLaMA model. The response contains two structured data objects:

- `form_data`: Extracted from the document, structured by its official schema (DD214, JST, or DD2586)
- `user_data`: Extracted user profile info inferred from the document, shaped according to your `User` model

## Request Fields

| Field          | Type       | Required | Description                          |
|----------------|------------|----------|--------------------------------------|
| `file_obj`     | `file`     | Yes      | PDF or image of the military document |
| `user_id`      | `string`   | Yes      | ID of the user uploading the document |
| `document_type`| `string`   | Yes      | One of: `DD214`, `JST`, `DD2586`     |

## Supported File Types

- `.pdf`
- `.jpg`
- `.jpeg`
- `.png`

## Notes

- Only one file should be uploaded at a time.
- File text is extracted using `pdfplumber` for PDFs and `pytesseract` for images.
- Text is passed to the LLM which returns structured JSON wrapped between `[[[JSON]]]` and `[[[/JSON]]]` markers.
- The response includes only the structured `user_data` and `form_data` extracted from the document.
```

## Endpoint
`POST /api/auth/update/user/data/`

## Description
This endpoint receives user form data along with a fingerprint, encrypts the data using the provided fingerprint, and stores the result in a MongoDB collection named `user_data`.

---

## Request

### Headers
- `Content-Type: application/json`

### Body Parameters

| Name         | Type   | Required | Description                             |
|--------------|--------|----------|-----------------------------------------|
| form_data    | object | Yes      | The form data object to be encrypted and stored. |
| fingerprint  | string | Yes      | A unique string used to encrypt the form data. |

#### Example
```json
{
  "form_data": {
    "name": "John Doe",
    "email": "john@example.com",
    "age": 30
  },
  "fingerprint": "unique-device-identifier"
}
```

### FetchRelJobs API

**Endpoint:** `/api/v1/jobs/all/`  
**Method:** `GET`  
**Authentication:** Required (Token or Session-based)  
**Permissions:** `IsAuthenticated`

---

*** Use this to show all the current available jobs ***

## 📄 Description

Fetch all job postings that have been matched and cached for the currently authenticated user, based on their unique fingerprint.

This endpoint queries the `cache_db` MongoDB collection and returns all job documents associated with the user's fingerprint.

---

## 🔐 Authentication

This endpoint requires the user to be authenticated. The user's fingerprint must be stored in the user model as `user.fingerprint`.

---

## 📥 Request

**GET** `/api/v1/jobs/fetch-related/`

### Headers

| Key            | Value                  |
|----------------|------------------------|
| Authorization  | `Bearer <access_token>` |

---

## ✅ Successful Response

**Code:** `200 OK`  
**Content:**  
Returns a JSON array of job objects with the following sample fields:

```json
[
  {
    "company_name": "Acme Inc",
    "job_title": "Operations Analyst",
    "location": "Remote",
    "job_tags": ["Veteran", "Operations", "Leadership"],
    "posted_time": "2 days ago",
    "applicants": 45,
    "salary": "$85,000 - $95,000",
    "employment_type": "Full-time",
    "work_mode": "Remote",
    "url": "https://linkedin.com/jobs/view/123456",
    "description": "Responsible for...",
    "matching_score": 87,
    "matching_label": "GOOD MATCH",
    "scraped_at": "2025-06-04T15:24:18.000Z",
    "fingerprint": "user-abc-123"
  }
]
```

### FetchNew API

**Endpoint:** `/api/v1/jobs/search/`  
**Method:** `GET`  
**Authentication:** Required (Token or Session-based)  
**Permissions:** `IsAuthenticated`

*** Use this to update the mongodb with new jobs ***
*** Make sure to append the data from this to the jobs array in localstorage or call the FetchRelJobs API for updated list ***


# Veteran BioData API

This module provides two endpoints for generating and exporting enriched bio-data for U.S. military veterans.

---

## 🔹 Endpoint 1: Generate BioData (JSON)

### `POST /api/v1/veteran/biodata/`

Generates an enriched civilian-friendly bio using a large language model and stores the result in MongoDB.

### 🔐 Authentication
Requires a valid JWT token (`IsAuthenticated` permission class).

### 🧾 Request Body
None — uses the logged-in user's fingerprint to retrieve their profile from `user_data` MongoDB collection.

### 🔍 Flow
1. Fetches user document from `user_data` based on `fingerprint`.
2. Sends the profile to LLaMA with a structured prompt to:
   - Translate military experience into civilian terms
   - Produce a complete resume-like JSON structure
3. Saves the generated data into the `bio_data` collection with the user's fingerprint.
4. Returns the enriched JSON.

### ✅ JSON Output Structure
```json
{
  "full_name": "John Doe",
  "headline": "Operations Manager | Logistics & Strategy",
  "summary": "John is a seasoned professional with over 10 years of experience...",
  "skills": ["Logistics", "Leadership", "Strategic Planning", "Supply Chain"],
  "education": "B.S. in Business Administration, University of Texas",
  "experience_summary": "Over 10 years in operational and leadership roles...",
  "experience_details": [
    {
      "role": "Logistics Coordinator",
      "organization": "US Army",
      "duration": "2015–2020",
      "description": "Oversaw the movement of equipment and personnel across international bases..."
    }
  ],
  "achievements": ["Army Achievement Medal", "Improved supply chain efficiency by 30%"],
  "certifications": ["Project Management Professional (PMP)"],
  "volunteer_experience": "Mentor at Veterans in Tech"
}

```

# 📄 API: Download Veteran BioData as PDF

This endpoint returns a professionally formatted PDF resume based on a veteran's enriched bio-data.

---

## 📥 Endpoint

### `POST /api/v1/veteran/biodata/pdf/`

---

## 🔐 Authentication

- Required: ✅ Yes (`IsAuthenticated`)
- Type: Bearer Token / Session Auth

---

## 📨 Request

- **Method**: `POST`
- **Body**: None
- **Headers**:
  ```http
  Authorization: Bearer <your_token_here>
```

To handle the download use similar to below

```js
downloadPDF() {
  fetch("/api/v1/veteran/biodata/pdf/", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${this.authToken}` // Adjust with your actual token source
    }
  })
    .then(response => {
      if (!response.ok) {
        throw new Error("Failed to download PDF");
      }
      return response.blob();
    })
    .then(blob => {
      const blobUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = blobUrl;
      link.download = "veteran_biodata.pdf";
      document.body.appendChild(link);
      link.click();
      link.remove();
    })
    .catch(error => {
      console.error("Error downloading PDF:", error);
    });
}

```