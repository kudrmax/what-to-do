from importlib.metadata import version

APP_NAME = "What To Do"
PACKAGE = "where-to-go"
VERSION = version(PACKAGE)
USER_AGENT = f"{PACKAGE}/{VERSION}"
