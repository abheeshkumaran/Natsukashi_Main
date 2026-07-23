import os
import sys
import traceback

def application(environ, start_response):
    try:
        from pathlib import Path
        BASE_DIR = Path(__file__).resolve().parent
        if str(BASE_DIR) not in sys.path:
            sys.path.append(str(BASE_DIR))
            
        from django.core.wsgi import get_wsgi_application
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'natsukashi_design.settings')
        _app = get_wsgi_application()
        return _app(environ, start_response)
    except Exception as e:
        status = '500 Internal Server Error'
        output = f"Vercel WSGI Crash!\n\n{traceback.format_exc()}".encode('utf-8')
        response_headers = [('Content-type', 'text/plain'),
                            ('Content-Length', str(len(output)))]
        start_response(status, response_headers)
        return [output]

app = application
