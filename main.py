from retrieve_urls import retrieve_urls
from migrate_twiki_projects import migrate_twiki_projects
from delete_confluence_spaces import get_available_spaces, manual_delete_space
from utils import clear_screen
import os
import json
from datetime import datetime
import pandas as pd
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from dotenv import load_dotenv
from analyze_error_from_log import analyze_error_from_log
from get_all_twiki_urls import get_all_twiki_urls

# Load environment variables from .env file
load_dotenv()

# SMTP credentials
default_recipients = os.getenv("default_recipients")
smtp_server = os.getenv("smtp_server")
smtp_port = os.getenv("smtp_port")
sender_email = os.getenv("sender_email")

def display_menu():
    """Display the main menu options"""
    print("\n" + "="*50)
    print("   TWiki to Confluence Migration Tool")
    print("="*50)
    print("1. Get all TWiki URLs")
    print("2. Check available TWiki URLs")
    print("3. Migrate TWiki projects")
    print("4. Check migration results")
    print("5. Manual delete Confluence spaces")
    print("q. Exit")
    print("="*50)

def get_user_choice():
    """Get and validate user input"""
    while True:
        try:
            choice = input("\nPlease select an option (1-4, q): ").strip().lower()
            if choice in ['1', '2', '3', '4', '5']:
                return int(choice)
            elif choice == 'q':
                return 'q'
            else:
                print("Invalid choice. Please enter 1, 2, 3, 4, 5, or q.")
        except KeyboardInterrupt:
            print("\n\nExiting...")
            return 'q'
        except Exception:
            print("Invalid input. Please enter 1, 2, 3, 4, 5, or q.")

def check_twiki_urls():
    # Retrieve TWiki URLs from twiki_urls.txt
    twiki_urls = retrieve_urls()
    
    if not twiki_urls:
        print("No TWiki URLs found.")
        input("Press Enter to continue...")
        return

    # Load project statistics from CSV file
    project_stats = {}
    csv_file_path = os.path.join('crawl_all_proj', 'project_topics_count.csv')
    
    try:
        if os.path.exists(csv_file_path):
            import pandas as pd
            df = pd.read_csv(csv_file_path)
            for _, row in df.iterrows():
                project_name = row['Project']
                project_stats[project_name] = {
                    'topic_count': row['Topic Count'],
                    'last_edited_by': row['LastEditedBy'] if pd.notna(row['LastEditedBy']) else 'Unknown',
                    'last_edited_on': row['LastEditedOn'] if pd.notna(row['LastEditedOn']) else 'Unknown'
                }
    except Exception as e:
        print(f"Warning: Could not load project statistics: {str(e)}")
        print("Topic counts and last edited info will not be displayed.")

    # Load existing migration summary to show migration status
    migration_status = {}
    try:
        with open('results/migration_summary.json', 'r') as f:
            migration_data = json.load(f)
        
        # Extract project names and their status from migration data
        for space_key, versions in migration_data.items():
            # Get the latest version to find project_name and status
            latest_timestamp = max(versions.keys())
            latest_data = versions[latest_timestamp]
            project_name = latest_data.get('project_name', '')
            status = latest_data.get('status', '').lower()
            
            if project_name:
                migration_status[project_name] = {
                    'status': status,
                    'space_key': space_key,
                    'success_percentage': latest_data.get('percentage_migration', 0),
                    'migration_ratio': latest_data.get('success_migrated/total_pages', 'N/A')
                }
                
    except (FileNotFoundError, json.JSONDecodeError):
        migration_status = {}

    def extract_topic_name(url):
        """Extract topic name from TWiki URL"""
        try:
            # Split by '/' and find the part after 'view' or 'viewauth'
            parts = url.split('/')
            for i, part in enumerate(parts):
                if part in ['view', 'viewauth'] and i + 1 < len(parts):
                    topic_name = parts[i + 1]
                    # Remove underscores and other symbols, keep only alphanumeric characters
                    cleaned_topic = ''.join(char for char in topic_name if char.isalnum())
                    return cleaned_topic
        except:
            pass
        return url  # Return original URL if extraction fails

    def sort_urls_by_date(urls):
        """Sort URLs by last edited date in descending order"""
        def get_sort_key(url):
            topic_name = extract_topic_name(url)
            stats = project_stats.get(topic_name, {})
            last_edited_on = stats.get('last_edited_on', 'Unknown')
            
            # Convert date to sortable format
            if last_edited_on and last_edited_on != 'Unknown':
                try:
                    # If it's already in YYYY-MM-DD format
                    if '-' in str(last_edited_on):
                        return str(last_edited_on)
                    else:
                        return '0000-00-00'  # Unknown dates go to bottom
                except:
                    return '0000-00-00'
            return '0000-00-00'
        
        return sorted(urls, key=get_sort_key, reverse=True)

    def get_migration_status_category(url):
        """Get migration status category for filtering"""
        topic_name = extract_topic_name(url)
        migration_info = migration_status.get(topic_name, {})
        status = migration_info.get('status', 'not migrated')
        
        if status == 'success' or status == 'partial success':
            return 'migrated'
        elif status == 'deleted':
            return 'deleted'
        elif status in ['fail', 'error']:
            return 'failed'
        else:
            return 'not migrated'

    def filter_by_migration_status(urls, status_filter, sort_by_percentage=True):
        """Filter URLs by migration status with optional sorting preference"""
        if not status_filter:
            return urls
        
        filtered_urls = [url for url in urls if get_migration_status_category(url) == status_filter.lower()]
        
        # Sort filtered data: if migrated status, use sort preference
        # Otherwise, keep the original date-based sorting
        if status_filter.lower() == 'migrated':
            if sort_by_percentage:
                def get_migration_percentage(url):
                    topic_name = extract_topic_name(url)
                    migration_info = migration_status.get(topic_name, {})
                    return migration_info.get('success_percentage', 0)
                
                filtered_urls.sort(key=get_migration_percentage, reverse=True)
            else:
                # Sort by last edited date (descending)
                def get_sort_key(url):
                    topic_name = extract_topic_name(url)
                    stats = project_stats.get(topic_name, {})
                    last_edited_on = stats.get('last_edited_on', 'Unknown')
                    
                    # Convert date to sortable format
                    if last_edited_on and last_edited_on != 'Unknown':
                        try:
                            # If it's already in YYYY-MM-DD format
                            if '-' in str(last_edited_on):
                                return str(last_edited_on)
                            else:
                                return '0000-00-00'  # Unknown dates go to bottom
                        except:
                            return '0000-00-00'
                    return '0000-00-00'
                
                filtered_urls.sort(key=get_sort_key, reverse=True)
        
        return filtered_urls

    # Sort URLs by last edited date by default
    twiki_urls = sort_urls_by_date(twiki_urls)

    # Paging setup
    urls_per_page = 10
    current_page = 1
    filtered_urls = twiki_urls[:]
    search_term = ""
    status_filter = ""  # New variable for status filtering
    migrated_sort_by_percentage = True  # Default to percentage sorting for migrated projects

    while True:
        # Calculate total pages for current filtered_urls
        total_pages = (len(filtered_urls) + urls_per_page - 1) // urls_per_page if filtered_urls else 1
        
        clear_screen()
        
        # Calculate start and end indices for current page
        start_idx = (current_page - 1) * urls_per_page
        end_idx = min(start_idx + urls_per_page, len(filtered_urls))
        
        # Display header information
        print(f"\n{'='*90}")
        print(f"Available TWiki Projects - Page {current_page} of {total_pages}")
        
        # Update sort description based on current filter
        if status_filter and status_filter.lower() == 'migrated':
            if migrated_sort_by_percentage:
                sort_description = "Sorted by Migration Percentage - highest first"
            else:
                sort_description = "Sorted by Last Edited Date - newest first"
        else:
            sort_description = "Sorted by Last Edited Date - newest first"
        
        print(f"Total TWiki URLs: {len(twiki_urls)} ({sort_description})")
        if len(filtered_urls) < len(twiki_urls):
            filters_applied = []
            if search_term:
                filters_applied.append(f"Search: '{search_term}'")
            if status_filter:
                filters_applied.append(f"Status: '{status_filter.title()}'")
            filter_text = " | ".join(filters_applied)
            print(f"Filtered results: {len(filtered_urls)} ({filter_text})")
        print(f"{'='*90}")
        
        # Print table header
        print(f"{'#':<3} {'Project Name':<20} {'Topics':<8} {'Last Edited By':<18} {'Last Edited On':<15} {'Migration Status'}")
        print("-" * 90)
        
        # Build O(1) index for display numbering
        twiki_url_index = {url: i + 1 for i, url in enumerate(twiki_urls)}

        # Display current page of URLs
        for i, url in enumerate(filtered_urls[start_idx:end_idx], start_idx + 1):
            topic_name = extract_topic_name(url)

            # Get project statistics
            stats = project_stats.get(topic_name, {})
            topic_count = stats.get('topic_count', 'N/A')
            last_edited_by = stats.get('last_edited_by', 'Unknown')[:17]  # Truncate for display
            last_edited_on = stats.get('last_edited_on', 'Unknown')

            # Format last edited date
            if last_edited_on and last_edited_on != 'Unknown':
                try:
                    # Convert to just date if it's in YYYY-MM-DD format
                    if '-' in str(last_edited_on):
                        last_edited_on = str(last_edited_on)[:10]
                except:
                    pass
            
            # Get migration status
            migration_info = migration_status.get(topic_name, {})
            status = migration_info.get('status', 'not migrated')
            
            # Format migration status for display
            if status == 'success' or status == 'partial success':
                migration_display = f"✓ Migrated ({migration_info.get('success_percentage', 0):.1f}%)"
            elif status == 'deleted':
                migration_display = "⚠ Deleted"
            elif status in ['fail', 'error']:
                migration_display = "✗ Failed"
            else:
                migration_display = "○ Not Migrated"
            
            # Calculate original index for display (O(1) lookup)
            original_idx = twiki_url_index.get(url, 0)
            
            print(f"{original_idx:<3} {topic_name[:19]:<20} {topic_count:<8} {last_edited_by:<18} {last_edited_on:<15} {migration_display}")
        
        # Display navigation and action options
        print(f"\n{'='*90}")
        print("Options:")
        if current_page > 1:
            print("p. Previous page")
        if current_page < total_pages:
            print("n. Next page")
        print("s. Search projects")
        if search_term:
            print("c. Clear search")
        print("f. Filter by migration status")
        if status_filter:
            print("cf. Clear status filter")
        # Add sort option only when filtered by "Migrated" status
        if status_filter and status_filter.lower() == 'migrated':
            if migrated_sort_by_percentage:
                print("st. Sort by last edited date (currently by migration percentage)")
            else:
                print("st. Sort by migration percentage (currently by last edited date)")
        print("v. View project details")
        print("q. Quit")
        print(f"{'='*90}")

        choice = input(f"\nSelect option or enter project number for details: ").strip().lower()

        if choice == 'q':
            return
        elif choice == 'p' and current_page > 1:
            current_page -= 1
        elif choice == 'n' and current_page < total_pages:
            current_page += 1
        elif choice == 's':
            new_search = input("Enter search term for project name: ").strip()
            if new_search:
                search_term = new_search
                search_term_lower = search_term.lower()
                
                # Apply both search and status filter
                temp_filtered = [url for url in twiki_urls if search_term_lower in extract_topic_name(url).lower()]
                if status_filter:
                    temp_filtered = filter_by_migration_status(temp_filtered, status_filter, migrated_sort_by_percentage)
                
                filtered_urls = temp_filtered
                current_page = 1
                if not filtered_urls:
                    print(f"No projects found containing '{search_term}'")
                    input("Press Enter to continue...")
                    # Reset search but keep status filter
                    search_term = ""
                    if status_filter:
                        filtered_urls = filter_by_migration_status(twiki_urls, status_filter, migrated_sort_by_percentage)
                    else:
                        filtered_urls = twiki_urls[:]
                    current_page = 1
        elif choice == 'c' and search_term:
            search_term = ""
            # Keep status filter if active
            if status_filter:
                filtered_urls = filter_by_migration_status(twiki_urls, status_filter, migrated_sort_by_percentage)
            else:
                filtered_urls = twiki_urls[:]
            current_page = 1
            print("Search cleared.")
        elif choice == 'f':
            print("\nAvailable migration status filters:")
            print("1. Migrated (Completely / Partially migrated projects)")
            print("2. Deleted (Deleted projects)")
            print("3. Failed (Failed migration projects)")
            print("4. Not Migrated (Projects not yet migrated)")
            
            filter_choice = input("\nSelect status filter (1-4): ").strip()
            
            status_map = {
                '1': 'migrated',
                '2': 'deleted', 
                '3': 'failed',
                '4': 'not migrated'
            }
            
            if filter_choice in status_map:
                status_filter = status_map[filter_choice]
                
                # Special handling for migrated status - ask for sort preference
                if status_filter == 'migrated':
                    print("\nSort migrated projects by:")
                    print("1. Migration Percentage (highest first) - Default")
                    print("2. Last Edited Date (newest first)")
                    
                    sort_choice = input("\nSelect sorting option (1-2, or Enter for default): ").strip()
                    migrated_sort_by_percentage = sort_choice != '2'  # Default to percentage unless user chooses 2
                
                # Apply both search and status filter
                temp_filtered = twiki_urls[:]
                if search_term:
                    search_term_lower = search_term.lower()
                    temp_filtered = [url for url in temp_filtered if search_term_lower in extract_topic_name(url).lower()]
                
                temp_filtered = filter_by_migration_status(temp_filtered, status_filter, migrated_sort_by_percentage)
                filtered_urls = temp_filtered
                current_page = 1
                
                if not filtered_urls:
                    print(f"No projects found with status '{status_filter.title()}'")
                    input("Press Enter to continue...")
                    # Reset status filter but keep search
                    status_filter = ""
                    migrated_sort_by_percentage = True  # Reset to default
                    if search_term:
                        search_term_lower = search_term.lower()
                        filtered_urls = [url for url in twiki_urls if search_term_lower in extract_topic_name(url).lower()]
                    else:
                        filtered_urls = twiki_urls[:]
                    current_page = 1
                else:
                    if status_filter == 'migrated':
                        sort_info = "by Migration Percentage (highest first)" if migrated_sort_by_percentage else "by Last Edited Date (newest first)"
                    else:
                        sort_info = "by Last Edited Date (newest first)"
                    print(f"Filtered by status: {status_filter.title()}")
                    print(f"Found {len(filtered_urls)} projects - sorted {sort_info}")
                    input("Press Enter to continue...")
            else:
                print("Invalid choice. Please select 1-4.")
                input("Press Enter to continue...")
        elif choice == 'cf' and status_filter:
            status_filter = ""
            migrated_sort_by_percentage = True  # Reset to default
            # Keep search filter if active
            if search_term:
                search_term_lower = search_term.lower()
                filtered_urls = [url for url in twiki_urls if search_term_lower in extract_topic_name(url).lower()]
            else:
                filtered_urls = twiki_urls[:]
            current_page = 1
            print("Status filter cleared.")
        elif choice == 'st' and status_filter and status_filter.lower() == 'migrated':
            # Toggle sort method for migrated projects
            migrated_sort_by_percentage = not migrated_sort_by_percentage
            
            # Re-apply current filters with new sort order
            temp_filtered = twiki_urls[:]
            if search_term:
                search_term_lower = search_term.lower()
                temp_filtered = [url for url in temp_filtered if search_term_lower in extract_topic_name(url).lower()]
            
            temp_filtered = filter_by_migration_status(temp_filtered, status_filter, migrated_sort_by_percentage)
            filtered_urls = temp_filtered
            current_page = 1
            
            sort_method = "Migration Percentage (highest first)" if migrated_sort_by_percentage else "Last Edited Date (newest first)"
            print(f"Sorting changed to: {sort_method}")
            input("Press Enter to continue...")
        elif choice == 'v':
            detail_input = input("Enter project number to view details: ").strip()
            try:
                detail_idx = int(detail_input) - 1
                if 0 <= detail_idx < len(twiki_urls):
                    url = twiki_urls[detail_idx]
                    topic_name = extract_topic_name(url)
                    
                    clear_screen()
                    print(f"\nProject Details - {topic_name}")
                    print("=" * 80)
                    print(f"Project Name: {topic_name}")
                    print(f"TWiki URL: {url}")
                    print(f"Project Number: {detail_idx + 1}")
                    
                    # Project statistics
                    stats = project_stats.get(topic_name, {})
                    print(f"Topic Count: {stats.get('topic_count', 'N/A')}")
                    print(f"Last Edited By: {stats.get('last_edited_by', 'Unknown')}")
                    print(f"Last Edited On: {stats.get('last_edited_on', 'Unknown')}")
                    
                    # Migration status details
                    migration_info = migration_status.get(topic_name, {})
                    if migration_info:
                        print(f"\nMigration Information:")
                        print(f"Status: {migration_info.get('status', 'not migrated').title()}")
                        print(f"Space Key: {migration_info.get('space_key', 'N/A')}")
                        print(f"Success Percentage: {migration_info.get('success_percentage', 0):.1f}%")
                        print(f"Migration Ratio: {migration_info.get('migration_ratio', 'N/A')}")
                    else:
                        print(f"\nMigration Information:")
                        print(f"Status: Not Migrated")
                        print(f"This project has not been migrated yet.")
                    
                    print("=" * 80)
                    input("Press Enter to continue...")
                else:
                    print(f"Invalid project number. Please enter a number between 1 and {len(twiki_urls)}.")
                    input("Press Enter to continue...")
            except ValueError:
                print("Please enter a valid number.")
                input("Press Enter to continue...")
        else:
            # Check if input is a project number for quick details
            try:
                project_num = int(choice)
                if 1 <= project_num <= len(twiki_urls):
                    url = twiki_urls[project_num - 1]
                    topic_name = extract_topic_name(url)
                    
                    # Quick info display
                    stats = project_stats.get(topic_name, {})
                    migration_info = migration_status.get(topic_name, {})
                    status = migration_info.get('status', 'not migrated')
                    
                    print(f"\nQuick Info - {topic_name}:")
                    print(f"Topics: {stats.get('topic_count', 'N/A')}")
                    print(f"Status: {status.title()}")
                    print(f"URL: {url}")
                    input("Press Enter to continue...")
                else:
                    print(f"Invalid project number. Please enter a number between 1 and {len(twiki_urls)}.")
                    input("Press Enter to continue...")
            except ValueError:
                print("Invalid option. Please try again.")
                input("Press Enter to continue...")

def start_twiki_confluence_migration():
    # Retrieve TWiki URLs from twiki_urls.txt
    twiki_urls = retrieve_urls()

    if not twiki_urls:
        print("No TWiki URLs found.")
        input("Press Enter to continue...")
        return

    # Load project statistics from CSV file
    project_stats = {}
    csv_file_path = os.path.join('crawl_all_proj', 'project_topics_count.csv')
    
    try:
        if os.path.exists(csv_file_path):
            import pandas as pd
            df = pd.read_csv(csv_file_path)
            for _, row in df.iterrows():
                project_name = row['Project']
                project_stats[project_name] = {
                    'topic_count': row['Topic Count'],
                    'last_edited_by': row['LastEditedBy'] if pd.notna(row['LastEditedBy']) else 'Unknown',
                    'last_edited_on': row['LastEditedOn'] if pd.notna(row['LastEditedOn']) else 'Unknown'
                }
    except Exception as e:
        print(f"Warning: Could not load project statistics: {str(e)}")
        print("Topic counts and last edited info will not be displayed.")

    # Load existing migration summary to filter out already migrated projects and show status
    migration_status = {}
    existing_project_names = set()
    deleted_project_names = set()
    
    try:
        with open('results/migration_summary.json', 'r') as f:
            migration_data = json.load(f)
        
        # Extract project names and their status from migration data
        for space_key, versions in migration_data.items():
            # Get the latest version to find project_name and status
            latest_timestamp = max(versions.keys())
            latest_data = versions[latest_timestamp]
            project_name = latest_data.get('project_name', '')
            status = latest_data.get('status', '').lower()
            
            if project_name:
                migration_status[project_name] = {
                    'status': status,
                    'space_key': space_key,
                    'success_percentage': latest_data.get('percentage_migration', 0),
                    'migration_ratio': latest_data.get('success_migrated/total_pages', 'N/A')
                }
                
                if status == 'deleted':
                    deleted_project_names.add(project_name)
                else:
                    existing_project_names.add(project_name)
                
    except (FileNotFoundError, json.JSONDecodeError):
        migration_status = {}

    def extract_topic_name(url):
        """Extract topic name from TWiki URL"""
        try:
            # Split by '/' and find the part after 'view' or 'viewauth'
            parts = url.split('/')
            for i, part in enumerate(parts):
                if part in ['view', 'viewauth'] and i + 1 < len(parts):
                    topic_name = parts[i + 1]
                    # Remove underscores and other symbols, keep only alphanumeric characters
                    cleaned_topic = ''.join(char for char in topic_name if char.isalnum())
                    return cleaned_topic
        except:
            pass
        return url  # Return original URL if extraction fails

    def sort_urls_by_date(urls):
        """Sort URLs by last edited date in descending order"""
        def get_sort_key(url):
            topic_name = extract_topic_name(url)
            stats = project_stats.get(topic_name, {})
            last_edited_on = stats.get('last_edited_on', 'Unknown')
            
            # Convert date to sortable format
            if last_edited_on and last_edited_on != 'Unknown':
                try:
                    # If it's already in YYYY-MM-DD format
                    if '-' in str(last_edited_on):
                        return str(last_edited_on)
                    else:
                        return '0000-00-00'  # Unknown dates go to bottom
                except:
                    return '0000-00-00'
            return '0000-00-00'
        
        return sorted(urls, key=get_sort_key, reverse=True)

    # Filter out URLs for projects that already exist in migration summary (excluding deleted ones)
    available_urls = []
    skipped_projects = []
    available_deleted_projects = []
    
    for url in twiki_urls:
        topic_name = extract_topic_name(url)  # This is the same as project_name
        if topic_name and topic_name in existing_project_names:
            # Project exists and is not deleted - skip it
            skipped_projects.append(topic_name)
        elif topic_name and topic_name in deleted_project_names:
            # Project exists but is deleted - include it but mark as deleted
            available_urls.append(url)
            available_deleted_projects.append(topic_name)
        else:
            # New project - include it
            available_urls.append(url)

    # Sort available URLs by last edited date by default
    available_urls = sort_urls_by_date(available_urls)

    # Show summary of filtering
    if skipped_projects or available_deleted_projects:
        if skipped_projects:
            print(f"\nFiltered out {len(skipped_projects)} successfully (completely / partially) migrated projects:")
            sorted_skipped = sorted(set(skipped_projects))
            for i, project in enumerate(sorted_skipped[:10]):
                print(f"  - {project}")
            if len(sorted_skipped) > 10:
                print(f"  ... and {len(sorted_skipped) - 10} more")
        
        if available_deleted_projects:
            print(f"\nIncluded {len(available_deleted_projects)} deleted projects available for re-migration:")
            sorted_deleted = sorted(set(available_deleted_projects))
            for i, project in enumerate(sorted_deleted[:10]):
                print(f"  - {project} [DELETED]")
            if len(sorted_deleted) > 10:
                print(f"  ... and {len(sorted_deleted) - 10} more")
        
        print(f"\nShowing {len(available_urls)} total projects available for migration (sorted by Last Edited Date).")
        if available_urls:
            input("Press Enter to continue...")

    if not available_urls:
        print("\nAll TWiki projects have been successfully migrated.")
        print("Check migration results to view existing projects or delete spaces to re-migrate.")
        input("Press Enter to continue...")
        return

    # Use available_urls instead of twiki_urls for the rest of the function
    twiki_urls = available_urls
    urls_per_page = 10
    current_page = 1
    selected_indices = set()  # Track selected topics across all pages

    while True:
        # Calculate total pages
        total_pages = (len(twiki_urls) + urls_per_page - 1) // urls_per_page
        
        clear_screen()
        
        # Calculate start and end indices for current page
        start_idx = (current_page - 1) * urls_per_page
        end_idx = min(start_idx + urls_per_page, len(twiki_urls))
        
        # Display current page of URLs
        print(f"\n{'='*100}")
        print(f"Available TWiki Projects - Page {current_page} of {total_pages}")
        print(f"Selected projects: {len(selected_indices)} total")
        if len(available_urls) < len(retrieve_urls()):
            original_count = len(retrieve_urls())
            successfully_migrated = len(skipped_projects)
            deleted_count = len(available_deleted_projects)
            print(f"Note: {successfully_migrated} completely / partially migrated projects filtered out")
            if deleted_count > 0:
                print(f"      {deleted_count} deleted projects available for re-migration")
            print(f"      Failed projects are not able to be migrated before it is deleted")
            print(f"      Please delete the failed projects before re-migration")
        print("Sorted by: Last Edited Date (newest first)")
        print(f"{'='*100}")
        
        # Print table header
        print(f"{'#':<3} {'Sel':<3} {'Project Name':<20} {'Topics':<8} {'Last Edited By':<18} {'Last Edited On':<15} {'Migration Status'}")
        print("-" * 100)
        
        for i, url in enumerate(twiki_urls[start_idx:end_idx], start_idx + 1):
            topic_name = extract_topic_name(url)
            
            # Selection status - simple indicator
            selection_indicator = "✓" if i in selected_indices else "○"
            
            # Get project statistics
            stats = project_stats.get(topic_name, {})
            topic_count = stats.get('topic_count', 'N/A')
            last_edited_by = stats.get('last_edited_by', 'Unknown')[:17]  # Truncate for display
            last_edited_on = stats.get('last_edited_on', 'Unknown')
            
            # Format last edited date
            if last_edited_on and last_edited_on != 'Unknown':
                try:
                    # Convert to just date if it's in YYYY-MM-DD format
                    if '-' in str(last_edited_on):
                        last_edited_on = str(last_edited_on)[:10]
                except:
                    pass
            
            # Get migration status (similar to check_twiki_urls)
            migration_info = migration_status.get(topic_name, {})
            status = migration_info.get('status', 'not migrated')
            
            # Format migration status for display (similar to check_twiki_urls)
            if status == 'success' or status == 'partial success':
                migration_display = f"✓ Migrated ({migration_info.get('success_percentage', 0):.1f}%)"
            elif status == 'deleted':
                migration_display = "⚠ Deleted"
            elif status in ['fail', 'error']:
                migration_display = "✗ Failed"
            else:
                migration_display = "○ Not Migrated"
            
            print(f"{i:<3} {selection_indicator:<3} {topic_name[:19]:<20} {topic_count:<8} {last_edited_by:<18} {last_edited_on:<15} {migration_display}")
        
        # Display navigation and action options
        print(f"\n{'='*100}")
        print("Options:")
        if current_page > 1:
            print("p. Previous page")
        if current_page < total_pages:
            print("n. Next page")
        print("a. Select ALL projects")
        print("c. Clear all selections")
        print("s. Show selected projects")
        print("m. Migrate selected projects")
        print("q. Quit")
        print(f"{'='*100}")

        choice = input(f"\nSelect projects (e.g., 1,3,5), use options above, or enter numbers: ").strip().lower()

        if choice == 'q':
            return
        elif choice == 'p' and current_page > 1:
            current_page -= 1
        elif choice == 'n' and current_page < total_pages:
            current_page += 1
        elif choice == 'a':
            selected_indices = set(range(1, len(twiki_urls) + 1))
            print(f"Selected all {len(twiki_urls)} projects.")
            input("Press Enter to continue...")
        elif choice == 'c':
            selected_indices.clear()
            print("Cleared all selections.")
            input("Press Enter to continue...")
        elif choice == 's':
            if selected_indices:
                print(f"\nSelected projects ({len(selected_indices)}):")
                print(f"{'#':<3} {'Sel':<3} {'Project Name':<20} {'Topics':<8} {'Last Edited By':<18} {'Last Edited On':<15} {'Migration Status'}")
                print("-" * 85)
                for idx in sorted(selected_indices):
                    topic_name = extract_topic_name(twiki_urls[idx - 1])
                    stats = project_stats.get(topic_name, {})
                    topic_count = stats.get('topic_count', 'N/A')
                    last_edited_by = stats.get('last_edited_by', 'Unknown')[:17]
                    last_edited_on = str(stats.get('last_edited_on', 'Unknown'))[:10]
                    
                    # Get migration status for selected view
                    migration_info = migration_status.get(topic_name, {})
                    status = migration_info.get('status', 'not migrated')
                    
                    if status == 'deleted':
                        migration_display = "⚠ Re-migration"
                    else:
                        migration_display = "○ New Migration"
                    
                    print(f"{idx:<3} {'✓':<3} {topic_name[:19]:<20} {topic_count:<8} {last_edited_by:<18} {last_edited_on:<15} {migration_display}")
            else:
                print("No projects selected.")
            input("Press Enter to continue...")
        elif choice == 'm':
            if selected_indices:
                selected_urls = [twiki_urls[i - 1] for i in sorted(selected_indices)]
                selected_topics = [extract_topic_name(url) for url in selected_urls]
                
                # Show which projects will be re-migrated
                new_projects = []
                re_migration_projects = []
                total_topics = 0
                
                print(f"\nMigration Summary:")
                print(f"{'Project Name':<20} {'Topics':<8} {'Type'}")
                print("-" * 45)
                
                for topic in selected_topics:
                    stats = project_stats.get(topic, {})
                    topic_count = stats.get('topic_count', 0)
                    if isinstance(topic_count, (int, float)):
                        total_topics += topic_count
                    
                    if topic in available_deleted_projects:
                        re_migration_projects.append(topic)
                        migration_type = "Re-migration"
                    else:
                        new_projects.append(topic)
                        migration_type = "New"
                    
                    print(f"{topic[:19]:<20} {topic_count:<8} {migration_type}")
                
                print("-" * 45)
                print(f"Total: {len(selected_topics)} projects, {total_topics} topics")
                
                if new_projects:
                    print(f"New migrations: {len(new_projects)} projects")
                if re_migration_projects:
                    print(f"Re-migrations: {len(re_migration_projects)} projects")
                
                # Ask user to confirm before starting migration
                start_input = input("\nType 'start' to begin migration or any other key to cancel: ").strip().lower()
                if start_input == 'start':
                    print("Starting migration...")
                    print(f"{'='*100}\n")
                    migrate_twiki_projects(selected_urls)
                    print(f"\n{'='*100}")
                    print("Migration completed.")
                    input("Press Enter to continue...")
                else:
                    print("Migration cancelled.")
                return
            else:
                print("No projects selected for migration.")
                input("Press Enter to continue...")
        else:
            # Parse comma-separated choices for current page
            try:
                page_start = (current_page - 1) * urls_per_page + 1
                page_end = min(current_page * urls_per_page, len(twiki_urls))
                
                choices = [int(x.strip()) for x in choice.split(',')]
                valid_choices = [c for c in choices if page_start <= c <= page_end]
                
                if valid_choices:
                    # Toggle selection for each choice
                    for choice_idx in valid_choices:
                        if choice_idx in selected_indices:
                            selected_indices.remove(choice_idx)
                        else:
                            selected_indices.add(choice_idx)
                    
                    selected_topics = [extract_topic_name(twiki_urls[c - 1]) for c in valid_choices]
                    print(f"Toggled selection for: {', '.join(selected_topics)}")
                    input("Press Enter to continue...")
                else:
                    print(f"Invalid choice(s). Please enter numbers between {page_start} and {page_end}.")
                    input("Press Enter to continue...")
            except ValueError:
                print("Invalid input format. Please use comma-separated numbers (e.g., 1,3,5).")
                input("Press Enter to continue...")

def check_migration_results():
    """Display migration results from migration_summary.json"""
    try:
        with open('results/migration_summary.json', 'r') as f:
            migration_data = json.load(f)
    except FileNotFoundError:
        print("No migration results found. Run a migration first.")
        input("Press Enter to continue...")
        return
    except json.JSONDecodeError:
        print("Error reading migration results file.")
        input("Press Enter to continue...")
        return

    if not migration_data:
        print("No migration data available.")
        input("Press Enter to continue...")
        return

    # Load project statistics from CSV file to get last edited info and topic counts
    project_stats = {}
    csv_file_path = os.path.join('crawl_all_proj', 'project_topics_count.csv')
    
    try:
        if os.path.exists(csv_file_path):
            import pandas as pd
            df = pd.read_csv(csv_file_path)
            for _, row in df.iterrows():
                project_name = row['Project']
                project_stats[project_name] = {
                    'last_edited_by': row['LastEditedBy'] if pd.notna(row['LastEditedBy']) else 'Unknown',
                    'last_edited_on': row['LastEditedOn'] if pd.notna(row['LastEditedOn']) else 'Unknown',
                    'topic_count': row['Topic Count'] if pd.notna(row['Topic Count']) else 0
                }
    except Exception as e:
        print(f"Warning: Could not load project statistics: {str(e)}")

    # Process data to get latest info for each project
    processed_data = []
    for space_key, versions in migration_data.items():
        # Get the latest version (most recent timestamp)
        latest_timestamp = max(versions.keys())
        latest_data = versions[latest_timestamp]
        
        project_name = latest_data.get('project_name', '')
        
        # Get project statistics
        stats = project_stats.get(project_name, {})
        
        # Get migration ratio from latest_data
        migration_ratio_raw = latest_data.get('success_migrated/total_pages', 'N/A')
        
        # If ratio is 0, N/A, or empty, use topic count from CSV as total pages
        if migration_ratio_raw in ['N/A', 0, '0', '', None] or (isinstance(migration_ratio_raw, str) and migration_ratio_raw.strip() == ''):
            topic_count = stats.get('topic_count', 0)
            if topic_count > 0:
                migration_ratio_display = f"0/{topic_count}"
            else:
                migration_ratio_display = "N/A"
        else:
            migration_ratio_display = str(migration_ratio_raw)
        
        processed_data.append({
            'project_name': project_name,
            'space_key': space_key,
            'latest_version': latest_data.get('version', 'N/A'),
            'latest_date': latest_timestamp,
            'migration_count': len(versions),
            'migration_ratio': migration_ratio_display,
            'success_percentage': latest_data.get('percentage_migration', 0),
            'status': latest_data.get('status', 'N/A'),
            'last_edited_by': stats.get('last_edited_by', 'Unknown'),
            'last_edited_on': stats.get('last_edited_on', 'Unknown'),
            'full_data': latest_data  # Store for detail view
        })

    # Sort by latest date (most recent first) - this is the default
    processed_data.sort(key=lambda x: x['latest_date'], reverse=True)

    # Paging setup
    page_size = 10
    current_page = 0
    filtered_data = processed_data[:]
    search_term = ""
    status_filter = ""  # New variable for status filtering
    total_pages = (len(filtered_data) + page_size - 1) // page_size

    def format_timestamp(timestamp_str):
        """Format timestamp for display"""
        try:
            dt = datetime.fromisoformat(timestamp_str)
            return dt.strftime("%Y-%m-%d %H:%M")
        except:
            return timestamp_str[:16]

    def format_date_only(date_str):
        """Format date for display (date only)"""
        if date_str and date_str != 'Unknown':
            try:
                # If it's already in YYYY-MM-DD format
                if '-' in str(date_str):
                    return str(date_str)[:10]
            except:
                pass
        return date_str

    def get_migration_status_category(item):
        """Get migration status category for filtering"""
        status = item['status'].lower()
        
        if status == 'success' or status == 'partial success':
            return 'migrated'
        elif status == 'deleted':
            return 'deleted'
        elif status in ['fail', 'error', 'failed']:
            return 'failed'
        else:
            return 'not migrated'

    def filter_by_migration_status(data, status_filter, sort_by_percentage=True):
        """Filter migration data by status with optional sorting preference"""
        if not status_filter:
            return data
        
        filtered_data = [item for item in data if get_migration_status_category(item) == status_filter.lower()]
        
        # Sort filtered data: if migrated status, use sort preference
        # Otherwise, sort by latest migration date (descending)
        if status_filter.lower() == 'migrated':
            if sort_by_percentage:
                filtered_data.sort(key=lambda x: x['success_percentage'], reverse=True)
            else:
                filtered_data.sort(key=lambda x: x['latest_date'], reverse=True)
        else:
            filtered_data.sort(key=lambda x: x['latest_date'], reverse=True)
        
        return filtered_data
    
    # Add sorting preference variable
    migrated_sort_by_percentage = True  # Default to percentage sorting for migrated projects

    def export_to_excel():
        """Export migration results to Excel file and optionally email it"""
        try:
            # Prepare data for Excel export
            export_data = []
            for i, item in enumerate(processed_data, 1):
                full_data = item['full_data']
                export_data.append({
                    'Project Number': i,
                    'Project Name': item['project_name'],
                    'Space Key': item['space_key'],
                    'Latest Version': item['latest_version'],
                    'Latest Migration Date': format_timestamp(item['latest_date']),
                    'Total Migrations': item['migration_count'],
                    'Migration Ratio': item['migration_ratio'],
                    'Success Percentage': f"{item['success_percentage']:.1f}%",
                    'Status': item['status'],
                    'Old TWiki URL': full_data.get('old_twiki_url', 'N/A'),
                    'New Confluence Link': full_data.get('new_confluence_link', 'N/A'),
                    'Admin Count': len(full_data.get('admin_list', []))
                })
            
            # Create DataFrame
            df = pd.DataFrame(export_data)
            
            # Create results directory if it doesn't exist
            os.makedirs('results', exist_ok=True)
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"results/migration_results_{timestamp}.xlsx"
            
            # Export to Excel
            df.to_excel(filename, index=False, engine='openpyxl')
            
            print(f"\nMigration results exported successfully to: {filename}")
            print(f"Total records exported: {len(export_data)}")
            
            # Ask if user wants to email the report
            email_choice = input("\nDo you want to email this report? (yes/no): ").strip().lower()
            
            if email_choice in ['yes', 'y']:
                send_email_report(filename, len(export_data))
            else:
                print("Report saved locally only.")
                
            input("Press Enter to continue...")
            
        except ImportError:
            print("\nError: Required libraries not found.")
            print("Please install pandas and openpyxl:")
            print("pip install pandas openpyxl")
            input("Press Enter to continue...")
        except Exception as e:
            print(f"\nError exporting to Excel: {str(e)}")
            input("Press Enter to continue...")

    def send_email_report(filename, record_count):
        """Send the Excel report via email using SMTP"""
        
        try:
            # Email configuration for Outlook
            
            recipient_emails = input("Enter recipient email(s) (comma-separated): ").strip()
            if not recipient_emails:
                print("Sending to default recipients list")
                recipient_emails = default_recipients
            else:
                recipient_emails += f",{default_recipients}"

            
            # Parse recipient emails
            recipients = [email.strip() for email in recipient_emails.split(',')]
            
            # Create message container
            msg = MIMEMultipart()
            msg['From'] = sender_email
            msg['To'] = ', '.join(recipients)
            msg['Subject'] = f"TWiki to Confluence Migration Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            
            # Create email body
            timestamp_str = datetime.now().strftime("%Y-%m-%d at %H:%M:%S")
            body = f"""
Dear Team,

Please find attached the TWiki to Confluence Migration Report generated on {timestamp_str}.

Report Summary:
- Total projects: {record_count}
- Generated from: migration_summary.json
- Export timestamp: {timestamp_str}

The attached Excel file contains detailed information about all migration activities including:
- Project names and space keys
- Migration dates and versions  
- Success percentages and ratios
- Current status of each project
- TWiki URLs and Confluence links
- Admin information

Best regards,
TWiki Migration Tool
"""
            
            # Attach body to email
            msg.attach(MIMEText(body, 'plain'))
            
            # Attach the Excel file
            if os.path.exists(filename):
                with open(filename, "rb") as attachment:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment.read())
                
                encoders.encode_base64(part)
                
                # Get just the filename without path for attachment name
                attachment_name = os.path.basename(filename)
                
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename= {attachment_name}',
                )
                
                msg.attach(part)
            else:
                print(f"Error: File {filename} not found.")
                return
            
            # First try: Port 25 without TLS (common for internal corporate servers)
            
            server = smtplib.SMTP(smtp_server, 25)
            
            # Send email
            print("Sending email...")
            text = msg.as_string()
            server.sendmail(sender_email, recipients, text)
            server.quit()
            
            print(f"✓ Email sent successfully to: {', '.join(recipients)}")
            print(f"Subject: {msg['Subject']}")
            print(f"Attachment: {os.path.basename(filename)}")
            print()
            return
                
        except smtplib.SMTPAuthenticationError:
            print("✗ SMTP Authentication failed.")
            print("For AMD corporate email:")
            print("1. Check if your password is correct")
            print("2. You might need to contact IT for SMTP access permissions")
            print("3. Some corporate servers may require special authentication")
            print("4. Try using your full email address as username")
        except smtplib.SMTPRecipientsRefused:
            print("✗ Recipients were refused by the server.")
            print("Check if the recipient email addresses are valid.")
        except smtplib.SMTPSenderRefused:
            print("✗ Sender was refused by the server.")
            print("Check if your sender email address is correctly configured.")
        except smtplib.SMTPConnectError:
            print("✗ Could not connect to SMTP server.")
            print("Check your network connection and server settings.")
            print(f"Server: {smtp_server}")
            print("You may need to contact IT for the correct SMTP settings.")
        except Exception as e:
            print(f"✗ Error sending email: {str(e)}")
            print("\nTroubleshooting tips:")
            print("1. Verify SMTP server address with IT department")
            print("2. Check if you need VPN connection")
            print("3. Confirm your email credentials")
            print("4. Check if SMTP access is enabled for your account")
        
        print()

    def delete_spaces_by_number():
        """Delete spaces by project number"""
        from confluence_api import delete_space
        
        delete_input = input("Enter project number(s) to delete (e.g., 1,3,5): ").strip()
        
        if not delete_input:
            print("No project numbers entered.")
            input("Press Enter to continue...")
            return
        
        try:
            # Parse comma-separated numbers
            project_numbers = [int(x.strip()) for x in delete_input.split(',')]
            
            # Validate project numbers
            valid_numbers = []
            invalid_numbers = []
            spaces_to_delete = []
            
            for num in project_numbers:
                if 1 <= num <= len(processed_data):
                    item = processed_data[num - 1]
                    # Check if already deleted
                    if item['status'].lower() == 'deleted':
                        print(f"Project #{num} ({item['space_key']}) is already deleted.")
                    else:
                        valid_numbers.append(num)
                        spaces_to_delete.append(item)
                else:
                    invalid_numbers.append(num)
            
            if invalid_numbers:
                print(f"Invalid project numbers: {', '.join(map(str, invalid_numbers))}")
                print(f"Valid range: 1-{len(processed_data)}")
            
            if not spaces_to_delete:
                print("No valid spaces to delete.")
                input("Press Enter to continue...")
                return
            
            # Display spaces to be deleted
            print(f"\nYou selected {len(spaces_to_delete)} space(s) for deletion:")
            for i, item in enumerate(spaces_to_delete, 1):
                print(f"  {i}. Project: {item['project_name']}")
                print(f"     Space Key: {item['space_key']}")
                print(f"     Status: {item['status']}")
                print()
            
            # Confirm deletion
            confirm = input(f"Are you sure you want to delete these {len(spaces_to_delete)} space(s)? (yes/no): ").strip().lower()
            
            if confirm not in ['yes', 'y']:
                print("Deletion cancelled.")
                input("Press Enter to continue...")
                return
            
            # Perform deletion
            deleted_spaces = []
            failed_spaces = []
            
            for item in spaces_to_delete:
                space_key = item['space_key']
                try:
                    print(f"\nDeleting space: {space_key}")
                    print("Running space deletion API...")
                    
                    response = delete_space(space_key)
                    
                    if response.status_code == 200 or response.status_code == 202:
                        deleted_spaces.append(space_key)
                        
                        # Update migration summary status to "Deleted"
                        if space_key in migration_data:
                            latest_timestamp = max(migration_data[space_key].keys())
                            migration_data[space_key][latest_timestamp]["status"] = "Deleted"
                        
                        print(f"✓ Successfully deleted space: {space_key}")
                        
                    else:
                        failed_spaces.append(space_key)
                        print(f"✗ Failed to delete space: {space_key}")
                        print(f"API Response: {response.status_code} - {response.text}")
                        
                except Exception as e:
                    failed_spaces.append(space_key)
                    print(f"✗ Error deleting space {space_key}: {str(e)}")
            
            # Update migration summary file if any spaces were deleted
            if deleted_spaces:
                try:
                    with open('results/migration_summary.json', 'w') as f:
                        json.dump(migration_data, f, indent=4)
                    print(f"\nMigration summary updated successfully.")
                    
                    # Update processed_data to reflect changes
                    for item in processed_data:
                        if item['space_key'] in deleted_spaces:
                            item['status'] = 'Deleted'
                            
                except Exception as e:
                    print(f"Error updating migration summary: {str(e)}")
            
            # Summary of results
            print(f"\n{'='*50}")
            print("DELETION SUMMARY")
            print(f"{'='*50}")
            
            if deleted_spaces:
                print(f"Successfully deleted {len(deleted_spaces)} space(s):")
                for space in deleted_spaces:
                    print(f"  ✓ {space}")
            
            if failed_spaces:
                print(f"\nFailed to delete {len(failed_spaces)} space(s):")
                for space in failed_spaces:
                    print(f"  ✗ {space}")
            
            input("\nPress Enter to continue...")
            
        except ValueError:
            print("Invalid input format. Please use comma-separated numbers (e.g., 1,3,5).")
            input("Press Enter to continue...")
        except Exception as e:
            print(f"Error processing deletion request: {str(e)}")
            input("Press Enter to continue...")

    def delete_space_by_key():
        """Delete space by manually entering space key"""
        from confluence_api import delete_space
        
        space_key = input("Enter space key to delete: ").strip()
        
        if not space_key:
            print("Space key cannot be empty.")
            input("Press Enter to continue...")
            return
        
        # Check if space exists in migration data
        space_found_in_data = False
        if space_key in migration_data:
            space_found_in_data = True
            # Check if already deleted
            latest_timestamp = max(migration_data[space_key].keys())
            latest_status = migration_data[space_key][latest_timestamp].get("status", "").lower()
            
            if latest_status == "deleted":
                print(f"Space '{space_key}' is already marked as deleted in migration data.")
                proceed = input("Do you want to proceed with deletion anyway? (yes/no): ").strip().lower()
                if proceed not in ['yes', 'y']:
                    return
        else:
            print(f"Warning: Space '{space_key}' not found in migration data.")
            proceed = input("Do you want to proceed with deletion anyway? (yes/no): ").strip().lower()
            if proceed not in ['yes', 'y']:
                return
        
        # Confirm deletion
        print(f"\nYou are about to delete space: {space_key}")
        confirm = input("Are you sure you want to delete this space? (yes/no): ").strip().lower()
        
        if confirm not in ['yes', 'y']:
            print("Deletion cancelled.")
            input("Press Enter to continue...")
            return
        
        try:
            print(f"\nDeleting space: {space_key}")
            print("Running space deletion API...")
            
            response = delete_space(space_key)
            
            if response.status_code == 200 or response.status_code == 202:
                print(f"✓ Successfully deleted space: {space_key}")
                
                # Update migration summary if space exists in it
                if space_found_in_data:
                    latest_timestamp = max(migration_data[space_key].keys())
                    migration_data[space_key][latest_timestamp]["status"] = "Deleted"
                    
                    try:
                        with open('results/migration_summary.json', 'w') as f:
                            json.dump(migration_data, f, indent=4)
                        print("Migration summary updated successfully.")
                        
                        # Update processed_data to reflect changes
                        for item in processed_data:
                            if item['space_key'] == space_key:
                                item['status'] = 'Deleted'
                                break
                                
                    except Exception as e:
                        print(f"Warning: Could not update migration summary: {str(e)}")
                
            else:
                print(f"✗ Failed to delete space: {space_key}")
                print(f"API Response: {response.status_code} - {response.text}")
                
        except Exception as e:
            print(f"✗ Error deleting space {space_key}: {str(e)}")
        
        input("\nPress Enter to continue...")

    def migrate_selected_spaces():
        """Migrate selected spaces that have 'Deleted' status"""
        from migrate_twiki_projects import migrate_twiki_projects
        
        # Filter spaces with 'Deleted' status
        deletable_spaces = [item for item in processed_data if item['status'].lower() == 'deleted']
        
        if not deletable_spaces:
            print("No spaces with 'Deleted' status found.")
            print("Only spaces with 'Deleted' status can undergo migration.")
            input("Press Enter to continue...")
            return
        
        print(f"\nSpaces available for migration (Status = 'Deleted'):")
        print("Note: Only spaces with 'Deleted' status can undergo migration.")
        print("-" * 60)
        print(f"{'#':<3} {'Project':<21} {'Space Key':<21}")
        print("-" * 60)

        for i, item in enumerate(deletable_spaces, 1):
            print(f"{i:<3} {item['project_name']:<21} {item['space_key']:<21}")
        print("-" * 60)
        
        migrate_input = input("Enter space number(s) to migrate (e.g., 1,3,5) or 'all' for all: ").strip().lower()
        
        if not migrate_input:
            print("No spaces selected.")
            input("Press Enter to continue...")
            return
        
        try:
            spaces_to_migrate = []
            
            if migrate_input == 'all':
                spaces_to_migrate = deletable_spaces[:]
            else:
                # Parse comma-separated numbers
                space_numbers = [int(x.strip()) for x in migrate_input.split(',')]
                
                # Validate space numbers
                invalid_numbers = []
                
                for num in space_numbers:
                    if 1 <= num <= len(deletable_spaces):
                        spaces_to_migrate.append(deletable_spaces[num - 1])
                    else:
                        invalid_numbers.append(num)
                
                if invalid_numbers:
                    print(f"Invalid space numbers: {', '.join(map(str, invalid_numbers))}")
                    print(f"Valid range: 1-{len(deletable_spaces)}")
                    input("Press Enter to continue...")
                    return
            
            if not spaces_to_migrate:
                print("No valid spaces selected for migration.")
                input("Press Enter to continue...")
                return
            
            # Display spaces to be migrated
            print(f"\nYou selected {len(spaces_to_migrate)} space(s) for migration:")
            for i, item in enumerate(spaces_to_migrate, 1):
                print(f"  {i}. Project: {item['project_name']}")
                print(f"     Space Key: {item['space_key']}")
                print()
            
            # Confirm migration
            confirm = input(f"Are you sure you want to migrate these {len(spaces_to_migrate)} space(s)? (yes/no): ").strip().lower()
            
            if confirm not in ['yes', 'y']:
                print("Migration cancelled.")
                input("Press Enter to continue...")
                return
            
            # Get TWiki URLs for selected spaces
            twiki_urls = []
            for item in spaces_to_migrate:
                full_data = item['full_data']
                old_twiki_url = full_data.get('old_twiki_url', '')
                if old_twiki_url and old_twiki_url != 'N/A':
                    twiki_urls.append(old_twiki_url)
                else:
                    print(f"Warning: No TWiki URL found for space {item['space_key']}")
            
            if not twiki_urls:
                print("No valid TWiki URLs found for migration.")
                input("Press Enter to continue...")
                return
            
            print(f"\nStarting migration for {len(twiki_urls)} space(s)...")
            print("=" * 60)
            
            # Perform migration
            migrate_twiki_projects(twiki_urls)
            
            print("=" * 60)
            print("Migration completed.")
            print("Check migration results for updated status.")
            input("Press Enter to continue...")
            
        except ValueError:
            print("Invalid input format. Please use comma-separated numbers (e.g., 1,3,5) or 'all'.")
            input("Press Enter to continue...")
        except Exception as e:
            print(f"Error processing migration request: {str(e)}")
            input("Press Enter to continue...")

    def view_project_details():
        detail_input = input("Enter project number to view details: ").strip()
        try:
            detail_idx = int(detail_input) - 1
            if 0 <= detail_idx < len(processed_data):
                item = processed_data[detail_idx]
                full_data = item['full_data']
                clear_screen()
                print(f"\nDetailed Migration Information")
                print("=" * 100)
                print(f"Project Name: {item['project_name']}")
                print(f"Space Key: {item['space_key']}")
                print(f"Latest Version: {item['latest_version']}")
                print(f"Total Migrations Performed: {item['migration_count']}")
                print(f"Latest Migration Date: {format_timestamp(item['latest_date'])}")
                print(f"Old TWiki URL: {full_data.get('old_twiki_url', 'N/A')}")
                print(f"New Confluence Link: {full_data.get('new_confluence_link', 'N/A')}")
                print(f"Migration Ratio: {item['migration_ratio']}")
                print(f"Success Percentage: {item['success_percentage']:.1f}%")
                print(f"Status: {item['status']}")
                print(f"Admin Count: {len(full_data.get('admin_list', []))}")
                print("=" * 100)
                print("Message:")
                print(f" - {full_data.get('message', 'N/A')}")
                if item['status'] != 'Success':
                    analyze_error_from_log(item['project_name'], full_data.get('message', 'N/A'))
                print("\n")
                print("=" * 100)
                input("Press Enter to continue...")
            else:
                print("Invalid project number.")
                input("Press Enter to continue...")
        except ValueError:
            print("Please enter a valid number.")
            input("Press Enter to continue...")

    while True:
        # Calculate total pages for current filtered_data
        total_pages = (len(filtered_data) + page_size - 1) // page_size if filtered_data else 1
        
        clear_screen()
        
        # Calculate start and end indices for current page
        start_idx = current_page * page_size
        end_idx = min(start_idx + page_size, len(filtered_data))
        
        # Display header information
        print(f"\n{'='*135}")
        print(f"Migration Results Summary - Page {current_page + 1} of {total_pages}")
        
        # Update sort description based on current filter
        if status_filter and status_filter.lower() == 'migrated':
            if migrated_sort_by_percentage:
                sort_description = "Sorted by Migration Percentage - highest first"
            else:
                sort_description = "Sorted by Latest Migration Date - newest first"
        else:
            sort_description = "Sorted by Latest Migration Date - newest first"
        
        print(f"Total Migration Records: {len(processed_data)} ({sort_description})")
        if len(filtered_data) < len(processed_data):
            filters_applied = []
            if search_term:
                filters_applied.append(f"Search: '{search_term}'")
            if status_filter:
                filters_applied.append(f"Status: '{status_filter.title()}'")
            filter_text = " | ".join(filters_applied)
            print(f"Filtered results: {len(filtered_data)} ({filter_text})")
        print(f"{'='*135}")
        
        # Print table header
        print(f"{'#':<3} {'Project Name':<20} {'Space Key':<15} {'Last Edited By':<18} {'Last Edited On':<15} {'Latest Migration':<18} {'Mig. Count':<10} {'Ratio':<8} {'Migration Status'}")
        print("-" * 135)
        
        # Display current page
        if filtered_data:
            for i in range(start_idx, end_idx):
                item = filtered_data[i]
                original_idx = processed_data.index(item) + 1
                
                project_name = item['project_name'][:19]
                space_key = item['space_key'][:14]
                last_edited_by = item['last_edited_by'][:17]
                last_edited_on = format_date_only(item['last_edited_on'])
                latest_migration = format_timestamp(item['latest_date'])[:17]
                migration_count = str(item['migration_count'])
                migration_ratio = str(item['migration_ratio'])[:7]
                
                # Format migration status similar to check_twiki_urls
                status = item['status'].lower()
                if status == 'success' or status == 'partial success':
                    migration_display = f"✓ Migrated ({item['success_percentage']:.1f}%)"
                elif status == 'deleted':
                    migration_display = "⚠ Deleted"
                elif status in ['fail', 'error', 'failed']:
                    migration_display = "✗ Failed"
                else:
                    migration_display = f"○ {status.title()}"
                
                print(f"{original_idx:<3} {project_name:<20} {space_key:<15} {last_edited_by:<18} {last_edited_on:<15} {latest_migration:<18} {migration_count:<10} {migration_ratio:<8} {migration_display}")
        else:
            print("No migration results to display.")
        
        # Display navigation and action options
        print(f"\n{'='*135}")
        print("Options:")
        if current_page > 0:
            print("p. Previous page")
        if current_page < total_pages - 1:
            print("n. Next page")
        print("s. Search projects")
        if search_term:
            print("c. Clear search")
        print("f. Filter by migration status")
        if status_filter:
            print("cf. Clear status filter")
        # Add sort option only when filtered by "Migrated" status
        if status_filter and status_filter.lower() == 'migrated':
            if migrated_sort_by_percentage:
                print("st. Sort by latest migration date (currently by migration percentage)")
            else:
                print("st. Sort by migration percentage (currently by latest migration date)")
        print("v. View project details")
        print("r. Re-migrate deleted spaces")
        print("d. Delete spaces by number")
        print("dd. Delete by space key")
        print("e. Export to Excel")
        print("q. Quit")
        print(f"{'='*135}")
        
        # Get user input
        user_input = input("\nSelect option or enter project number for details: ").strip().lower()
        
        if user_input == 'q':
            break
        elif user_input == 'n' and current_page < total_pages - 1:
            current_page += 1
        elif user_input == 'p' and current_page > 0:
            current_page -= 1
        elif user_input == 's':
            new_search = input("Enter search term for project name: ").strip()
            if new_search:
                search_term = new_search
                search_term_lower = search_term.lower()
                
                # Apply both search and status filter
                temp_filtered = [item for item in processed_data if search_term_lower in item['project_name'].lower()]
                if status_filter:
                    temp_filtered = filter_by_migration_status(temp_filtered, status_filter)
                
                filtered_data = temp_filtered
                current_page = 0
                if not filtered_data:
                    print(f"No projects found containing '{search_term}'")
                    input("Press Enter to continue...")
                    # Reset search but keep status filter
                    search_term = ""
                    if status_filter:
                        filtered_data = filter_by_migration_status(processed_data, status_filter)
                    else:
                        filtered_data = processed_data[:]
                    current_page = 0
        elif user_input == 'c' and search_term:
            search_term = ""
            # Keep status filter if active
            if status_filter:
                filtered_data = filter_by_migration_status(processed_data, status_filter)
            else:
                filtered_data = processed_data[:]
            current_page = 0
            print("Search cleared.")
        elif user_input == 'f':
            print("\nAvailable migration status filters:")
            print("1. Migrated (Completed / partially migrated projects)")
            print("2. Deleted (Deleted projects)")
            print("3. Failed (Failed migration projects)")
            print("4. Not Migrated (Projects not yet migrated)")
            
            filter_choice = input("\nSelect status filter (1-4): ").strip()
            
            status_map = {
                '1': 'migrated',
                '2': 'deleted', 
                '3': 'failed',
                '4': 'not migrated'
            }
            
            if filter_choice in status_map:
                status_filter = status_map[filter_choice]
                
                # Special handling for migrated status - ask for sort preference
                if status_filter == 'migrated':
                    print("\nSort migrated projects by:")
                    print("1. Migration Percentage (highest first) - Default")
                    print("2. Latest Migration Date (newest first)")
                    
                    sort_choice = input("\nSelect sorting option (1-2, or Enter for default): ").strip()
                    migrated_sort_by_percentage = sort_choice != '2'  # Default to percentage unless user chooses 2
                
                # Apply both search and status filter
                temp_filtered = processed_data[:]
                if search_term:
                    search_term_lower = search_term.lower()
                    temp_filtered = [item for item in temp_filtered if search_term_lower in item['project_name'].lower()]
                
                temp_filtered = filter_by_migration_status(temp_filtered, status_filter, migrated_sort_by_percentage)
                filtered_data = temp_filtered
                current_page = 0
                
                if not filtered_data:
                    print(f"No projects found with status '{status_filter.title()}'")
                    input("Press Enter to continue...")
                    # Reset status filter but keep search
                    status_filter = ""
                    migrated_sort_by_percentage = True  # Reset to default
                    if search_term:
                        search_term_lower = search_term.lower()
                        filtered_data = [item for item in processed_data if search_term_lower in item['project_name'].lower()]
                    else:
                        filtered_data = processed_data[:]
                    current_page = 0
                else:
                    if status_filter == 'migrated':
                        sort_info = "by Migration Percentage (highest first)" if migrated_sort_by_percentage else "by Latest Migration Date (newest first)"
                    else:
                        sort_info = "by Latest Migration Date (newest first)"
                    print(f"Filtered by status: {status_filter.title()}")
                    print(f"Found {len(filtered_data)} projects - sorted {sort_info}")
                    input("Press Enter to continue...")
            else:
                print("Invalid choice. Please select 1-4.")
                input("Press Enter to continue...")
        elif user_input == 'cf' and status_filter:
            status_filter = ""
            migrated_sort_by_percentage = True  # Reset to default
            # Keep search filter if active, but return to default date sorting
            if search_term:
                search_term_lower = search_term.lower()
                filtered_data = [item for item in processed_data if search_term_lower in item['project_name'].lower()]
            else:
                filtered_data = processed_data[:]
            current_page = 0
            print("Status filter cleared.")
        elif user_input == 'st' and status_filter and status_filter.lower() == 'migrated':
            # Toggle sort method for migrated projects
            migrated_sort_by_percentage = not migrated_sort_by_percentage
            
            # Re-apply current filters with new sort order
            temp_filtered = processed_data[:]
            if search_term:
                search_term_lower = search_term.lower()
                temp_filtered = [item for item in temp_filtered if search_term_lower in item['project_name'].lower()]
            
            temp_filtered = filter_by_migration_status(temp_filtered, status_filter, migrated_sort_by_percentage)
            filtered_data = temp_filtered
            current_page = 0
            
            sort_method = "Migration Percentage (highest first)" if migrated_sort_by_percentage else "Latest Migration Date (newest first)"
            print(f"Sorting changed to: {sort_method}")
            input("Press Enter to continue...")
        elif user_input == 'e':
            export_to_excel()
        elif user_input == 'r':
            migrate_selected_spaces()
        elif user_input == 'd':
            delete_spaces_by_number()
        elif user_input == 'dd':
            delete_space_by_key()
        elif user_input == 'v':
            view_project_details()
        else:
            # Check if input is a project number for quick details
            try:
                project_num = int(user_input)
                if 1 <= project_num <= len(processed_data):
                    item = processed_data[project_num - 1]
                    
                    # Quick info display
                    print(f"\nQuick Info - {item['project_name']}:")
                    print(f"Space Key: {item['space_key']}")
                    print(f"Status: {item['status'].title()}")
                    print(f"Success: {item['success_percentage']:.1f}%")
                    print(f"Ratio: {item['migration_ratio']}")
                    print(f"Migrations: {item['migration_count']}")
                    input("Press Enter to continue...")
                else:
                    print(f"Invalid project number. Please enter a number between 1 and {len(processed_data)}.")
                    input("Press Enter to continue...")
            except ValueError:
                print("Invalid option. Please try again.")
                input("Press Enter to continue...")


def manual_delete_confluence_spaces():
    # Save all migration details to a JSON file
    migration_summary_file = os.path.join("results", "migration_summary.json")

    # Read content from migration_summary.json
    try:
        with open(migration_summary_file, "r") as file:
            migration_summary = json.load(file)
    except FileNotFoundError:
        print("Error: migration_summary.json not found.")
        input("Press Enter to return to main menu...")
        return
    except json.JSONDecodeError:
        print("Error: Invalid JSON in migration_summary.json.")
        input("Press Enter to return to main menu...")
        return

    
    # Get list of spaces that are not marked as deleted in their latest version
    space_keys = []
    
    for space_key, versions in migration_summary.items():
        # Get the latest timestamp (most recent entry)
        latest_timestamp = max(versions.keys())
        latest_status = versions[latest_timestamp].get("status", "").lower()

    manual_delete_space(migration_summary, migration_summary_file)


def main():
    """Main menu loop"""
    while True:
        clear_screen()
        display_menu()
        choice = get_user_choice()
        
        if choice == 1:
            clear_screen()
            print("\n[INFO] Crawl all TWiki projects WebTopicList URLs...")
            get_all_twiki_urls()

        elif choice == 2:
            clear_screen()
            print("\n[INFO] Checking available TWiki URLs...")
            check_twiki_urls()

        elif choice == 3:
            clear_screen()
            print("\n[INFO] Starting TWiki to Confluence migration...")
            start_twiki_confluence_migration()
            
        elif choice == 4:
            clear_screen()
            print("\n[INFO] Checking migration results...")
            check_migration_results()
            
        elif choice == 5:
            clear_screen()
            print("\n[INFO] Manual deleting Confluence spaces...")
            manual_delete_confluence_spaces()
            
        elif choice == 'q':
            print("\n[INFO] Exiting the application. Goodbye!")
            break

if __name__ == "__main__":
    main()
