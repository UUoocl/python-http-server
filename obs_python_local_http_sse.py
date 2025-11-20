# A python HTTP server with SSE events
# Created with Google AI studio
"""
# crashes on refresh or OBS exit 
"""

import obspython as obs
import http.server
import socketserver
import threading
import os
import time
import json # Added for JSON data in SSE example

# --- Configuration ---
HOST_NAME = "localhost" # 127.0.0.1
PORT_NUMBER = 8080 
SCRIPT_PATH = ""
# ---------------------

# Global variables to hold the server thread and the server object
server_thread = None
httpd = None

# --- NEW Globals for Hotkey and SSE Management ---
# Use a set to hold the wfile objects of connected SSE clients
sse_connections = set() 
hotkey_id = None # To store the registered hotkey ID
hotkey_counter = 0 # To track how many times the hotkey was pressed
# --------------------------------------------------

# --- Helper Function for Broadcasting SSE Events ---
def broadcast_sse_event(event_name, data):
    """Sends an event to all connected SSE clients."""
    global sse_connections
    
    # SSE Format: event: <name>\ndata: <json_data>\n\n
    message = f"event: {event_name}\ndata: {data}\n\n"
    message_bytes = message.encode("utf-8")
    
    disconnected = set()
    
    # Iterate over a copy of the set to allow safe modification
    for wfile in list(sse_connections): 
        try:
            wfile.write(message_bytes)
            wfile.flush()
        except Exception:
            # Client disconnected (e.g., BrokenPipeError)
            disconnected.add(wfile)
            obs.script_log(obs.LOG_INFO, "SSE Client detected as disconnected during broadcast.")
            
    # Clean up disconnected clients
    sse_connections -= disconnected

# --- NEW Hotkey Callback Function ---
def hotkey_callback(pressed):
    """Called when the registered hotkey is pressed."""
    global hotkey_counter
    print(f"hk pressed {pressed}")
    # We only care about the key-down event, not key-up
    if not pressed:
        hotkey_counter += 1
        
        # 1. Prepare the JSON data for the event
        data = json.dumps({
            "time": time.strftime("%H:%M:%S"), 
            "press_count": hotkey_counter, 
            "message": "OBS Hotkey Pressed!"
        })
        
        # 2. Broadcast the event with a specific name
        broadcast_sse_event("hotkey_trigger", data)
        obs.script_log(obs.LOG_INFO, f"SSE Hotkey pressed. Event broadcast: {hotkey_counter}. Total Clients: {len(sse_connections)}")

# --- Custom Request Handler with Routing and File Serving ---
class OBSCustomHandler(http.server.SimpleHTTPRequestHandler):

    # Helper function to send the standard headers
    def _set_headers(self, status_code=200, content_type="text/html"):
        self.send_response(status_code)
        self.send_header("Content-type", content_type)
        self.end_headers()

    def do_GET(self):
        # ... (other routes remain the same)
        path = self.path.split('?')[0] 
       
        obs.script_log(obs.LOG_INFO, f"HTTP Server GET request for path: {path}")

        if path == "/status":
            self._set_headers(200)
            response_html = "<html><body><h1>OBS Status...</h1></body></html>"
            self.wfile.write(bytes(response_html, "utf-8"))
            
        elif path == "/json-data":
            data = {"status": "online"}
            self._set_headers(200, "application/json") 
            self.wfile.write(bytes(json.dumps(data), "utf-8"))

        elif path == "/sse-stream": 
            # --- Server-Sent Events (SSE) Route ---
            global sse_connections
            
            # 1. Set SSE Headers
            self.send_response(200)
            self.send_header("Content-type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*") 
            self.end_headers()
            
            # 2. Add this connection to the global set
            sse_connections.add(self.wfile)
            obs.script_log(obs.LOG_INFO, "New SSE Client Connected. Total: " + str(len(sse_connections)))
            
            # 3. Send a welcome message
            welcome_message = "event: welcome\ndata: Connected to OBS SSE Stream\n\n"
            try:
                self.wfile.write(welcome_message.encode("utf-8"))
                self.wfile.flush()
            except Exception:
                sse_connections.discard(self.wfile)
                return
            
            # 4. Keep the connection alive
            try:
                # This loop keeps the request handler thread blocked.
                while self.wfile in sse_connections:
                    # Non-blocking wait is necessary
                    threading.Event().wait(timeout=1.0) 
            except Exception as e:
                obs.script_log(obs.LOG_INFO, f"SSE Client connection closed (handler side): {e}")
            finally:
                sse_connections.discard(self.wfile)
                obs.script_log(obs.LOG_INFO, "SSE Client connection cleanup complete.")

        else:
            # --- File Serving ---
            script_dir = os.path.dirname(SCRIPT_PATH)
            requested_file = os.path.normpath(self.path.lstrip('/'))
            file_path = os.path.join(script_dir, requested_file)
            print(f"filePath {file_path}")
            if os.path.exists(file_path) and file_path.startswith(script_dir):
                original_path = self.path
                self.path = file_path 
                try:
                    super().do_GET()
                finally:
                    self.path = original_path 
            else:
                self._set_headers(404) 
                response_html = f"<html><body><h1>Error</h1><p>The file <b>{self.path}</b> was not found in the script directory or access was denied.</p></body></html>"
                self.wfile.write(bytes(response_html, "utf-8"))

# --- Server Control Functions ---
def start_server_in_thread():
    """Starts the HTTP server in a new, non-blocking thread."""
    global httpd
    
    try:
        Handler = OBSCustomHandler
        
        # Use ThreadingMixIn for concurrent requests (required for SSE)
        class ThreadingServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
            pass

        ThreadingServer.allow_reuse_address = True
        
        httpd = ThreadingServer((HOST_NAME, PORT_NUMBER), Handler)
        
        obs.script_log(obs.LOG_INFO, f"Starting HTTP server on http://{HOST_NAME}:{PORT_NUMBER}")
        
        httpd.serve_forever()
        
    except Exception as e:
        obs.script_log(obs.LOG_ERROR, f"Error starting server: {e}")
        if httpd:
            httpd.server_close()
        

# --- OBS Script Functions for Hotkey and Server Management ---

def script_properties():
    """Defines the hotkey property in the OBS script panel."""
    props = obs.obs_properties_create()
    
    # The string "sse_trigger_hotkey" is the unique ID for the hotkey setting
    # obs.obs_properties_add_hotkey(props, "sse_trigger_hotkey", "OBS SSE Hotkey Trigger")
    
    return props

def script_load(settings):
    global SCRIPT_PATH
    global server_thread, hotkey_id
   
    SCRIPT_PATH = script_path()

    # Attach signal handlers to keyHotkey text source
    source_name = "keyHotkey"
    print(f"source name {source_name}")
    source = obs.obs_get_source_by_name(source_name)
    print(f"source object {source}")
    if source:
        signal_handler = obs.obs_source_get_signal_handler(source)
        obs.signal_handler_connect(signal_handler,"update", source_signal_callback)
        obs.obs_source_release(source)
    else:
        print(f"Source {source_name} not found for signal handler.")

    # 1. Start the HTTP Server Thread (Unchanged)
    if server_thread is None:
        server_thread = threading.Thread(target=start_server_in_thread, name="HTTP_Server_Thread")
        server_thread.daemon = True 
        server_thread.start()
        obs.script_log(obs.LOG_INFO, "HTTP Server Thread Initialized.")

    # 2. Register and Load the Hotkey
    hotkey_save_data = obs.obs_data_get_array(settings, "sse_trigger_hotkey")
    hotkey_id = obs.obs_hotkey_register_frontend("OBS_SSE_HOTKEY", "OBS SSE Trigger", hotkey_callback)
    obs.obs_hotkey_load(hotkey_id, hotkey_save_data)


def script_save(settings):
    """Saves the hotkey binding when the script settings are closed."""
    global hotkey_id
    if hotkey_id is not None:
        hotkey_save_data = obs.obs_hotkey_save(hotkey_id)
        obs.obs_data_set_array(settings, "sse_trigger_hotkey", hotkey_save_data)
        
def script_unload():
    global httpd, server_thread, hotkey_id
    
    # remove signal handlers to keyHotkey text source
    source_name = "keyHotkey"
    print(f"source name {source_name}")
    source = obs.obs_get_source_by_name(source_name)
    print(f"source object {source}")
    try:
        if source:
            handler = obs.obs_source_get_signal_handler(source)
            obs.signal_handler_disconnect(handler,"update", source_signal_callback)
            obs.obs_source_release(source)
    except Exception as e:
        print("no source signal to remove")

    # 1. Unregister the hotkey
    if hotkey_id is not None:
        obs.obs_hotkey_unregister(hotkey_callback)
        obs.script_log(obs.LOG_INFO, "Hotkey unregistered.")
        
    # 2. Stop the HTTP server (Unchanged)
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
        "<h2>OBS HTTP Localhost Server with Hotkey SSE</h2>"
        "Runs a multithreaded HTTP server.<br>"
        "An SSE event is sent to all connected clients when the configured Hotkey is pressed.<br>"
        f"SSE Stream: <b>http://{HOST_NAME}:{PORT_NUMBER}/sse-stream</b>"
    )

def script_update(settings):
    pass


# -- source signal handler
def source_signal_callback(calldata):
    try:
        source = obs.calldata_source(calldata,"source")
        source_name = obs.obs_source_get_name(source)
        # find client that matches updated text source
        source_settings = obs.obs_source_get_settings(source)
        text = obs.obs_data_get_string(source_settings, "text").replace(" ","")
        print(f"source text {type(text)} {text}")

        # 1. Prepare the JSON data for the event
        data = json.dumps({
            "time": time.strftime("%H:%M:%S"), 
            "press_count": hotkey_counter, 
            "message": text
        })
        
        # 2. Broadcast the event with a specific name
        broadcast_sse_event("hotkey_trigger", data)
        obs.script_log(obs.LOG_INFO, f"SSE Hotkey pressed. Event broadcast: {hotkey_counter}. Total Clients: {len(sse_connections)}")

        obs.obs_data_release(source_settings)
        obs.obs_source_release(source_name)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
    except Exception as e:
        print(f"Error processing SSE send data: {e}")
