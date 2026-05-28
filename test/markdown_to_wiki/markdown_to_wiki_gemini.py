import requests
import json
import os
import re
from dotenv import load_dotenv

load_dotenv()
# API endpoint
url = "https://llm-api.amd.com/vertex/gemini/gemini-1.5-pro-002/text"


def chunk_markdown(markdown_content, max_chunk_size=4000):
    """
    Split markdown content into manageable chunks based on headers.
    
    Args:
        markdown_content (str): The full markdown content
        max_chunk_size (int): Maximum size of each chunk in characters
        
    Returns:
        list: List of markdown chunks
    """
    # Split by headers (# or ## or ###)
    header_pattern = re.compile(r'^(#{1,3})\s+', re.MULTILINE)
    
    # Find all header positions
    header_matches = list(header_pattern.finditer(markdown_content))
    
    if not header_matches:
        # If no headers found, just return the whole content as one chunk if it's small enough
        if len(markdown_content) <= max_chunk_size:
            return [markdown_content]
        else:
            # Or split by paragraphs
            paragraphs = re.split(r'\n\s*\n', markdown_content)
            chunks = []
            current_chunk = ""
            
            for paragraph in paragraphs:
                if len(current_chunk) + len(paragraph) + 2 <= max_chunk_size:
                    current_chunk += paragraph + "\n\n"
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = paragraph + "\n\n"
            
            if current_chunk:
                chunks.append(current_chunk.strip())
            
            return chunks
    
    # Get the start positions of each header
    chunk_positions = [match.start() for match in header_matches]
    chunk_positions.append(len(markdown_content))  # Add the end of the text
    
    chunks = []
    for i in range(len(chunk_positions) - 1):
        chunk = markdown_content[chunk_positions[i]:chunk_positions[i+1]]
        
        # Further split if chunk is too large
        if len(chunk) > max_chunk_size:
            # Split large chunks by paragraphs
            paragraphs = re.split(r'\n\s*\n', chunk)
            current_chunk = ""
            
            for paragraph in paragraphs:
                if len(current_chunk) + len(paragraph) + 2 <= max_chunk_size:
                    current_chunk += paragraph + "\n\n"
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = paragraph + "\n\n"
            
            if current_chunk:
                chunks.append(current_chunk.strip())
        else:
            chunks.append(chunk)
    
    return chunks


def process_chunk(markdown_chunk, wiki_format):
    """
    Process a single markdown chunk into Confluence Wiki markup
    
    Args:
        markdown_chunk (str): Chunk of markdown content
        wiki_format (str): Confluence wiki format guide
        
    Returns:
        str: Converted chunk in wiki format
    """
    system_message = """You are an expert markdown to Confluence Wiki Markup converter. 
    Convert markdown to Confluence Wiki Markup syntax, preserving structure and formatting. 
    Output only the converted content, no explanations or delimiters."""

    human_message = f"""Convert this markdown chunk to Confluence Wiki Markup:

    Confluence Wiki Markup Guide:
    {wiki_format}
    
    Markdown Content to Convert:
    {markdown_chunk}
    
    Important: Return ONLY the converted Confluence Wiki Markup with no extra text or explanations.
    """
    
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "Ocp-Apim-Subscription-Key": os.getenv("LLM_GATEWAY_KEY")
    }
    
    payload = {
        "prompt": f"{system_message}\n\n{human_message}",
        "temperature": 0.2,
        "top_P": 0.95,
        "top_K": 40,
        "max_Output_Tokens": 8000  # Reduced to safe limit per chunk
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        
        result = response.json()
        print(f"Processed chunk of size {len(markdown_chunk)}")
        
        # Extract the content from the response
        if 'candidates' in result and len(result['candidates']) > 0:
            return result['candidates'][0]['content']['parts'][0]['text']
        else:
            print("Warning: Unexpected response format")
            return ""
            
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP Error processing chunk: {http_err}")
        print(f"Response content: {response.text}")
        return ""
    except Exception as e:
        print(f"Error processing chunk: {e}")
        return ""


def convert_markdown_to_wiki(
    markdown_file_path, is_attachments, attachment, project_name, page_name
):
    """
    Convert markdown content to Confluence wiki markup format using Gemini model.

    Args:
        markdown_file_path (str): Path to the markdown file to convert
        is_attachments (bool): Whether there are attachments to include
        attachment (DataFrame): DataFrame containing attachment information
        project_name (str): Name of the project for file organization
        page_name (str): Name of the page for file organization

    Returns:
        str: The converted content in Confluence wiki markup format
    """
    
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

    # Split the markdown into manageable chunks
    chunks = chunk_markdown(markdown_content)
    print(f"Split content into {len(chunks)} chunks")
    
    # Process each chunk
    converted_chunks = []
    for i, chunk in enumerate(chunks):
        print(f"Processing chunk {i+1}/{len(chunks)}")
        converted_chunk = process_chunk(chunk, wiki_format)
        converted_chunks.append(converted_chunk)
    
    # Combine the converted chunks
    wiki_content = "\n".join(converted_chunks)
    
    # Add attachments section if needed
    if is_attachments and attachment is not None:
        attachments_system_message = """Convert the attachment information into a Confluence Wiki Markup table."""
        
        attachments_message = f"""
        Create a Confluence Wiki Markup table with headers:
        - file_name
        - file_size
        - file_datetime_created
        - file_owner
        - file_comment
        
        Use this data:
        {attachment.to_string()}
        
        The table should be preceded by an h2 header "Attachments:"
        """
        
        headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "Ocp-Apim-Subscription-Key": os.getenv("LLM_GATEWAY_KEY")
        }
        
        payload = {
            "prompt": f"{attachments_system_message}\n\n{attachments_message}",
            "temperature": 0.2,
            "top_P": 0.95,
            "top_K": 40,
            "max_Output_Tokens": 4000
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            
            result = response.json()
            if 'candidates' in result and len(result['candidates']) > 0:
                attachments_table = result['candidates'][0]['content']['parts'][0]['text']
                wiki_content += "\n\n" + attachments_table
            
        except Exception as e:
            print(f"Error processing attachments: {e}")
    
    return wiki_content


if __name__ == "__main__":
    print("Converting markdown to Confluence Wiki Markup...")
    markdown_file_path = '/workspaces/twiki-confluence-migration/BRMacro/Arl2data_SYNCF/pattern_topic.md'
    project_name = 'Test'
    page_name = 'test123'
    is_attachments = False
    attachment = None
    converted_content = convert_markdown_to_wiki(markdown_file_path, is_attachments, attachment, project_name, page_name)
    
    # Save the result to a file
    output_file = f"{page_name}_converted.txt"
    with open(output_file, "w", encoding="utf-8") as file:
        file.write(converted_content)
    
    print(f"Conversion complete. Result saved to {output_file}")