from flask import Flask
import os

application = Flask(__name__)
application.secret_key = os.urandom(24)

def patch_wsgi(app):
    def wrapper(environ, start_response):
        environ.setdefault('CONTENT_LENGTH', '0')
        return app(environ, start_response)
    return wrapper

application.wsgi_app = patch_wsgi(application.wsgi_app)

from planning import routes, functions

