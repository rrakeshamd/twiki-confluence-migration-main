import requests
import base64
import os

def upload_to_confluence(file_path, file_type, confluence_url, confluence_username, confluence_api_token, confluence_space_id, confluence_parent_id):
    """Function to upload the DOCX file content to Confluence using the POST API"""
    with open(file_path, 'rb') as file:
        file_content = file.read()

    # Encode the credentials for the Authorization header
    auth_token = f"{confluence_username}:{confluence_api_token}"
    auth_token_encoded = base64.b64encode(auth_token.encode()).decode()

    content_type = ''

    if file_type == 'docx':
        content_type = 'vnd.openxmlformats-officedocument.wordprocessingml.document'
    else:
        content_type = 'json'

    headers = {
        "Accept": "application/json",
        "Content-Type": f"application/{content_type}",
        "Authorization": f"Basic {auth_token_encoded}"
    }

    post_url = f"https://{confluence_url}/wiki/api/v2/pages"
    post_payload = {
        "spaceId": confluence_space_id,
        "status": "current",    # set status = draft for review
        "title": "Uploaded DOCX from Script",
        "parentId": confluence_parent_id,
        "body": {
            "representation": "storage",
            "value": file_content.decode('latin1')  # Decode as latin1 to handle binary content
        }
    }
    post_response = requests.post(post_url, json=post_payload, headers=headers)
    print("POST Response:")
    print(post_response.status_code)
    print(post_response.json())
