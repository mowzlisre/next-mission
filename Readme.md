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


# 🧵 Forum API – Base URL

```
/api/v1/forum/
```

---

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


