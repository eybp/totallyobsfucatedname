class invalid_cookie(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message
        