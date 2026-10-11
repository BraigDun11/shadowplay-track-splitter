"""Update channels, version comparison, download safety and the exe swap."""
import os, sys, tempfile, threading, http.server, functools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import updater as u

P = u.DOWNLOAD_PREFIX


def rel(tag, **kw):
    d = {"tag_name": tag, "draft": False, "html_url": "https://x/" + tag,
         "assets": [{"name": "ShadowPlayTrackSplitter.exe", "size": 5,
                     "browser_download_url": P + tag + "/ShadowPlayTrackSplitter.exe"}]}
    d.update(kw)
    return d


R = [rel("v1.3"), rel("v1.4"), rel("v1.4.1"), rel("v1.4.10"), rel("v1.4.9"), rel("v1.5", draft=True),
     rel("v1.5.1")]
assert u.parse_version("v1.4.10") == (1, 4, 10) and u.parse_version("latest") is None
# stable users see only two-number releases that are newer
assert u.pick_update(R, "1.3")["tag"] == "v1.4"
assert u.pick_update(R, "1.4") is None
assert u.pick_update(R, "1.4.9") is None                # a developer build is already ahead of 1.4
# developers see everything (drafts excluded): 1.4.10 is newer than 1.4.9, 1.5.1 newest
assert u.pick_update(R, "1.4.9", dev=True)["tag"] == "v1.5.1"
assert u.pick_update(R, "1.5.1", dev=True) is None
assert u.pick_update(R, "1.4.10", dev=True)["tag"] == "v1.5.1"
# a release without an exe, or with a foreign download address, is ignored
bad = rel("v2.0"); bad["assets"][0]["browser_download_url"] = "https://evil.example/x.exe"
assert u.pick_update([bad], "1.4") is None
assert u.pick_update([rel("v2.0", assets=[])], "1.4") is None

# download: only the project's address is allowed; MZ header, size and checksum are checked
tmp = tempfile.mkdtemp()
try:
    u.download("https://evil.example/x.exe", os.path.join(tmp, "a"))
    raise AssertionError("foreign address accepted")
except ValueError:
    pass
data = b"MZ" + b"x" * 1000
open(os.path.join(tmp, "srv.exe"), "wb").write(data)
h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=tmp)
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
threading.Thread(target=srv.serve_forever, daemon=True).start()
orig = u.DOWNLOAD_PREFIX
u.DOWNLOAD_PREFIX = "http://127.0.0.1:%d/" % srv.server_address[1]
try:
    dest = os.path.join(tmp, "got.exe")
    seen = []
    u.download(u.DOWNLOAD_PREFIX + "srv.exe", dest, progress=seen.append, size=len(data))
    assert open(dest, "rb").read() == data and seen and seen[-1] == 1.0
    import hashlib
    u.download(u.DOWNLOAD_PREFIX + "srv.exe", dest, sha256=hashlib.sha256(data).hexdigest())
    try:
        u.download(u.DOWNLOAD_PREFIX + "srv.exe", dest, sha256="0" * 64)
        raise AssertionError("bad checksum accepted")
    except IOError:
        assert not os.path.exists(dest)
finally:
    u.DOWNLOAD_PREFIX = orig
    srv.shutdown()

# swap: the running exe is renamed to .old, the new one takes its place
exe = os.path.join(tmp, "app.exe"); new = os.path.join(tmp, "app.exe.new")
open(exe, "wb").write(b"MZold"); open(new, "wb").write(b"MZnew")
u.apply_update(new, exe)
assert open(exe, "rb").read() == b"MZnew" and open(exe + ".old", "rb").read() == b"MZold"
print("OK")
