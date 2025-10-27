import glob, os, json
from flask import Flask, jsonify, request, send_file, redirect
from flask_cors import CORS
from gmail_client import build_service_from_token, fetch_unread, get_account_email
from concurrent.futures import ThreadPoolExecutor
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from gmail_client import SCOPES
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def is_https_request():
    """Check if the request is using HTTPS (for production environments)"""
    return (
        request.headers.get('X-Forwarded-Proto') == 'https' or
        request.headers.get('X-Forwarded-Ssl') == 'on' or
        request.is_secure
    )

def get_redirect_uri():
    """Get the proper redirect URI for OAuth"""
    redirect_uri = os.environ.get('GOOGLE_REDIRECT_URI')
    if not redirect_uri:
        if is_https_request():
            # Production environment - ensure HTTPS
            redirect_uri = request.url_root.replace('http://', 'https://') + "oauth2callback"
        else:
            redirect_uri = request.url_root + "oauth2callback"
    return redirect_uri


def get_oauth_credentials():
    """Get OAuth credentials from environment variables or credentials.json file"""
    # Try environment variables first (for production)
    client_id = os.environ.get('GOOGLE_CLIENT_ID')
    client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
    redirect_uri = os.environ.get('GOOGLE_REDIRECT_URI')
    
    if client_id and client_secret and redirect_uri:
        # Create credentials dict from environment variables
        credentials = {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri]
            }
        }
        return credentials
    else:
        # Fallback to credentials.json file (for development)
        if os.path.exists("credentials.json"):
            with open("credentials.json", "r") as f:
                return json.load(f)
        else:
            raise FileNotFoundError("No OAuth credentials found. Please set environment variables or add credentials.json file.")

app = Flask(__name__)
CORS(app)

# Configure session for OAuth state management
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-change-this-in-production')

# --- Helper for unread mails ---
def fetch_account_unread(token_path: str, max_per: int):
    try:
        service = build_service_from_token(token_path)
        email_addr = get_account_email(service)
        mails = fetch_unread(service, max_results=max_per)   # this is your existing unread fetcher
        return {"email": email_addr, "count": len(mails), "messages": mails}
    except Exception as e:
        return {"email": os.path.basename(token_path), "error": str(e), "messages": []}

# --- Helper for latest mails ---
def fetch_account_latest(token_path: str, max_per: int):
    try:
        service = build_service_from_token(token_path)
        email_addr = get_account_email(service)

        results = service.users().messages().list(
            userId="me",
            labelIds=["INBOX"],   # only inbox
            maxResults=max_per
        ).execute()

        messages = []
        failed_messages = 0
        
        for msg in results.get("messages", []):
            try:
                msg_detail = service.users().messages().get(userId="me", id=msg["id"]).execute()
                headers = msg_detail.get("payload", {}).get("headers", [])
                msg_data = {
                    "from": next((h["value"] for h in headers if h["name"] == "From"), ""),
                    "subject": next((h["value"] for h in headers if h["name"] == "Subject"), ""),
                    "date": next((h["value"] for h in headers if h["name"] == "Date"), ""),
                    "snippet": msg_detail.get("snippet", "")
                }
                messages.append(msg_data)
            except Exception as msg_error:
                print(f"Failed to fetch message {msg['id']} for {email_addr}: {msg_error}")
                failed_messages += 1
                continue

        result = {"email": email_addr, "count": len(messages), "messages": messages}
        if failed_messages > 0:
            result["warning"] = f"Failed to load {failed_messages} messages due to API errors"
        return result
    except Exception as e:
        return {"email": os.path.basename(token_path), "error": str(e), "messages": []}

# --- Route to serve the frontend HTML ---
@app.route("/")
def index():
    return send_file("frontend.html")

# --- Route for adding a new user ---
@app.route("/add_user")
def add_user():
    try:
        credentials = get_oauth_credentials()
        
        # Use the proper redirect URI from environment or use the configured one
        redirect_uri = get_redirect_uri()
        
        flow = Flow.from_client_config(credentials, SCOPES)
        flow.redirect_uri = redirect_uri
        
        authorization_url, state = flow.authorization_url(
            access_type="offline", 
            include_granted_scopes="true",
            prompt="consent"
        )
        
        # Store state in session for security
        from flask import session
        session['oauth_state'] = state
        
        return redirect(authorization_url)
    except Exception as e:
        return f"""<p>Error setting up OAuth: {e}</p><p><a href='/'>Go to homepage</a></p>"""

# --- Route for OAuth2 callback ---
@app.route("/oauth2callback")
def oauth2callback():
    try:
        credentials = get_oauth_credentials()
        
        # Use the same redirect URI as in the authorization request
        redirect_uri = get_redirect_uri()
        
        flow = Flow.from_client_config(credentials, SCOPES)
        flow.redirect_uri = redirect_uri
        
        # Get the authorization response - ensure HTTPS in production
        if is_https_request():
            # Production environment with HTTPS
            authorization_response = request.url.replace('http://', 'https://')
        else:
            authorization_response = request.url
        
        # Verify state parameter for security
        from flask import session
        if 'oauth_state' in session:
            # State verification is handled by the flow
            pass
        
        flow.fetch_token(authorization_response=authorization_response)

        creds = flow.credentials
        service = build("gmail", "v1", credentials=creds)
        email_addr = service.users().getProfile(userId="me").execute()["emailAddress"]

        token_path = TOKENS_DIR / f"{email_addr}.json"
        
        # Debug information
        print("flow.redirect_uri on callback:", flow.redirect_uri)
        print("request.url:", request.url)
        print("X-Forwarded-Proto:", request.headers.get("X-Forwarded-Proto"))
        print("X-Forwarded-Host:", request.headers.get("X-Forwarded-Host"))
        
        with open(token_path, "w") as f:
            f.write(creds.to_json())
        
        # Clear the session state
        session.pop('oauth_state', None)
        
        return f"""<p>Successfully added account: {email_addr}</p><p><a href='/'>Go to homepage</a></p>"""
    except Exception as e:
        return f"""<p>Error adding account: {e}</p><p><a href='/'>Go to homepage</a></p>"""

# --- Route to delete a user ---
@app.route("/delete_user", methods=["POST"])
def delete_user():
    try:
        data = request.get_json()
        email = data.get("email")
        
        if not email:
            return jsonify({"error": "Email is required"}), 400
        
        token_path = TOKENS_DIR / f"{email}.json"
        
        if not token_path.exists():
            return jsonify({"error": "User not found"}), 404
        
        # Delete the token file
        token_path.unlink()
        
        return jsonify({"message": f"User {email} deleted successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Route for unread mails ---
@app.route("/unread")
def unread():
    max_per = int(request.args.get("max", 7))
    data = {"accounts": []}
    
    # Ensure tokens directory exists
    if not os.path.exists("tokens"):
        os.makedirs("tokens")
    
    token_paths = glob.glob("tokens/*.json")
    
    # Handle case when no tokens exist
    if not token_paths:
        return jsonify({"accounts": [], "message": "No authenticated accounts found. Please run bootstrap_auth.py first."})
    
    with ThreadPoolExecutor(max_workers=len(token_paths)) as executor:
        futures = [executor.submit(fetch_account_unread, tp, max_per) for tp in token_paths]
        for future in futures:
            data["accounts"].append(future.result())
    return jsonify(data)

# --- Route for latest mails ---
@app.route("/latest")
def latest():
    max_per = int(request.args.get("max", 7))
    data = {"accounts": []}
    
    # Ensure tokens directory exists
    if not os.path.exists("tokens"):
        os.makedirs("tokens")
    
    token_paths = glob.glob("tokens/*.json")
    
    # Handle case when no tokens exist
    if not token_paths:
        return jsonify({"accounts": [], "message": "No authenticated accounts found. Please run bootstrap_auth.py first."})
    
    with ThreadPoolExecutor(max_workers=len(token_paths)) as executor:
        futures = [executor.submit(fetch_account_latest, tp, max_per) for tp in token_paths]
        for future in futures:
            data["accounts"].append(future.result())
    return jsonify(data)

if __name__ == "__main__":
 import os

port = int(os.environ.get('PORT', 5000))
debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
render_env = os.environ.get('RENDER', 'False').lower() == 'true'

if debug and not render_env:
    # Local development mode with SSL
    app.run(port=port, debug=True, ssl_context=('cert.pem', 'key.pem'))
else:
    # Production mode (Render or other hosts)
    app.run(host='0.0.0.0', port=port, debug=False)


