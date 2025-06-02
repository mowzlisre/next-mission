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
  "password": "your_password"
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



# 🧵 Forum API – Usage Guide

This API supports posting content, reacting to posts with emojis, adding comments, and replying to comments (1 level only).

---

## 📌 Base URL

```
/posts/
```

---

## 📄 Create a Post

**Endpoint:**

```
POST /posts/
```

**Headers:**

```
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Body:**

```json
{
  "content": "My first post",
  "image": null
}
```

---

## 🔁 React to a Post

**Endpoint:**

```
POST /posts/<post_id>/react/
```

**Body:**

```json
{
  "type": "love"
}
```

Available reactions:
- `like`
- `love`
- `laugh`
- `sad`
- `angry`

> One reaction per user per post — submitting again will update the existing one.

---

## 💬 Add Comment to Post

**Endpoint:**

```
POST /posts/<post_id>/comments/
```

**Body:**

```json
{
  "content": "Nice post!"
}
```

---

## 💬 Reply to a Comment (1-Level Only)

**Endpoint:**

```
POST /comments/<comment_id>/replies/
```

**Body:**

```json
{
  "content": "Totally agree!"
}
```

> Replies can only be made to comments. Replies **cannot** have replies.

---

## 👀 Get a Single Post (with Top 2 Comments)

**Endpoint:**

```
GET /posts/<post_id>/
```

**Returns:**

- Post content
- Reactions summary
- Top 2 latest comments
  - With replies

---

## 📄 Get All Comments for a Post (Paginated)

**Endpoint:**

```
GET /posts/<post_id>/comments/all/?page=1&page_size=10
```

**Returns:**

```json
{
  "count": 23,
  "next": "...",
  "previous": null,
  "results": [
    {
      "id": 1,
      "author_email": "user@example.com",
      "content": "Nice post!",
      "created_at": "...",
      "replies": [
        {
          "id": 5,
          "author_email": "another@example.com",
          "content": "I agree!"
        }
      ]
    }
  ]
}
```

---

## 🧠 Notes

- All endpoints require authentication.
- Only the author of a post/comment should be allowed to edit/delete (not yet implemented).
- Pagination default is 10 items per page; override with `?page_size=` query param.

