# TWiki to Confluence Migration Tool

A Python-based tool that automates the end-to-end migration of TWiki project spaces to Atlassian Confluence. It handles content extraction, format conversion (HTML → Markdown → Confluence Wiki markup), attachment uploads, internal link rewriting, and admin permission assignment.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
  - [Option A: Local (Python)](#option-a-local-python)
  - [Option B: Docker (Recommended)](#option-b-docker-recommended)
- [Migration Steps](#migration-steps)
- [Understanding the Output](#understanding-the-output)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

- Python 3.9+ (for local setup)
- Docker & Docker Compose (for containerized setup)
- Network access to both TWiki and Confluence instances
- TWiki credentials (username + password)
- Confluence API token ([generate one here](https://id.atlassian.com/manage-profile/security/api-tokens))

---

## Configuration

Create a `.env` file in the project root before running the tool. The file must **not** be committed to version control.

```env
# ─── TWiki ───────────────────────────────────────────────────────────────────
USERNAME=<your_twiki_username>
PASSWORD=<your_twiki_password>
BASE_URL=https://twiki.example.com

# ─── Confluence ──────────────────────────────────────────────────────────────
CONFLUENCE_URL=<your-domain>.atlassian.net
CONFLUENCE_USERNAME=<your_confluence_email>
CONFLUENCE_API_TOKEN=<your_confluence_api_token>

# ─── Space Admin (Optional) ──────────────────────────────────────────────────
# Fallback admin assigned to every migrated space
DEFAULT_ADMIN_EMAIL=admin@example.com

# ─── Email / SMTP (Optional — required only for Excel report emailing) ────────
smtp_server=mail.example.com
smtp_port=25
sender_email=migration-tool@example.com
default_recipients=team@example.com,manager@example.com
```

---

## Running the Application

### Option A: Local (Python)

```bash
# 1. Enter the project directory
cd twiki-confluence-migration-main

# 2. Create the .env file (see Configuration above)

# 3. Install dependencies
pip install -r requirements.txt

# 4. Launch the tool
python main.py
```

### Option B: Docker (Recommended)

Docker provides an isolated, reproducible environment and is the preferred way to run long migrations.

```bash
# 1. Create the .env file (see Configuration above)

# 2. Build and start the container in the background
docker-compose up -d

# 3. Attach to the running migration session
docker exec -it twiki-migration-app tmux attach-session -t migration-session

# 4. Inside the tmux session, launch the tool
python main.py

# ── Detach from tmux without stopping the session ──
# Press Ctrl+B, then D

# 5. Re-attach at any time
docker exec -it twiki-migration-app tmux attach-session -t migration-session

# 6. Stop the container when done
docker-compose down
```

**Volume mounts** (data persists on the host):

| Host path          | Container path          | Purpose                           |
|--------------------|-------------------------|-----------------------------------|
| `./results`        | `/app/results`          | Migration logs and JSON output    |
| `./.env`           | `/app/.env`             | Configuration file                |
| `./crawl_all_proj` | `/app/crawl_all_proj`   | Project metadata (topic counts)   |

---

## Migration Steps

After running `python main.py` you will see the main menu:

```
==================================================
   TWiki to Confluence Migration Tool
==================================================
1. Get all TWiki URLs
2. Check available TWiki URLs
3. Migrate TWiki projects
4. Check migration results
5. Manual delete Confluence spaces
q. Exit
==================================================
```

Follow these steps in order for a complete migration:

---

### Step 1 — Discover TWiki projects (Option 1)

Select **1** to crawl all TWiki `WebTopicList` pages and build the project list.

- Writes discovered project URLs to `twiki_urls.txt`
- Also generates `crawl_all_proj/project_topics_count.csv` with topic counts and last-edited metadata

> Run this step once before any migration. Re-run it if new projects are added to TWiki.

---

### Step 2 — Review available projects (Option 2)

Select **2** to browse the discovered projects in a paginated table showing:

| Column | Description |
|--------|-------------|
| Project Name | TWiki project identifier |
| Topics | Number of pages in the project |
| Last Edited By | Most recent author |
| Last Edited On | Date of last edit |
| Migration Status | Not Migrated / Migrated / Deleted / Failed |

**Navigation commands:**

| Key | Action |
|-----|--------|
| `n` / `p` | Next / previous page |
| `s` | Search by project name |
| `f` | Filter by migration status |
| `v` | View full project details |
| `q` | Return to main menu |

---

### Step 3 — Migrate projects (Option 3)

Select **3** to open the migration selection screen.

1. **Select projects** — enter project numbers (e.g. `1,3,5`), or press `a` to select all
2. Press `s` to review your selection
3. Press `m` to confirm, then type `start` at the prompt to begin

The tool automatically runs a 5-phase migration for each selected project:

| Phase | What happens |
|-------|-------------|
| **1 — Create space & migrate WebTopicList** | Creates a new Confluence space and uploads the index page |
| **2 — Parallel page migration** | Migrates all pages concurrently (4 workers, up to 3 retries per page) |
| **3 — Rewrite internal links** | Replaces all TWiki URLs with Confluence URLs; marks broken links as `DEPRECATED!!` |
| **4 — Assign admins** | Grants admin permissions in Confluence to all page authors |
| **5 — Save results & clean up** | Writes logs and JSON summary; removes temporary local files |

Progress is printed to the terminal in real time. For Docker users, the tmux session keeps the migration running even if you detach.

---

### Step 4 — Check results (Option 4)

Select **4** to view a paginated results table with:

- Migration ratio (pages migrated / total pages)
- Success percentage
- Status: Migrated / Partial Success / Failed / Deleted
- Latest migration date

**Actions available in this view:**

| Key | Action |
|-----|--------|
| `v` | View full details + error analysis for a project |
| `d` | Delete spaces by project number (enables re-migration) |
| `dd` | Delete a space by manually entering its space key |
| `r` | Re-migrate previously deleted spaces |
| `e` | Export results to Excel (optionally email the report) |
| `f` | Filter by status |
| `s` | Search by project name |

---

### Step 5 — Delete spaces for re-migration (Option 5)

Select **5** if you need to manually delete a Confluence space outside of the results view. Spaces can also be deleted from within Option 4 using the `d` or `dd` keys.

After deletion, the space status is set to **Deleted** in `migration_summary.json`, making it available for re-migration via Option 3 or the `r` key in Option 4.

---

## Understanding the Output

All output is written to the `results/` directory (mounted to the host when using Docker):

```
results/
├── migration_summary.json                     # Cumulative summary of all migrations
├── <ProjectName>/
│   ├── migration_log.txt                      # Detailed per-page log for the project
│   └── results.json                           # Page-level metadata
└── migration_results_YYYYMMDD_HHMMSS.xlsx     # Excel export (generated on demand)
```

**`migration_summary.json` structure (per project):**

```json
{
  "SPACEKEY": {
    "2024-01-15T10:30:00": {
      "version": 1,
      "project_name": "MyProject",
      "old_twiki_url": "https://twiki.example.com/view/MyProject/WebTopicList",
      "new_confluence_link": "https://your-domain.atlassian.net/wiki/spaces/SPACEKEY",
      "admin_list": ["user@example.com"],
      "success_migrated/total_pages": "48/50",
      "percentage_migration": 96.0,
      "status": "Partial Success",
      "message": "..."
    }
  }
}
```

**Status values:**

| Status | Meaning |
|--------|---------|
| `Success` | All pages migrated successfully |
| `Partial Success` | Some pages migrated (check ratio for details) |
| `Fail` | Space creation failed or critical error occurred |
| `Deleted` | Space has been deleted from Confluence |

---

## Troubleshooting

**Authentication errors (TWiki)**
- Verify `USERNAME`, `PASSWORD`, and `BASE_URL` in `.env`
- Confirm the account has read access to the TWiki projects

**Authentication errors (Confluence)**
- Verify `CONFLUENCE_USERNAME` is your full email address
- Regenerate `CONFLUENCE_API_TOKEN` at `id.atlassian.com` and update `.env`
- Confirm the account has Space Creator permissions in Confluence

**Pages failing to migrate**
- The tool retries each page up to 3 times with exponential backoff
- Failed pages are recorded in `migration_log.txt` and `results.json`
- Delete the space (Option 4 → `d`) and re-migrate once the underlying issue is resolved

**`twiki_urls.txt` is empty**
- Run Option 1 first to crawl and populate the project list

**Docker container exits immediately**
- Ensure `.env` exists in the project root before running `docker-compose up`
- Check logs with: `docker logs twiki-migration-app`

**Excel export fails**
- Ensure `pandas` and `openpyxl` are installed: `pip install pandas openpyxl`
- These are included in `requirements.txt` and should be present in the Docker image

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
