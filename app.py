# app.py

import os
import io
import time
import threading

# Kivy & KivyMD
from kivy.lang import Builder
from kivy.properties import (
    ListProperty, NumericProperty, BooleanProperty
)
from kivy.uix.screenmanager import Screen, ScreenManager, SlideTransition
from kivy.uix.scrollview import ScrollView
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.widget import Widget
from kivy.graphics import Color, Line

from kivy.core.window import Window  # For drag & drop on desktop
from kivy.utils import platform     # Detect Android / iOS / win / linux / macos

from kivymd.app import MDApp
from kivymd.uix.navigationdrawer import MDNavigationDrawer
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.list import OneLineListItem
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDFlatButton
from kivymd.uix.toolbar import MDTopAppBar

# For file picking
from plyer import filechooser

# PDF (PyMuPDF) & Image
import fitz
from PIL import Image as PILImage


###############################################################################
# Simple drawing widget: White background, black lines
###############################################################################
class DrawingCanvas(Widget):
    """
    A basic freehand drawing widget with a white background and black lines.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        with self.canvas:
            Color(0, 0, 0, 1)  # black lines
            touch.ud["line"] = Line(points=(touch.x, touch.y), width=2)

    def on_touch_move(self, touch):
        if "line" in touch.ud and self.collide_point(*touch.pos):
            line = touch.ud["line"]
            line.points += [touch.x, touch.y]

    def clear_canvas(self):
        """Clear all lines and redraw the background."""
        self.canvas.clear()
        self._draw_bg()

    def on_size(self, *args):
        self._draw_bg()

    def on_pos(self, *args):
        self._draw_bg()

    def _draw_bg(self):
        """
        Fill the widget with a white rectangle behind any drawn lines.
        """
        self.canvas.before.clear()
        with self.canvas.before:
            Color(1, 1, 1, 1)  # white
            from kivy.graphics import Rectangle
            Rectangle(pos=self.pos, size=self.size)


###############################################################################
# Screens
###############################################################################
class MainScreen(Screen):
    """Home screen with basic navigation."""
    pass


class PDFViewerScreen(Screen):
    """
    A PDF viewer that:
    - Supports multiple PDFs (open file + drag & drop).
    - Next/Prev PDF, lock PDF, scrollable pages.
    - A left drawing panel toggled by "Drawing Panel" button on desktop.
    - On phone (Android/iOS), the drawing panel is hidden entirely.
    """
    pdf_files = ListProperty()
    current_index = NumericProperty(0)
    pdf_locked = BooleanProperty(False)

    # We track phone_mode to hide the drawing panel on mobile
    phone_mode = BooleanProperty(False)

    # panel_visible is for toggling the panel on desktop
    panel_visible = BooleanProperty(False)

    def on_enter(self):
        """Determine if we're on phone or desktop. Hide the panel if phone."""
        if platform in ("android", "ios"):
            self.phone_mode = True
        else:
            self.phone_mode = False

    def open_pdfs_dialog(self):
        """Pick multiple PDF files from the file system."""
        filechooser.open_file(
            multiple=True,
            filters=[("PDF files", "*.pdf")],
            on_selection=self.handle_pdfs_selection
        )

    def handle_pdfs_selection(self, selection):
        """Append the chosen PDFs to our list, and display the first if new."""
        if not selection:
            self.ids.pdf_info_label.text = "No PDFs selected."
            return

        # Add the new PDF paths
        self.pdf_files.extend(selection)

        # If we had none before, load the first new one
        if len(selection) and len(self.pdf_files) == len(selection):
            self.current_index = 0
            self.load_current_pdf()
        else:
            self.update_pdf_label()

    def load_current_pdf(self):
        """Render pages of the current PDF into a scrollable layout."""
        if not self.pdf_files:
            self.ids.pdf_info_label.text = "No PDFs selected."
            return

        pdf_path = self.pdf_files[self.current_index]
        name = os.path.basename(pdf_path)
        self.ids.pdf_info_label.text = f"Loading {name}..."

        pages_layout = self.ids.pages_layout
        pages_layout.clear_widgets()

        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            self.ids.pdf_info_label.text = f"Error opening PDF:\n{e}"
            return

        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap()
            png_data = pix.tobytes("png")

            from kivy.uix.image import Image
            img_widget = Image(allow_stretch=True, keep_ratio=True)
            img_widget.texture = self._png_to_texture(png_data)

            wrapper = BoxLayout(orientation='vertical', size_hint_y=None)
            wrapper.height = 1000  # approximate
            wrapper.padding = 10
            wrapper.add_widget(img_widget)

            pages_layout.add_widget(wrapper)

        doc.close()
        self.update_pdf_label()

    def _png_to_texture(self, png_data):
        from kivy.graphics.texture import Texture
        pil_img = PILImage.open(io.BytesIO(png_data))
        tex = Texture.create(size=(pil_img.width, pil_img.height))
        tex.flip_vertical()
        mode = 'rgba' if pil_img.mode == 'RGBA' else 'rgb'
        tex.blit_buffer(pil_img.tobytes(), colorfmt=mode, bufferfmt='ubyte')
        return tex

    def update_pdf_label(self):
        """Show which PDF is active, plus lock status."""
        if not self.pdf_files:
            self.ids.pdf_info_label.text = "No PDFs selected."
            return
        current = self.current_index + 1
        total = len(self.pdf_files)
        name = os.path.basename(self.pdf_files[self.current_index])
        locked_text = " (Locked)" if self.pdf_locked else ""
        self.ids.pdf_info_label.text = f"Viewing {current}/{total}: {name}{locked_text}"

    def prev_pdf(self):
        """Go to the previous PDF if not locked."""
        if self.pdf_locked:
            return
        if self.pdf_files:
            self.current_index = (self.current_index - 1) % len(self.pdf_files)
            self.load_current_pdf()

    def next_pdf(self):
        """Go to the next PDF if not locked."""
        if self.pdf_locked:
            return
        if self.pdf_files:
            self.current_index = (self.current_index + 1) % len(self.pdf_files)
            self.load_current_pdf()

    def toggle_lock(self):
        """Lock or unlock PDF switching."""
        self.pdf_locked = not self.pdf_locked
        self.update_pdf_label()

    def toggle_draw_panel(self):
        """
        Toggle the left drawing panel (desktop only).
        On phone, it won't be shown anyway.
        """
        self.panel_visible = not self.panel_visible

    def clear_drawing(self):
        """Clear lines from the drawing panel."""
        self.ids.draw_canvas.clear_canvas()

    def add_dropped_pdf(self, path):
        """
        Called if the user drags a PDF into the app.
        We'll add it to the list. If it's the first PDF, load it.
        """
        lower_path = path.lower()
        if not lower_path.endswith(".pdf"):
            return
        old_len = len(self.pdf_files)
        self.pdf_files.append(path)
        if old_len == 0:
            self.current_index = 0
            self.load_current_pdf()
        else:
            self.update_pdf_label()


###############################################################################
# KV
###############################################################################
KV = r"""
#:import SlideTransition kivy.uix.screenmanager.SlideTransition

MDNavigationLayout:
    orientation: "horizontal"

    ScreenManager:
        id: screen_manager
        transition: SlideTransition()

        MainScreen:
        PDFViewerScreen:
        # Removed PDFCreationScreen
        # Removed the (already removed) AutoScanScreen

    MDNavigationDrawer:
        id: nav_drawer
        type: "standard"
        width: dp(240)
        radius: (0, 16, 16, 0)

        MDBoxLayout:
            orientation: "vertical"
            spacing: dp(20)
            padding: dp(20)

            MDLabel:
                text: "Navigation"
                halign: "center"
                font_style: "H5"

            OneLineListItem:
                text: "Home"
                on_release:
                    nav_drawer.set_state("close")
                    app.change_screen("home")

            OneLineListItem:
                text: "PDF Viewer"
                on_release:
                    nav_drawer.set_state("close")
                    app.change_screen("pdfviewer")

            # Removed the "Create PDF" item

<MainScreen>:
    name: "home"
    MDBoxLayout:
        orientation: "vertical"

        MDTopAppBar:
            title: "Student Note Manager"
            elevation: 4
            left_action_items: [["menu", lambda x: nav_drawer.set_state("toggle")]]

        MDBoxLayout:
            orientation: "vertical"
            spacing: dp(20)
            padding: dp(20)

            MDLabel:
                text: "Welcome! Choose an option."
                halign: "center"

            MDFlatButton:
                text: "PDF Viewer"
                pos_hint: {"center_x": 0.5}
                on_release:
                    app.change_screen("pdfviewer")

            # Removed the "Create PDF From Images" button

            MDFlatButton:
                text: "Exit"
                pos_hint: {"center_x": 0.5}
                on_release:
                    app.stop()

<PDFViewerScreen>:
    name: "pdfviewer"

    BoxLayout:
        orientation: "horizontal"

        # Left drawing panel
        # If phone_mode is True, we hide it entirely by setting size_hint_x=0
        # We also hide the toggle button in the next box layout
        BoxLayout:
            orientation: "vertical"
            size_hint_x:
                (0 if root.phone_mode else (0.3 if root.panel_visible else 0))
            padding: dp(8)

            MDLabel:
                text: "Drawing Panel"
                halign: "left"
                size_hint_y: None
                height: self.texture_size[1] + dp(20)

            DrawingCanvas:
                id: draw_canvas
                size_hint: (1, 1)

            MDFlatButton:
                text: "Clear Drawing"
                pos_hint: {"center_x": 0.5}
                on_release: root.clear_drawing()

        BoxLayout:
            orientation: "vertical"
            spacing: dp(10)

            MDLabel:
                id: pdf_info_label
                text: "Click 'Open PDFs' or drag some in."
                halign: "center"
                size_hint_y: None
                height: self.texture_size[1] + dp(20)

            ScrollView:
                bar_width: dp(8)
                do_scroll_x: False
                do_scroll_y: True

                BoxLayout:
                    id: pages_layout
                    orientation: "vertical"
                    size_hint_y: None
                    height: self.minimum_height

            MDBoxLayout:
                size_hint_y: None
                height: dp(48)
                spacing: dp(8)
                padding: dp(8)

                MDFlatButton:
                    text: "Open PDFs"
                    on_release: root.open_pdfs_dialog()

                MDFlatButton:
                    text: "< Prev PDF"
                    on_release: root.prev_pdf()

                MDFlatButton:
                    text: "Next PDF >"
                    on_release: root.next_pdf()

                MDFlatButton:
                    text: "Lock PDF"
                    on_release: root.toggle_lock()

                # Hide/disable this toggle if phone_mode is True
                MDFlatButton:
                    text: "Drawing Panel"
                    on_release: root.toggle_draw_panel()
                    opacity: 1 if not root.phone_mode else 0
                    disabled: True if root.phone_mode else False

            MDBoxLayout:
                size_hint_y: None
                height: dp(48)
                MDFlatButton:
                    text: "Back to Home"
                    pos_hint: {"center_x": 0.5}
                    on_release:
                        app.change_screen("home")
"""


###############################################################################
# Main App
###############################################################################
class MyApp(MDApp):
    def build(self):
        self.title = "Student Note Manager"
        self.theme_cls.theme_style = "Dark"
        root = Builder.load_string(KV)
        return root

    def on_start(self):
        """
        Bind the on_dropfile event so that if the user drags PDFs in,
        we pass them to the PDFViewerScreen.
        """
        # On desktop, the user can drag PDFs. On mobile, typically won't do that.
        Window.bind(on_dropfile=self._handle_file_drop)

    def _handle_file_drop(self, window, file_path):
        """
        Called when a file is dragged onto the app window (desktop).
        We pass the path to the PDFViewerScreen.
        """
        path_str = file_path.decode("utf-8")
        pdf_screen = self.root.ids.screen_manager.get_screen('pdfviewer')
        pdf_screen.add_dropped_pdf(path_str)

    def change_screen(self, screen_name):
        """
        Switch screens in the main ScreenManager.
        """
        sm = self.root.ids.screen_manager
        if screen_name == "home":
            sm.transition.direction = "right"
        else:
            sm.transition.direction = "left"
        sm.current = screen_name


if __name__ == "__main__":
    MyApp().run()
