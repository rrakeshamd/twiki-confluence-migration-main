import requests
from bs4 import BeautifulSoup
import os
import time


def get_twiki_projects():
    # download the page manually
    # go to the url, then right click on empty space and save it html file, name it "all_projects.html"
    url = "https://twiki.amd.com/twiki/bin/view/TWiki/WelcomeGuest"
    
    try:
        # Read the html_content from all_projects.html
        file_path = 'all_projects.html'
        if not os.path.exists(file_path):
            print(f"Error: {file_path} does not exist")
            return []
            
        with open(file_path, 'r', encoding='utf-8') as file:
            html_content = file.read()
            
        if not html_content:
            print("Error: HTML content is empty")
            return []
        
        # Parse HTML content
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find the ul element that starts with "Webs:"
        project_texts = []
        for ul in soup.find_all('ul'):
            # Check if the first element contains "Webs:"
            first_li = ul.find('li')
            if first_li and first_li.get_text().strip().startswith('Webs:'):
                # Get all <a> tags inside this first list item, skipping the first one
                a_tags = first_li.find_all('a')
                if len(a_tags) > 1:
                    for a_tag in a_tags[1:]:  # Skip the first <a> tag
                        project_name = a_tag.get_text(strip=True)
                        if project_name and project_name != "TWiki":  # Only add non-empty project names and exclude "TWiki"
                            project_texts.append(project_name)
                            print(f"Found project: {project_name}")
                
                print(f"Total projects found: {len(project_texts)}")
                break  # We've found the ul we're looking for, so exit the loop
            
        # Save to file
        if project_texts:
            with open('all_projects.txt', 'w') as file:
                for project in project_texts:
                    file.write(f"{project}\n")
            
            print(f"Successfully saved {len(project_texts)} projects to all_projects.txt")
        else:
            print("No projects found in the HTML")
            
        return project_texts
    
    except Exception as e:
        print(f"An error occurred: {e}")
    
    return []

if __name__ == "__main__":
    get_twiki_projects()