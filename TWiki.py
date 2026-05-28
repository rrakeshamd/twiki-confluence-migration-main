class TWiki:
    """
    TWiki class to store information about a TWiki page.

    Attributes:
        url (str): Full URL of the TWiki page
        base_url (str): Base URL of the TWiki site
        project_name (str): Name of the project extracted from the page title
        page_name (str): Name of the page extracted from the page title
    """

    def __init__(self, url, base_url):
        """
        Initialize a TWiki object with URL information.

        Args:
            url (str): Full URL of the TWiki page
            base_url (str): Base URL of the TWiki site
        """
        self.url = url
        self.base_url = base_url
        self.project_name = None
        self.page_name = None

    def __str__(self):
        """
        Return a string representation of the TWiki object.

        Returns:
            str: String representation with URL, base URL, and title
        """
        return f"URL: {self.url}, Base URL: {self.base_url}, Project: {self.project_name}, Page: {self.page_name}"

    def set_project_page_name(self, soup):
        """
        Extract and format the title of the webpage and set project and page names.

        Example title format: 'Wiki < SDSEng < ODC'
        This would set:
            - project_name = 'SDSEng'
            - page_name = 'ODC'

        Special cases like 'WebHome' and 'WebTopicList' are converted to
        'Home' and 'TopicList' respectively.

        Args:
            soup (BeautifulSoup): BeautifulSoup object of the parsed HTML
        """
        # Extract title parts from the page title
        title_parts = soup.title.string.strip().split(" < ")
        title_parts.reverse()  # Reverse to get hierarchical order

        # Set project name to the middle part of the title (alphanumeric only)
        self.project_name = ''.join(char for char in title_parts[1] if char.isalnum())

        # Handle special page names with a mapping
        check_list = {"WebHome": "Home", "WebTopicList": "TopicList"}
        if title_parts[2] in check_list:
            self.page_name = check_list[title_parts[2]]
        else:
            self.page_name = title_parts[2]