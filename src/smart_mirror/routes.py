"""HTTP validation and responses; analysis belongs to the controller."""
import secrets

from flask import Blueprint, Response, current_app, jsonify, render_template, request

from .errors import InvalidImage, InvalidReview, MirrorBusy, MirrorUnavailable

routes = Blueprint("mirror", __name__)


def _controller():
    return current_app.extensions["mirror_controller"]


@routes.before_app_request
def protect_api():
    if request.path.startswith("/api/"):
        supplied = request.headers.get("X-Mirror-Token", "").encode("utf-8")
        expected = current_app.config["ACCESS_TOKEN"].encode("utf-8")
        if not secrets.compare_digest(supplied, expected):
            return jsonify(error="Unauthorized"), 401
        origin = request.headers.get("Origin")
        if origin and origin != request.host_url.rstrip("/"):
            return jsonify(error="Untrusted origin"), 403


@routes.after_app_request
def privacy_headers(response):
    response.headers.update({
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "X-Frame-Options": "DENY",
        "Content-Security-Policy": (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'none'"
        ),
    })
    return response


@routes.get("/health")
def health():
    return "ok", 200


@routes.get("/")
def index():
    return render_template("index.html", access_token=current_app.config["ACCESS_TOKEN"])


@routes.get("/api/audio/result.mp3")
def get_audio():
    try:
        return Response(_controller().read_audio(), mimetype="audio/mpeg")
    except FileNotFoundError:
        return jsonify(error="No audio generated yet"), 404
    except MirrorBusy as exc:
        return jsonify(error=str(exc)), 409
    except MirrorUnavailable as exc:
        return jsonify(error=str(exc)), 503
    except Exception:
        current_app.logger.error("Mirror audio unavailable; check local output state")
        return jsonify(error="Audio unavailable; check local output state"), 503


@routes.post("/api/cmd")
def command():
    if not request.is_json:
        return jsonify(error="Request must be JSON"), 400
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get("cmd"), str):
        return jsonify(error="Provide a command object"), 400
    mode = body["cmd"].strip().lower()
    if mode not in {"rate", "decide"} or set(body) - {"cmd", "image_data_url", "image_base64"}:
        return jsonify(error="cmd must be 'rate' or 'decide'; unexpected fields are rejected"), 400
    try:
        result = _controller().analyze(mode, body)
        return jsonify(ok=True, mode=result.mode, review=result.review,
                       spoken_text=result.spoken_text, audio_url="/api/audio/result.mp3")
    except InvalidImage as exc:
        return jsonify(error=str(exc)), 400
    except InvalidReview:
        return jsonify(error="The provider returned an invalid review; please retry"), 502
    except MirrorBusy as exc:
        return jsonify(error=str(exc)), 409
    except MirrorUnavailable as exc:
        return jsonify(error=str(exc)), 503
    except Exception:
        current_app.logger.error("Mirror analysis failed; check hardware and provider configuration")
        return jsonify(error="Analysis failed; check camera, speaker and provider configuration"), 503
