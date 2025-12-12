# API Documentation

## Using the API with Authentication

You need to generate an API key in your account settings, and add it in the request header (`"Authorization: Bearer YOUR_API_KEY"`).

## Example: Adding a Subscriber

**Endpoint:** `PUT /api/v1/lists/{list_id}/subscribers`

**Request:**
```json
{
  "email": "user@example.com",
  "name": "John Doe",
  "comment": "Subscribed at conference 2025"
}
```

**Response (201 Created):**
```json
{
  "message": "Subscriber user@example.com added successfully to list announcements"
}
```

### Using curl

```bash
# Add a subscriber
curl -X PUT "https://lists.example.com/api/v1/lists/announcements/subscribers" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "name": "John Doe",
    "comment": "Optional comment"
  }'
```
