class User:
    """
    User class to store authentication credentials.

    Attributes:
        username (str): Username for authentication
        password (str): Password for authentication
    """

    def __init__(self, username, password):
        """
        Initialize a User object with authentication credentials.

        Args:
            username (str): Username for authentication
            password (str): Password for authentication
        """
        self.username = username
        self.password = password

    def __str__(self):
        """
        Return a string representation of the User object.

        Returns:
            str: String representation with username and password
        """
        return f"Username: {self.username}, Password: {self.password}"