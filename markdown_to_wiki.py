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

def print_response_details(response):
    """
    Check if the response is successful.
    Handle different response types (LangChain response objects or HTTP responses).

    Args:
        response: Response object, could be from LangChain or requests library
        
    Returns:
        bool: True if response is successful, False otherwise
    """
    # For LangChain response objects
    if hasattr(response, 'content'):
        print(f"Response: Success with LangChain response")
        return True

    # For HTTP response objects
    if hasattr(response, 'status_code'):
        if response.status_code in (200, 201, 204):
            print(f"Response: Success with status code {response.status_code}")
            if hasattr(response, 'content') and response.content:
                print(f"Response content: {response.content[:100]}...")  # Print first 100 chars
            return True
        elif response.status_code == 429:
            print(f"Response: Rate limit exceeded (429). Please retry after a delay.")
            if hasattr(response, 'json'):
                try:
                    error_details = response.json()
                    if 'message' in error_details:
                        print(f"Error message: {error_details['message']}")
                    elif 'error' in error_details and 'message' in error_details['error']:
                        print(f"Error message: {error_details['error']['message']}")
                except:
                    print(f"Error details: {response.content}")
            return False
        else:
            print(f"Response: Failed with status code {response.status_code}")
            # Print error details
            if hasattr(response, 'content') and response.content:
                print(f"Error details: {response.content}")
            return False
    
    return False

def convert_markdown_to_wiki(
    markdown_file_path, is_attachments, attachment, project_name, page_name
):
    """
    Convert markdown content to Confluence wiki markup format using an Azure OpenAI model.

    Args:
        markdown_file_path (str): Path to the markdown file to convert
        is_attachments (bool): Whether there are attachments to include
        attachment (DataFrame): DataFrame containing attachment information
        project_name (str): Name of the project for file organization
        page_name (str): Name of the page for file organization

    Returns:
        str: The converted content in Confluence wiki markup format
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

    # Read the markdown content from file
    markdown_content = ""
    with open(markdown_file_path, "r", encoding="utf-8") as file:
        markdown_content = file.read()

    # Read the Confluence wiki format guide from file
    wiki_format = ""
    with open(
        os.path.join(os.getcwd(), "confluence_wiki_format.txt"), "r", encoding="utf-8"
    ) as file:
        wiki_format = file.read()

    # Define system message with conversion instructions
    system_message = """You are an expert markdown to Confluence Wiki Markup converter. Your task is to precisely transform markdown content into Confluence Wiki Markup syntax, ensuring:
    - Complete preservation of content structure
    - Accurate conversion of formatting elements
    - Intelligent handling of attachments
    - Strict output of only the converted content, no ```confluence or ``` symbol in the convered content
    """

    # Define human message with specific conversion requirements
    human_message = []
    if is_attachments:
        # If attachments exist, include instructions for creating an attachments table
        human_message = f"""Convert the markdown content to Confluence Wiki Markup syntax with attachment handling.
        Conversion Instructions:
        1. Transform markdown to Confluence Wiki Markup
        2. For the attachment_df:
            - Add h2 "Attachments:" at document end
            - Create a table with columns:
                file_name (as hyperlink to download_link)
                file_size
                file_datetime_created
                file_owner
                file_comment

        Conversion Rules:
        1. Do not include ```confluence or any ``` content
        2. Output ONLY the converted wiki markup

        Variables:
        wiki_format: Confluence Wiki Markup syntax guide
        markdown_content: Markdown content to convert
        attachment_df: DataFrame with attachment details

        Confluence Wiki Markup Syntax Guide:
        {wiki_format}
        Input Markdown Content:
        {markdown_content}
        Attachment Details:
        {attachment.to_string()}
        Conversion Output:
        """
    else:
        # If no attachments, provide simpler conversion instructions
        human_message = f"""Convert the markdown content to Confluence Wiki Markup syntax with attachment handling.
        Conversion Instructions:
        1. Transform markdown to Confluence Wiki Markup

        Conversion Rules:
        1. Do not include ```confluence or any ``` content
        2. Output ONLY the converted wiki markup

        Variables:
        wiki_format: Confluence Wiki Markup syntax guide
        markdown_content: Markdown content to convert

        Confluence Wiki Markup Syntax Guide:
        {wiki_format}
        Input Markdown Content:
        {markdown_content}
        Conversion Output:
        """

    # Prepare message list for the chat model
    messages = [
        SystemMessage(content=system_message),
        HumanMessage(content=human_message)
    ]

    print("\nTask: Converting markdown to wiki")
    
    # Invoke the chat model to perform the conversion
    response = chat.invoke(messages)

    flag = print_response_details(response)

    if flag:
        # Ensure the directory exists
        output_dir = os.path.join(project_name, page_name)
        os.makedirs(output_dir, exist_ok=True)
        
        # Save the converted content to a file
        output_file_path = os.path.join(output_dir, "wiki_content.txt")
        with open(output_file_path, "w", encoding="utf-8") as output_file:
            output_file.write(response.content)
        # print(f"Converted content saved to: {output_file_path}")

    return response.content, flag
    


if __name__ == "__main__":
    print("Testing Azure API...")
    markdown_file_path = '/workspaces/twiki-confluence-migration/BRMacro/BRespshell/pattern_topic.md'
    project_name = 'temp'
    page_name = 'temp123'
    is_attachments = False
    attachment = None
    converted_content, flag = convert_markdown_to_wiki(markdown_file_path, is_attachments, attachment, project_name, page_name)
    # print(converted_content)
