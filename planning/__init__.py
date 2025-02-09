from flask import Flask
import os

application = Flask(__name__, static_url_path='/planning/static', static_folder='static')
application.secret_key = os.urandom(24)
application.config['UPLOAD_FOLDER'] = '/planning/static/uploads'

from planning import routes, functions