import os
import tkinter as tk
import unittest
from tkinter import ttk
from unittest.mock import patch

from audio_player.dialogs import QueryDialog, askinteger, askstring
from audio_player.theme import THEMES, ThemeMixin


@unittest.skipUnless(os.environ.get("VAULT_TEST_GUI") == "1", "Set VAULT_TEST_GUI=1 to run native Tk dialog tests")
class DialogTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.theme = ThemeMixin()
        self.theme.root = self.root
        self.theme.apply_theme_to_tk_widgets = lambda: None
        self.configure_theme("light")

    def configure_theme(self, mode):
        self.theme.theme_mode = mode
        self.theme.configure_theme()

    def run_prompt(self, prompt, interact, **options):
        failures = []

        def handle_dialog():
            dialog = next(child for child in self.root.winfo_children() if isinstance(child, QueryDialog))
            try:
                interact(dialog)
            except Exception as error:
                failures.append(error)
            finally:
                if dialog.winfo_exists():
                    dialog.cancel()

        self.root.after(100, handle_dialog)
        result = prompt("Test dialog", "Value:", parent=self.root, **options)
        if failures:
            raise failures[0]
        return result

    def buttons(self, dialog):
        return [
            widget
            for frame in dialog.winfo_children()
            for widget in frame.winfo_children()
            if isinstance(widget, ttk.Button)
        ]

    def test_buttons_use_themed_colours_in_both_modes_and_interaction_states(self):
        for mode, palette in THEMES.items():
            with self.subTest(mode=mode):
                self.configure_theme(mode)

                def inspect_buttons(dialog):
                    buttons = self.buttons(dialog)
                    self.assertEqual([button.cget("text") for button in buttons], ["OK", "Cancel"])
                    style = ttk.Style(self.root)
                    for button in buttons:
                        self.assertEqual(button.winfo_class(), "TButton")
                        style_name = button.cget("style")
                        self.assertEqual(style.lookup(style_name, "foreground"), palette["text_color"])
                        self.assertEqual(style.lookup(style_name, "background"), palette["button_bg"])
                        for state in ((), ("active",), ("pressed",), ("active", "pressed")):
                            self.assertNotEqual(
                                style.lookup(style_name, "foreground", state),
                                style.lookup(style_name, "background", state),
                            )

                self.assertIsNone(self.run_prompt(askstring, inspect_buttons))

    def test_ok_returns_the_entered_playlist_name(self):
        def accept(dialog):
            dialog.entry.insert(0, "Evening mixes – 夜")
            self.buttons(dialog)[0].invoke()

        self.assertEqual(self.run_prompt(askstring, accept), "Evening mixes – 夜")

    def test_initial_value_is_selected_and_can_be_replaced(self):
        def replace(dialog):
            self.assertEqual(dialog.entry.get(), "Old playlist")
            self.assertTrue(dialog.entry.selection_present())
            dialog.entry.delete(0, tk.END)
            dialog.entry.insert(0, "New playlist")
            dialog.ok()

        self.assertEqual(self.run_prompt(askstring, replace, initialvalue="Old playlist"), "New playlist")

    def test_cancel_returns_none_even_after_editing(self):
        def cancel(dialog):
            dialog.entry.insert(0, "Discard this")
            self.buttons(dialog)[1].invoke()

        self.assertIsNone(self.run_prompt(askstring, cancel))

    def test_return_accepts_and_escape_cancels(self):
        for key, expected in (("Return", "Keyboard playlist"), ("Escape", None)):
            with self.subTest(key=key):
                def press_key(dialog):
                    dialog.entry.insert(0, "Keyboard playlist")
                    dialog.entry.focus_force()
                    dialog.update()
                    dialog.entry.event_generate(f"<{key}>")
                    self.assertFalse(dialog.winfo_exists())

                self.assertEqual(self.run_prompt(askstring, press_key), expected)

    def test_bpm_rejects_invalid_values_and_accepts_both_limits(self):
        def enter_bpm(dialog):
            with patch("audio_player.dialogs.messagebox.showwarning") as warning:
                for value in ("not a number", "1.5", "0", "301"):
                    dialog.entry.delete(0, tk.END)
                    dialog.entry.insert(0, value)
                    dialog.ok()
                    self.assertTrue(dialog.winfo_exists())
                    self.assertIsNone(dialog.result)
                self.assertEqual(warning.call_count, 4)
            for value in ("1", "300"):
                dialog.entry.delete(0, tk.END)
                dialog.entry.insert(0, value)
                self.assertTrue(dialog.validate())
                self.assertEqual(dialog.result, int(value))
            dialog.ok()

        self.assertEqual(self.run_prompt(askinteger, enter_bpm, minvalue=1, maxvalue=300), 300)


if __name__ == "__main__":
    unittest.main()
