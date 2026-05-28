import requests
import base64
import os
from dotenv import load_dotenv
import pandas as pd
from bs4 import BeautifulSoup

# Load environment variables from .env file
load_dotenv()

# Confluence credentials and details from environment variables
confluence_url = os.getenv("CONFLUENCE_URL")
confluence_username = os.getenv("CONFLUENCE_USERNAME")
confluence_api_token = os.getenv("CONFLUENCE_API_TOKEN")

# Encode the credentials for the Authorization header
auth_token = f"{confluence_username}:{confluence_api_token}"
auth_token_encoded = base64.b64encode(auth_token.encode()).decode()


def print_response_details(response):
    """
    Print the response status code and a success message if the status code indicates success.

    Args:
        response (Response): HTTP response object from requests library
    """
    if response.status_code == 200 or response.status_code == 201 or response.status_code == 204:
        print(f"Response: Success with status code {response.status_code}")
    else:
        print(f"Response: Failed with status code {response.status_code}")
        # Uncomment below to see full error details when debugging
        print(f"Error message: {response.content}")


def create_empty_page(confluence_space_id, confluence_parent_id, page_name):
    """
    Create an empty page in Confluence.

    Args:
        page_name (str): Title of the page to create

    Returns:
        tuple: (page_id, version_number) - ID and version of the created page
    """
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Basic {auth_token_encoded}",
    }

    post_url = f"https://{confluence_url}/wiki/api/v2/pages"
    post_payload = {
        "spaceId": confluence_space_id,
        "status": "current",  # set status = draft for review
        "title": page_name,
        "parentId": confluence_parent_id,
        "body": {
            "representation": "wiki",
            "value": "empty page",
        },
    }
    post_response = requests.post(post_url, json=post_payload, headers=headers)

    # Print the response details
    print("\nTask: Creating empty page")
    print_response_details(post_response)

    page_id = ""
    version_number = ""
    if post_response.status_code == 200 or post_response.status_code == 201:
        response_data = post_response.json()
        page_id = response_data.get("id")
        version_number = response_data.get("version", {}).get("number")

        return page_id, version_number
    else:
        return None, None


def upload_attachments(is_attachments, attachment_df, attachments_folder, page_id, topic_url_mapping, got_pub_files):
    """
    Upload attachments to a given page in the Confluence space.

    Args:
        attachment_df (DataFrame): DataFrame containing attachment metadata
        attachments_folder (str): Path to folder containing attachment files
        page_id (str): ID of the Confluence page to attach files to

    Returns:
        DataFrame: Updated DataFrame with attachment IDs and download links
    """
    attachment_data = []
    number_of_files = 0
    print("\nTask: Uploading attachments")

    for filename in os.listdir(attachments_folder):
        file_path = os.path.join(attachments_folder, filename)
        if os.path.isfile(file_path):
            put_url = f"https://{confluence_url}/wiki/rest/api/content/{page_id}/child/attachment"
            headers = {
                "X-Atlassian-Token": "nocheck",
                "Authorization": f"Basic {auth_token_encoded}",
            }

            with open(file_path, "rb") as file:
                files = {
                    "file": (filename, file),
                    "minorEdit": (None, "true"),
                    "comment": (None, "Example attachment comment"),
                }
                put_response = requests.post(put_url, headers=headers, files=files)

            print_response_details(put_response)

            # Extract attachment details from response
            put_response_data = put_response.json()
            attachment_id = (
                put_response_data["results"][0]["id"]
                if "results" in put_response_data
                and len(put_response_data["results"]) > 0
                else None
            )

            if attachment_id:
                base_link = put_response_data["_links"]["base"]
                download_link = (
                    base_link + put_response_data["results"][0]["_links"]["download"]
                )
                attachment_data.append(
                    {
                        "file_name": filename,
                        "attachment_id": attachment_id,
                        "download_link": download_link,
                    }
                )
                # Update topic_url_mapping if the file exists in the mapping values
                for url, mapped_filename in topic_url_mapping.items():
                    if mapped_filename == filename:
                        # Replace the original URL's value with the download link
                        topic_url_mapping[url] = download_link
                        break

                number_of_files += 1
            else:
                print(f"No attachment found for {filename}.")

    print("Total number of attachments: ", number_of_files)
    # Merge new attachment info with original DataFrame
    if is_attachments:
        return pd.merge(
            attachment_df, pd.DataFrame(attachment_data), on="file_name", how="outer"
        ), topic_url_mapping
    else:
        return attachment_df, topic_url_mapping


def upload_content_to_confluence(content, representation, page_id, version_number, page_name, set_width, chunk_size=4800):
    """
    Upload content to Confluence using the PUT API, handling large content by uploading in chunks.
    Saves each chunk to temp folder for debugging purposes.

    Args:
        content (str): Content to upload
        representation (str): Content representation format ('wiki' or 'storage')
        page_id (str): ID of the Confluence page
        version_number (int): Current version number of the page
        page_name (str): Title of the page
        set_width (bool): Whether to set the page to full width
        chunk_size (int): Maximum size of content to upload at once (default: 4800)

    Returns:
        Response: HTTP response from the final content update request
    """
    print("\nTask: Uploading wiki content to Confluence")
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Basic {auth_token_encoded}",
    }

    print(f'Total content length: {len(content)} characters')
    
    # Create temp directory if it doesn't exist
    temp_dir = "temp"
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
        print(f"Created temporary directory: {temp_dir}")
    
    # If content is small enough, upload it all at once
    if len(content) <= chunk_size:
        # Save content to file
        temp_file = os.path.join(temp_dir, f"{page_id}_full.txt")
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Saved full content to {temp_file}")
        
        return _perform_content_upload(content, representation, page_id, version_number, 
                                      page_name, set_width, headers)
    
    # For large content, upload in chunks
    print(f"Content exceeds {chunk_size} characters. Splitting into chunks for upload.")
    
    # Initial upload with first chunk
    current_chunk = content[:chunk_size] + "\n\n(Content continued in next update...)"
    
    # Save first chunk to file
    temp_file = os.path.join(temp_dir, f"{page_id}_chunk_1.txt")
    with open(temp_file, "w", encoding="utf-8") as f:
        f.write(current_chunk)
    print(f"Saved chunk 1 to {temp_file}")
    
    print(f"Uploading first chunk ({len(current_chunk)} characters)...")
    
    response = _perform_content_upload(current_chunk, representation, page_id, 
                                      version_number, page_name, set_width, headers)
    
    if response.status_code not in [200, 201]:
        print("Failed to upload first chunk. Aborting.")
        return response
    
    # Update version number for subsequent uploads
    version_number += 1
    
    # Process remaining content in chunks
    remaining_content = content[chunk_size:]
    chunk_num = 2
    
    while remaining_content:
        if chunk_num == 2:
            chunk_num += 1
            continue
        # Calculate size of next chunk
        next_chunk_size = min(chunk_size, len(remaining_content))
        current_chunk = remaining_content[:next_chunk_size]
        
        # Add continuation note if more content follows
        if next_chunk_size < len(remaining_content):
            current_chunk += "\n\n(Content continued in next update...)"
        
        # Save chunk to file
        temp_file = os.path.join(temp_dir, f"{page_id}_chunk_{chunk_num}.txt")
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(current_chunk)
        print(f"Saved chunk {chunk_num} to {temp_file}")
            
        print(f"Uploading chunk {chunk_num} ({len(current_chunk)} characters)...")
        
        # Get the latest page content to ensure we're updating with the right version
        latest_page = get_page_content(page_id)
        if not latest_page:
            print("Failed to retrieve latest page version. Aborting.")
            return response
            
        current_version = latest_page.get("version", {}).get("number", version_number)
        print(f"Current version: {current_version}")
        
        # Upload current chunk
        response = _perform_content_upload(current_chunk, representation, page_id,
                                          current_version, page_name, False, headers)
        
        if response.status_code not in [200, 201]:
            print(f"Failed to upload chunk {chunk_num}. Aborting.")
            return response
            
        # Move to next chunk
        remaining_content = remaining_content[next_chunk_size:]
        chunk_num += 1
        
    # If all chunks uploaded successfully, return final response
    print(f"Successfully uploaded all {chunk_num-1} chunks")
    return response


def _perform_content_upload(content, representation, page_id, version_number, page_name, set_width, headers):
    """
    Helper function to perform the actual content upload.
    """
    put_url = f"https://{confluence_url}/wiki/api/v2/pages/{page_id}"
    put_payload = {
        "id": page_id,
        "status": "current",  # set status = draft for review
        "title": page_name,
        "body": {
            "representation": representation,
            "value": content,
        },
        "version": {
            "number": version_number + 1,
            "message": f"TWiki Content Migration {version_number + 1}",
        },
    }
    
    try:
        content_response = requests.put(put_url, json=put_payload, headers=headers)
        
        # Print the response details
        print_response_details(content_response)
        
        # Set page width if requested
        if set_width and content_response.status_code == 200:
            # Set the width to full-width for draft version
            print("\nTask: Setting width in draft")
            post_url = f"https://{confluence_url}/wiki/api/v2/pages/{page_id}/properties"
            post_payload = {"key": "content-appearance-draft", "value": "full-width"}
            property_response = requests.post(post_url, json=post_payload, headers=headers)
            print_response_details(property_response)

            # Set the width to full-width for published version
            print("\nTask: Setting width in published")
            post_url = f"https://{confluence_url}/wiki/api/v2/pages/{page_id}/properties"
            post_payload = {"key": "content-appearance-published", "value": "full-width"}
            property_response = requests.post(post_url, json=post_payload, headers=headers)
            print_response_details(property_response)
            
        return content_response
        
    except Exception as e:
        print(f"Exception during content upload: {str(e)}")
        raise


def get_page_content(page_id):
    """
    Retrieve the content of a Confluence page using its page ID.

    Args:
        page_id (str): ID of the Confluence page

    Returns:
        dict or None: JSON response data with page content if successful, None otherwise
    """
    print("\nTask: Retrieving page content")

    headers = {
        "Accept": "application/json",
        "Authorization": f"Basic {auth_token_encoded}",
    }

    get_url = (
        f"https://{confluence_url}/wiki/api/v2/pages/{page_id}?body-format=storage"
    )
    response = requests.get(get_url, headers=headers)

    # Print the response details
    print_response_details(response)

    if response.status_code == 200:
        return response.json()
    else:
        print("Failed to retrieve page content.")
        return None

def delete_page(page_id):
    """
    Delete a Confluence page using its page ID.

    Args:
        page_id (str): ID of the Confluence page to delete

    Returns:
        bool: True if the page was successfully deleted, False otherwise
    """
    print("\nTask: Deleting page")

    headers = {
        "Authorization": f"Basic {auth_token_encoded}",
    }

    delete_url = f"https://{confluence_url}/wiki/api/v2/pages/{page_id}"
    response = requests.delete(delete_url, headers=headers)

    # Print the response details
    print_response_details(response)

    return response
    


def create_space(space_key, space_name, space_description):
    """
    Create a new Confluence space using the REST API.

    Args:
        space_key (str): Unique key for the space
        space_name (str): Display name for the space
        space_description (str): Description of the space

    Returns:
        dict or None: JSON response data with space details if successful, None otherwise
    """
    headers = {
        "Authorization": f"Basic {auth_token_encoded}",
        "Content-Type": "application/json",
    }

    post_url = f"https://{confluence_url}/wiki/api/v2/spaces"
    post_payload = {
        "key": space_key,  # Must be unique
        "name": space_name,
        "alias": space_key,
        "description": {
            "plain": {"value": space_description, "representation": "plain"}
        },
    }

    response = requests.post(post_url, headers=headers, json=post_payload)

    # Print the response details
    print("\nTask: Creating Confluence Space")
    print_response_details(response)

    if response.status_code == 201:
        print("Space created successfully!")
        return response.json()
    else:
        print(f"Failed to create space: {response.status_code}")
        print(response.text)
        return None

def get_space_by_id(space_id):
    """
    Retrieve information about a Confluence space using its ID.

    Args:
        space_id (str): ID of the Confluence space

    Returns:
        dict or None: JSON response data with space details if successful, None otherwise
    """
    print("\nTask: Retrieving space information")

    headers = {
        "Accept": "application/json",
        "Authorization": f"Basic {auth_token_encoded}",
    }

    get_url = f"https://{confluence_url}/wiki/api/v2/spaces/{space_id}"
    response = requests.get(get_url, headers=headers)

    # Print the response details
    print_response_details(response)

    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to retrieve space information: {response.status_code}")
        return None



# Example usage for testing functions
if __name__ == "__main__":
    # # Test the create_space function
    # test_space_key = "TESTKEY"
    # test_space_name = "Test SpaceName"
    # test_space_description = "This is a test space created via REST API."
    
    # created_space = create_space(test_space_key, test_space_name, test_space_description)
    # if created_space:
    #     print("\nCreated Space Details:")
    #     print(created_space)
    # else:
    #     print("\n Space not created")

    # # Test the get_space_by_id function
    # test_space_id = "30244868"  # 30244868  78643202
    # space_info = get_space_by_id(test_space_id)
    # if space_info:
    #     print("Plain Info:")
    #     print(space_info)
    #     print("\nSpace Information:")
    #     print(f"ID: {space_info.get('id')}")
    #     print(f"Key: {space_info.get('key')}")
    #     print(f"Name: {space_info.get('name')}")
    #     print(f"Type: {space_info.get('type')}")
    #     print(f"Status: {space_info.get('status')}")
    #     print(f"Author ID: {space_info.get('authorId')}")
    #     print(f"Created At: {space_info.get('createdAt')}")
    #     print(f"Homepage ID: {space_info.get('homepageId')}")
    #     print(f"Space Owner ID: {space_info.get('spaceOwnerId')}")
    #     print(f"Current Active Alias: {space_info.get('currentActiveAlias')}")
        
    #     # Get description if available
    #     description = space_info.get('description', {})
    #     if description and 'plain' in description:
    #         print(f"Description: {description.get('plain', {}).get('value', 'N/A')}")
        
    #     # Get icon information if available
    #     icon = space_info.get('icon', {})
    #     if icon:
    #         print(f"Icon Path: {icon.get('path', 'N/A')}")
    #         print(f"Icon Download Link: {icon.get('apiDownloadLink', 'N/A')}")
        
    #     # Get web UI link if available
    #     links = space_info.get('_links', {})
    #     if links:
    #         base_url = links.get('base', '')
    #         webui_path = links.get('webui', '')
    #         full_webui_link = f"{base_url}{webui_path}" if base_url and webui_path else 'N/A'
    #         print(f"Web UI Link: {full_webui_link}")

    # # Test on get_page_content function
    # test_page_id = "79759972"  # Replace with a valid page ID
    # page_content = get_page_content(test_page_id)
    
    # if page_content:
    #     print("\nPage Content Information:")
    #     print(f"Page ID: {page_content.get('id')}")
    #     print(f"Title: {page_content.get('title')}")
    #     print(f"Version: {page_content.get('version', {}).get('number')}")
    #     print(f"Space ID: {page_content.get('spaceId')}")
    #     print(f"Parent ID: {page_content.get('parentId', 'None')}")
    #     print(f"Created At: {page_content.get('createdAt')}")
        
    #     # Print body content (first 150 chars)
    #     body = page_content.get('body', {}).get('storage', {}).get('value', '')
    #     print(f"Content Preview: {body[:150]}..." if len(body) > 150 else f"Content: {body}")
        
    #     # Save the content to a file
    #     try:
    #         with open("home.html", "w", encoding="utf-8") as file:
    #             file.write(body)
    #             print(f"Content saved to home.html")
    #     except Exception as e:
    #         print(f"Error while saving HTML: {e}")
    # else:
    #     print("Failed to retrieve page content or page doesn't exist.")



    # Test retrieving page content
    test_page_id = "83428228"
    page_content = get_page_content(test_page_id)

    if page_content:
        print("\nPage Content Retrieved:")
        print(f"Page ID: {page_content.get('id')}")
        print(f"Title: {page_content.get('title')}")
        print(f"Version: {page_content.get('version', {}).get('number')}")
        
        # Read content from file
        try:
            input_file = "/workspaces/twiki-confluence-migration/BRMacro/BRespshell/wiki_content.txt"
            with open(input_file, "r", encoding="utf-8") as file:
                wiki_content = file.read()
            
            # # Get info about the content
            # content_length = len(wiki_content)
            # print(f"Content length: {content_length} characters")
            
            # # Try with first portion of content if it's large
            # if content_length > 10000:
            #     print("Content is large, trying with first 5000 characters as a test")
            #     test_content = wiki_content[:1000] + "\n\n(Content truncated for testing)"
            #     test_upload = True
            # else:
            #     test_content = wiki_content
            #     test_upload = False

            # # Get info about the content
            # content_length = len(test_content)
            # print(f"Content length (after truncated): {content_length} characters")
            
            current_version = page_content.get("version", {}).get("number", 0)
            page_title = page_content.get("title", "Untitled Page")
            
            # # First try with test content if needed
            # if test_upload:
            #     # Test with incremental content sizes to find maximum limit
            #     test_sizes = [500, 1000, 2000, 3000, 4000, 5000]
            #     max_successful_size = 0
                
            #     for size in test_sizes:
            #         if size > len(wiki_content):
            #             print(f"Content length ({len(wiki_content)}) is less than test size ({size}), skipping")
            #             continue
                        
            #         print(f"\nTesting upload with {size} characters...")
            #         size_test_content = wiki_content[:size] + "\n\n(Content truncated for testing)"
                    
            #         test_response = upload_content_to_confluence(
            #             size_test_content, "wiki", test_page_id, current_version, page_title, False
            #         )
                    
            #         if test_response.status_code in [200, 201]:
            #             print(f"✓ Test with {size} characters successful")
            #             max_successful_size = size
            #             # Update current version after successful test upload
            #             current_version += 1
            #         else:
            #             print(f"✗ Test with {size} characters failed")
            #             print(f"Maximum successful size was {max_successful_size} characters")
            #             break
                
            #     if max_successful_size > 0:
            #         print(f"\nMaximum successful content size: {max_successful_size} characters")
                    
            #         # If the full content is smaller than the max successful size, try uploading it
            #         if len(wiki_content) <= max_successful_size:
            #             print("\nFull content is within successful size limit, uploading full content...")
            #             response = upload_content_to_confluence(
            #                 wiki_content, "wiki", test_page_id, current_version, page_title, False
            #             )
                        
            #             if response.status_code in [200, 201]:
            #                 print(f"Content from {input_file} uploaded successfully!")
            #             else:
            #                 print(f"Failed to upload full content: {response.status_code}")
            #         else:
            #             print(f"\nFull content size ({len(wiki_content)}) exceeds maximum successful size ({max_successful_size})")
            #             print("Consider splitting the content into multiple pages")
            #     else:
            #         print("All test uploads failed")
            #         print("Please check the wiki markup syntax for errors")
            #         # Exit the function
            #         import sys
            #         sys.exit(1)
            # else:
                # Original code for when test_upload is False
            response = upload_content_to_confluence(
                wiki_content, "wiki", test_page_id, current_version, page_title, False
            )
            
            if response.status_code in [200, 201]:
                print(f"Content from {input_file} uploaded successfully!")
            else:
                print(f"Failed to upload content: {response.status_code}")
                
        except Exception as e:
            print(f"Error reading or uploading content: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("Failed to retrieve page content.")


    # # Test deleting page
    # test_page_id = "79758662"  # replace with a real page ID you want to delete
    # deletion_result = delete_page(test_page_id)
    
    # if deletion_result:
    #     print(f"Page {test_page_id} was successfully deleted")
    # else:
    #     print(f"Failed to delete page {test_page_id}")
