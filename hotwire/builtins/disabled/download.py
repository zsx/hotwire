from hotwire import FilePath
from hotwire.iterdir import iterdir

from hotwire.builtin import Builtin, BuiltinRegistry, streamtypes

class DownloadBuiltin(Builtin):
    def __init__(self):
        super(DownloadBuiltin, self).__init__('download')

    @streamtypes(FilePath, None)
    def execute(self, context):
        for arg in context.input:
            context.hotwire.start_download(FilePath(arg, context.cwd))
        return []
BuiltinRegistry.getInstance().register(DownloadBuiltin())
