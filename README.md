# ReFocused Backend

:)

## Study Set API Endpoints

The study set API allows users to manage their flashcards and study sets. All endpoints require authentication via JWT token.

### Endpoints

1. **Get All Study Sets** 
   - `GET /api/v1/study/sets`
   - Returns all study sets belonging to the authenticated user

2. **Get Study Set by ID**
   - `GET /api/v1/study/sets/{study_set_id}`
   - Returns a specific study set by ID if owned by the authenticated user

3. **Create/Update Study Set**
   - `POST /api/v1/study/sets`
   - Creates a new study set or updates an existing one
   - Request body must contain title and flashcards array
   - To update an existing set, include the set ID in the request

4. **Bulk Create/Update Study Sets**
   - `POST /api/v1/study/sets/bulk`
   - Creates or updates multiple study sets in a single request
   - Request body must contain an array of study sets

5. **Delete Study Set**
   - `DELETE /api/v1/study/sets/{study_set_id}`
   - Deletes a study set and all its flashcards
   - Returns 204 No Content on success

### Security Features

- All endpoints are protected by authentication
- Each study set is associated with a specific user
- Users can only access and modify their own study sets
- Rate limiting is applied to prevent abuse
- All actions are logged for security purposes
