from md2cf.utils.confluencemd import ConfluenceMD
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Confluence credentials and details from environment variables
confluence_url = os.getenv('CONFLUENCE_URL')
confluence_username = os.getenv('CONFLUENCE_USERNAME')
confluence_api_token = os.getenv('CONFLUENCE_API_TOKEN')
confluence_space_id = os.getenv('CONFLUENCE_SPACE_ID')
confluence_parent_id = os.getenv('CONFLUENCE_PARENT_ID')

markdown_file_path = '/workspaces/twiki-confluence-migration/TWiki_SDSEng_ODC/pattern_topic.md'

# conf_md = ConfluenceMD(
#     username=confluence_username,
#     token=confluence_api_token,
#     url='https://{confluence_url}/wiki/api/v2/pages',
#     md_file='/workspaces/twiki-confluence-migration/TWiki_SDSEng_ODC/pattern_topic.md'
# )
# page_id = conf_md.create_new("30245016", "Test script", overwrite=True)  # Update existing page

import mistune
from md2cf.confluence_renderer import ConfluenceRenderer

with open(markdown_file_path, 'r', encoding='utf-8') as file:
    markdown_content = file.read()

renderer = ConfluenceRenderer(use_xhtml=True)
confluence_mistune = mistune.Markdown(renderer=renderer)
confluence_body = confluence_mistune(markdown_content)
# print(confluence_body)

from md2cf.api import MinimalConfluence

confluence = MinimalConfluence(host='https://{confluence_url}/rest/api', username=confluence_username, token=confluence_api_token)

confluence.create_page(space='CTWIKI', title='Test page', body='<p>Nothing</p>', update_message='Created page')

page = confluence.get_page(title='Test page', space_key='CTWIKI')
confluence.update_page(page=page, body='New content', update_message='Changed page contents')