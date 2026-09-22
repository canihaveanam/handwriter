import os


class FontManager:

    def __init__(
        self,
        resource_path_func,
        fonts_dir="fonts",
        default_font="StyleA",
    ):
        self.resource_path_func = resource_path_func
        self.fonts_dir = fonts_dir
        self.default_font = default_font

    def get_fonts_dir(self):
        return self.resource_path_func(self.fonts_dir)

    def list_fonts(self):
        fonts_dir = self.get_fonts_dir()

        if not os.path.isdir(fonts_dir):
            return []

        fonts = []

        for filename in os.listdir(fonts_dir):
            if filename.lower().endswith(".ttf"):
                fonts.append(os.path.splitext(filename)[0])

        return sorted(fonts, key=str.lower)

    def get_default_font(self):
        fonts = self.list_fonts()

        if self.default_font in fonts:
            return self.default_font

        if fonts:
            return fonts[0]

        return None

    def get_font_path(self, font_name):
        fonts = self.list_fonts()

        if font_name not in fonts:
            return None

        return os.path.join(
            self.get_fonts_dir(),
            font_name + ".ttf",
        )
