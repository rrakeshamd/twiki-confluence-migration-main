import os
import sys
from utils import clear_screen

# Add the crawl_all_proj directory to the path so we can import modules from it
sys.path.append(os.path.join(os.path.dirname(__file__), 'crawl_all_proj'))

from get_all_projects_name import get_twiki_projects
from crawl_all_projects import main as crawl_projects

def display_menu():
    """Display the main menu options"""
    print("\n" + "="*50)
    print("   TWiki Projects Discovery Tool")
    print("="*50)
    print("1. Get all project names from TWiki")
    print("2. Get statistics for all projects")
    print("q. Exit")
    print("="*50)

def get_user_choice():
    """Get and validate user input"""
    while True:
        try:
            choice = input("\nPlease select an option (1-2, q): ").strip().lower()
            if choice in ['1', '2']:
                return int(choice)
            elif choice == 'q':
                return 'q'
            else:
                print("Invalid choice. Please enter 1, 2, or q.")
        except KeyboardInterrupt:
            print("\n\nExiting...")
            return 'q'
        except Exception:
            print("Invalid input. Please enter 1, 2, or q.")

def get_all_project_names():
    """Execute the get all project names functionality"""
    print("\n" + "="*60)
    print("Getting all TWiki project names...")
    print("="*60)
    
    # Check if all_projects.html exists
    html_file_path = os.path.join('crawl_all_proj', 'all_projects.html')
    if not os.path.exists(html_file_path):
        print(f"Error: {html_file_path} does not exist")
        print("\nTo use this feature:")
        print("1. Go to https://twiki.amd.com/twiki/bin/view/TWiki/WelcomeGuest")
        print("2. Save the page as 'all_projects.html' in the crawl_all_proj directory")
        print("3. Run this option again")
        input("\nPress Enter to continue...")
        return
    
    # Change to the crawl_all_proj directory to run the function
    original_dir = os.getcwd()
    try:
        os.chdir('crawl_all_proj')
        projects = get_twiki_projects()
        
        if projects:
            print(f"\n✓ Successfully extracted {len(projects)} project names")
            print("✓ Projects saved to 'crawl_all_proj/all_projects.txt'")
            
            # Show first 10 projects as preview
            print(f"\nPreview of first 10 projects:")
            for i, project in enumerate(projects[:10], 1):
                print(f"  {i}. {project}")
            
            if len(projects) > 10:
                print(f"  ... and {len(projects) - 10} more projects")
                
        else:
            print("✗ No projects were extracted. Please check the HTML file.")
            
    except Exception as e:
        print(f"✗ Error occurred: {str(e)}")
    finally:
        os.chdir(original_dir)
    
    input("\nPress Enter to continue...")

def get_project_statistics():
    """Execute the crawl all projects functionality"""
    print("\n" + "="*60)
    print("Getting statistics for all TWiki projects...")
    print("="*60)
    
    # Check if all_projects.txt exists
    projects_file_path = os.path.join('crawl_all_proj', 'all_projects.txt')
    if not os.path.exists(projects_file_path):
        print(f"Error: {projects_file_path} does not exist")
        print("\nPlease run option 1 first to get all project names.")
        input("\nPress Enter to continue...")
        return
    
    # Check credentials
    username = os.environ.get("USERNAME")
    password = os.environ.get("PASSWORD")
    
    if not username or not password:
        print("Error: USERNAME and PASSWORD environment variables must be set")
        print("\nPlease set your TWiki credentials in the .env file:")
        print("USERNAME=your_username")
        print("PASSWORD=your_password")
        input("\nPress Enter to continue...")
        return
    
    print("Starting project crawling and statistics generation...")
    print("This will:")
    print("- Crawl TWiki projects to count topics")
    print("- Generate statistics (mean, median, mode)")
    print("- Create CSV report with results")
    print("- Save successful URLs to twiki_urls.txt")
    print()
    
    # Ask for confirmation
    confirm = input("Do you want to continue? (yes/no): ").strip().lower()
    if confirm not in ['yes', 'y']:
        print("Operation cancelled.")
        input("Press Enter to continue...")
        return

    # Ask user to choose which projects file to load
    print("\nChoose projects file to load:")
    print("1. all_projects.txt (full project list)")
    print("2. all_projects_test.txt (test subset)")
    
    while True:
        file_choice = input("\nSelect file option (1-2): ").strip()
        if file_choice == '1':
            projects_file = 'all_projects.txt'
            break
        elif file_choice == '2':
            projects_file = 'all_projects_test.txt'
            break
        else:
            print("Invalid choice. Please enter 1 or 2.")
    
    # Verify the selected file exists
    selected_file_path = os.path.join('crawl_all_proj', projects_file)
    if not os.path.exists(selected_file_path):
        print(f"Error: {projects_file} does not exist in crawl_all_proj directory")
        input("Press Enter to continue...")
        return
    
    print(f"\nUsing projects file: {projects_file}")

    # Change to the crawl_all_proj directory to run the crawling
    original_dir = os.getcwd()
    try:
        os.chdir('crawl_all_proj')
        print(f"\nStarting crawl from directory: {os.getcwd()}")
        print("="*60)
        
        # Run the crawling function
        crawl_projects(projects_file)
        
        print("="*60)
        print("✓ Crawling completed successfully!")
        
        # Show generated files
        files_created = []
        if os.path.exists('project_topics_count.csv'):
            files_created.append('crawl_all_proj/project_topics_count.csv')
        if os.path.exists('crawl_status_twiki_urls.txt'):
            files_created.append('crawl_all_proj/crawl_status_twiki_urls.txt')
        if os.path.exists('../twiki_urls.txt'):
            files_created.append('twiki_urls.txt')
        if os.path.exists('crawler.log'):
            files_created.append('crawl_all_proj/crawler.log')
            
        if files_created:
            print(f"\nFiles created:")
            for file in files_created:
                print(f"  ✓ {file}")
        
    except Exception as e:
        print(f"✗ Error occurred during crawling: {str(e)}")
    finally:
        os.chdir(original_dir)
    
    input("\nPress Enter to continue...")

def get_all_twiki_urls():
    """Main function to run the TWiki URLs discovery tool"""
    while True:
        clear_screen()
        display_menu()
        choice = get_user_choice()
        
        if choice == 1:
            clear_screen()
            get_all_project_names()
            
        elif choice == 2:
            clear_screen()
            get_project_statistics()
            
        elif choice == 'q':
            print("\n[INFO] Exiting TWiki Projects Discovery Tool. Goodbye!")
            break

def main():
    """Entry point when running this file directly"""
    get_all_twiki_urls()

if __name__ == "__main__":
    main()