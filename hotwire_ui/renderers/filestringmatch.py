import os, stat, signal, datetime

import gtk, gobject, pango

import hotwire
import hotwire_ui.widgets as hotwidgets
from hotwire_ui.renderers.file import FilePathRenderer
from hotwire_ui.render import ClassRendererMapping
from hotwire.builtins.fsearch import FileStringMatch
from hotwire.util import markup_for_match

class FileStringMatchRenderer(FilePathRenderer):
    def __init__(self, *args, **kwargs):
        if not 'column_types' in kwargs.iterkeys():
            kwargs['column_types'] = [gobject.TYPE_PYOBJECT, gobject.TYPE_PYOBJECT, gobject.TYPE_PYOBJECT]
        super(FileStringMatchRenderer, self).__init__(*args,
                                                      **kwargs)

    def _setup_view_columns(self):
        self._setup_icon_path_columns()
        colidx = self._table.insert_column_with_data_func(-1, 'Match',
                                                          hotwidgets.CellRendererText(),
                                                          self._render_match)
        col = self._table.get_column(colidx-1)
        col.set_spacing(0)

    def _match_for_iter(self, model, iter):
        return model.get_value(iter, 2)

    def _render_match(self, col, cell, model, iter):
        obj = self._match_for_iter(model, iter)
        matchmarkup = markup_for_match(obj.text, obj.match_start, obj.match_end)
        cell.set_property('markup', matchmarkup)

    def _get_row(self, obj):
        uprow = super(FileStringMatchRenderer, self)._get_row(obj.path)
        return uprow + (obj,)

    def get_objects(self):
        iter = self._model.get_iter_first()
        while iter:
            val = self._model.get_value(iter, 2)
            yield val
            iter = self._model.iter_next(iter)

ClassRendererMapping.getInstance().register(FileStringMatch, FileStringMatchRenderer)
