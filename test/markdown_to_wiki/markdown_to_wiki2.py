from langchain_openai import AzureChatOpenAI
from langchain_core.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from langchain.schema import HumanMessage, SystemMessage
import os
import re
import time
import random
from dotenv import load_dotenv
from chunk_utils import chunk_markdown

# Load environment variables from .env file
load_dotenv()

# Azure LLM configuration
url = "https://llm-api.amd.com"
api_version = "2024-02-01"
model_name = "GPT-4o"
max_tokens = 4000  # Reduced to a safer limit per chunk
headers = {
    "Ocp-Apim-Subscription-Key": os.getenv("LLM_GATEWAY_KEY"),
}

# Module-level singleton LLM client (avoid re-instantiation per call)
_chat_client = AzureChatOpenAI(
    azure_endpoint=url,
    api_key="dummy",  # API key is handled via headers
    model=model_name,
    api_version=api_version,
    temperature=0,
    max_tokens=max_tokens,
    default_headers=headers,
)


# chunk_markdown is imported from chunk_utils


def process_chunk_with_retry(chat, markdown_chunk, wiki_format, max_retries=5, recursion_depth=0):
    """
    Process a single markdown chunk with retry logic for rate limits
    
    Args:
        chat: LangChain chat model
        markdown_chunk (str): Chunk of markdown content
        wiki_format (str): Confluence wiki format guide
        max_retries (int): Maximum number of retry attempts
        recursion_depth (int): Current recursion depth to prevent infinite recursion
        
    Returns:
        str: Converted chunk in wiki format
    """
    # Prevent infinite recursion - add a maximum recursion depth
    if recursion_depth > 10:
        print(f"WARNING: Maximum recursion depth reached. Forcing chunk split by character count.")
        # Force split by character count when recursion gets too deep
        chunk_size = len(markdown_chunk) // 4  # Quarter the size each time
        if chunk_size < 1000:  # If chunks are getting too small, set a minimum
            chunk_size = 1000
            
        chunks = []
        for i in range(0, len(markdown_chunk), chunk_size):
            chunks.append(markdown_chunk[i:i+chunk_size])
            
        combined_result = ""
        for small_chunk in chunks:
            # Use a minimal wiki format
            minimal_format = "Headings: h1. h2. h3.\nLists: * # -\nFormatting: *bold* _italic_"
            small_result = process_chunk_with_minimal_format(chat, small_chunk, minimal_format, max_retries)
            combined_result += small_result + "\n"
            
        return combined_result.strip()
    
    # Define system message with conversion instructions
    system_message = """You are an expert markdown to Confluence Wiki Markup converter. 
    Convert markdown to Confluence Wiki Markup syntax, preserving structure and formatting. 
    Output only the converted content, no explanations or delimiters."""

    # Check if we need to trim the wiki format guide
    if len(wiki_format) > 5000:  # Drastically reduce size threshold
        # Extract just the essential parts of the wiki format guide
        wiki_format = "Headings: h1. h2. h3.\nLists: * # -\nFormatting: *bold* _italic_\nLinks: [link|url]\nTables: Use |cell|cell| format"
        print("Wiki format guide was minimized to essential elements")

    # Check if the markdown chunk is too large
    if len(markdown_chunk) > 5000:  # Reduce size threshold even further
        print(f"WARNING: Markdown chunk of size {len(markdown_chunk)} is too large, splitting further")
        
        # Split the chunk by characters if it's extremely large
        if len(markdown_chunk) > 100000:
            print("Extremely large chunk detected. Forcing split by character count.")
            chunk_size = 5000  # Set to a reasonable size
            chunks = []
            for i in range(0, len(markdown_chunk), chunk_size):
                chunks.append(markdown_chunk[i:i+chunk_size])
        else:
            # Split the chunk into smaller parts
            try:
                smaller_chunks = chunk_markdown(markdown_chunk, max_chunk_size=2500)
            except RecursionError:
                print("RecursionError during chunking. Forcing split by character count.")
                chunk_size = 2500
                chunks = []
                for i in range(0, len(markdown_chunk), chunk_size):
                    chunks.append(markdown_chunk[i:i+chunk_size])
                smaller_chunks = chunks
        
        combined_result = ""
        
        for small_chunk in smaller_chunks:
            # Process each smaller chunk with incremented recursion depth
            small_result = process_chunk_with_retry(chat, small_chunk, wiki_format, max_retries, recursion_depth + 1)
            combined_result += small_result + "\n"
            
        return combined_result.strip()

    # Define human message for chunk conversion
    human_message = f"""Convert this markdown chunk to follow the Confluence Wiki Markup syntax.
    
    Conversion Rules:
    1. Do not include ```confluence or any ``` content
    2. Output ONLY the converted wiki markup
    3. Preserve all content and formatting
    
    Please use this confluence Wiki Markup Guide for conversion guideline:
    {wiki_format}
    
    Markdown Chunk to Convert:
    {markdown_chunk}
    """

    # Prepare message list for the chat model
    messages = [
        SystemMessage(content=system_message),
        HumanMessage(content=human_message)
    ]

    # Initialize retry counter
    retry_count = 0
    
    # Try with exponential backoff
    while retry_count <= max_retries:
        try:
            response = chat.invoke(messages)
            print(f"Processed chunk of size {len(markdown_chunk)}")
            return response.content
        except Exception as e:
            error_str = str(e)
            retry_count += 1
            
            # Check for context length exceeded error
            if "context_length_exceeded" in error_str or "maximum context length" in error_str:
                print("Context length exceeded. Attempting to reduce input size...")
                
                # Further trim the wiki format guide
                if len(wiki_format) > 5000:
                    wiki_format = wiki_format[:2000] + "\n...\n" + wiki_format[-2000:]
                    print("Wiki format guide was drastically trimmed")
                    
                    # Create new messages with trimmed format
                    human_message = f"""Convert this markdown chunk to follow the Confluence Wiki Markup syntax.
                    
                    Conversion Rules:
                    1. Do not include ```confluence or any ``` content
                    2. Output ONLY the converted wiki markup
                    3. Preserve all content and formatting
                    
                    Basic Confluence Wiki Markup Rules:
                    {wiki_format}
                    
                    Markdown Chunk to Convert:
                    {markdown_chunk}
                    """
                    
                    messages = [
                        SystemMessage(content=system_message),
                        HumanMessage(content=human_message)
                    ]
                else:
                    # If we can't trim the format guide anymore, break the chunk into smaller pieces
                    print("Wiki format guide already minimized. Splitting markdown chunk...")
                    smaller_chunks = chunk_markdown(markdown_chunk, max_chunk_size=7000)
                    combined_result = ""
                    
                    for small_chunk in smaller_chunks:
                        # Recursive call with smaller chunks
                        small_result = process_chunk_with_retry(chat, small_chunk, wiki_format[:1000] + "\n...\n" + wiki_format[-1000:], max_retries)
                        combined_result += small_result + "\n"
                        
                    return combined_result.strip()
            
            # Check if it's a rate limit error (429)
            elif "429" in error_str:
                # Extract wait time if specified in the error message
                wait_time = 60  # Default wait time in seconds
                if "retry after" in error_str.lower():
                    try:
                        # Try to parse the suggested retry time
                        wait_str = re.search(r'retry after (\d+)', error_str.lower())
                        if wait_str:
                            wait_time = int(wait_str.group(1))
                    except:
                        pass  # Use default wait time if parsing fails
                
                # Add jitter to avoid thundering herd problem
                wait_time = wait_time + random.uniform(1, 5)
                
                # Exponential backoff
                wait_time = wait_time * (2 ** (retry_count - 1))
                
                print(f"Rate limit reached. Waiting for {wait_time:.1f} seconds before retry {retry_count}/{max_retries}...")
                time.sleep(wait_time)
            else:
                # For other errors, use a shorter retry with exponential backoff
                wait_time = 2 ** retry_count
                print(f"Error: {e}. Retrying in {wait_time} seconds. Attempt {retry_count}/{max_retries}")
                time.sleep(wait_time)
            
            # If we've reached max retries, give up and return empty string
            if retry_count > max_retries:
                print(f"Maximum retries reached. Skipping chunk.")
                return ""
    
    return ""  # In case of unexpected flow


# Add a new function to handle extreme cases with minimal formatting
def process_chunk_with_minimal_format(chat, markdown_chunk, wiki_format, max_retries=5):
    """Process chunk with minimal formatting when deep recursion occurs"""
    system_message = """Convert markdown to Confluence Wiki Markup in the simplest way possible."""
    human_message = f"""Convert this text to Confluence Wiki Markup.
    Basic rules: {wiki_format}
    Text to convert: {markdown_chunk}"""
    
    messages = [
        SystemMessage(content=system_message),
        HumanMessage(content=human_message)
    ]
    
    retry_count = 0
    while retry_count <= max_retries:
        try:
            response = chat.invoke(messages)
            return response.content
        except Exception as e:
            error_str = str(e)
            retry_count += 1
            wait_time = 2 ** retry_count
            
            if "429" in error_str:
                wait_time = 60 + random.uniform(1, 5)
                
            print(f"Error in minimal format conversion: {e}. Waiting {wait_time}s...")
            time.sleep(wait_time)
            
            if retry_count > max_retries:
                # As a last resort, return the original markdown
                print("Failed to convert with minimal format. Returning original markdown.")
                return markdown_chunk
    
    return markdown_chunk  # Return original if all else fails


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
    # Use module-level singleton LLM client
    chat = _chat_client

    # Read the markdown content from file
    try:
        print(f"Reading markdown file: {markdown_file_path}")
        with open(markdown_file_path, "r", encoding="utf-8") as file:
            markdown_content = file.read()
            
        # Handle extremely large files
        if len(markdown_content) > 1000000:  # If > 1MB, try to extract important sections
            print(f"Warning: Very large markdown file detected ({len(markdown_content)} bytes)")
            print("Attempting to extract and process key sections only")
            
            # Try to find content between headers
            header_pattern = re.compile(r'^(#{1,3})\s+', re.MULTILINE)
            header_matches = list(header_pattern.finditer(markdown_content))
            
            if len(header_matches) > 100:
                print(f"Found {len(header_matches)} headers, processing first 100 only")
                # Process only first 100 headers to avoid memory issues
                header_matches = header_matches[:100]
    except Exception as e:
        print(f"Error reading markdown file: {e}")
        return f"Error: Could not read markdown file - {str(e)}"

    # Use a simplified static wiki format guide to avoid large file reading
    wiki_format = """
    Headings:
    h1. Heading 1
    h2. Heading 2
    h3. Heading 3
    
    Lists:
    * Bullet 1
    * Bullet 2
    ** Sub-bullet
    # Numbered 1
    # Numbered 2
    ## Sub-number
    
    Links:
    [Link Text|URL]
    
    Text Formatting:
    *bold*
    _italic_
    {{monospace}}
    
    Tables:
    || Header 1 || Header 2 ||
    | Cell 1 | Cell 2 |
    
    Code Blocks:
    {code:language=python}
    def example():
        return "example"
    {code}
    
    Images:
    !image.jpg!
    """
    
    try:
        # Split the markdown into manageable chunks - use smaller chunks to avoid context limits
        chunks = chunk_markdown(markdown_content, max_chunk_size=2000) # Using smaller chunks
        print(f"Split content into {len(chunks)} chunks")
        
        # Process each chunk with retry logic
        converted_chunks = []
        for i, chunk in enumerate(chunks):
            print(f"Processing chunk {i+1}/{len(chunks)}")
            # Use a checkpoint file to track progress
            checkpoint_file = os.path.join(project_name, page_name, f"chunk_{i+1}.txt")
            os.makedirs(os.path.dirname(checkpoint_file), exist_ok=True)
            
            # Check if we already processed this chunk
            if os.path.exists(checkpoint_file):
                print(f"Using cached result for chunk {i+1}")
                with open(checkpoint_file, "r", encoding="utf-8") as f:
                    converted_chunk = f.read()
            else:
                # Process the chunk with retry logic
                converted_chunk = process_chunk_with_retry(chat, chunk, wiki_format, 5, 0)
                
                # Save this chunk result to cache
                with open(checkpoint_file, "w", encoding="utf-8") as f:
                    f.write(converted_chunk)
                    
                # Add a delay between chunks to avoid rate limits
                time.sleep(3)
                
            converted_chunks.append(converted_chunk)
        
        # Combine the converted chunks
        wiki_content = "\n".join(converted_chunks)
        
        # Add attachments section if needed
        if is_attachments and attachment is not None:
            # Similar retry logic for attachments processing
            attachments_system_message = """You are an expert at creating Confluence Wiki Markup tables.
            Convert the attachment information into a properly formatted Confluence Wiki Markup table."""

            attachments_human_message = f"""Create a Confluence Wiki Markup table for attachments.
            
            Instructions:
            1. Add h2 header "Attachments:" at the beginning
            2. Create a table with columns:
                - file_name (as hyperlink to download_link)
                - file_size
                - file_datetime_created
                - file_owner
                - file_comment
                
            Attachment Data:
            {attachment.to_string()}
            """

            messages = [
                SystemMessage(content=attachments_system_message),
                HumanMessage(content=attachments_human_message)
            ]

            # Process attachments with retry logic
            retry_count = 0
            max_retries = 5
            while retry_count <= max_retries:
                try:
                    attachments_response = chat.invoke(messages)
                    wiki_content += "\n\n" + attachments_response.content
                    break
                except Exception as e:
                    retry_count += 1
                    wait_time = 2 ** retry_count + random.uniform(1, 5)
                    print(f"Error processing attachments: {e}. Retrying in {wait_time:.1f} seconds.")
                    time.sleep(wait_time)
                    if retry_count > max_retries:
                        print("Failed to process attachments after maximum retries.")
                        break

        # Ensure the output directory exists
        os.makedirs(os.path.join(project_name, page_name), exist_ok=True)
        
        # Save the converted content to a file
        output_file_path = os.path.join(project_name, page_name, "wiki_content.txt")
        with open(output_file_path, "w", encoding="utf-8") as output_file:
            output_file.write(wiki_content)
        print(f"Converted content saved to: {output_file_path}")

        return wiki_content
        
    except RecursionError:
        error_msg = "Recursion error occurred during processing. The file may be too large or complex."
        print(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(error_msg)
        return error_msg


if __name__ == "__main__":
    print("Converting markdown to Confluence Wiki Markup...")
    markdown_file_path = '/workspaces/twiki-confluence-migration/BRMacro/Arl2data_SYNCF/pattern_topic.md'
    project_name = 'Test'
    page_name = 'test123'
    is_attachments = False
    attachment = None
    converted_content = convert_markdown_to_wiki(markdown_file_path, is_attachments, attachment, project_name, page_name)
    print("Conversion complete.")