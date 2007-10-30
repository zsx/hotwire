from hotwire_ui.render import ClassRendererMapping, TreeObjectsRenderer, menuitem
from hotwire.sysdep.proc import Process

class ProcessRenderer(TreeObjectsRenderer):
    def _setup_view_columns(self):
        self._insert_propcol('pid', title='PID', ellipsize=False)
        self._insert_proptext('owner_name', title='Owner', ellipsize=False)
        cmdcol = self._insert_proptext('cmd', title='Command', ellipsize=False)
        self._set_search_column(cmdcol)

    @menuitem()
    def kill(self, iter):
        proc = self._model.get_value(iter, 0)
        proc.kill()

ClassRendererMapping.getInstance().register(Process, ProcessRenderer)
