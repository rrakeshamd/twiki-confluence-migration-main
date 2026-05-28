import re
from bs4 import BeautifulSoup, NavigableString

def test_square_bracket_removal():
    """Test function to verify square bracket edit link removal"""
    
    # Test string with multiple square bracket edit links
    test_text = 'X86EXERCISER [ ? |https://twiki.amd.com/twiki/bin/edit/CBPgmmgt/X86EXERCISER?topicparent=CBPgmmgt.CBJiraMovScratchPad&nowysiwyg=1 "Create this topic"], X86REGRESSION [ ? |https://twiki.amd.com/twiki/bin/edit/CBPgmmgt/X86REGRESSION?topicparent=CBPgmmgt.CBJiraMovScratchPad&nowysiwyg=1 "Create this topic"], X86RTL [ ? |https://twiki.amd.com/twiki/bin/edit/CBPgmmgt/X86RTL?topicparent=CBPgmmgt.CBJiraMovScratchPad&nowysiwyg=1 "Create this topic"] - Sanjay to review'
    
    print("Original text:")
    print(test_text)
    print("\n" + "="*80 + "\n")
    
    # Pattern to match square bracket edit links
    pattern = r'\[\s*([^|]+)\s*\|\s*(https?://[^|\]]+twiki/bin/edit[^"]*)\s*"Create this topic"\s*\]'
    
    # Find all matches
    matches = list(re.finditer(pattern, test_text))
    print(f"Found {len(matches)} matches:")
    for i, match in enumerate(matches, 1):
        print(f"  {i}. {match.group(0)}")
    
    print("\n" + "="*80 + "\n")
    
    # Replace all matches at once
    new_text = re.sub(pattern, '', test_text)
    
    # Fix multiple spaces that might be created by the removal
    new_text = re.sub(r'\s{2,}', ' ', new_text)
    
    print("After removal:")
    print(new_text)
    print("\n" + "="*80 + "\n")
    
    # Test with BeautifulSoup context
    html_content = f'<div><p>{test_text}</p></div>'
    soup = BeautifulSoup(html_content, "html.parser")
    
    print("Testing with BeautifulSoup:")
    print("Original HTML:")
    print(soup.prettify())
    
    # Find text nodes and process them
    for text_node in soup.find_all(string=True):
        if isinstance(text_node, NavigableString) and text_node.parent.name != 'a':
            text_str = str(text_node)
            
            if re.search(pattern, text_str):
                new_text = re.sub(pattern, '', text_str)
                new_text = re.sub(r'\s{2,}', ' ', new_text)
                
                if new_text != text_str:
                    new_node = NavigableString(new_text)
                    text_node.replace_with(new_node)
                    print("\nAfter processing with BeautifulSoup:")
                    print(soup.prettify())
                    print(f"Successfully replaced text node")
                    break

if __name__ == "__main__":
    test_square_bracket_removal()