"""
Shared chunking utility for markdown-to-wiki conversion scripts.
"""
import re


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
        # If no headers found, return the whole content if small enough
        if len(markdown_content) <= max_chunk_size:
            return [markdown_content]
        # Otherwise split by paragraphs
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
    chunk_positions.append(len(markdown_content))  # End of text

    chunks = []
    for i in range(len(chunk_positions) - 1):
        chunk = markdown_content[chunk_positions[i]:chunk_positions[i + 1]]

        # Further split if chunk is too large
        if len(chunk) > max_chunk_size:
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
