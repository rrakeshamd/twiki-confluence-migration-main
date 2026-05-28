def modify_space_home_content(project_name, webTopicList_url):
    try:
        with open('defaultHomePage.html', 'r', encoding='utf-8') as file:
            body_content = file.read()
    except FileNotFoundError:
        print("Error: defaultHomePage.html file not found")
        return ""

    print("Task: Modifying space home content")
    # Replace all occurrences of the literal strings (not using \b anymore)
    body_content = body_content.replace("project_name", project_name)
    body_content = body_content.replace("webTopicList_url", webTopicList_url)
    print("Response: Success with newly modified home content")

    return body_content

if __name__ == "__main__":
    project_name = 'test123'
    webTopicList_url = 'https://example.com/topic-list'

    beautified_content = modify_space_home_content(project_name, webTopicList_url)

    if beautified_content:
        print("\nPage Content Retrieved:")
        print(beautified_content)

        # Beautify and save
        try:
            output_file = "home_page_content2.html"
            with open(output_file, "w", encoding="utf-8") as file:
                file.write(beautified_content)

            print(f"Beautified content saved to {output_file}")
        except Exception as e:
            print(f"Error saving content to file: {e}")
    else:
        print("No body content found.")
