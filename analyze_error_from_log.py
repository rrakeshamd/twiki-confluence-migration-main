from langchain_openai import AzureChatOpenAI
from langchain_core.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from langchain.schema import HumanMessage, SystemMessage
import os
from dotenv import load_dotenv
import re
from datetime import datetime
import sys
import time
import threading

# Load environment variables from .env file
load_dotenv()

# Azure LLM configuration
url = "https://llm-api.amd.com"
api_version = "2024-02-01"
model_name = "GPT-4o"
max_tokens = 16000
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

def extract_latest_migration_log(log_content):
    """
    Extract the content from the latest migration session based on the starting datetime.
    
    Args:
        log_content (str): Full log content
        
    Returns:
        tuple: (latest_migration_content, total_migration_count, latest_timestamp_str)
    """
    # Pattern to match migration start timestamps
    start_pattern = r"--- Migration started at (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+) ---"
    
    # Find all migration start matches with their positions
    start_matches = []
    for match in re.finditer(start_pattern, log_content):
        timestamp_str = match.group(1)
        position = match.start()
        
        # Parse timestamp
        try:
            timestamp = datetime.strptime(timestamp_str.split('.')[0], "%Y-%m-%d %H:%M:%S")
            start_matches.append((timestamp, position, timestamp_str))
        except ValueError:
            continue
    
    total_migration_count = len(start_matches)
    
    if not start_matches:
        return log_content, 0, None  # Return full content, 0 count, and None timestamp if no migration starts found
    
    # Sort by timestamp to get the latest
    start_matches.sort(key=lambda x: x[0], reverse=True)
    latest_timestamp, latest_position, latest_timestamp_str = start_matches[0]
    
    # print(f"Total migrations found in log: {total_migration_count}")
    # print(f"Latest migration session found: {latest_timestamp_str}")
    
    # Find the end of the latest migration session
    # Look for the next migration start or end marker after the latest start
    end_pattern = r"--- Migration ended at \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+ ---"
    
    # Get content starting from the latest migration start
    content_from_latest = log_content[latest_position:]
    
    # Find the migration end marker
    end_match = re.search(end_pattern, content_from_latest)
    
    if end_match:
        # Include the end marker
        latest_migration_content = content_from_latest[:end_match.end()]
    else:
        # No end marker found, take everything from the latest start
        latest_migration_content = content_from_latest
    
    return latest_migration_content, total_migration_count, latest_timestamp_str


class ProgressLoader:
    """A simple progress loader with spinning animation"""
    
    def __init__(self, message="Processing"):
        self.message = message
        self.running = False
        self.thread = None
        self.spinner_chars = ['|', '/', '-', '\\']
        self.current_char = 0
        
    def _animate(self):
        """Animation loop for the progress loader"""
        while self.running:
            sys.stdout.write(f'\r{self.message} {self.spinner_chars[self.current_char]}')
            sys.stdout.flush()
            self.current_char = (self.current_char + 1) % len(self.spinner_chars)
            time.sleep(0.2)
    
    def start(self):
        """Start the progress loader animation"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._animate)
            self.thread.daemon = True
            self.thread.start()
    
    def stop(self):
        """Stop the progress loader animation"""
        if self.running:
            self.running = False
            if self.thread:
                self.thread.join(timeout=0.5)
            # Clear the line and move cursor to beginning
            sys.stdout.write('\r' + ' ' * (len(self.message) + 5) + '\r')
            sys.stdout.flush()

def truncate_log_content(log_content, error_message, max_tokens=128000):
    """
    Truncate log content to fit within token limits while preserving relevant error context.
    
    Args:
        log_content (str): Full log content
        error_message (str): Primary error message to investigate
        max_tokens (int): Maximum tokens to allow (leaving buffer for system/human messages)
        
    Returns:
        str: Truncated log content with most relevant parts preserved
    """
    # Rough estimation: 1 token ≈ 4 characters
    max_chars = max_tokens * 4
    
    if len(log_content) <= max_chars:
        return log_content
    
    # Split log into lines for better processing
    lines = log_content.split('\n')
    
    # Find lines containing error messages or critical issues
    error_keywords = [
        'Error', 'error', 'Exception', 'exception', 'Failed', 'failed',
        'Critical', 'critical', 'Fatal', 'fatal', 'context_length_exceeded',
        'authentication', 'rate limit', 'maximum retry', 'terminated'
    ]
    
    # If we have a specific error message, add its key terms to search
    if error_message:
        error_words = error_message.lower().split()
        error_keywords.extend(error_words)
    
    # Collect important lines
    important_lines = []
    error_context_lines = []
    
    for i, line in enumerate(lines):
        # Check if line contains error keywords
        if any(keyword.lower() in line.lower() for keyword in error_keywords):
            # Add context around error lines (2 lines before and after)
            start_idx = max(0, i - 2)
            end_idx = min(len(lines), i + 3)
            error_context_lines.extend(lines[start_idx:end_idx])
            
    # Remove duplicates while preserving order
    seen = set()
    unique_error_lines = []
    for line in error_context_lines:
        if line not in seen:
            seen.add(line)
            unique_error_lines.append(line)
    
    # Start building truncated content
    truncated_content = ""
    
    # Always include the beginning (migration info)
    beginning_lines = lines[:50]  # First 50 lines for context
    truncated_content += '\n'.join(beginning_lines) + '\n\n'
    
    # Add error context
    if unique_error_lines:
        truncated_content += "=== RELEVANT ERROR SECTIONS ===\n"
        truncated_content += '\n'.join(unique_error_lines) + '\n\n'
    
    # If still space, add the end of the log
    current_length = len(truncated_content)
    remaining_chars = max_chars - current_length
    
    if remaining_chars > 1000 and len(lines) > 100:
        truncated_content += "=== END OF LOG ===\n"
        end_lines = lines[-20:]  # Last 20 lines
        end_content = '\n'.join(end_lines)
        if len(end_content) <= remaining_chars:
            truncated_content += end_content
    
    # Final length check and truncation if needed
    if len(truncated_content) > max_chars:
        truncated_content = truncated_content[:max_chars]
        truncated_content += "\n\n[LOG TRUNCATED DUE TO LENGTH LIMIT]"
    
    return truncated_content

def analyze_error_from_log(project_name, error_message):
    """
    Convert markdown content to Confluence wiki markup format using an Azure OpenAI model.

    Args:
        project_name (str): Name of the project for file organization

    Returns:
        tuple: (converted_content, flag, total_migration_count)
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
        # # Enable these for debugging
        # streaming=True,
        # callbacks=[StreamingStdOutCallbackHandler()]
    )

    # Read the migration content from file
    log_content = ""
    log_file_path = os.path.join("results", project_name, "migration_log.txt")
    with open(log_file_path, "r", encoding="utf-8") as file:
        log_content = file.read()

    # Extract the latest migration log content and get total count
    log_content, total_migration_count, latest_timestamp = extract_latest_migration_log(log_content)
    
    # Truncate log content if it's too long
    original_length = len(log_content)
    log_content = truncate_log_content(log_content, error_message, max_tokens=100000)
    truncated_length = len(log_content)
    
    print(f"\n{'='*50}")
    print(f"Migration Log AI Analysis Summary")
    print(f"{'='*50}")
    print(f"Total migrations in log: {total_migration_count}")
    print(f"Latest migration session: {latest_timestamp if latest_timestamp else 'None found'}")
    if truncated_length < original_length:
        print(f"Log content truncated due to max token limit: {original_length} -> {truncated_length} chars")
    print(f"Analyzing latest migration session...")
    print(f"{'='*50}\n")
    
    # # Uncomment below to see the log content before analysis
    # print(log_content)
    # input("Press enter to continue...")

    # Define system message with conversion instructions
    system_message = """
    You are an expert migration log analyst specializing in TWiki to Confluence migrations. Your task is to:
    1. Identify critical errors that cause migration failures and process termination
    2. Focus on errors that prevent successful migration completion (ignore non-blocking warnings)
    3. Analyze the root cause of migration-stopping errors
    4. Provide actionable recommendations to resolve critical issues that halt the migration process
    5. Distinguish between fatal errors and non-critical warnings/informational messages
    
    Focus ONLY on errors that cause the migration to fail or stop completely. Ignore non-blocking issues like missing files, profile lookup failures, or informational messages that don't prevent migration completion.
    
    Note: The log content may be truncated due to length limits, but the most relevant error sections have been preserved.
    """

    # Define human message with specific conversion requirements
    human_message = f"""Analyze this TWiki to Confluence migration log to identify CRITICAL ERRORS that caused migration failure.

    **Primary Error Message to Investigate:**
    {error_message}

    **FOCUS ONLY ON MIGRATION-STOPPING ERRORS:**
    - Errors that cause the migration process to terminate
    - Issues that prevent successful page creation or conversion
    - Critical API failures that halt the process
    - Context length exceeded errors
    - Authentication failures that stop migration
    - Rate limiting that causes maximum retry failures

    **IGNORE NON-CRITICAL ISSUES:**
    - "No email found in profile page" (informational)
    - "No pub files found" (expected behavior)
    - "No TWiki files found from attachments table" (not blocking)
    - Individual file not found messages (unless they stop migration)

    **Analysis Requirements:**
    1. **Root Cause Analysis**: Identify what specifically caused the migration to fail
    2. **Error Pattern**: Look for recurring critical errors in the log
    3. **Failure Point**: Determine at what stage the migration fails
    4. **Impact Assessment**: Assess why this error stops the entire migration
    5. **Solution Focus**: Provide specific steps to resolve the migration-stopping error

    **Output Format:**
    - **CRITICAL ERROR ANALYSIS**: Focus on "{error_message}" and related migration failures
    - **FAILURE PATTERN**: Show how many times this critical error occurred
    - **ROOT CAUSE**: Explain why this error causes migration to stop
    - **IMMEDIATE SOLUTION**: Specific steps to fix the migration-stopping issue
    - **SUCCESS CRITERIA**: How to verify the fix works

    **Migration Context:**
    - Total migration sessions: {total_migration_count}
    - Latest session timestamp: {latest_timestamp if latest_timestamp else 'None found'}
    - Critical error under investigation: {error_message}
    - Log content length: {"Truncated" if truncated_length < original_length else "Full"}

    **Log Content to Analyze:**
    {log_content}

    **CRITICAL ERROR ANALYSIS:**
    """

    # Prepare message list for the chat model
    messages = [
        SystemMessage(content=system_message),
        HumanMessage(content=human_message)
    ]

    # print("Task: Analyze error from log")
    
    # Initialize and start progress loader
    loader = ProgressLoader("Analyzing migration log with AI model")
    loader.start()
    
    try:
        # Invoke the chat model to perform the conversion
        response = chat.invoke(messages)
    finally:
        # Always stop the loader, even if there's an exception
        loader.stop()
    
    print("Analysis completed!")

    flag = print_response_details(response)

    if flag:
        # Ensure the directory exists
        output_dir = os.path.join("results", project_name)
        os.makedirs(output_dir, exist_ok=True)
        
        # Save the converted content to a file
        output_file_path = os.path.join(output_dir, "analysis_results.txt")
        with open(output_file_path, "w", encoding="utf-8") as output_file:
            # Include migration count in the saved results
            analysis_header = f"Migration Log AI Analysis Results\n"
            analysis_header += f"Total migrations found in log: {total_migration_count}\n"
            analysis_header += f"Latest migration session: {latest_timestamp if latest_timestamp else 'None found'}\n"
            analysis_header += f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            analysis_header += f"{'='*60}\n\n"
            
            output_file.write(analysis_header + response.content)
        print(f"Analysis results saved to: {output_file_path}")

        # Print a summary of the analysis results
        print("\n" + "="*50)
        print("ANALYSIS RESULTS:")
        print("="*50)
        print(response.content)

if __name__ == "__main__":
    print("Testing Azure API...")
    project_name = 'NonMSCollab'
    error_message = 'Error code 200: authentication failed'
    analyze_error_from_log(project_name, error_message)
    