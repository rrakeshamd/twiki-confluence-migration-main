import os
import re


# ---------------------------------------------------------------------------
# Code block protection
# ---------------------------------------------------------------------------

def _extract_code_blocks(text):
    """Extract fenced and indented code blocks into null-byte placeholders."""
    placeholders = {}
    counter = [0]

    def store(content):
        key = f'\x00CODE_{counter[0]}\x00'
        placeholders[key] = content
        counter[0] += 1
        return key

    # Fenced code blocks: ```[lang]\n...\n```
    def replace_fenced(m):
        lang = m.group(1).strip() if m.group(1) else ''
        body = m.group(2)
        tag = f'```{lang}\n' if lang else '```\n'
        return store(tag + body + '```')

    text = re.sub(r'```(\w*)\n(.*?)```', replace_fenced, text, flags=re.DOTALL)

    # Indented code blocks: consecutive lines with 4+ spaces or a tab
    def replace_indented(m):
        return store(m.group(0))

    text = re.sub(r'(?:(?:^(?:    |\t)[^\n]*\n)+)', replace_indented, text, flags=re.MULTILINE)

    return text, placeholders


def _restore_code_blocks(text, placeholders):
    """Re-insert code blocks as Confluence {code}...{code}."""
    for key, original in placeholders.items():
        # Strip the fenced markers and any language tag
        body = re.sub(r'^```\w*\n?', '', original)
        body = re.sub(r'```\s*$', '', body)
        # Strip 4-space / tab indentation from indented blocks
        body = re.sub(r'^(?:    |\t)', '', body, flags=re.MULTILINE)
        text = text.replace(key, '{code}\n' + body.strip('\n') + '\n{code}')
    return text


# ---------------------------------------------------------------------------
# Individual conversion rules
# ---------------------------------------------------------------------------

def _convert_headings(text):
    for level in range(6, 0, -1):
        pattern = r'^' + '#' * level + r'\s+(.+)$'
        text = re.sub(pattern, f'h{level}. \\1', text, flags=re.MULTILINE)
    return text


def _convert_horizontal_rules(text):
    # * * *, - - -, _ _ _ (3 or more, with optional spaces)
    text = re.sub(r'^\s*(\*\s*){3,}\s*$', '----', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*(-\s*){3,}\s*$', '----', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*(_\s*){3,}\s*$', '----', text, flags=re.MULTILINE)
    return text


def _convert_blockquotes(text):
    lines = text.split('\n')
    result = []
    in_quote = False
    for line in lines:
        if line.startswith('>'):
            content = re.sub(r'^(>\s*)+', '', line)
            if not in_quote:
                result.append('{quote}')
                in_quote = True
            result.append(content)
        else:
            if in_quote:
                result.append('{quote}')
                in_quote = False
            result.append(line)
    if in_quote:
        result.append('{quote}')
    return '\n'.join(result)


def _convert_tables(text):
    lines = text.split('\n')
    result = []
    i = 0
    sep_re = re.compile(r'^\s*\|[\s\-|:]+\|\s*$')
    while i < len(lines):
        line = lines[i]
        if (line.strip().startswith('|') and
                i + 1 < len(lines) and sep_re.match(lines[i + 1])):
            # Header row
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            result.append('|| ' + ' || '.join(cells) + ' ||')
            i += 2  # skip separator
            # Data rows
            while i < len(lines) and lines[i].strip().startswith('|'):
                cells = [c.replace('\\|', '|').strip()
                         for c in lines[i].strip().strip('|').split('|')]
                result.append('| ' + ' | '.join(cells) + ' |')
                i += 1
        else:
            result.append(line)
            i += 1
    return '\n'.join(result)


def _convert_lists(text):
    unordered_re = re.compile(r'^(\s*)[*\-+]\s+(.*)$')
    ordered_re = re.compile(r'^(\s*)\d+\.\s+(.*)$')
    lines = text.split('\n')
    result = []
    for line in lines:
        line = line.replace('\t', '  ')
        um = unordered_re.match(line)
        om = ordered_re.match(line)
        if um:
            indent, content = um.groups()
            level = (len(indent) // 2) + 1
            result.append('*' * level + ' ' + content)
        elif om:
            indent, content = om.groups()
            level = (len(indent) // 2) + 1
            result.append('#' * level + ' ' + content)
        else:
            result.append(line)
    return '\n'.join(result)


def _convert_emphasis(text):
    """Convert bold, italic, bold+italic, strikethrough.

    Strategy: use null-byte placeholders for bold output so the subsequent
    italic regex cannot re-match the single * delimiters introduced by bold.
    """
    # 1. Bold + italic (triple markers — must precede double and single)
    text = re.sub(r'\*\*\*(.+?)\*\*\*', lambda m: f'\x01BI\x01{m.group(1)}\x01BI\x01', text)
    text = re.sub(r'___(.+?)___',        lambda m: f'\x01BI\x01{m.group(1)}\x01BI\x01', text)

    # 2. Bold (double markers)
    text = re.sub(r'\*\*(.+?)\*\*', lambda m: f'\x01B\x01{m.group(1)}\x01B\x01', text)
    text = re.sub(r'__(.+?)__',     lambda m: f'\x01B\x01{m.group(1)}\x01B\x01', text)

    # 3. Italic — only single * or _ not adjacent to another * or _
    #    At this point all ** and *** are already replaced with placeholders,
    #    so remaining * are safe to treat as italic.
    text = re.sub(r'(?<!\*)\*(?!\*| )(.+?)(?<! )\*(?!\*)', r'_\1_', text)
    text = re.sub(r'(?<!_)_(?!_)(.+?)(?<!_)_(?!_)', r'_\1_', text)

    # 4. Strikethrough
    text = re.sub(r'~~(.+?)~~', r'-\1-', text)

    # 5. Restore bold and bold+italic placeholders to Confluence markup
    text = text.replace('\x01BI\x01', '\x01BI_DELIM\x01')  # temp to avoid double-replace
    text = re.sub(r'\x01BI_DELIM\x01(.+?)\x01BI_DELIM\x01', r'*_\1_*', text)
    text = re.sub(r'\x01B\x01(.+?)\x01B\x01', r'*\1*', text)

    return text


def _convert_images(text):
    # ![alt](url) → !url!
    text = re.sub(r'!\[.*?\]\((.+?)\)', r'!\1!', text)
    return text


def _convert_links(text):
    def replace_link(m):
        display = m.group(1).strip()
        url = m.group(2).strip()
        if url.startswith('http://') or url.startswith('https://') or url.startswith('mailto:'):
            if display and display != url:
                return f'[{display}|{url}]'
            return f'[{url}]'
        else:
            # Internal: take last non-empty path segment
            page = url.rstrip('/').split('/')[-1].split('?')[0].split('#')[0]
            page = page or url
            if display and display != page:
                return f'[{display}|{page}]'
            return f'[{page}]'

    # Handle balanced parentheses in URLs (one level deep)
    text = re.sub(r'\[([^\]]*)\]\(((?:[^()]+|\([^()]*\))+)\)', replace_link, text)
    return text


def _convert_inline_code(text):
    # `code` → {{code}}
    text = re.sub(r'`([^`\n]+)`', r'{{\1}}', text)
    return text


def _post_cleanup(text):
    # Remove stray leftover ``` markers
    text = re.sub(r'^```\w*\s*$', '', text, flags=re.MULTILINE)
    # Collapse 3+ consecutive blank lines to 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def _convert_markdown_to_confluence_wiki(markdown_text):
    """Run the full rule-based conversion pipeline."""
    text, placeholders = _extract_code_blocks(markdown_text)

    # Unescape markdown backslash escapes (outside code blocks)
    text = re.sub(r'\\([*_`\[\]()#+\-.!])', r'\1', text)

    text = _convert_headings(text)
    text = _convert_horizontal_rules(text)
    text = _convert_blockquotes(text)
    text = _convert_tables(text)
    text = _convert_lists(text)
    text = _convert_emphasis(text)
    text = _convert_images(text)
    text = _convert_links(text)
    text = _convert_inline_code(text)
    text = _restore_code_blocks(text, placeholders)
    text = _post_cleanup(text)
    return text


# ---------------------------------------------------------------------------
# Attachment table
# ---------------------------------------------------------------------------

def build_attachment_table(attachment_df):
    """Build a Confluence wiki markup attachment table from a DataFrame."""
    lines = ['h2. Attachments:', '']
    lines.append('|| file_name || file_size || file_datetime_created || file_owner || file_comment ||')
    for _, row in attachment_df.iterrows():
        def cell(col):
            val = row[col]
            try:
                import math
                if isinstance(val, float) and math.isnan(val):
                    return ''
            except Exception:
                pass
            return str(val).strip()

        file_name = cell('file_name')
        file_link = f'[{file_name}^{file_name}]'
        lines.append(
            f'| {file_link} | {cell("file_size")} | {cell("file_datetime_created")} '
            f'| {cell("file_owner")} | {cell("file_comment")} |'
        )
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Public API (signature unchanged)
# ---------------------------------------------------------------------------

def convert_markdown_to_wiki(
    markdown_file_path, is_attachments, attachment, project_name, page_name
):
    """
    Convert a markdown file to Confluence Wiki Markup using rule-based conversion.

    Args:
        markdown_file_path (str): Path to the markdown file to convert.
        is_attachments (bool): Whether there are attachments to include.
        attachment (DataFrame): DataFrame with attachment metadata (or None).
        project_name (str): Project name used for output directory.
        page_name (str): Page name used for output directory.

    Returns:
        tuple[str, bool]: (wiki_content, success_flag)
            success_flag is False only if the input file cannot be read.
    """
    print("\nTask: Converting markdown to wiki")

    try:
        with open(markdown_file_path, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
    except OSError as e:
        print(f"Error reading markdown file: {e}")
        return ('', False)

    wiki_content = _convert_markdown_to_confluence_wiki(markdown_content)

    if is_attachments and attachment is not None and len(attachment) > 0:
        wiki_content += '\n\n' + build_attachment_table(attachment)

    output_dir = os.path.join(project_name, page_name)
    os.makedirs(output_dir, exist_ok=True)
    output_file_path = os.path.join(output_dir, 'wiki_content.txt')
    try:
        with open(output_file_path, 'w', encoding='utf-8') as f:
            f.write(wiki_content)
    except OSError as e:
        print(f"Warning: could not save wiki_content.txt: {e}")

    return (wiki_content, True)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import sys

    failures = []

    def check(label, got, expected):
        if got != expected:
            failures.append(f'FAIL [{label}]\n  got:      {repr(got)}\n  expected: {repr(expected)}')
        else:
            print(f'  OK  {label}')

    print('Running self-tests...')

    # Headings
    check('h1', _convert_headings('# Title'), 'h1. Title')
    check('h3', _convert_headings('### Sub'), 'h3. Sub')
    check('h6', _convert_headings('###### Deep'), 'h6. Deep')

    # Horizontal rule
    check('hr ---', _convert_horizontal_rules('---'), '----')
    check('hr * * *', _convert_horizontal_rules('* * *'), '----')

    # Emphasis
    check('bold', _convert_emphasis('**bold**'), '*bold*')
    check('italic', _convert_emphasis('_italic_'), '_italic_')
    check('bold+italic', _convert_emphasis('***both***'), '*_both_*')
    check('strike', _convert_emphasis('~~del~~'), '-del-')

    # Inline code
    check('inline code', _convert_inline_code('`cmd`'), '{{cmd}}')

    # Lists
    check('ul level1', _convert_lists('* item'), '* item')
    check('ul level2', _convert_lists('  * sub'), '** sub')
    check('ol level1', _convert_lists('1. first'), '# first')
    check('ol level2', _convert_lists('  1. nested'), '## nested')

    # Tables
    tbl = '| A | B |\n|---|---|\n| 1 | 2 |'
    check('table', _convert_tables(tbl), '|| A || B ||\n| 1 | 2 |')

    # Links
    check('ext link', _convert_links('[Go](https://example.com)'), '[Go|https://example.com]')
    check('int link', _convert_links('[Page](/wiki/view/Proj/PageName)'), '[Page|PageName]')

    # Images
    check('image', _convert_images('![alt](https://example.com/img.png)'), '!https://example.com/img.png!')

    # Blockquotes
    check('blockquote', _convert_blockquotes('> hello'), '{quote}\nhello\n{quote}')

    # Code block round-trip
    md = '```python\nprint("hi")\n```'
    result = _convert_markdown_to_confluence_wiki(md)
    assert '{code}' in result and 'print("hi")' in result, f'code block failed: {repr(result)}'
    print('  OK  fenced code block')

    # Attachment table
    try:
        import pandas as pd
        df = pd.DataFrame([['file.txt', '1KB', '2024-01-01', 'user', 'note']],
                          columns=['file_name', 'file_size', 'file_datetime_created',
                                   'file_owner', 'file_comment'])
        tbl_out = build_attachment_table(df)
        assert '[file.txt^file.txt]' in tbl_out, 'attachment link missing'
        assert '|| file_name ||' in tbl_out, 'attachment header missing'
        print('  OK  attachment table')
    except ImportError:
        print('  SKIP attachment table (pandas not available)')

    if failures:
        print('\nFailed tests:')
        for f in failures:
            print(f)
        sys.exit(1)
    else:
        print('\nAll tests passed.')
