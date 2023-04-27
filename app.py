#!/usr/bin/env python3
import argparse
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO
import pty
import os
import subprocess
import select
import termios
import struct
import fcntl
import shlex
import logging
import sys

import traceback
from flask_cors import CORS, cross_origin

logging.getLogger("werkzeug").setLevel(logging.ERROR)

__version__ = "0.5.0.2"

app = Flask(__name__, template_folder="templates", static_folder=".", static_url_path="")
app.config["SECRET_KEY"] = "secret!"
app.config["fd"] = None
app.config["child_pid"] = None
socketio = SocketIO(app)


def set_winsize(fd, row, col, xpix=0, ypix=0):
    logging.debug("setting window size with termios")
    winsize = struct.pack("HHHH", row, col, xpix, ypix)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)


def read_and_forward_pty_output():
    max_read_bytes = 1024 * 20
    while True:
        socketio.sleep(0.01)
        if app.config["fd"]:
            timeout_sec = 0
            (data_ready, _, _) = select.select([app.config["fd"]], [], [], timeout_sec)
            if data_ready:
                output = os.read(app.config["fd"], max_read_bytes).decode(
                    errors="ignore"
                )
                socketio.emit("pty-output", {"output": output}, namespace="/pty")


@app.route("/")
def index():
    return render_template("index.html")

cmds = {
    'nodejs':{"run":"node main.js", "install":""},
    'python':{"run":"python main.py", "install":""},
}

@app.route("/terminal/<slug>/")
def lang_terminal(slug):
    cmd = cmds.get(slug)
    
    return render_template("lang-terminal.html", data = cmd)


class InputsNotProvidedError(Exception):
    """Base class for other exceptions"""
    pass



@app.route("/run_python_code/",  methods = ['GET','POST'])
@cross_origin()
def run_python_code():
    if request.method=="POST":

        d = {"error":False}

        request_data = request.get_json()
        inputs = request_data.get('inputs',"").strip()
        code = request_data.get('code',"").strip()
        assert_code = request_data.get("assert_code","")

    
        if inputs:
            if "\n" in inputs:
                a = [i.strip() for i in inputs.split("\n")]
            elif  '\\n' in inputs:
                a = [i.strip() for i in inputs.split("\\n")]
            else:
                a = [inputs]
        else:
            a = []

        i = 0
        l = len(a)
        def input(str=""):
            nonlocal i
            if i<l:
                val = a[i]
                i = i + 1
                return val
            else:
                raise InputsNotProvidedError("input value(s) may not provided")

        orig_stdout = sys.stdout
        with open('file.txt', "w") as f:
            sys.stdout = f
            try:
                exec(code)
            except SyntaxError as err:
                error_class = err.__class__.__name__
                detail = err.args[0]
                line_number = err.lineno
                d = {"error": True, "errorText":"%s at line %d of %s" % (error_class, line_number, detail)}

            except InputsNotProvidedError as err:
                error_class = err.__class__.__name__
                detail = err.args[0]
                d = {"error": True, "errorText":"%s: %s" % (error_class,detail)}

            except Exception as err:
                error_class = err.__class__.__name__
                detail = err.args[0]
                cl, exc, tb = sys.exc_info()
                line_number = traceback.extract_tb(tb)[-1][1]
                d = {"error": True, "errorText":"%s at line %d of %s" % (error_class, line_number, detail)}
            
            except:
                d = {"error": True, "errorText":"Error"}

            sys.stdout = orig_stdout

        if not d['error'] and assert_code!="":
            try:
                exec(assert_code)
                # print("done", assert_code)
            except Exception as err:
                # print(err)
                error_class = err.__class__.__name__
                detail = err.args[0]
                d = {"error": True, "errorText":"%s : %s" % (error_class, detail)}
                # print(d)

        with open("file.txt", 'r') as f:
            v = f.read()
            d['output'] = v

        return jsonify(d)
        
    else:
        return "nothing"
    


@socketio.on("pty-input", namespace="/pty")
def pty_input(data):
    """write to the child pty. The pty sees this as if you are typing in a real
    terminal.
    """
    if app.config["fd"]:
        # logging.debug("received input from browser: %s" % data["input"])
        os.write(app.config["fd"], data["input"].encode())


@socketio.on("resize", namespace="/pty")
def resize(data):
    if app.config["fd"]:
        # logging.debug(f"Resizing window to {data['rows']}x{data['cols']}")
        set_winsize(app.config["fd"], data["rows"], data["cols"])


@socketio.on("connect", namespace="/pty")
def connect():
    """new client connected"""
    logging.info("new client connected")
    if app.config["child_pid"]:
        # already started child process, don't start another
        return

    # create child process attached to a pty we can read from and write to
    (child_pid, fd) = pty.fork()
    if child_pid == 0:
        # this is the child process fork.
        # anything printed here will show up in the pty, including the output
        # of this subprocess
        subprocess.run(app.config["cmd"])
    else:
        # this is the parent process fork.
        # store child fd and pid
        app.config["fd"] = fd
        app.config["child_pid"] = child_pid
        set_winsize(fd, 50, 50)
        cmd = " ".join(shlex.quote(c) for c in app.config["cmd"])
        # logging/print statements must go after this because... I have no idea why
        # but if they come before the background task never starts
        socketio.start_background_task(target=read_and_forward_pty_output)

        logging.info("child pid is " + child_pid)
        logging.info(
            f"starting background task with command `{cmd}` to continously read "
            "and forward pty output to client"
        )
        logging.info("task started")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "A fully functional terminal in your browser. "
            "https://github.com/cs01/pyxterm.js"
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-p", "--port", default=5000, help="port to run server on", type=int
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="host to run server on (use 0.0.0.0 to allow access from other hosts)",
    )
    parser.add_argument("--debug", action="store_true", help="debug the server")
    parser.add_argument("--version", action="store_true", help="print version and exit")
    parser.add_argument(
        "--command", default="bash", help="Command to run in the terminal"
    )
    parser.add_argument(
        "--cmd-args",
        default="",
        help="arguments to pass to command (i.e. --cmd-args='arg1 arg2 --flag')",
    )
    args = parser.parse_args()
    if args.version:
        print(__version__)
        exit(0)
    app.config["cmd"] = [args.command] + shlex.split(args.cmd_args)
    green = "\033[92m"
    end = "\033[0m"
    log_format = (
        green
        + "pyxtermjs > "
        + end
        + "%(levelname)s (%(funcName)s:%(lineno)s) %(message)s"
    )
    logging.basicConfig(
        format=log_format,
        stream=sys.stdout,
        level=logging.DEBUG if args.debug else logging.INFO,
    )
    logging.info(f"serving on http://{args.host}:{args.port}")
    socketio.run(app, debug=args.debug, port=args.port, host=args.host)


if __name__ == "__main__":
    main()