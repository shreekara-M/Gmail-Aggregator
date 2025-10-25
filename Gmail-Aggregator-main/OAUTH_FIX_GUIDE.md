# OAuth Fix Guide for Render Deployment

## Problem
The application works locally but fails on Render with "Error adding account: (invalid_client) Unauthorized" when users try to add their Gmail accounts.

## Root Cause
The issue occurs because:
1. **OAuth Flow Type**: The code was using `InstalledAppFlow` which is for desktop apps, not web apps
2. **Redirect URI Mismatch**: Dynamic redirect URIs don't work with Google OAuth in production
3. **Missing Environment Variables**: Production OAuth credentials weren't properly configured

## Solution

### 1. Code Changes Made

#### Updated OAuth Flow
- Changed from `InstalledAppFlow` to `Flow` (web application flow)
- Added proper redirect URI handling for production
- Added session management for OAuth state security

#### Key Changes in `app.py`:
```python
# Before (Desktop App Flow)
from google_auth_oauthlib.flow import InstalledAppFlow
flow = InstalledAppFlow.from_client_config(credentials, SCOPES)

# After (Web App Flow)
from google_auth_oauthlib.flow import Flow
flow = Flow.from_client_config(credentials, SCOPES)
```

### 2. Environment Variables Setup

#### For Local Development (.env file):
```env
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:5000/oauth2callback
SECRET_KEY=your-secret-key
```

#### For Production (Render Dashboard):
1. Go to your Render service dashboard
2. Navigate to "Environment" tab
3. Add these environment variables:
   - `GOOGLE_CLIENT_ID`: Your Google OAuth Client ID
   - `GOOGLE_CLIENT_SECRET`: Your Google OAuth Client Secret
   - `GOOGLE_REDIRECT_URI`: `https://your-app-name.onrender.com/oauth2callback`
   - `SECRET_KEY`: A random secret key for session management

### 3. Google Cloud Console Configuration

#### Step 1: Update OAuth Credentials
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to "APIs & Services" > "Credentials"
3. Find your OAuth 2.0 Client ID
4. Click "Edit" (pencil icon)

#### Step 2: Update Authorized Redirect URIs
Add these URIs to your OAuth client:
- `https://your-app-name.onrender.com/oauth2callback`
- `https://your-app-name.onrender.com/` (for the main app)

#### Step 3: Verify Application Type
- Make sure your OAuth client is configured as "Web application"
- NOT "Desktop application"

### 4. Deployment Steps

#### Step 1: Update Your Code
1. Pull the latest changes from your repository
2. The code has been updated to use the proper web OAuth flow

#### Step 2: Configure Environment Variables
1. In Render dashboard, go to your service
2. Navigate to "Environment" tab
3. Add the required environment variables (see section 2)

#### Step 3: Redeploy
1. Trigger a new deployment in Render
2. Wait for the deployment to complete

#### Step 4: Test
1. Visit your deployed app
2. Click "Add User"
3. Complete the OAuth flow
4. Verify the user is added successfully

### 5. Troubleshooting

#### If you still get "invalid_client" error:
1. **Check Redirect URI**: Ensure the redirect URI in Google Console exactly matches your Render URL
2. **Verify Environment Variables**: Make sure all OAuth environment variables are set in Render
3. **Check OAuth Client Type**: Ensure it's configured as "Web application" not "Desktop application"

#### If you get "redirect_uri_mismatch" error:
1. Double-check the redirect URI in Google Console
2. Make sure there are no trailing slashes or extra characters
3. The URI should be exactly: `https://your-app-name.onrender.com/oauth2callback`

#### If the app doesn't start:
1. Check Render logs for any startup errors
2. Verify all environment variables are set
3. Ensure the `SECRET_KEY` is set (required for sessions)

### 6. Security Notes

1. **SECRET_KEY**: Use a strong, random secret key in production
2. **OAuth Credentials**: Keep your client secret secure
3. **HTTPS**: Render provides HTTPS automatically, which is required for OAuth

### 7. Testing Checklist

- [ ] App starts successfully on Render
- [ ] "Add User" button works
- [ ] OAuth flow completes without errors
- [ ] User email is displayed after authentication
- [ ] Emails can be fetched for authenticated users

## Additional Resources

- [Google OAuth 2.0 Documentation](https://developers.google.com/identity/protocols/oauth2)
- [Render Environment Variables](https://render.com/docs/environment-variables)
- [Flask Sessions](https://flask.palletsprojects.com/en/2.0.x/quickstart/#sessions)
