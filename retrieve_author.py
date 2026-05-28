from retrieve_urls import retrieve_urls
from User import User
from TWiki import TWiki
import os
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup, NavigableString



# Load environment variables from .env file
load_dotenv()

# Initialize User object with credentials from environment variables
user = User(username=os.getenv("USERNAME"), password=os.getenv("PASSWORD"))

def retrieve_email(profile_url):
    email = None

    # Fetch the profile page content
    content = fetch_webpage(profile_url, user.username, user.password)
    if content is None:
        print(f"Failed to fetch profile page: {profile_url}")
        return None
    
    # Parse the content with BeautifulSoup
    soup = BeautifulSoup(content, "html.parser")
    
    # Find all mailto links
    mailto_links = soup.find_all("a", href=lambda href: href and href.startswith("mailto:"))
    
    if mailto_links:
        print(f'Number of mail links: {len(mailto_links)}')
        for link in mailto_links:
            # Extract email from href attribute
            email = link.get("href").replace("mailto:", "")
            # Check if the email domain is amd.com
            if email.endswith("@amd.com"):
                print(f"Found email: {email}")
            else:
                print(f"Email {email} doesn't have amd.com domain")
                email = None
    else:
        print("No email found in profile page")
    
    return email


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


def retrieve_author(soup):
    # Extract patternRevInfo content from patternTop div
    pattern_top = soup.find("div", class_="patternTop")
    author_name = None
    author_email = None

    if pattern_top:
        pattern_rev_info = pattern_top.find("span", class_="patternRevInfo")
        if pattern_rev_info:
            print(f"Found revision info: {pattern_rev_info.get_text(strip=True)}")
            
            # If you want to extract the date and author separately
            rev_text = pattern_rev_info.get_text(strip=True)
            author_link = pattern_rev_info.find("a", class_="twikiLink")
            if author_link:
                author_name = author_link.get_text(strip=True)
                author_href = author_link.get("href")
                print(f"Author: {author_name}")
                print(f"Author link: {author_href}")
                author_email = retrieve_email(f'{os.getenv("BASE_URL")}{author_href}')
            else:
                # Extract author from the revision text if link is not found
                if "," in rev_text and len(rev_text.split(",")) > 1:
                    author_name = rev_text.split(",")[1].strip("()?")
                    print(f"Author: {author_name}")
                else:
                    author_name = None
                    print(f"Author: None")
                
                print(f"Author link: None")
            
        else:
            print("No patternRevInfo found in patternTop")
    else:
        print("No patternTop div found")
    
    return author_name, author_email


if __name__ == "__main__":
    twiki_urls = retrieve_urls()

    for twiki_url in twiki_urls:
        print(twiki_url)

        content = None
        retry_flag = False
        iteration = 0
        while content is None:
            if iteration > 2:
                priont(f"Retry more than 3 times, skipped {twiki_url} page...")
                continue
            if retry_flag:
                # pause the script for 60s
                print("Pausing for 2 seconds before retry...")
                time.sleep(2)
                retry_flag = False
            # Fetch and parse the webpage content
            content = fetch_webpage(twiki_url, user.username, user.password)
            if content is None:
                print(f'Retry on fetching {twiki_url} page')
                retry_flag = True
                iteration += 1
            else:
                print(f'Content fetched from {twiki_url} page')

        soup = BeautifulSoup(content, "html.parser")
        author_name, author_email = retrieve_author(soup)

        print(author_name, author_email)

        input("Press enter to continue\n")