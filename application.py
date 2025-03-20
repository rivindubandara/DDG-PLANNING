from flask import Flask
import os

application = Flask(__name__, static_url_path='/static', static_folder='static')
application.secret_key = 'nettletontribe_secret_key'

from routes import register_routes
register_routes(application)

from functions import *

if __name__ == '__main__':
    application.run(host='0.0.0.0', port=5000)
