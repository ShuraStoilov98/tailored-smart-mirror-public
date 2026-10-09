"""Flask application factory, configuration and dependency wiring."""
from flask import Flask, jsonify, request
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from .config import MirrorSettings, SRC_DIR, default_config
from .controller import MirrorController
from .provider import OpenAIProvider
from .routes import routes


def create_app(config=None, *, hardware=None, client=None, provider=None):
    """Build one controller; imports require neither a key nor physical devices."""
    app = Flask(__name__, static_folder=str(SRC_DIR / "static"), static_url_path="/static",
                template_folder=str(SRC_DIR / "templates"))
    app.config.update(default_config())
    if config:
        app.config.update(config)
    settings = MirrorSettings.from_config(app.config)
    controller = MirrorController(
        settings, provider if provider is not None else OpenAIProvider(settings, client),
        hardware=hardware, logger=app.logger,
    )
    app.extensions["mirror_controller"] = controller
    app.extensions["mirror_close"] = controller.close
    app.register_blueprint(routes)

    @app.errorhandler(BadRequest)
    @app.errorhandler(RequestEntityTooLarge)
    def malformed_request(error):
        if request.path.startswith("/api/"):
            message = "Request is too large" if error.code == 413 else "Invalid request"
            return jsonify(error=message), error.code
        return error

    return app
