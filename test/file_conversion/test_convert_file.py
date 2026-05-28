import markdown2
import pypandoc
import xml.etree.ElementTree as ET
import xml.dom.minidom

def convert_markdown_to_xml(markdown_content, page_name):
    """Convert Markdown content to XML."""
    markdown_html = markdown2.markdown(markdown_content)
    soup = BeautifulSoup(markdown_html, 'html.parser')

    def convert_to_xml(element):
        xml_element = ET.Element(element.name)
        if element.attrs:
            for key, value in element.attrs.items():
                xml_element.set(key, value)
        if element.string:
            xml_element.text = element.string
        for child in element.children:
            if isinstance(child, str):
                continue
            xml_element.append(convert_to_xml(child))
        return xml_element

    xml_content = ET.Element("root")
    for child in soup.children:
        if isinstance(child, str):
            continue
        xml_content.append(convert_to_xml(child))

    xml_str = ET.tostring(xml_content, encoding='utf-8')
    pretty_xml_str = xml.dom.minidom.parseString(xml_str).toprettyxml(indent="  ")

    xml_file_path = os.path.join(page_name, 'pattern_topic.xml')
    with open(xml_file_path, 'w', encoding='utf-8') as file:
        file.write(pretty_xml_str)

def convert_html_to_word(html_content, page_name):
    """Convert HTML content to a Word document."""
    word_file_path = os.path.join(page_name, 'pattern_topic.docx')
    pypandoc.convert_text(html_content, 'docx', format='html', outputfile=word_file_path)