from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
from jinja2 import Environment, PackageLoader, select_autoescape
from app.config import Config
from flask_caching import Cache


def create_app(config_class=Config):
    app = Flask(__name__, static_url_path='')
    app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=1)
    app.config.from_object(config_class)
    app.env = Environment(
        loader=PackageLoader("app"),
        autoescape=select_autoescape()
    )
    app.cache = Cache(config={'CACHE_TYPE': 'SimpleCache'})
    app.cache.init_app(app)

    return app
