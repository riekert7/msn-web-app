import sentry_sdk
from flask import Flask

sentry_sdk.init(
    dsn="https://d84860339636444445baabd8f122c8b6@o4511356961685504.ingest.de.sentry.io/4511356967780432",
    # Add data like request headers and IP for users,
    # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
    send_default_pii=True,
)

app = Flask(__name__)

@app.route("/")
def hello_world():
    1/0  # raises an error
    return "<p>Hello, World!</p>"