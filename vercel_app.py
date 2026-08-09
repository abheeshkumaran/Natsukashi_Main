import os
import sys
import traceback

from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'natsukashi_design.settings')

# Built once at module/cold-start time, not per-request. Calling
# get_wsgi_application() (and therefore django.setup()) on every single
# request meant that if setup ever failed once in a warm container (e.g. a
# transient DB hiccup), Django's global app registry was left partially
# populated, and every later request in that same warm container failed with
# confusing unrelated errors (e.g. ContentType "not in INSTALLED_APPS") even
# though settings were fine. Building once means a failure fails loudly with
# its real traceback and Vercel spins up a fresh container instead of reusing
# a corrupted one.
_setup_error = None
_app = None
try:
    from django.core.wsgi import get_wsgi_application
    _app = get_wsgi_application()
except Exception:
    _setup_error = traceback.format_exc()


def application(environ, start_response):
    if _setup_error is not None:
        status = '500 Internal Server Error'
        output = f"Vercel WSGI Crash!\n\n{_setup_error}".encode('utf-8')
        response_headers = [('Content-type', 'text/plain'),
                            ('Content-Length', str(len(output)))]
        start_response(status, response_headers)
        return [output]

    try:
        return _app(environ, start_response)
    except Exception:
        status = '500 Internal Server Error'
        output = f"Vercel WSGI Crash!\n\n{traceback.format_exc()}".encode('utf-8')
        response_headers = [('Content-type', 'text/plain'),
                            ('Content-Length', str(len(output)))]
        start_response(status, response_headers)
        return [output]


app = application
