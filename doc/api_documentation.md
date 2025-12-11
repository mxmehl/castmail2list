# API Documentation

## Accessing Swagger UI

Once the application is running, you can access the interactive API documentation at:

```
http://localhost:<port>/api/docs/
```

For example, if running on port 2278:
```
http://localhost:2278/api/docs/
```

## Features

The Swagger UI provides:

- **Interactive testing** - Try out API endpoints directly from the browser
- **Request/response examples** - See what data to send and expect
- **Authentication** - Test with your API key using the "Authorize" button
- **Complete documentation** - All endpoints, parameters, and responses

## Using the API with Authentication

1. Click the **"Authorize"** button in the Swagger UI
2. Enter your API key (see account settings) in the format: `Bearer YOUR_API_KEY`
3. Click "Authorize" to save
4. Now you can test authenticated endpoints

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

## Using curl

```bash
# Add a subscriber
curl -X PUT "http://localhost:2278/api/v1/lists/announcements/subscribers" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "name": "John Doe",
    "comment": "Optional comment"
  }'
```

## Documentation Format

The API documentation is generated from:
- **Route docstrings** - YAML-formatted Swagger specs in function docstrings
- **Automatic discovery** - Only routes under `/api/v1` are documented
- **OpenAPI 2.0** - Standard format, compatible with many tools

## Adding Documentation to New Endpoints

Add a docstring to route function with YAML Swagger specification:

```python
@api1.route("/your/route", methods=["GET"])
@api_auth_required
def your_route():
    """Short description
    Longer description here
    ---
    tags:
      - YourTag
    parameters:
      - name: param_name
        in: path
        type: string
        required: true
        description: Parameter description
    security:
      - Bearer: []
    responses:
      200:
        description: Success response
        schema:
          type: object
          properties:
            result:
              type: string
    """
    # Code here
```
