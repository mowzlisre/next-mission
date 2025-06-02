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