from confluence_api import delete_space
import json
import os

def display_spaces_paginated(space_keys, migration_summary, page_size=10):
    """Display spaces with pagination and search functionality"""
    if not space_keys:
        print("No spaces found in migration summary.")
        input("Press Enter to continue...")
        return
    
    filtered_spaces = space_keys[:]
    current_page = 0
    
    while True:
        os.system('clear')
        
        # Calculate pagination
        total_pages = (len(filtered_spaces) + page_size - 1) // page_size if filtered_spaces else 1
        start_idx = current_page * page_size
        end_idx = min(start_idx + page_size, len(filtered_spaces))
        
        # Display header
        print(f"\n{'='*60}")
        print(f"Confluence Spaces - Page {current_page + 1} of {total_pages}")
        if len(filtered_spaces) < len(space_keys):
            print(f"Showing {len(filtered_spaces)} filtered results")
        print(f"{'='*60}")
        
        # Display current page of spaces
        if filtered_spaces:
            for i in range(start_idx, end_idx):
                original_idx = space_keys.index(filtered_spaces[i]) + 1
                print(f"{original_idx}. {filtered_spaces[i]}")
        else:
            print("No spaces found matching search criteria.")
        
        # Display navigation options
        print(f"\n{'-'*60}")
        nav_options = []
        if current_page > 0:
            nav_options.append("p) Previous page")
        if current_page < total_pages - 1:
            nav_options.append("n) Next page")
        nav_options.append("s) Search spaces")
        nav_options.append("c) Clear search")
        nav_options.append("q) Back to main menu")
        
        print(" | ".join(nav_options))
        
        # Get user input
        user_input = input("\nSelect option: ").strip().lower()
        
        if user_input == 'q':
            break
        elif user_input == 'n' and current_page < total_pages - 1:
            current_page += 1
        elif user_input == 'p' and current_page > 0:
            current_page -= 1
        elif user_input == 's':
            search_term = input("Enter search term: ").strip()
            if search_term:
                search_term_lower = search_term.lower()
                filtered_spaces = [space for space in space_keys if search_term_lower in space.lower()]
                current_page = 0
                if not filtered_spaces:
                    print(f"No spaces found containing '{search_term}'")
                    input("Press Enter to continue...")
            else:
                print("Search term cannot be empty.")
                input("Press Enter to continue...")
        elif user_input == 'c':
            filtered_spaces = space_keys[:]
            current_page = 0
            print("Search cleared.")
        else:
            print("Invalid option. Please try again.")
            input("Press Enter to continue...")

def select_and_delete_spaces(space_keys, migration_summary, migration_summary_file):
    """Display spaces with selection interface similar to TWiki migration"""
    if not space_keys:
        print("No spaces found in migration summary.")
        input("Press Enter to continue...")
        return

    spaces_per_page = 10
    total_pages = (len(space_keys) + spaces_per_page - 1) // spaces_per_page
    current_page = 1
    selected_indices = set()  # Track selected spaces across all pages

    while True:
        os.system('clear')
        
        # Calculate start and end indices for current page
        start_idx = (current_page - 1) * spaces_per_page
        end_idx = min(start_idx + spaces_per_page, len(space_keys))
        
        # Display current page of spaces
        print(f"\n{'='*60}")
        print(f"Confluence Spaces - Page {current_page} of {total_pages}")
        print(f"Selected spaces: {len(selected_indices)} total")
        print(f"{'='*60}")
        
        for i, space_key in enumerate(space_keys[start_idx:end_idx], start_idx + 1):
            status = " [SELECTED]" if i in selected_indices else ""
            print(f"{i}. {space_key}{status}")
        
        # Display navigation and action options
        print(f"\n{'='*60}")
        print("Options:")
        if current_page > 1:
            print("p. Previous page")
        if current_page < total_pages:
            print("n. Next page")
        print("a. Select ALL spaces")
        print("c. Clear all selections")
        print("s. Show selected spaces")
        print("d. Delete selected spaces")
        print("q. Quit")
        print(f"{'='*60}")

        choice = input(f"\nSelect spaces (e.g., 1,3,5), use options above, or enter numbers: ").strip().lower()

        if choice == 'q':
            return
        elif choice == 'p' and current_page > 1:
            current_page -= 1
        elif choice == 'n' and current_page < total_pages:
            current_page += 1
        elif choice == 'a':
            selected_indices = set(range(1, len(space_keys) + 1))
            print(f"Selected all {len(space_keys)} spaces.")
            input("Press Enter to continue...")
        elif choice == 'c':
            selected_indices.clear()
            print("Cleared all selections.")
            input("Press Enter to continue...")
        elif choice == 's':
            if selected_indices:
                print(f"\nSelected spaces ({len(selected_indices)}):")
                for idx in sorted(selected_indices):
                    print(f"{idx}. {space_keys[idx - 1]}")
            else:
                print("No spaces selected.")
            input("Press Enter to continue...")
        elif choice == 'd':
            if selected_indices:
                selected_spaces = [space_keys[i - 1] for i in sorted(selected_indices)]
                print(f"\nYou selected {len(selected_spaces)} space(s) for deletion:")
                for space in selected_spaces:
                    print(f"  - {space}")
                
                confirm = input(f"\nAre you sure you want to delete these {len(selected_spaces)} space(s)? (yes/no): ").strip().lower()
                
                if confirm in ['yes', 'y']:
                    deleted_spaces = []
                    failed_spaces = []
                    
                    for selected_space in selected_spaces:
                        try:
                            # Delete the space
                            print(f"\nDeleting space: {selected_space}")
                            print(f"Running space deletion API...")

                            response = delete_space(selected_space)

                            if response.status_code == 200 or response.status_code == 202:
                                deleted_spaces.append(selected_space)
                                
                                # Update the latest version status to "deleted" instead of removing the space
                                if selected_space in migration_summary:
                                    # Get the latest timestamp (most recent entry)
                                    latest_timestamp = max(migration_summary[selected_space].keys())
                                    # Update the status to "deleted"
                                    migration_summary[selected_space][latest_timestamp]["status"] = "Deleted"
                                
                                # Remove the space from space_keys list for UI purposes
                                space_keys.remove(selected_space)
                                
                                # Update selected_indices to account for removed space
                                space_idx = selected_spaces.index(selected_space) + 1
                                if space_idx in selected_indices:
                                    selected_indices.remove(space_idx)
                                    
                            else:
                                failed_spaces.append(selected_space)
                                
                        except Exception as e:
                            print(f"Error deleting space {selected_space}: {str(e)}")
                            failed_spaces.append(selected_space)
                    
                    # Update the migration summary file if any spaces were deleted
                    if deleted_spaces:
                        try:
                            with open(migration_summary_file, "w") as file:
                                json.dump(migration_summary, file, indent=4)
                            print(f"\nMigration summary updated successfully.")
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
                    
                    # Recalculate pagination after deletion
                    total_pages = (len(space_keys) + spaces_per_page - 1) // spaces_per_page if space_keys else 1
                    if current_page > total_pages:
                        current_page = total_pages
                    
                    # Clear selections after deletion
                    selected_indices.clear()
                    
                    input("\nPress Enter to continue...")
                    
                else:
                    print("Deletion cancelled.")
                    input("Press Enter to continue...")
            else:
                print("No spaces selected for deletion.")
                input("Press Enter to continue...")
        else:
            # Parse comma-separated choices for current page
            try:
                page_start = (current_page - 1) * spaces_per_page + 1
                page_end = min(current_page * spaces_per_page, len(space_keys))
                
                choices = [int(x.strip()) for x in choice.split(',')]
                valid_choices = [c for c in choices if page_start <= c <= page_end]
                
                if valid_choices:
                    # Toggle selection for each choice
                    for choice_idx in valid_choices:
                        if choice_idx in selected_indices:
                            selected_indices.remove(choice_idx)
                        else:
                            selected_indices.add(choice_idx)
                    
                    selected_space_names = [space_keys[c - 1] for c in valid_choices]
                    print(f"Toggled selection for: {', '.join(selected_space_names)}")
                    input("Press Enter to continue...")
                else:
                    print(f"Invalid choice(s). Please enter numbers between {page_start} and {page_end}.")
                    input("Press Enter to continue...")
            except ValueError:
                print("Invalid input format. Please use comma-separated numbers (e.g., 1,3,5).")
                input("Press Enter to continue...")

def manual_delete_space(migration_summary, migration_summary_file):
    """Allow user to manually input space key for deletion"""
    while True:
        os.system('clear')
        print(f"\n{'='*60}")
        print("Manual Space Deletion")
        print(f"{'='*60}")
        
        space_key = input("Enter space key to delete (or 'q' to quit): ").strip()
        
        if space_key.lower() == 'q':
            return
            
        if not space_key:
            print("Space key cannot be empty.")
            input("Press Enter to continue...")
            continue
        
        # Check if space exists in migration summary
        if space_key not in migration_summary:
            print(f"Warning: Space '{space_key}' not found in migration summary.")
            proceed = input("Do you want to proceed with deletion anyway? (yes/no): ").strip().lower()
            if proceed not in ['yes', 'y']:
                continue
        else:
            # Check if space is already deleted
            latest_timestamp = max(migration_summary[space_key].keys())
            latest_status = migration_summary[space_key][latest_timestamp].get("status", "").lower()
            
            if latest_status == "deleted":
                print(f"Note: Space '{space_key}' is already marked as deleted.")
        
        # Confirm deletion
        print(f"\nYou are about to delete space: {space_key}")
        confirm = input("Are you sure you want to delete this space? (yes/no): ").strip().lower()
        
        if confirm in ['yes', 'y']:
            try:
                print(f"\nDeleting space: {space_key}")
                print("Running space deletion API...")
                
                response = delete_space(space_key)
                
                if response.status_code == 200 or response.status_code == 202:
                    print(f"✓ Successfully deleted space: {space_key}")
                    
                    # Update migration summary if space exists in it
                    if space_key in migration_summary:
                        latest_timestamp = max(migration_summary[space_key].keys())
                        migration_summary[space_key][latest_timestamp]["status"] = "Deleted"
                        
                        try:
                            with open(migration_summary_file, "w") as file:
                                json.dump(migration_summary, file, indent=4)
                            print("Migration summary updated successfully.")
                        except Exception as e:
                            print(f"Warning: Could not update migration summary: {str(e)}")
                    
                else:
                    print(f"✗ Failed to delete space: {space_key}")
                    print(f"API Response: {response.status_code} - {response.text}")
                    
            except Exception as e:
                print(f"✗ Error deleting space {space_key}: {str(e)}")
                
        else:
            print("Deletion cancelled.")
        
        input("\nPress Enter to continue...")

def main_menu():
    """Display main menu and get user choice"""
    print("\n" + "="*50)
    print("   Delete Confluence Spaces")
    print("=" * 50)
    print("1. List all spaces")
    print("2. Delete spaces (selection)")
    print("3. Delete space manually")
    print("q. Exit")
    print("-" * 50)
    
    while True:
        choice = input("Select an option (1-3, or 'q' to quit): ").strip()
        if choice in ['1', '2', '3']:
            return choice
        elif choice.lower() == 'q':
            return 'q'
        print("Please enter a valid option (1-3) or 'q' to quit")

def get_available_spaces(migration_summary):
    """Get list of spaces that are not marked as deleted in their latest version"""
    available_spaces = []
    
    for space_key, versions in migration_summary.items():
        # Get the latest timestamp (most recent entry)
        latest_timestamp = max(versions.keys())
        latest_status = versions[latest_timestamp].get("status", "").lower()
        
        # Only include spaces that are not marked as deleted
        if latest_status != "deleted":
            available_spaces.append(space_key)
    
    return available_spaces

def delete_confluence_spaces():

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

    # Extract only available (non-deleted) space keys from the migration summary
    space_keys = get_available_spaces(migration_summary)
    
    while True:
        os.system('clear')
        choice = main_menu()
        
        if choice == '1':
            # List all spaces with pagination and search
            if not space_keys:
                print("No available spaces found in migration summary.")
                print("All spaces have been deleted or no spaces exist.")
                input("Press Enter to continue...")
            else:
                display_spaces_paginated(space_keys, migration_summary)

        elif choice == '2':
            # Delete spaces with selection interface
            if not space_keys:
                print("No available spaces found in migration summary.")
                print("All spaces have been deleted or no spaces exist.")
                input("Press Enter to continue...")
            else:
                select_and_delete_spaces(space_keys, migration_summary, migration_summary_file)
        
        elif choice == '3':
            # Manual space deletion
            manual_delete_space(migration_summary, migration_summary_file)
                    
        elif choice == 'q':
            # Exit
            break



if __name__ == "__main__":
    delete_confluence_spaces()