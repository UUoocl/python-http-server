'''
# An OBS Python Script to create an HTTP server
# Add pages to the script folder to run local apps
'''

import obspython as obs
import http.server
import socketserver
import threading
import os

# --- Configuration ---
HOST_NAME = "localhost" # 127.0.0.1
PORT_NUMBER = 8080 # Changed to a common HTTP port
SCRIPT_PATH = ""
# ---------------------

# Global variables to hold the server thread and the server object
server_thread = None
httpd = None

# --- Custom Request Handler with Routing and File Serving ---
class OBSCustomHandler(http.server.SimpleHTTPRequestHandler):

    # Helper function to send the standard headers
    def _set_headers(self, status_code=200, content_type="text/html"):
        self.send_response(status_code)
        self.send_header("Content-type", content_type)
        self.end_headers()

    def do_GET(self):
        # 1. Check the requested path
        path = self.path.split('?')[0] 
       
        obs.script_log(obs.LOG_INFO, f"HTTP Server GET request for path: {path}")

        # 2. Handle specific OBS-related routes example
        if path == "/status":
            # --- Status Page ('/status') - Special OBS Route ---
            self._set_headers(200)
            # ... (response content remains the same as previous answer)
            response_html = "<html><body><h1>OBS Status...</h1></body></html>"
            self.wfile.write(bytes(response_html, "utf-8"))
            
        elif path == "/json-data":
            # --- API Endpoint ('/json-data') - Special OBS Route ---
            # ... (response content remains the same as previous answer)
            import json
            data = {"status": "online"}
            self._set_headers(200, "application/json") 
            self.wfile.write(bytes(json.dumps(data), "utf-8"))

        else:
            # --- Root Path ('/') - Try to load the specified external file ---
            
            # Get the directory of the current script
            #script_path = script_path()
            script_dir = os.path.dirname(SCRIPT_PATH)
            file_path = f"{script_dir}{self.path}"
       
            if os.path.exists(file_path):
                # We found the file! We'll use the parent class's logic to serve it.
                # Temporarily change the requested path to the file name so the
                # SimpleHTTPRequestHandler can find and open it correctly.
                original_path = self.path
                self.path = file_path
                # Call the do_GET method of the parent class (SimpleHTTPRequestHandler)
                # This handles opening, reading, setting correct headers, and serving the file.
                try:
                    super().do_GET()
                finally:
                    # Restore the original path afterwards (good practice)
                    self.path = original_path 
            else:
                # File not found
                self._set_headers(404) 
                response_html = f"<html><body><h1>Error</h1><p>The file <b>{self.path}</b> was not found in the script directory.</p></body></html>"
                self.wfile.write(bytes(response_html, "utf-8"))

# --- Server Control Functions ---
def start_server_in_thread():
    """Starts the HTTP server in a new, non-blocking thread."""
    global httpd
    
    try:
        Handler = OBSCustomHandler
        socketserver.TCPServer.allow_reuse_address = True
        
        # Simple HTTP server creation
        httpd = socketserver.TCPServer((HOST_NAME, PORT_NUMBER), Handler)
        
        obs.script_log(obs.LOG_INFO, f"Starting HTTP server on http://{HOST_NAME}:{PORT_NUMBER}")
        
        httpd.serve_forever()
        
    except Exception as e:
        obs.script_log(obs.LOG_ERROR, f"Error starting server: {e}")
        if httpd:
            httpd.server_close()
        

# script functions
def script_load(settings):
    global SCRIPT_PATH
    global server_thread
   
    SCRIPT_PATH = script_path()
   
    if server_thread is None:
        server_thread = threading.Thread(target=start_server_in_thread)
        server_thread.daemon = True 
        server_thread.start()
        obs.script_log(obs.LOG_INFO, "HTTP Server Thread Initialized.")

def script_unload():
    global httpd, server_thread
    print(f"http unload {httpd}")
    print(f"server_thread.is_alive() {server_thread}")
    if httpd:
        obs.script_log(obs.LOG_INFO, "Stopping HTTP Server...")
        httpd.shutdown()
        httpd.server_close()
        obs.script_log(obs.LOG_INFO, "HTTP Server closed")
        
    # if server_thread and server_thread.is_alive():
    #     server_thread.join(timeout=1.0)
    #     obs.script_log(obs.LOG_INFO, "HTTP Server Thread Cleanly Shut Down.")

def script_description():
    return (
        "<h2>OBS HTTP Localhost Server</h2>"
        "Runs a simple HTTP server in a background thread.<br>"
        f"Access at: <b>http://{HOST_NAME}:{PORT_NUMBER}</b>"
    )

def script_update(settings):
    pass