"""Launch the app preloaded with Isaac's Week 12 sample data."""
import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
import main as appmod

XL = r"C:/Users/isaac/Downloads/Week 12 Isaacx.xls"
EST1 = r"C:/Users/isaac/Downloads/Week 12 Day 1 Isaac.est"
EST2 = r"C:/Users/isaac/Downloads/Week 12 Day 2 Isaac.est"

app = QApplication(sys.argv)
win = appmod.MainWindow()
win.show()

import traceback

_done = {"ran": False}

def preload():
    if _done["ran"]:
        return
    _done["ran"] = True
    try:
        win.excel_paths = [XL]
        win.est_paths = [EST1, EST2]
        win._refresh_file_lists()
        win._set_origin(34.11864, -117.919266)  # first Azusa site as start
        win._build_route_from_uploads()  # runs route in worker, switches to Route page
        with open("_diag_py.txt", "w", encoding="utf-8") as f:
            f.write(f"preload_ok stops={len(win.state.stops)} home={win.state.home}\n")
    except Exception:
        with open("_diag_py.txt", "w", encoding="utf-8") as f:
            f.write("PRELOAD_ERROR\n" + traceback.format_exc())

DIAG_JS = r"""(function(){
  function gl(){try{var c=document.createElement('canvas');
    var g=c.getContext('webgl2')||c.getContext('webgl')||c.getContext('experimental-webgl');
    if(!g) return 'none'; var dbg=g.getExtension('WEBGL_debug_renderer_info');
    return dbg ? g.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : 'webgl-ok';}catch(e){return 'err:'+e;}}
  var segs=-1, c=null, z=null;
  try{ var s=window._map.getSource('segments'); segs=(s._data.features||[]).length;
       var cc=window._map.getCenter(); c=[+cc.lng.toFixed(3),+cc.lat.toFixed(3)];
       z=+window._map.getZoom().toFixed(2); }catch(e){}
  return JSON.stringify({loaded:!!window.__mapLoaded, inject:!!window.__jsInject,
    bridge:!!window.__bridgeReady, webgl:gl(), segs:segs, center:c, zoom:z, dbg:window.__dbg,
    errs:(window.__jsErrors||[]).slice(0,10)});
})()"""

def diag():
    win.view.page().runJavaScript(DIAG_JS,
        lambda r: open("_diag.json", "w", encoding="utf-8").write(r or "EMPTY"))

# Run preload only AFTER the JS map bridge is connected, so the first state push
# is actually received. Fallback timer in case mapReady is missed.
win.bridge.mapReady.connect(lambda: QTimer.singleShot(600, preload))
QTimer.singleShot(7000, preload)   # safety net
QTimer.singleShot(13000, diag)
sys.exit(app.exec())
