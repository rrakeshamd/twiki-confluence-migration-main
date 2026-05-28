from langchain_openai import AzureChatOpenAI
from langchain_core.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from langchain.schema import HumanMessage, SystemMessage
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Azure LLM configuration
url = "https://llm-api.amd.com"
api_version = "2024-02-01"
model_name = "GPT-4o"
max_tokens = 10000
headers = {
    "Ocp-Apim-Subscription-Key": os.getenv("LLM_GATEWAY_KEY"),
}


def modify_space_home_content(home_page_content, project_name, webTopicList_url):
    """
    Modify the Confluence space home page content to include migration information.

    This function uses an Azure OpenAI model to generate a custom welcome message
    that informs users about the migration from TWiki to Confluence while keeping
    the original Confluence onboarding content.

    Args:
        home_page_content (str): Original Confluence space home page content
        project_name (str): Name of the TWiki project that was migrated
        webTopicList_url (str): URL to the TopicList page in Confluence

    Returns:
        str: Modified Confluence space home page content in storage format
    """
    # Initialize Azure OpenAI chat model
    chat = AzureChatOpenAI(
        azure_endpoint=url,
        api_key="dummy",  # API key is handled via headers
        model=model_name,
        api_version=api_version,
        temperature=0,
        max_tokens=max_tokens,
        default_headers=headers,
        # Enable these for debugging
        # streaming=True,
        # callbacks=[StreamingStdOutCallbackHandler()]
    )

    # Define system message with content generation instructions
    system_message = """You are a Confluence documentation assistant trained to produce high-quality content in Confluence Storage Format (the XML-like markup format used by Confluence Cloud). Your task is to create a Home page for a newly migrated Confluence Space. You must:

    1. Use professional, welcoming, and informative tone.
    2. Structure the content using valid Confluence Storage Format elements such as <ac:structured-macro>, <h2>, <p>, <ul>, <strong>, etc.
    3. Maintain compatibility with Confluence Cloud rendering (no markdown or unsupported elements).
    4. Incorporate the existing content from retrieved_page_content.html as-is at the end of the page. This is the default onboarding guidance from Confluence and should not be modified.

    The goal is to blend a custom welcome message with the default onboarding content into a single seamless Home page.
    """

    # Define human message with specific content requirements
    human_message = f"""
    While keeping the original content from home_page_content, please generate a Confluence Storage Format page for the Home page of a newly migrated Confluence Space from a TWiki project named Project {project_name}.

    Conversion Rules:
    1. Do not include ```xml or any ``` content
    2. Output ONLY the generated content

    home_page_content:{home_page_content}
    Note: Keep home_page_content exactly the same, do not modify anything

    The generated content should:

    1. Start with a welcoming section informing users that this space was migrated from TWiki (Project {project_name}).
    2. Mention that Confluence is now the official documentation platform replacing TWiki and should be used moving forward.
    3. Check on the page TopicList (link using the TopicList URL) which shows all pages within this project space, TopicList URL: {webTopicList_url}
    4. Introduce the default onboarding content below as helpful guidance on how to use Confluence.
    5. Finally, include home_page_content after all the generated contents in the page. 
    
    Structure everything cleanly with panels or headings or bold wordings as appropriate. Make sure the result is valid Confluence Storage Format and ready to be published in a Confluence Cloud page.
    """

    # Prepare message list for the chat model
    messages = [
        SystemMessage(content=system_message),
        HumanMessage(content=human_message),
    ]

    # Invoke the chat model to generate the modified content
    # print("\n------- Streaming is starting -------")
    response = chat.invoke(messages)
    # print("\n--------- End of Streaming ----------")

    # Save the modified content to a file
    output_file_path = os.path.join(project_name, "space_home_content.html")
    with open(output_file_path, "w", encoding="utf-8") as output_file:
        output_file.write(response.content)
    # print(f"Converted content saved to: {output_file_path}")

    return response.content


# # Example usage
# home_file_path = '/workspaces/twiki-confluence-migration/retrieved_page_content.html'
# converted_content = modify_space_home_content(home_file_path, "Project Blue", "test")
# print(converted_content)
