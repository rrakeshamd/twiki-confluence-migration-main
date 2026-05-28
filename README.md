# TWiki to Confluence Migration

A comprehensive toolkit to migrate content from TWiki to Atlassian Confluence. Handles page fetching, HTML-to-Markdown conversion, LLM-powered wiki markup generation, attachment uploads, permission assignment, and link rewriting.

---

## Features

- **Full page migration** — fetches TWiki pages, converts them to Confluence Wiki Markup via Azure OpenAI (GPT-4o), and uploads to Confluence
- **Attachment handling** — downloads and uploads file attachments; rewrites in-page links automatically
- **Parallel processing** — page migration and attachment uploads run concurrently for 5–10× speedup
- **Author & permission management** — retrieves TWiki authors and assigns Confluence space permissions
- **Project discovery** — crawls all TWiki projects to build a migration list
- **Interactive CLI** — menu-driven interface to start migrations, filter/search projects, and view results
- **Error analysis** — uses an LLM to analyze migration logs and summarize failures
- **Space cleanup** — safely delete migrated Confluence spaces with confirmation prompts

---

## Architecture

```
main.py                        # Interactive CLI entry point
migrate_twiki_projects.py      # Core migration orchestration (parallel)
confluence_api.py              # Confluence REST API wrapper (v1 & v2)
markdown_to_wiki.py            # Azure OpenAI Markdown → Confluence Wiki Markup
retrieve_author.py             # TWiki author extraction
retrieve_urls.py               # URL list loader
modify_space_home_content.py   # Space home page template generation
analyze_error_from_log.py      # LLM-based log error analysis
delete_confluence_spaces.py    # Interactive space deletion utility
get_all_twiki_urls.py          # TWiki URL discovery
utils.py                       # Shared utilities (fetch, backoff, clear_screen)
crawl_all_proj/
  crawl_all_projects.py        # Concurrent project crawler
  get_all_projects_name.py     # Project name extractor
test/
  markdown_to_wiki/
    chunk_utils.py             # Shared markdown chunking logic
    markdown_to_wiki2.py       # Azure OpenAI chunked converter
    markdown_to_wiki_gemini.py # Gemini LLM chunked converter
```

---

## Setup

### 1. Clone the repository

```sh
git clone https://github.com/your-repo/twiki-confluence-migration.git
cd twiki-confluence-migration
```

### 2. Install dependencies

```sh
pip install -r requirements.txt
```

### 3. Configure environment variables

Create a `.env` file in the root directory:

```env
# TWiki credentials
USERNAME=your_twiki_username
PASSWORD=your_twiki_password
BASE_URL=https://your-twiki-instance.com

# Confluence credentials
CONFLUENCE_URL=your_confluence_url
CONFLUENCE_USERNAME=your_confluence_username
CONFLUENCE_API_TOKEN=your_confluence_api_token
CONFLUENCE_SPACE_ID=your_confluence_space_id
CONFLUENCE_PARENT_ID=your_confluence_parent_id

# Azure OpenAI / LLM gateway
LLM_GATEWAY_KEY=your_llm_gateway_key

# Optional: default admin email to assign space admin permissions
DEFAULT_ADMIN_EMAIL=admin@example.com

# Git (used in Docker setup)
GIT_USER_NAME=your_git_username
GIT_USER_EMAIL=your_git_email
```

---

## Usage

### Run the interactive migration CLI

```sh
python3 main.py
```

The CLI menu provides:

| Option | Description |
|--------|-------------|
| 1 | Retrieve all TWiki URLs |
| 2 | Browse / search available projects |
| 3 | Start migration to Confluence |
| 4 | View migration results |
| 5 | Delete Confluence spaces |
| 6 | Analyze migration log errors |

### Crawl all TWiki projects

```sh
cd crawl_all_proj
python3 crawl_all_projects.py
```

Outputs `../twiki_urls.txt` with all discovered project URLs, and `project_topics_count.csv` with topic counts and last-edit metadata.

---

## Docker Setup

```sh
docker-compose up --build
```

Then connect to the running container's tmux session:

```sh
docker exec -it twiki-migration tmux attach -t migration-session
```

Inside tmux, run:

```sh
python3 main.py
```

---

## Performance

The migration pipeline is optimized for speed and reliability:

| Optimization | Detail |
|---|---|
| Parallel page migration | `ThreadPoolExecutor(max_workers=4)` — pages migrated concurrently |
| Parallel attachment uploads | `ThreadPoolExecutor(max_workers=5)` — files uploaded concurrently |
| HTTP connection pooling | `requests.Session` reused across calls |
| Request timeouts | 30 s for API calls, 60 s for file downloads |
| Exponential backoff | Replaces fixed 60 s sleeps on retries |
| LLM client singleton | `AzureChatOpenAI` instantiated once at module load |
| Wiki format caching | `confluence_wiki_format.txt` read once and cached |

---

## Key Files

| File | Purpose |
|---|---|
| `utils.py` | Shared: `fetch_webpage`, `is_success_response`, `exponential_backoff`, `clear_screen` |
| `test/markdown_to_wiki/chunk_utils.py` | Shared `chunk_markdown` used by both LLM converters |
| `confluence_wiki_format.txt` | Reference guide fed to the LLM for markup conversion |
| `defaultHomePage.html` | Template for Confluence space home pages |
| `twiki_urls.txt` | Input URL list for migration |
| `results/` | Migration outputs: JSON summaries, logs, per-project HTML |

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
