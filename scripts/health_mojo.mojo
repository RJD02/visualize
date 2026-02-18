from python import Python

def main():
    builtins = Python.import_module("builtins")
    globals = builtins.dict()
    code = """
import http.server
import socketserver

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()

def run():
    with socketserver.TCPServer(("0.0.0.0", 8083), Handler) as httpd:
        httpd.serve_forever()

run()
"""
    builtins.exec(code, globals, globals)

