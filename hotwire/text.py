class MarkupText(str):
    def __new__(cls, value, tag=None):
        inst = super(MarkupText, cls).__new__(cls, value)
        inst.markup = []
        if tag:
            inst.add_markup(tag)
        return inst

    def add_markup(self, tag, start=0, end=-1):
        self.markup.append((tag, start, end))
