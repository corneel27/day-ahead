import os
from http import HTTPStatus
import urllib.parse
import datetime
import html
import sys, io
from http.server import HTTPServer, CGIHTTPRequestHandler# Make sure the server is created at current directory

class ModifiedHTTPRequestHandler(CGIHTTPRequestHandler):
    def list_directory(self, path):
        """Helper to produce a directory listing (absent index.html).

        Return value is either a file object, or None (indicating an
        error).  In either case, the headers are sent, making the
        interface the same as for send_head().

        """
        try:
            list = os.listdir(path)
        except OSError:
            self.send_error(
                HTTPStatus.NOT_FOUND,
                "No permission to list directory")
            return None
        list.sort(key=lambda a: os.path.getmtime(a), reverse=True)
        r = []
        try:
            displaypath = urllib.parse.unquote(self.path,
                                               errors='surrogatepass')
        except UnicodeDecodeError:
            displaypath = urllib.parse.unquote(path)
        displaypath = html.escape(displaypath, quote=False)
        enc = sys.getfilesystemencoding()
        title = f'Directory listing for {displaypath}'
        r.append('<!DOCTYPE HTML>')
        r.append('<html lang="en">')
        r.append('<head>')
        r.append(f'<meta charset="{enc}">')
        r.append(f'<title>{title}</title>\n</head>')
        r.append(f'<body>\n<h1>{title}</h1>')
        r.append('<hr>\n<ul>')
        for name in list:
            fullname = os.path.join(path, name)
            displayname = linkname = name
            # Append / for directories or @ for symbolic links
            if os.path.isdir(fullname):
                displayname = name + "/"
                linkname = name + "/"
            if os.path.islink(fullname):
                displayname = name + "@"
                # Note: a link to a directory displays with @ and links with /
            file_time = datetime.datetime.fromtimestamp(os.path.getmtime(fullname))
            r.append('<li>%s <a href="%s">%s</a></li>'
                    % (file_time.strftime("%Y-%m-%d, %H:%M"),
                       urllib.parse.quote(linkname,
                                          errors='surrogatepass'),
                       html.escape(displayname, quote=False)))
        r.append('</ul>\n<hr>\n</body>\n</html>\n')
        encoded = '\n'.join(r).encode(enc, 'surrogateescape')
        f = io.BytesIO()
        f.write(encoded)
        f.seek(0)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-type", "text/html; charset=%s" % enc)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        return f


old_stdout = sys.stdout
s = os.getcwd()
print(s)
#log_file = open("data/log/webserver" + datetime.datetime.now().strftime("%H%M") + ".log", "x")
#sys.stdout = log_file

os.chdir('../data/images')
# Create server object listening the port 80
server_object = HTTPServer(server_address=('', 8012), RequestHandlerClass=ModifiedHTTPRequestHandler)
# Start the web server
server_object.serve_forever()

sys.stdout = old_stdout
#log_file.close()
