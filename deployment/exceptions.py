class MessageException(Exception):
    pass


class ConfigException(MessageException):
    pass


class DownloadFailedException(MessageException):
    pass
