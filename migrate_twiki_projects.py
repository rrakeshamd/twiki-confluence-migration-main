import requests
from bs4 import BeautifulSoup, NavigableString
from dotenv import load_dotenv
import os
import html2text
from confluence_api import (
    create_empty_page,
    upload_attachments,
    upload_content_to_confluence,
    get_page_content,
    delete_space,
    create_space,
    add_admin_permissions,
    delete_page,
    get_accountId_by_email
)
from markdown_to_wiki import convert_markdown_to_wiki
from modify_space_home_content import modify_space_home_content
from retrieve_author import retrieve_author
import pandas as pd
from User import User
from TWiki import TWiki
import json
import shutil
from retrieve_urls import retrieve_urls
import sys
import datetime
from contextlib import contextmanager
import time
import re

# Load environment variables from .env file
load_dotenv()

# Initialize User object with credentials from environment variables
user = User(username=os.getenv("USERNAME"), password=os.getenv("PASSWORD"))

# Confluence credentials and details from environment variables
confluence_url = os.getenv("CONFLUENCE_URL")
confluence_username = os.getenv("CONFLUENCE_USERNAME")
confluence_api_token = os.getenv("CONFLUENCE_API_TOKEN")


# Add this function after the imports
@contextmanager
def log_to_file(log_file_path):
    """
    Context manager to redirect print statements to both console and a log file.
    
    Args:
        log_file_path (str): Path to the log file
    """
    # Create or open the log file for appending
    log_file = open(log_file_path, 'a', encoding='utf-8')
    
    # Store the original stdout
    original_stdout = sys.stdout
    
    # Define a custom stdout class to write to both console and file
    class CustomOutput:
        def write(self, message):
            original_stdout.write(message)
            log_file.write(message)
            log_file.flush()  # Ensure content is written immediately
            
        def flush(self):
            original_stdout.flush()
            log_file.flush()
    
    # Redirect stdout to our custom output
    sys.stdout = CustomOutput()
    
    try:
        # Add timestamp at the beginning of new log entries
        print(f"\n--- Migration started at {datetime.datetime.now()} ---\n")
        yield
    finally:
        # Add timestamp at the end of log entries
        print(f"\n--- Migration ended at {datetime.datetime.now()} ---\n")
        # Restore the original stdout
        sys.stdout = original_stdout
        # Close the log file
        log_file.close()

def create_new_confluence_space(space_key, space_name, space_description):
    """
    Create a new Confluence space with the provided details.
    
    Args:
        space_key (str): The unique key identifier for the space
        space_name (str): The display name of the space
        space_description (str): Description for the space
        
    Returns:
        dict: Dictionary containing the created space details including:
              - id: Unique identifier for the space
              - key: Space key
              - name: Space name
              - homepageId: ID of the space's home page
              - and other metadata
    """
    # Create a new Confluence space using the API
    space_response = create_space(space_key, space_name, space_description)

    # Process successful response
    if space_response is not None and (space_response.status_code == 200 or space_response.status_code == 201):
        space_data = space_response.json()
        
        # Extract and structure the response data
        space_dict = {
            "id": space_data.get("id"),
            "key": space_data.get("key"),
            "name": space_data.get("name"),
            "homepageId": space_data.get("homepage", {}).get("id"),
            "homepageTitle": space_data.get("homepage", {}).get("title"),
            "spaceLink": space_data.get("_links", {}).get("base") + space_data.get("_links", {}).get("webui")
        }
        return space_dict
    else:
        return None


def fetch_webpage(url, username, password):
    """
    Fetch the webpage content with authentication.

    Args:
        url (str): The URL to fetch
        username (str): Authentication username
        password (str): Authentication password

    Returns:
        bytes: The raw content of the webpage

    Raises:
        HTTPError: If the response status code is 4xx or 5xx
    """
    
    try:
        response = requests.get(url, auth=(username, password))
        if response and (response.status_code == 200 or response.status_code == 201):
            return response.content
    except requests.HTTPError as e:
        print(f"\nHTTPError: {e.response.status_code} - {e.response.reason}")
        return None
    except requests.RequestException as e:
        print(f"\nRequestException: {e}")
        return None
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        return None
    return None


def create_folder(twiki, page_name):
    """
    Create a folder with the given page_name if it doesn't exist.

    Args:
        twiki (TWiki): TWiki object containing project information
        page_name (str): Name of the page to create a folder for
    """
    if not os.path.exists(os.path.join(twiki.project_name, page_name)):
        os.makedirs(os.path.join(twiki.project_name, page_name))


def save_pretty_html(twiki, soup, page_name):
    """
    Save the beautified HTML content to a file.

    Args:
        twiki (TWiki): TWiki object containing project information
        soup (BeautifulSoup): BeautifulSoup object with the parsed HTML
        page_name (str): Name of the page for file organization
    """
    pretty_html = soup.prettify()
    with open(
        os.path.join(twiki.project_name, page_name, "main_content.html"),
        "w",
        encoding="utf-8",
    ) as output:
        output.write(pretty_html)
    print("\nHTML content saved to main_content file.")


def save_html_content(twiki, html_content, page_name):
    """
    Save the HTML content to a pattern_topic.html file.

    Args:
        twiki (TWiki): TWiki object containing project information
        html_content (str): HTML content to save
        page_name (str): Name of the page for file organization
    """
    html_file_path = os.path.join(twiki.project_name, page_name, "pattern_topic.html")
    with open(html_file_path, "w", encoding="utf-8") as file:
        file.write(html_content)


def process_pattern_topic_div(twiki, soup, page_name):
    """
    Process the patternTopic div and save its content in various formats.

    This function:
    1. Finds the pattern topic div
    2. Removes TOC and elements before it
    3. Removes non-HTTP(S) images
    4. Removes specific sections like "Site_Tools"
    5. Removes comment forms
    6. For TopicList pages, cleans up excluded links and verbose content

    Args:
        twiki (TWiki): TWiki object containing project information
        soup (BeautifulSoup): BeautifulSoup object with the parsed HTML
        page_name (str): Name of the page being processed

    Returns:
        str or None: The cleaned HTML content or None if no patternTopic div found
    """
    soup_pattern_topic = soup.find("div", {"class": "patternTopic"})
    html_content = ""

    if soup_pattern_topic:
        print('Div with class "patternTopic" found')
        # Remove the div with class "twikiToc" if it exists
        toc_div = soup_pattern_topic.find("div", {"class": "twikiToc"})

        if toc_div:
            # Remove all elements before the ToC div
            for previous in list(toc_div.previous_siblings):
                if hasattr(previous, "decompose"):
                    previous.decompose()

            # Remove the ToC itself
            toc_div.decompose()

        # Remove non-HTTP(S) images
        for img in soup_pattern_topic.find_all("img"):
            if not img["src"].startswith(("http://", "https://")):
                img.decompose()

        # Find all h2 tags and remove sections starting with "Site_Tools"
        for h2 in soup_pattern_topic.find_all("h2"):
            anchor = h2.find("a", attrs={"name": True})

            if anchor and anchor["name"].startswith("Site_Tools"):
                # Remove all elements that come after this <h2>
                for element in list(h2.next_siblings):
                    if hasattr(element, "decompose"):
                        element.decompose()

                # Remove the h2 itself
                h2.decompose()
                break  # Stop after the first match

        # Remove comment form
        form_tag = soup_pattern_topic.find("form", {"id": "above0"})
        if form_tag:
            form_tag.decompose()

            # Remove the h2 heading with anchor name="Comments"
            h2_tag = soup_pattern_topic.find("h2")
            if h2_tag and h2_tag.find("a", {"name": "Comments"}):
                h2_tag.decompose()
        
        # Also find and remove any h2 tags that have "Comments" text directly
        for h2_tag in soup_pattern_topic.find_all("h2"):
            if h2_tag.text.strip() == "Comments" or "Comments" in h2_tag.text.strip():
                h2_tag.decompose()

        # Special handling for TopicList pages
        if twiki.page_name == "TopicList":
            # Define links to exclude from the list
            excluded_links = {
                "WebAtom",
                "WebChanges",
                "WebCreationInformation",
                "WebIndex",
                "WebLeftBar",
                "WebNotify",
                "WebPreferences",
                "WebRss",
                "WebSearch",
                "WebSearchAdvanced",
                "WebStatistics",
            }

            # Remove excluded links
            for a_tag in soup_pattern_topic.select("ul li a"):
                href = a_tag.get("href")
                if href and any(excluded in href for excluded in excluded_links):
                    a_tag.parent.decompose()  # Remove the entire <li> element containing the link
                elif href and "WebHome" in href:
                    a_tag.string = "Home"  # Change WebHome link text to Home
                elif href and "WebTopicList" in href:
                    a_tag.string = "TopicList"  # Change WebTopicList link text to TopicList

            # Loop through the contents to find the verbose line and remove it
            found = False
            for i, element in enumerate(soup_pattern_topic.contents):
                if isinstance(element, NavigableString) and element.strip().startswith(
                    "See also the verbose"
                ):
                    found = True
                    break

            if found:
                # Remove this element and everything after it
                for el in soup_pattern_topic.contents[i:]:
                    el.extract()

        # Get the final HTML content and save it
        html_content = str(soup_pattern_topic.prettify())
        save_html_content(twiki, html_content, page_name)
    else:
        print('No div with class "patternTopic" found.')
        return None

    return html_content


def process_attachments_table(twiki, soup, page_name, topic_url_mapping):
    """
    Process the TWiki attachments table and download all files into an attachments folder.

    Args:
        twiki (TWiki): TWiki object containing project information
        soup (BeautifulSoup): BeautifulSoup object with the parsed HTML
        page_name (str): Name of the page for file organization

    Returns:
        tuple: (bool, DataFrame, str) - (has_attachments, attachments_dataframe, attachments_folder_path)
    """

    """
    Process the TWiki attachments table and download all files into an attachments folder.
    Also downloads files from twiki/pub/project_name links found in the HTML content.

    Args:
        twiki (TWiki): TWiki object containing project information
        soup (BeautifulSoup): BeautifulSoup object with the parsed HTML
        page_name (str): Name of the page for file organization
        topic_url_mapping (dict): Mapping of TWiki URLs to Confluence URLs

    Returns:
        tuple: (has_attachments, DataFrame, str, dict) - (has_attachments, attachments_dataframe, attachments_folder, updated_topic_url_mapping)
    """
    got_pub_files = False
    # Create attachments folder if it doesn't exist
    attachments_folder = os.path.join(twiki.project_name, page_name, "attachments")
    if not os.path.exists(attachments_folder):
        os.makedirs(attachments_folder)
    
    # Process twiki/pub links from the content first
    # Read pattern_topic.html if it exists (for pages already processed)
    pattern_topic_path = os.path.join(twiki.project_name, page_name, "pattern_topic.html")
    if os.path.exists(pattern_topic_path):
        with open(pattern_topic_path, "r", encoding="utf-8") as file:
            content_html = file.read()
        content_soup = BeautifulSoup(content_html, "html.parser")
    else:
        content_soup = soup  # Use the original soup if pattern_topic.html doesn't exist yet
    
    # Find all <a> tags with href containing twiki/pub
    pub_links = content_soup.find_all("a", href=lambda href: href and "twiki/pub" in href)
    
    if len(pub_links) > 0:
        got_pub_files = True
        print("Processing pub files in the main content")
        # Download files from twiki/pub links
        for link in pub_links:
            file_url = link["href"]
            # Extract file name from URL
            file_name = file_url.split("/")[-1]
            
            # Save the file URL to the topic_url_mapping dictionary
            topic_url_mapping[file_url] = file_name
            
            # Download the file
            file_path = os.path.join(attachments_folder, file_name)
            try:
                response = requests.get(file_url, auth=(user.username, user.password))
                response.raise_for_status()
                with open(file_path, "wb") as file:
                    file.write(response.content)
                print(f"Downloaded: {file_name}")
            except requests.RequestException as e:
                print(f"Failed to download {file_name}: {e}")
    else:
        print("No pub files found in the main content")

    attachments_table = soup.find("table", {"id": "twikiAttachmentsTable"})

    # Create an empty DataFrame with required columns if no attachments found
    if not attachments_table:
        print("\nNo TWiki files found from attachments table")
        return (
            False,
            pd.DataFrame(
                columns=[
                    "file_name",
                    "file_size",
                    "file_datetime_created",
                    "file_owner",
                    "file_comment",
                ]
            ),
            attachments_folder,
            topic_url_mapping,
            got_pub_files
        )
    else:
        print("\nProcessing TWiki files found from attachments table")

        # Process each row in the attachments table
        data = []
        for row in attachments_table.find_all("tr")[1:]:  # Skip the header row
            cols = row.find_all("td")
            if len(cols) < 2:
                continue

            file_link = cols[1].find("a")
            if file_link and "href" in file_link.attrs:
                file_url = file_link["href"]
                file_name = file_link.text.strip()
                
                # Save the file url to the key of topic_url_mapping and set value to ""
                topic_url_mapping[file_url] = file_name

                # Download the file
                file_path = os.path.join(attachments_folder, file_name)
                try:
                    response = requests.get(file_url, auth=(user.username, user.password))
                    response.raise_for_status()
                    with open(file_path, "wb") as file:
                        file.write(response.content)
                    print(f"Downloaded: {file_name}")
                except requests.RequestException as e:
                    print(f"Failed to download {file_name}: {e}")

            # Extract file metadata
            file_size = cols[4].text.strip()
            file_datetime_created = cols[5].text.strip()
            file_owner = cols[6].text.strip()
            file_comment = cols[7].text.strip()

            data.append(
                [file_name, file_size, file_datetime_created, file_owner, file_comment]
            )

        # Create DataFrame with attachment information
        df = pd.DataFrame(
            data,
            columns=[
                "file_name",
                "file_size",
                "file_datetime_created",
                "file_owner",
                "file_comment",
            ],
        )
        return True, df, attachments_folder, topic_url_mapping, got_pub_files


def web_scrape(twiki, soup, page_name, topic_url_mapping):
    """
    Extract necessary content from TWiki page.

    Args:
        twiki (TWiki): TWiki object containing project information
        soup (BeautifulSoup): BeautifulSoup object with the parsed HTML
        page_name (str): Name of the page being processed

    Returns:
        tuple: (html_content, has_attachments, attachments_dataframe, attachments_folder_path)
    """
    html_content = process_pattern_topic_div(twiki, soup, page_name)
    is_attachments, df, attachments_folder, topic_url_mapping, got_pub_files = process_attachments_table(
        twiki, soup, page_name, topic_url_mapping
    )
    return html_content, is_attachments, df, attachments_folder, topic_url_mapping, got_pub_files


def convert_html_to_markdown(twiki, html_content):
    """
    Convert HTML content to Markdown.

    Args:
        twiki (TWiki): TWiki object containing project information
        html_content (str): HTML content to convert

    Returns:
        str: Converted Markdown content
    """
    h = html2text.HTML2Text()
    h.body_width = 0  # Disable word wrapping
    h.baseurl = (
        twiki.base_url
    )  # Set the base URL for converting relative links to absolute links
    return h.handle(html_content)


def save_markdown_content(twiki, markdown_content, page_name):
    """
    Save the Markdown content to a file.

    Args:
        twiki (TWiki): TWiki object containing project information
        markdown_content (str): Markdown content to save
        page_name (str): Name of the page for file organization
    """
    markdown_file_path = os.path.join(twiki.project_name, page_name, "pattern_topic.md")
    with open(markdown_file_path, "w", encoding="utf-8") as file:
        file.write(markdown_content)


def upload_to_confluence(
    twiki,
    markdown_content,
    is_attachments,
    attachment_df,
    attachments_folder,
    confluence_space_id, 
    confluence_parent_id, 
    page_name,
    topic_url_mapping, 
    got_pub_files
):
    """
    Convert Markdown to wiki format and upload to Confluence.

    Args:
        twiki (TWiki): TWiki object containing project information
        markdown_content (str): Markdown content to upload
        is_attachments (bool): Whether the page has attachments
        attachment_df (DataFrame): DataFrame with attachment information
        attachments_folder (str): Path to the attachments folder
        page_name (str): Name of the page to create in Confluence

    Returns:
        Response: The API response from Confluence
    """
    # Create empty page and get the page id
    page_id, version_number = create_empty_page(confluence_space_id, confluence_parent_id, page_name)

    if page_id is not None:
        try:
            # Upload attachments if present
            if is_attachments or got_pub_files:
                attachment_df, topic_url_mapping = upload_attachments(is_attachments, attachment_df, attachments_folder, page_id, topic_url_mapping, got_pub_files)

            # Convert markdown to wiki format and upload the content
            wiki_content = ''

            wiki_content, flag = convert_markdown_to_wiki(
                os.path.join(twiki.project_name, page_name, "pattern_topic.md"),
                is_attachments,
                attachment_df,
                twiki.project_name,
                page_name,
            )

            if flag:
                response = upload_content_to_confluence(
                    wiki_content, "wiki", page_id, version_number, page_name, True
                )

                if response and response.status_code == 200:
                    return response, topic_url_mapping
                else:
                    error_msg = f"Failed to upload content: Status code {response.status_code if response else 'None'}"
                    raise Exception(error_msg)  # Explicitly raise exception to trigger the delete page API
            else:
                error_msg = f"Failed to convert markdown to wiki"
                raise Exception(error_msg)

        except Exception as e:
            print(f"\nError in upload_to_confluence function: {str(e)}")
            try:
                delete_response = delete_page(page_id)
                if delete_response and delete_response.status_code in (200, 204):
                    print(f"Successfully deleted page {page_id}")
                else:
                    print(f"Failed to delete page {page_id}")
            except Exception as delete_error:
                print(f"Error while trying to delete page {page_id}: {str(delete_error)}")
            return None, topic_url_mapping

    else:
        return None, None


def conversion_and_upload(
    twiki, html_content, is_attachments, attachment_df, attachments_folder, confluence_space_id, confluence_parent_id, page_name, topic_url_mapping, got_pub_files
):
    """
    Convert HTML to Markdown and upload to Confluence.

    Args:
        twiki (TWiki): TWiki object containing project information
        html_content (str): HTML content to convert and upload
        is_attachments (bool): Whether the page has attachments
        attachment_df (DataFrame): DataFrame with attachment information
        attachments_folder (str): Path to the attachments folder
        page_name (str): Name of the page for Confluence

    Returns:
        Response: The API response from Confluence
    """
    markdown_content = convert_html_to_markdown(twiki, html_content)
    save_markdown_content(twiki, markdown_content, page_name)
    return upload_to_confluence(
        twiki,
        markdown_content,
        is_attachments,
        attachment_df,
        attachments_folder,
        confluence_space_id, 
        confluence_parent_id, 
        page_name,
        topic_url_mapping, 
        got_pub_files
    )


def migrate_twiki_page_to_confluence(twiki, confluence_space_id, confluence_parent_id, topic_url_mapping):
    """
    Migrate a single TWiki page to Confluence.

    This function:
    1. Fetches the TWiki page content
    2. Parses the HTML
    3. Extracts the page name
    4. Creates a local folder for the content
    5. Extracts and processes the main content
    6. Processes any attachments
    7. Converts the content to Markdown
    8. Uploads everything to Confluence

    Args:
        twiki (TWiki): TWiki object containing URL and base URL

    Returns:
        tuple: (result_dict, page_id) - Dictionary with migration details and Confluence page ID
    """
    try:
        # Fetch and parse the webpage content
        content = None
        retry_flag = False
        iteration = 0
        while content is None:
            if iteration > 2:
                error_msg = f"Retry more than 3 times, skipped..."
                raise Exception(error_msg)
            if retry_flag:
                # pause the script for 60s
                print("Pausing for 2 seconds before retry...")
                time.sleep(2)
                retry_flag = False
            # Fetch and parse the webpage content
            content = fetch_webpage(twiki.url, user.username, user.password)
            if content is None:
                print(f'Retry on fetching {twiki.url} page')
                retry_flag = True
                iteration += 1
            else:
                print(f'Content fetched from {twiki.url} page')
        
        soup = BeautifulSoup(content, "html.parser")
        author_name, author_email = retrieve_author(soup)

        # Extract and format the page_name
        twiki.set_project_page_name(soup)

        # Create a folder with the page_name
        create_folder(twiki, twiki.page_name)

        # Save the beautified HTML content
        save_pretty_html(twiki, soup, twiki.page_name)

        print('\nTask: Starting web scrape')

        # Start web scrape necessary content in TWiki
        html_content, is_attachments, attachment_df, attachments_folder, topic_url_mapping, got_pub_files = web_scrape(
            twiki, soup, twiki.page_name, topic_url_mapping
        )

        response = ""
        if html_content:
            print('Result: Web scrape completed')
            # Start html content conversion and upload to Confluence
            response, topic_url_mapping = conversion_and_upload(
                twiki,
                html_content,
                is_attachments,
                attachment_df,
                attachments_folder,
                confluence_space_id, 
                confluence_parent_id,
                twiki.page_name,
                topic_url_mapping, 
                got_pub_files
            )

        # Process successful response
        if response and (response.status_code == 200 or response.status_code == 201):
            response_data = response.json()
            page_id = response_data.get("id")
            version_number = response_data.get("version", {}).get("number")
            body_value = response_data.get("body", {}).get("storage", {}).get("value")
            title = response_data.get("title")
            parent_id = response_data.get("parentId")
            space_id = response_data.get("spaceId")
            parent_type = response_data.get("parentType")
            page_link = response_data.get("_links", {}).get(
                "base", ""
            ) + response_data.get("_links", {}).get("webui", "")

            # Create result dictionary with all page details
            result = {
                "parentId": parent_id,
                "spaceId": space_id,
                "parentType": parent_type,
                "versionNumber": version_number,
                "bodyValue": body_value,
                "title": title,
                "pageLink": page_link,
                "twikiProjectName": twiki.project_name,
                "twikiPageName": twiki.page_name,
                "twikiPageURL": twiki.url,
                "twikiBaseURL": twiki.base_url,
                "authorName": author_name,
                "authorEmail": author_email
            }

            return result, page_id, topic_url_mapping
        else:
            return None, None, topic_url_mapping

    except requests.HTTPError as e:
        print(f"\nHTTPError: {e.response.status_code} - {e.response.reason}")
        return None, None, topic_url_mapping
    except requests.RequestException as e:
        print(f"\nRequestException: {e}")
        return None, None, topic_url_mapping
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        return None, None, topic_url_mapping

def assign_admin_access_to_user(confluence_space_key, author_name, author_email):
    # Retrieve admin name from base URL
    admin_name = author_name
    admin_email = author_email

    try:
        response_content = get_accountId_by_email(admin_email)

        if response_content:
            admin_account_id = response_content[0]["accountId"]

            permissions_flag = add_admin_permissions(confluence_space_key, 'user', admin_account_id)

            return permissions_flag, admin_name, admin_email

    except requests.HTTPError as e:
        print(f"\nHTTPError: {e.response.status_code} - {e.response.reason}")
        return False, admin_name, admin_email
    except requests.RequestException as e:
        print(f"\nRequestException: {e}")
        return False, admin_name, admin_email
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        return False, admin_name, admin_email

def modify_twiki_links_confluence_links(topic_url_mapping, project_name, page_name, page_id, version_number, base_url):
    """
    Update TWiki links to point to their Confluence equivalents.

    Args:
        topic_url_mapping (dict): Mapping of TWiki URLs to Confluence URLs
        project_name (str): Name of the project
        page_name (str): Name of the page being processed
        page_id (str): Confluence page ID
        version_number (int): Current version number of the page
        base_url (str): Base URL of the TWiki site

    Returns:
        tuple: (page_id, new_version_number) - Updated page ID and version number
    """
    try:
        # Get page content using the GET API
        page_content = get_page_content(page_id)

        if page_content:
            body_content = (
                page_content.get("body", {}).get("storage", {}).get("value", "")
            )

            # Parse the content with BeautifulSoup
            soup = BeautifulSoup(body_content, "html.parser")

            # Save the modified content to an HTML file
            output_file = os.path.join(
                project_name, page_name, "before_editLink_content.html"
            )
            with open(output_file, "w", encoding="utf-8") as file:
                file.write(str(soup))

            trimmed_base_url = base_url[8:]

            cleaned_topic_url_mapping = {}
            for url, value in topic_url_mapping.items():
                # Clean URL by removing view or viewauth part
                if '/twiki/bin/view/' in url:
                    parts = url.split('/twiki/bin/view/')
                    if len(parts) > 1:
                        # Reconstruct URL without the view part
                        cleaned_url = parts[0] + '/twiki/bin/' + parts[1]
                        cleaned_topic_url_mapping[cleaned_url] = value
                        # Keep the original mapping as well
                        cleaned_topic_url_mapping[url] = value
                elif '/twiki/bin/viewauth/' in url:
                    parts = url.split('/twiki/bin/viewauth/')
                    if len(parts) > 1:
                        # Reconstruct URL without the viewauth part
                        cleaned_url = parts[0] + '/twiki/bin/' + parts[1]
                        cleaned_topic_url_mapping[cleaned_url] = value
                        # Keep the original mapping as well
                        cleaned_topic_url_mapping[url] = value
                else:
                    # Keep URLs that don't need cleaning
                    cleaned_topic_url_mapping[url] = value

            # Modify links based on the topic_url_mapping dictionary
            for a_tag in soup.find_all("a", href=True):
                full_url = a_tag["href"]
                # Remove http or https prefix before checking
                clean_url = full_url
                if clean_url.startswith("http://"):
                    clean_url = clean_url[7:]
                elif clean_url.startswith("https://"):
                    clean_url = clean_url[8:]
                    
                # Check if URL contains twiki/bin/edit pattern and remove the whole tag
                if "twiki/bin/edit" in full_url:
                    a_tag.decompose()
                    # print(f'Removed edit link: {full_url}')
                    continue
                
                # Clean URL by removing view or viewauth part
                if '/twiki/bin/view/' in clean_url:
                    parts = clean_url.split('/twiki/bin/view/')
                    if len(parts) > 1:
                        # Reconstruct URL without the view part
                        clean_url = parts[0] + '/twiki/bin/' + parts[1]
                elif '/twiki/bin/viewauth/' in clean_url:
                    parts = clean_url.split('/twiki/bin/viewauth/')
                    if len(parts) > 1:
                        # Reconstruct URL without the viewauth part
                        clean_url = parts[0] + '/twiki/bin/' + parts[1]
                
                # Check if URL is related to our TWiki base
                if clean_url.startswith(trimmed_base_url):
                    # Try full URL first
                    if full_url in topic_url_mapping:
                        a_tag["href"] = topic_url_mapping[full_url]
                        # print(f'Updated link to: {topic_url_mapping[full_url]}')
                    elif full_url.endswith("#sorted_table"):
                        # For table sorting links, remove the href but keep the text
                        text_content = a_tag.get_text(strip=True)
                        a_tag.replace_with(text_content)
                    # Handle URLs with sections (like #IP_Name)
                    elif '#' in clean_url:
                        # Special handling for sections with #Comments - remove these completely
                        if '#Comments' in clean_url:
                            a_tag.decompose()
                            # print(f'Removed comment link: {full_url}')
                        else:
                            # print("'#' in clean_url")
                            # print(f'Clean url: {clean_url}')

                            # Split the URL into base and section parts
                            base_url_part, section_part = clean_url.split('#', 1)
                                
                            # Find matching base URL in our mapping
                            matched_url = None
                            print(f"Mapping url for {base_url_part}")
                            for mapping_url, mapping_value in cleaned_topic_url_mapping.items():
                                # print(f'Mapping url: {mapping_url}')
                                # Check if the base URL part matches the beginning of a key in our mapping
                                if base_url_part in mapping_url:
                                    matched_url = mapping_value
                                    print(f'Matched: {mapping_url} > {matched_url}')
                                    break
                            print(f'Matched url: {matched_url}')
                            if matched_url:
                                # Convert section ID from TWiki format to Confluence format (replace _ with -)
                                section_part = section_part.replace('_', '-')
                                new_url = f"{matched_url}#{section_part}"
                                a_tag["href"] = new_url
                                print(f'Updated section link from {full_url} to {new_url}')
                            else:
                                # Keep the original href but mark as deprecated
                                original_text = a_tag.text.strip()
                                a_tag.string = f'{original_text} (DEPRECATED!!)'
                                # print(f'Marked as deprecated: {full_url}')
                    else:
                        # Keep the original href but mark as deprecated
                        original_text = a_tag.text.strip()
                        a_tag.string = f'{original_text} (DEPRECATED!!)'
                        # print(f'Marked as deprecated: {full_url}')
            
            # Handle square bracket format TWiki edit links: [text|edit_url]
            for text_node in soup.find_all(string=True):
                if isinstance(text_node, NavigableString) and text_node.parent.name != 'a':
                    # Look for patterns like [ ? | edit_url "Create this topic"]
                    pattern = r'\[\s*([^|]+)\s*\|\s*(https?://[^|\]]+twiki/bin/edit[^"]*)\s*"Create this topic"\s*\]'
                    
                    text_str = str(text_node)
                    
                    # Find all matches first, then replace all at once
                    if re.search(pattern, text_str):
                        # Replace all matches in the text string
                        new_text = re.sub(pattern, '', text_str)
                        # Fix multiple spaces that might be created by the removal
                        new_text = re.sub(r'\s{2,}', ' ', new_text)
                        
                        # Only replace if there were actual changes
                        if new_text != text_str:
                            # Replace the text node with the modified text
                            new_node = NavigableString(new_text)
                            text_node.replace_with(new_node)
                            
                            print(f'\nRemoved square bracket edit links')
                            print(f'Original text: {text_str}')
                            print(f'New text: {new_text}')

            # Do a final check through the content and if there is any text which is a link to TWiki, 
            # convert it to an <a> tag with DEPRECATED!! postfix
            for text_node in soup.find_all(string=True):
                if isinstance(text_node, NavigableString):
                    # Look for patterns that resemble TWiki URLs but aren't in <a> tags
                    text_str = str(text_node)
                    
                    # URL pattern that matches TWiki URLs in text
                    url_pattern = re.compile(r'(https?://[^\s<>"\']+?twiki[^\s<>"\']*)')
                    
                    # Find all matches
                    matches = list(url_pattern.finditer(text_str))
                    
                    # Process matches in reverse to avoid messing up string positions
                    if matches:
                        # Create a new soup fragment to hold the modified content
                        new_fragment = BeautifulSoup("", "html.parser")
                        last_end = 0
                        
                        for match in matches:
                            url = match.group(0)
                            start_pos = match.start()
                            end_pos = match.end()
                            
                            # Only process if it contains the base URL
                            if trimmed_base_url in url:
                                # Add text before the URL
                                if start_pos > last_end:
                                    new_fragment.append(NavigableString(text_str[last_end:start_pos]))
                                
                                # Create a new <a> tag with the URL
                                a_tag = soup.new_tag('a', href=url)
                                a_tag.string = f"{url} DEPRECATED!!"
                                new_fragment.append(a_tag)
                                
                                last_end = end_pos
                                print(f'\nConverted plain text URL to link with DEPRECATED!!: {url}')
                        
                        # Add any remaining text
                        if last_end < len(text_str):
                            new_fragment.append(NavigableString(text_str[last_end:]))
                        
                        if matches:
                            # Replace the original text node with our fragment
                            text_node.replace_with(new_fragment)

            # Save the modified content to an HTML file
            output_file = os.path.join(
                project_name, page_name, "after_editLink_content.html"
            )
            with open(output_file, "w", encoding="utf-8") as file:
                file.write(str(soup))

            # Update the content to the site
            response = upload_content_to_confluence(
                str(soup), "storage", page_id, version_number, page_name, False
            )

            if response.status_code == 200 or response.status_code == 201:
                response_data = response.json()
                page_id = response_data.get("id")
                version_number = response_data.get("version", {}).get("number")

                return page_id, version_number
            else:
                return None, None

        else:
            print("No body content found.")
            return None, None

    except requests.HTTPError as e:
        print(f"\nHTTPError: {e.response.status_code} - {e.response.reason}")
        return None, None
    except requests.RequestException as e:
        print(f"\nRequestException: {e}")
        return None, None
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        return None, None


def modify_upload_home_content(project_name, page_id, webTopicList_url):
    """
    Modify and upload the home page content for the Confluence space.

    Args:
        project_name (str): Name of the project
        page_id (str): Confluence page ID for the home page
        webTopicList_url (str): URL of the WebTopicList page in Confluence

    Returns:
        tuple: (result_dict, page_id) - Dictionary with page details and Confluence page ID
    """
    try:
        # Get page content using the GET API
        home_response_content = get_page_content(page_id)

        if home_response_content:
            body_content = (
                home_response_content.get("body", {})
                .get("storage", {})
                .get("value", "")
            )
            version_number = home_response_content.get("version", {}).get("number")

            body_content = modify_space_home_content(
                    project_name, webTopicList_url
            )

            # Update the content to the site
            response = upload_content_to_confluence(
                body_content, "storage", page_id, version_number, project_name + "SpaceHome", False
            )
            if response.status_code == 200 or response.status_code == 201:
                response_data = response.json()
                page_id = response_data.get("id")
                version_number = response_data.get("version", {}).get("number")
                body_value = (
                    response_data.get("body", {}).get("storage", {}).get("value")
                )
                title = response_data.get("title")
                parent_id = response_data.get("parentId")
                space_id = response_data.get("spaceId")
                parent_type = response_data.get("parentType")
                page_link = response_data.get("_links", {}).get(
                    "base", ""
                ) + response_data.get("_links", {}).get("webui", "")

                # Create result dictionary with updated home page details
                result = {
                    "parentId": parent_id,
                    "spaceId": space_id,
                    "parentType": parent_type,
                    "versionNumber": version_number,
                    "bodyValue": body_value,
                    "title": title,
                    "pageLink": page_link,
                    "twikiProjectName": None,
                    "twikiPageName": None,
                    "twikiPageURL": None,
                    "twikiBaseURL": None,
                    "authorName": None,
                    "authorEmail": None
                }

                return result, page_id

    except requests.HTTPError as e:
        print(f"\nHTTPError: {e.response.status_code} - {e.response.reason}")
        return None, None
    except requests.RequestException as e:
        print(f"\nRequestException: {e}")
        return None, None
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        return None, None


def save_migration_summary(results_dir, migration_summary):
    # Load existing migration summary if it exists
    output_summary_file = os.path.join(results_dir, "migration_summary.json")
    existing_summary = {}
    if os.path.exists(output_summary_file):
        try:
            with open(output_summary_file, "r", encoding="utf-8") as f:
                existing_summary = json.load(f)
        except Exception as e:
            print(f"Error reading existing migration summary: {str(e)}")

    # Update existing summary with new information
    for space_key, summary_data in migration_summary.items():
        # There is only one datetime_key in summary_data
        datetime_key = next(iter(summary_data))
        datetime_data = summary_data[datetime_key]

        if space_key in existing_summary:
            # Get the latest version from existing entries
            existing_versions = [
                entry.get("version", 0)
                for entry in existing_summary[space_key].values()
            ]
            latest_version = max(existing_versions, default=0)

            # Update version
            datetime_data["version"] = latest_version + 1

            # Add new datetime entry
            existing_summary[space_key][datetime_key] = datetime_data
        else:
            # New space key, assign version 1
            datetime_data["version"] = 1
            existing_summary[space_key] = {datetime_key: datetime_data}

    # Save the updated summary to file
    with open(output_summary_file, "w", encoding="utf-8") as f:
        json.dump(existing_summary, f, indent=4, ensure_ascii=False)


def migrate_twiki_projects(twiki_urls):
    """
    Main function to execute the TWiki to Confluence migration process.

    This function:
    1. Migrates the WebTopicList page first
    2. Extracts links to other pages from WebTopicList
    3. Migrates all linked pages
    4. Updates all TWiki links to point to their Confluence equivalents
    5. Modifies the Confluence space home page to link to the migrated content
    6. Saves all migration details to a JSON file
    """

    # Create results directory if it doesn't exist
    results_dir = "results"
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)

    # # Retrieve TWiki URLs from twiki_urls.txt
    # twiki_urls = retrieve_urls()

    for twiki_url in twiki_urls:
        # Create a overall summary dict to store the TWiki URL migration status, number of pages migrated and admin list
        migration_summary = {}
        
        # Migrate WebTopicList content for the current TWiki project
        webTopicList_twiki = TWiki(url=twiki_url, base_url=os.getenv("BASE_URL"))
        
        content = None
        retry_flag = False
        iteration = 0
        while content is None:
            if iteration > 2:
                priont(f"Retry more than 3 times, skipped {webTopicList_twiki.url} page...")
                continue
            if retry_flag:
                # pause the script for 2s
                print("Pausing for 2 seconds before retry...")
                time.sleep(2)
                retry_flag = False
            # Fetch and parse the webpage content
            content = fetch_webpage(webTopicList_twiki.url, user.username, user.password)
            if content is None:
                print(f'Retry on fetching {webTopicList_twiki.url} page')
                retry_flag = True
                iteration += 1
            else:
                print(f'Content fetched from {webTopicList_twiki.url} page')

        soup = BeautifulSoup(content, "html.parser")

        # Extract and format the page_name
        webTopicList_twiki.set_project_page_name(soup)

        # Create project-specific log file path
        project_specific_results_dir = os.path.join(results_dir, webTopicList_twiki.project_name)
        if not os.path.exists(project_specific_results_dir):
            os.makedirs(project_specific_results_dir)
        log_file_path = os.path.join(project_specific_results_dir, "migration_log.txt")

        with log_to_file(log_file_path):
            try:
                # ====== Start: Require Create Confluence Space API access ======
                
                # Create new confluence space

                print(f'Creating new Confluence Space for project {webTopicList_twiki.project_name}')

                space_description = f'{webTopicList_twiki.project_name} Confluence Space migrated from TWiki {webTopicList_twiki.url}'

                test_space_key = webTopicList_twiki.project_name
                test_space_key_count = 0

                space_dict = None
                retry_flag = False
                while space_dict is None:
                    if test_space_key_count > 5:
                        break
                    if retry_flag:
                        # pause the script for 5s
                        print("\nPausing for 5 seconds before retry...")
                        time.sleep(5)
                        retry_flag = False
                    
                    space_dict = create_new_confluence_space(test_space_key, webTopicList_twiki.project_name, space_description)

                    if space_dict is None:
                        print("\nRetry on creating the new Confluence Space")
                        retry_flag = True
                        test_space_key_count += 1
                        test_space_key = webTopicList_twiki.project_name + str(test_space_key_count)

                if space_dict:
                    confluence_space_id = space_dict['id']
                    confluence_parent_id = space_dict['homepageId']
                    confluence_space_key = space_dict['key']

                    print('New Confluence Space created successfully')
                    print(f'Space ID: {confluence_space_id}')
                    print(f'Parent ID: {confluence_parent_id}')
                    print(f'Space Key: {confluence_space_key}')

                else:
                    print(f'Failed to create Confluence Space for TWiki project {webTopicList_twiki.project_name}')
                    current_datetime = datetime.datetime.now().isoformat()
                    # Overall Summary
                    migration_summary[webTopicList_twiki.project_name] = {
                        current_datetime: {
                            "version": 0,
                            "project_name": webTopicList_twiki.project_name,
                            "old_twiki_url": webTopicList_twiki.url,
                            "new_confluence_link": "None",
                            "admin_list": "None",
                            "success_migrated/total_pages": "0",
                            "percentage_migration": 0,
                            "status": "Fail",
                            "message": "Failed to create Confluence Space"
                        }
                    }
                    save_migration_summary(results_dir, migration_summary)
                    
                    continue

                print(f"\nStarting migration for project: {webTopicList_twiki.project_name}")
                print(f"TWiki URL: {webTopicList_twiki.url}")
                print("\nMigration starts with page WebTopicList")

                # Initialize dictionaries and lists to track migration progress
                topic_list = {}  # Details of all migrated pages
                topic_url_mapping = {}  # Mapping of TWiki URLs to Confluence URLs
                page_ids = []  # List of all Confluence page IDs
                home_page_id = ""  # Confluence space home page ID

                # Migrate WebTopicList page with retry until successful
                webTopicList_dict, page_id = None, None
                retry_flag = False
                iteration = 0
                while webTopicList_dict is None or page_id is None:
                    if iteration > 2:
                        print("\nMax retries (3 tries) exceeded for migrating WebTopicList page")
                        break
                    if retry_flag:
                        # pause the script for 60s
                        print("\nPausing for 60 seconds before retry...")
                        time.sleep(60)
                        retry_flag = False
                    webTopicList_dict, page_id, topic_url_mapping = migrate_twiki_page_to_confluence(
                        webTopicList_twiki, confluence_space_id, confluence_parent_id, topic_url_mapping
                    )
                    if webTopicList_dict is None or page_id is None:
                        print("\nRetry on migrating WebTopicList page")
                        retry_flag = True
                        iteration += 1

                # Store WebTopicList page details
                if webTopicList_dict:
                    topic_list[page_id] = {
                        "parentId": webTopicList_dict["parentId"],
                        "spaceId": webTopicList_dict["spaceId"],
                        "parentType": webTopicList_dict["parentType"],
                        "versionNumber": webTopicList_dict["versionNumber"],
                        # "bodyValue": webTopicList_dict["bodyValue"],
                        "bodyValueLenght": len(webTopicList_dict["bodyValue"]),
                        "title": webTopicList_dict["title"],
                        "pageLink": webTopicList_dict["pageLink"],
                        "twikiProjectName": webTopicList_dict["twikiProjectName"],
                        "twikiPageName": webTopicList_dict["twikiPageName"],
                        "twikiPageURL": webTopicList_dict["twikiPageURL"],
                        "twikiBaseURL": webTopicList_dict["twikiBaseURL"],
                        "authorName": webTopicList_dict["authorName"],
                        "authorEmail": webTopicList_dict["authorEmail"],
                    }
                    topic_url_mapping[webTopicList_dict["twikiPageURL"]] = webTopicList_dict[
                        "pageLink"
                    ]
                    page_ids.append(page_id)
                    home_page_id = webTopicList_dict["parentId"]

                    # Extract project details from the migrated WebTopicList page
                    project_name = topic_list[page_id]["twikiProjectName"]
                    page_name = topic_list[page_id]["twikiPageName"]
                    base_url = topic_list[page_id]["twikiBaseURL"]
                    page_link = topic_list[page_id]["pageLink"]
                    webTopicList_url = page_link 

                    # Read the local HTML content to extract links to other pages
                    pattern_topic_path = os.path.join(project_name, page_name, "pattern_topic.html")
                    with open(pattern_topic_path, "r", encoding="utf-8") as file:
                        html_content = file.read()

                    # Parse the HTML content
                    soup = BeautifulSoup(html_content, "html.parser")
                    
                    # Initialize links_dict with full_url: False (not migrated yet)
                    links_dict = {}
                    for a_tag in soup.select("div.patternTopic ul li a"):
                        href = a_tag.get("href")
                        # if href and not href.endswith("WebTopicList") and pages to include in migration
                        # pages_to_migrate = []
                        # if href and not href.endswith("WebTopicList") and any(href.endswith(page) for page in pages_to_migrate):
                        if href and not href.endswith("WebTopicList"):
                            full_url = base_url + href
                            links_dict[full_url] = False  # Initially mark as not migrated

                    iteration = 0

                    retry_flag = False
                    page_migration_status = {}
                    # Retry until all page migrations succeed
                    while not all(links_dict.values()):
                        if iteration > 2:
                            break
                        if retry_flag:
                            # pause the script for 60s
                            print("\nPausing for 60 seconds before retry...")
                            time.sleep(60)
                            retry_flag = False

                        print(f"\n================================================")
                        print(f"============= Migration Attempt #{iteration + 1} =============")

                        for i, (link, status) in enumerate(links_dict.items()):
                            if status:
                                continue  # Skip already migrated pages

                            print(f"\n{i}: {link}")
                            currentTwiki = TWiki(url=link, base_url=base_url)
                            currentTwiki_dict, page_id, topic_url_mapping = migrate_twiki_page_to_confluence(
                                currentTwiki, confluence_space_id, confluence_parent_id, topic_url_mapping
                            )

                            print("\nResult:")
                            if currentTwiki_dict is not None and page_id is not None:
                                # Store successful migration details
                                topic_list[page_id] = {
                                    "parentId": currentTwiki_dict["parentId"],
                                    "spaceId": currentTwiki_dict["spaceId"],
                                    "parentType": currentTwiki_dict["parentType"],
                                    "versionNumber": currentTwiki_dict["versionNumber"],
                                    # "bodyValue": currentTwiki_dict["bodyValue"],
                                    "bodyValueLenght": len(currentTwiki_dict["bodyValue"]),
                                    "title": currentTwiki_dict["title"],
                                    "pageLink": currentTwiki_dict["pageLink"],
                                    "twikiProjectName": currentTwiki_dict["twikiProjectName"],
                                    "twikiPageName": currentTwiki_dict["twikiPageName"],
                                    "twikiPageURL": currentTwiki_dict["twikiPageURL"],
                                    "twikiBaseURL": currentTwiki_dict["twikiBaseURL"],
                                    "authorName": currentTwiki_dict["authorName"],
                                    "authorEmail": currentTwiki_dict["authorEmail"],
                                }
                                topic_url_mapping[currentTwiki_dict["twikiPageURL"]] = (
                                    currentTwiki_dict["pageLink"]
                                )
                                page_ids.append(page_id)
                                page_migration_status[currentTwiki.page_name] = True
                                print("Page Name:", currentTwiki.page_name)
                                print("Status: Success")
                                links_dict[link] = True  # Mark as migrated
                            else:
                                page_migration_status[currentTwiki.page_name] = False
                                print("Page Name:", currentTwiki.page_name)
                                print("Status: Fail")

                        iteration += 1
                        retry_flag = True

                    # Phase 2: Modify all TWiki links to Confluence links in each page
                    print(f"\n================================================")
                    print("Links modification starts")
                    i = 0
                    for page_id in page_ids:
                        print(f'\n{i}: {topic_list[page_id]["twikiPageURL"]}')
                        page_id, version_number = modify_twiki_links_confluence_links(
                            topic_url_mapping,
                            project_name,
                            topic_list[page_id]["twikiPageName"],
                            page_id,
                            topic_list[page_id]["versionNumber"],
                            topic_list[page_id]["twikiBaseURL"],
                        )

                        print("\nResult:")
                        if page_id != None and version_number != None and version_number != topic_list[page_id]["versionNumber"]:
                            # Update the version number in topic_list
                            topic_list[page_id]["versionNumber"] = version_number
                            print("Page Name:", topic_list[page_id]["twikiPageName"])
                            print("Status: Success")
                        else:
                            print("Page Name:", topic_list[page_id]["twikiPageName"])
                            print("Status: Fail")
                        i += 1
                    print("\nLinks modification completed")

                    # Phase 3: Modify home page content to link to the migrated content
                    print("\nHome page modification starts")
                    homePage_dict, home_page_id = modify_upload_home_content(
                        project_name, home_page_id, webTopicList_url
                    )
                    if homePage_dict:
                        topic_list[home_page_id] = {
                            "parentId": homePage_dict["parentId"],
                            "spaceId": homePage_dict["spaceId"],
                            "parentType": homePage_dict["parentType"],
                            "versionNumber": homePage_dict["versionNumber"],
                            # "bodyValue": homePage_dict["bodyValue"],
                            "title": homePage_dict["title"],
                            "pageLink": homePage_dict["pageLink"],
                            "twikiProjectName": homePage_dict["twikiProjectName"],
                            "twikiPageName": homePage_dict["twikiPageName"],
                            "twikiPageURL": homePage_dict["twikiPageURL"],
                            "twikiBaseURL": homePage_dict["twikiBaseURL"],
                            "authorName": homePage_dict["authorName"],
                            "authorEmail": homePage_dict["authorEmail"]
                        }
                    print("\nHome page modification completed")

                    # Phase 4: Assign admin access to all author who made the recent edit to each page
                    # Use API to get user account id using email, then assign Admin access to the user

                    print("\nAssignment of Admin access for new Confluence Space starts")           
                    
                    # Collect unique author emails
                    unique_authors = {}  
                    for page_id, page_info in topic_list.items():
                        author_name = page_info.get("authorName")
                        author_email = page_info.get("authorEmail")
                        
                        if author_name is not None and author_email is not None:
                            # Add to unique authors dictionary with email as key
                            unique_authors[author_email] = author_name
                    
                    print(f"Found {len(unique_authors)} unique authors")
                    
                    successful_admin_email_assigned = ['Elwin.Chiong@amd.com']
                    # Assign admin access to each unique author
                    for author_email, author_name in unique_authors.items():
                        try:
                            print(f"\nAttempting to assign admin access to: {author_name} ({author_email})")
                            
                            admin_flag, admin_name, admin_email = assign_admin_access_to_user(
                                confluence_space_key, author_name, author_email
                            )

                            if admin_flag:
                                print(f"Successfully assigned admin access to: {admin_name} ({admin_email})")
                                successful_admin_email_assigned.append(admin_email)
                            else:
                                print(f"Failed to assign admin access to: {admin_name} ({admin_email})")
                        except Exception as e:
                            print(f"Error assigning admin access to {author_email}: {str(e)}")
                    
                    print("\nAssignment of Admin access for new Confluence Space completed")    
                    
                    # Save all migration details to a JSON file
                    output_filename = os.path.join(project_name, "results.json")
                    with open(output_filename, "w", encoding="utf-8") as f:
                        json.dump(topic_list, f, indent=4, ensure_ascii=False)

                    # Phase 5: Save results and clean up temporary files
                    # Copy the results file to the results directory with a project-specific name
                    source_file = os.path.join(project_name, "results.json")
                    destination_file = os.path.join(project_specific_results_dir, "results.json")
                    
                    # Copy the results file to the results directory with a project-specific name
                    if os.path.exists(source_file):
                        shutil.copy2(source_file, destination_file)
                        print(f"\nResults copied to: {destination_file}")
                    
                    # Clean up by removing the temporary project folder and all its contents
                    if os.path.exists(project_name):
                        shutil.rmtree(project_name)
                        print(f"Temporary folder '{project_name}' has been removed")

                    print(f"\nMigration completed successfully for project: {project_name}")
                    print(f"Migration details saved to: {destination_file}")
                    print(f"Migration log saved to: {log_file_path}")
                    print("===============================================================")
                    print(f"Project Name: {project_name}")
                    print(f"Old TWiki link: {webTopicList_twiki.url}")
                    print(f"New Confluence Link: {topic_list[home_page_id]['pageLink']}")
                    print(f"Confluence Space Key: {confluence_space_key}")
                    print(f"Admin assigned: {successful_admin_email_assigned}")
                    successful_migrations = sum(1 for status in page_migration_status.values() if status)
                    total_pages = len(page_migration_status)
                    print(f"TWiki pages migration success rate: {successful_migrations}/{total_pages}")
                    print(f"Migration percentage: {(successful_migrations / total_pages * 100) if total_pages > 0 else 0}")
                    print(f"Status: {'Success' if successful_migrations == total_pages else 'Partial Success'}")
                    print("===============================================================")

                    # Fill up the overall summary dict
                    current_datetime = datetime.datetime.now().isoformat()
                    migration_summary[confluence_space_key] = {
                        current_datetime: {
                            "version": 0,
                            "project_name": project_name,
                            "old_twiki_url": webTopicList_twiki.url,
                            "new_confluence_link": topic_list[home_page_id]['pageLink'],
                            "admin_list": successful_admin_email_assigned,
                            "success_migrated/total_pages": f"{successful_migrations}/{total_pages}" if total_pages > 0 else 0,
                            "percentage_migration": (successful_migrations / total_pages * 100) if total_pages > 0 else 0,
                            "status": "Success" if successful_migrations == total_pages else "Partial Success",
                            "message": "Migration completed successfully" if successful_migrations == total_pages else "Migration completed with partial success"
                        }
                    }

                    save_migration_summary(results_dir, migration_summary)
                else:
                    print(f"Error occurred when migrating the project: Failed to migrate WebTopicList page")
                    
                    # Read the local HTML content to extract links to other pages
                    pattern_topic_path = os.path.join(webTopicList_twiki.project_name, "TopicList", "pattern_topic.html")
                    with open(pattern_topic_path, "r", encoding="utf-8") as file:
                        html_content = file.read()

                    # Parse the HTML content
                    soup = BeautifulSoup(html_content, "html.parser")

                    total_number_of_pages = 0
                    
                    # Initialize links_dict with full_url: False (not migrated yet)
                    links_dict = {}
                    for a_tag in soup.select("div.patternTopic ul li a"):
                        href = a_tag.get("href")
                        # if href and not href.endswith("WebTopicList") and pages to include in migration
                        # pages_to_migrate = []
                        # if href and not href.endswith("WebTopicList") and any(href.endswith(page) for page in pages_to_migrate):
                        if href and not href.endswith("WebTopicList"):
                            total_number_of_pages += 1

                    current_datetime = datetime.datetime.now().isoformat()
                    # Overall Summary
                    migration_summary[confluence_space_key] = {
                        current_datetime: {
                            "version": 0,
                            "project_name": webTopicList_twiki.project_name,
                            "old_twiki_url": webTopicList_twiki.url,
                            "new_confluence_link": "None",
                            "admin_list": "None",
                            "success_migrated/total_pages": f"0/{total_number_of_pages}",
                            "percentage_migration": 0,
                            "status": "Fail",
                            "message": "Failed to migrate WebTopicList page"
                        }
                    }
                    save_migration_summary(results_dir, migration_summary)

                    # Clean up by removing the temporary project folder and all its contents
                    if os.path.exists(webTopicList_twiki.project_name):
                        shutil.rmtree(webTopicList_twiki.project_name)
                        print(f"Temporary folder '{webTopicList_twiki.project_name}' has been removed")

            except Exception as e:
                print(f"Error occurred when migrating the project: {str(e)}")
                current_datetime = datetime.datetime.now().isoformat()
                # Overall Summary
                migration_summary[confluence_space_key] = {
                    current_datetime: {
                        "version": 0,
                        "project_name": webTopicList_twiki.project_name,
                        "old_twiki_url": webTopicList_twiki.url,
                        "new_confluence_link": "None",
                        "admin_list": "None",
                        "success_migrated/total_pages": "0",
                        "percentage_migration": 0,
                        "status": "Fail",
                        "message": str(e)
                    }
                }
                save_migration_summary(results_dir, migration_summary)

                # Clean up by removing the temporary project folder and all its contents
                if os.path.exists(webTopicList_twiki.project_name):
                    shutil.rmtree(webTopicList_twiki.project_name)
                    print(f"Temporary folder '{webTopicList_twiki.project_name}' has been removed")


if __name__ == "__main__":
    twiki_urls = retrieve_urls()

    migrate_twiki_projects(twiki_urls)
