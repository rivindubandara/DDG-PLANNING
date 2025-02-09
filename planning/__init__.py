from flask import Flask
import os

application = Flask(__name__)
application.secret_key = os.urandom(24)

from planning import routes, functions