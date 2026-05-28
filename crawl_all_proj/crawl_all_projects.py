import requests
from bs4 import BeautifulSoup, NavigableString
import time
import re
import random
from urllib.parse import quote
import logging
from concurrent.futures import ThreadPoolExecutor
import csv
import os
from getpass import getpass
from dotenv import load_dotenv
import statistics

# Load environment variables from .env file
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("crawl_all_proj/crawler.log"),
        logging.StreamHandler()
    ]
)

# Define the base URL
BASE_URL = "https://twiki.amd.com/twiki/bin/view/"

# Excluded links for topic lists
EXCLUDED_LINKS = {
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
def read_project_file(projects_file):
    # Read project names from file
    with open(f'{projects_file}', 'r') as f:
        # Read lines and strip whitespace
        projects = [line.strip() for line in f if line.strip()]

    return projects

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

def save_twiki_url_to_file(project_name, url, status):
    """
    Save processed TWiki URLs ending with WebTopicList to files.
    
    Args:
        project_name (str): Name of the project
        url (str): The TWiki URL that was processed
        status (str): Processing status (Success, Error, etc.)
    """
    try:
        # Save to status file (all URLs with status)
        with open('crawl_status_twiki_urls.txt', 'a', encoding='utf-8') as f:
            f.write(f"{project_name}|{url}|{status}\n")
        
        # Save to success-only file (only successful URLs)
        if status == "Success":
            with open('../twiki_urls.txt', 'a', encoding='utf-8') as f:
                f.write(f"{url}\n")
                
    except Exception as e:
        logging.error(f"Error saving URL to file: {str(e)}")

# Function to count topics in a project
def count_topics(project_name):
    try:
        # Encode the project name for the URL
        encoded_project = quote(project_name)
        url = f"{BASE_URL}{encoded_project}/WebTopicList"
        
        # Add a random delay to avoid overloading the server
        time.sleep(random.uniform(0.5, 2.0))
        
        # Get credentials from environment variables or prompt user
        username = os.environ.get("USERNAME")
        password = os.environ.get("PASSWORD")

        # Fetch and parse the webpage content
        content = None
        max_retries = 3
        retry_count = 0
        
        while content is None and retry_count < max_retries:
            # Fetch and parse the webpage content
            content = fetch_webpage(url, username, password)
            if content is None:
                retry_count += 1
                logging.warning(f'Retry {retry_count}/{max_retries} on fetching {project_name} page')
                time.sleep(random.uniform(2.0, 5.0))  # Longer delay between retries
            else:
                logging.info(f'Content fetched from {project_name} page')
        
        if content is None:
            # Save failed URL to file
            save_twiki_url_to_file(project_name, url, f"Failed after {max_retries} retries")
            return project_name, 0, f"Failed after {max_retries} retries", "", ""
        
        # Parse the HTML
        soup = BeautifulSoup(content, 'html.parser')
        
        # Find the topic list (usually in a div with patternContent class)
        content_div = soup.find('div', class_='patternContent')
        if not content_div:
            save_twiki_url_to_file(project_name, url, "No content div found")
            return project_name, 0, "No content div found", "", ""
        
        # Find all list items in the content
        topics_list = content_div.find_all('li')
        if not topics_list:
            save_twiki_url_to_file(project_name, url, "No topics found")
            return project_name, 0, "No topics found", "", ""
        
        # Filter out excluded links
        filtered_topics = []
        for li in topics_list:
            a_tag = li.find('a')
            if a_tag and a_tag.get('href'):
                href = a_tag.get('href')
                # Skip excluded links and edit links
                if not any(excluded in href for excluded in EXCLUDED_LINKS) and "/twiki/bin/edit/" not in href:
                    filtered_topics.append(li)
        
        # Fetch WebChanges page to get last edited information
        changes_url = f"{BASE_URL}{encoded_project}/WebChanges"
        changes_content = None
        changes_retry_count = 0
        
        while changes_content is None and changes_retry_count < max_retries:
            changes_content = fetch_webpage(changes_url, username, password)
            if changes_content is None:
                changes_retry_count += 1
                logging.warning(f'Retry {changes_retry_count}/{max_retries} on fetching {project_name} WebChanges page')
                time.sleep(random.uniform(2.0, 5.0))  # Longer delay between retries
            else:
                logging.info(f'WebChanges content fetched from {project_name} page')
        
        last_edited_by = ""
        last_edited_on = ""
        
        if changes_content:
            changes_soup = BeautifulSoup(changes_content, 'html.parser')
            
            # Find the first search result in the pattern topic
            pattern_topic = changes_soup.find('div', class_='patternTopic')
            if pattern_topic:
                search_result = pattern_topic.find('div', class_='patternSearchResult')
                if search_result:
                    # Extract last edited by (author)
                    author_span = search_result.find('span', class_='twikiSRAuthor')
                    if author_span:
                        # Check if there's a direct <a> tag
                        author_link = author_span.find('a')
                        if author_link and author_link.get_text().strip() != '?':
                            last_edited_by = author_link.get_text().strip()
                        # Check if there's a twikiNewLink span (for users without pages)
                        else:
                            new_link_span = author_span.find('span', class_='twikiNewLink')
                            if new_link_span:
                                # Get the text directly from the span, excluding the "?" link
                                text_content = ''.join(child for child in new_link_span.contents 
                                                     if isinstance(child, NavigableString))
                                last_edited_by = text_content.strip()
                                print(f"? is found and change to {last_edited_by}")
                    
                    # Extract last edited date
                    rev_span = search_result.find('span', class_='twikiSRRev')
                    if rev_span and rev_span.find('a'):
                        date_link = rev_span.find('a')
                        if date_link.get('title'):
                            # Extract the date portion from the title attribute
                            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', date_link.get('title'))
                            if date_match:
                                last_edited_on = date_match.group(1)
        
        # Save successful URL to file
        save_twiki_url_to_file(project_name, url, "Success")
        
        # Return project name, count of topics, and last edited information
        return project_name, len(filtered_topics), "Success", last_edited_by, last_edited_on
    
    except Exception as e:
        logging.error(f"Error processing {project_name}: {str(e)}")
        # Save error URL to file
        url = f"{BASE_URL}{quote(project_name)}/WebTopicList"
        save_twiki_url_to_file(project_name, url, f"Error: {str(e)}")
        return project_name, 0, f"Error: {str(e)}", "", ""


def main(projects_file):
    results = []

    projects = read_project_file(projects_file)

    total_projects = len(projects)
    
    # Clear both files at the start
    try:
        # Initialize status file with header
        with open('crawl_status_twiki_urls.txt', 'w', encoding='utf-8') as f:
            f.write("# Format: ProjectName|URL|Status\n")
        
        # Initialize success-only file (no header, just URLs)
        with open('../twiki_urls.txt', 'w', encoding='utf-8') as f:
            f.write("")  # Empty file to start
            
        logging.info("Initialized crawl_status_twiki_urls.txt and twiki_urls.txt files")
    except Exception as e:
        logging.error(f"Error initializing files: {str(e)}")
    
    # Limit to only crawl 10 projects
    projects_to_crawl = min(total_projects, total_projects)
    limited_projects = projects[:projects_to_crawl]
    
    logging.info(f"Starting crawl of {projects_to_crawl} projects (out of {total_projects} total)")
    
    # Use ThreadPoolExecutor for concurrent requests
    with ThreadPoolExecutor(max_workers=10) as executor:
        for i, result in enumerate(executor.map(count_topics, limited_projects)):
            project_name, topic_count, status, last_edited_by, last_edited_on = result

            # Remove _ from project names
            project_name = project_name.replace("_", "")

            results.append((project_name, topic_count, status, last_edited_by, last_edited_on))
            
            # Log progress
            if (i + 1) % 5 == 0 or (i + 1) == projects_to_crawl:
                logging.info(f"Processed {i + 1}/{projects_to_crawl} projects")
    
    # Sort results by topic count (highest first)
    results.sort(key=lambda x: x[1], reverse=True)
    
    # Write results to CSV
    with open('project_topics_count.csv', 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Project', 'Topic Count', 'Status', 'LastEditedBy', 'LastEditedOn'])
        writer.writerows(results)
    
    # Print summary
    topic_counts = [count for _, count, _, _, _ in results]
    total_topics = sum(topic_counts)
    successful_projects = sum(1 for _, _, status, _, _ in results if status == "Success")
    
    # Calculate statistics
    mean_count = statistics.mean(topic_counts) if topic_counts else 0
    median_count = statistics.median(topic_counts) if topic_counts else 0
    
    # Calculate mode (might return multiple values if there's a tie)
    try:
        mode_count = statistics.mode(topic_counts) if topic_counts else 0
        mode_str = f"{mode_count}"
    except statistics.StatisticsError:
        # Handle case where there might be multiple modes
        mode_counts = statistics.multimode(topic_counts) if topic_counts else []
        mode_str = f"{mode_counts}"
    
    logging.info(f"Crawl complete. Found {total_topics} topics across {successful_projects} projects.")
    logging.info(f"Results saved to project_topics_count.csv")
    logging.info(f"All processed URLs saved to crawl_status_twiki_urls.txt")
    logging.info(f"Successful URLs only saved to twiki_urls.txt")

    logging.info(f"\n==================================================================================")

    # Print all projects since we're only testing with 10
    logging.info("All crawled projects by topic count:")
    for i, (project, count, status, last_edited_by, last_edited_on) in enumerate(results):
        edited_info = f" (Last edited by {last_edited_by} on {last_edited_on})" if last_edited_by and last_edited_on else ""
        status_info = f" [{status}]" if status != "Success" else ""
        logging.info(f"{i+1}. {project}: {count} topics{edited_info}{status_info}")

    logging.info(f"\n==================================================================================")

    logging.info(f"Statistics (based on {projects_to_crawl} projects):")
    logging.info(f"  - Total projects processed: {projects_to_crawl}")
    logging.info(f"  - Successful projects: {successful_projects}")
    logging.info(f"  - Failed projects: {projects_to_crawl - successful_projects}")
    logging.info(f"  - Total topics found: {total_topics}")
    logging.info(f"  - Mean topic count: {mean_count:.2f}")
    logging.info(f"  - Median topic count: {median_count}")
    logging.info(f"  - Mode topic count: {mode_str}")

if __name__ == "__main__":
    # Test with all_projects.txt
    projects_file = 'all_projects.txt'
    main(projects_file)