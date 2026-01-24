#!/usr/bin/env python3
"""
Simple HTTP server for the Heimdall demo
"""

import http.server
import logging
import os
import socketserver
import sys
import webbrowser
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="[DEMO] %(message)s"
)
logger = logging.getLogger(__name__)

PORT = 3000

class DemoHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, x-policy-id, x-tenant-id')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()


def main() -> None:
    demo_dir = Path(__file__).parent
    os.chdir(demo_dir)

    handler = DemoHandler
    try:
        with socketserver.TCPServer(('', PORT), handler) as httpd:
            logger.info('Demo server running at http://localhost:%s', PORT)
            logger.info('Serving files from %s', demo_dir)
            logger.info('Opening demo in the browser...')
            logger.info('Start Heimdall gateway on port 8000: python -m bifrost.main')

            webbrowser.open(f'http://localhost:{PORT}')
            httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info('Demo server stopped')
    except OSError as err:
        if 'Address already in use' in str(err):
            logger.error('Port %s already in use. Stop the other server or use a different port.', PORT)
            sys.exit(1)
        raise


if __name__ == '__main__':
    main()
