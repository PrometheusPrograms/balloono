from flask import Flask

app = Flask(__name__)


@app.route("/")
def index():
    return "<!doctype html><html><body><pre>:)</pre></body></html>"




if __name__ == "__main__":
    app.run()
