import tkinter as tk
from tkinter import messagebox, simpledialog, ttk


class QueryDialog(simpledialog.Dialog):
    def __init__(self, parent, title, prompt, initialvalue=None, integer=False, minvalue=None, maxvalue=None):
        self.prompt = prompt
        self.initialvalue = initialvalue
        self.integer = integer
        self.minvalue = minvalue
        self.maxvalue = maxvalue
        super().__init__(parent, title)

    def body(self, master):
        ttk.Label(master, text=self.prompt, justify=tk.LEFT).grid(row=0, padx=5, pady=(0, 5), sticky="w")
        self.entry = ttk.Entry(master, width=30)
        self.entry.grid(row=1, padx=5, sticky="ew")
        if self.initialvalue is not None:
            self.entry.insert(0, self.initialvalue)
            self.entry.selection_range(0, tk.END)
        return self.entry

    def buttonbox(self):
        buttons = ttk.Frame(self)
        ttk.Button(buttons, text="OK", width=10, command=self.ok, style="Action.TButton").pack(
            side=tk.LEFT, padx=5, pady=5,
        )
        ttk.Button(buttons, text="Cancel", width=10, command=self.cancel, style="Action.TButton").pack(
            side=tk.LEFT, padx=5, pady=5,
        )
        buttons.pack(pady=(5, 0))
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)

    def validate(self):
        result = self.entry.get()
        if self.integer:
            try:
                result = self.getint(result)
            except (ValueError, tk.TclError):
                messagebox.showwarning("Illegal value", "Not an integer.\nPlease try again", parent=self)
                return False
            if self.minvalue is not None and result < self.minvalue:
                messagebox.showwarning(
                    "Too small", f"The allowed minimum value is {self.minvalue}. Please try again.", parent=self,
                )
                return False
            if self.maxvalue is not None and result > self.maxvalue:
                messagebox.showwarning(
                    "Too large", f"The allowed maximum value is {self.maxvalue}. Please try again.", parent=self,
                )
                return False
        self.result = result
        return True


def askstring(title, prompt, *, parent, initialvalue=None):
    return QueryDialog(parent, title, prompt, initialvalue=initialvalue).result


def askinteger(title, prompt, *, parent, initialvalue=None, minvalue=None, maxvalue=None):
    return QueryDialog(
        parent, title, prompt, initialvalue=initialvalue, integer=True, minvalue=minvalue, maxvalue=maxvalue,
    ).result
