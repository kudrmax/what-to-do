from importlib.metadata import version

APP_NAME = "Чем заняться"
PACKAGE = "where-to-go"
VERSION = version(PACKAGE)
USER_AGENT = f"{PACKAGE}/{VERSION}"
