# -*- coding: utf-8 -*-
"""Couleurs de l'interface (tkinter) : thèmes prédéfinis, application à toute la fenêtre et fenêtre de choix manuel."""
import tkinter as tk
from tkinter import ttk, colorchooser

CLES = ("bg", "fg", "champ", "bouton", "accent", "sel")

THEMES = {
    "Clair / Light": dict(bg="#f2f2f2", fg="#1e1e1e", champ="#ffffff", bouton="#e2e2e2", accent="#3b7dd8", sel="#cfe0f7"),
    "Sombre / Dark": dict(bg="#25272b", fg="#e6e6e6", champ="#2f3237", bouton="#3a3d44", accent="#5aa0ff", sel="#3d5a80"),
    "Océan / Ocean": dict(bg="#e4f0f6", fg="#10303f", champ="#ffffff", bouton="#c5dde9", accent="#0e7fa8", sel="#b4d8e8"),
    "Forêt / Forest": dict(bg="#e7efe4", fg="#1d3320", champ="#fbfdf9", bouton="#cddfc8", accent="#3a8f4a", sel="#bcdcb6"),
    "Pourpre / Purple": dict(bg="#2b2233", fg="#eadff5", champ="#372c42", bouton="#463a54", accent="#b07cf0", sel="#5b4573"),
    "Parchemin / Parchment": dict(bg="#efe4c8", fg="#3a2d14", champ="#fbf5e3", bouton="#decfa6", accent="#a86a1b", sel="#e3cd95"),
}
DEFAUT = "Clair / Light"

LIBELLES = {
    "fr": {"titre": "Couleurs de l'interface", "bg": "Fond", "fg": "Texte", "champ": "Champs et tableaux", "bouton": "Boutons et en-têtes",
           "accent": "Survol des boutons", "sel": "Ligne sélectionnée", "themes": "Thème de départ", "reset": "Réinitialiser",
           "fermer": "Fermer", "choisir": "Choisir la couleur"},
    "en": {"titre": "Interface colors", "bg": "Background", "fg": "Text", "champ": "Fields and tables", "bouton": "Buttons and headers",
           "accent": "Button hover", "sel": "Selected row", "themes": "Starting theme", "reset": "Reset",
           "fermer": "Close", "choisir": "Choose color"},
}


def eclaircir(v, f=0.16):
    """Couleur #rrggbb mélangée à f de blanc (état « survol » des barres de défilement)."""
    r, g, b = (int(v[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(int(x + (255 - x) * f) for x in (r, g, b))


def complet(c):
    """Couleurs valides (clés manquantes ou invalides remplacées par le thème par défaut)."""
    base = dict(THEMES[DEFAUT])
    if isinstance(c, dict):
        for k in CLES:
            v = c.get(k)
            if isinstance(v, str) and len(v) == 7 and v[0] == "#":
                try:
                    int(v[1:], 16)
                    base[k] = v
                except ValueError:
                    pass
    return base


def appliquer(racine, c):
    """Applique les couleurs c (voir CLES) aux widgets ttk et aux widgets tk classiques déjà créés ou à venir."""
    c = complet(c)
    s = ttk.Style(racine)
    try:
        s.theme_use("clam")
    except tk.TclError:
        pass
    s.configure(".", background=c["bg"], foreground=c["fg"], fieldbackground=c["champ"], bordercolor=c["bouton"],
                lightcolor=c["bouton"], darkcolor=c["bouton"], troughcolor=c["bouton"], focuscolor=c["accent"])
    for n in ("TFrame", "TLabelframe", "TLabelframe.Label", "TLabel", "TCheckbutton", "TRadiobutton"):
        s.configure(n, background=c["bg"], foreground=c["fg"])
    s.map("TCheckbutton", background=[("active", c["bg"])])
    s.map("TRadiobutton", background=[("active", c["bg"])])
    s.configure("TButton", background=c["bouton"], foreground=c["fg"])
    s.map("TButton", background=[("active", c["accent"])], foreground=[("active", "#ffffff")])
    s.configure("TEntry", fieldbackground=c["champ"], foreground=c["fg"], insertcolor=c["fg"])
    s.configure("TCombobox", fieldbackground=c["champ"], background=c["bouton"], foreground=c["fg"], arrowcolor=c["fg"],
                selectbackground=c["champ"], selectforeground=c["fg"])
    s.map("TCombobox", fieldbackground=[("readonly", c["champ"])], foreground=[("readonly", c["fg"])])
    s.configure("Treeview", background=c["champ"], fieldbackground=c["champ"], foreground=c["fg"])
    s.map("Treeview", background=[("selected", c["sel"])], foreground=[("selected", c["fg"])])
    s.configure("Treeview.Heading", background=c["bouton"], foreground=c["fg"], bordercolor=c["bouton"],
                lightcolor=c["bouton"], darkcolor=c["bouton"], relief="flat")
    surv_h = eclaircir(c["bouton"], 0.08)
    for opt in ("background", "lightcolor", "darkcolor", "bordercolor"):
        s.map("Treeview.Heading", **{opt: [("pressed", surv_h), ("active", surv_h), ("!active", c["bouton"])]})
    s.map("Treeview.Heading", foreground=[("pressed", c["fg"]), ("active", c["fg"]), ("!active", c["fg"])])
    s.configure("TNotebook", background=c["bg"])
    s.configure("TNotebook.Tab", background=c["bouton"], foreground=c["fg"])
    s.map("TNotebook.Tab", background=[("selected", c["bg"]), ("active", c["accent"])],
          foreground=[("selected", c["fg"]), ("active", "#ffffff")])
    surv = eclaircir(c["bouton"])
    for n in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        # tous les états gardent les couleurs du thème (un peu plus clair au survol et au clic)
        s.configure(n, background=c["bouton"], troughcolor=c["bg"], arrowcolor=c["fg"], bordercolor=c["bouton"],
                    lightcolor=c["bouton"], darkcolor=c["bouton"], gripcount=0)
        for opt in ("background", "lightcolor", "darkcolor", "bordercolor"):
            s.map(n, **{opt: [("disabled", c["bouton"]), ("pressed", surv), ("active", surv), ("!active", c["bouton"])]})
        s.map(n, arrowcolor=[("disabled", c["fg"]), ("pressed", c["fg"]), ("active", c["fg"]), ("!active", c["fg"])])
    racine.option_add("*TCombobox*Listbox.background", c["champ"])
    racine.option_add("*TCombobox*Listbox.foreground", c["fg"])
    racine.option_add("*TCombobox*Listbox.selectBackground", c["accent"])
    racine.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
    racine.configure(bg=c["bg"])
    # widgets tk classiques créés plus tard (formulaires, boîtes de dialogue)
    for cl, opts in (("Text", dict(background=c["champ"], foreground=c["fg"], insertBackground=c["fg"],
                                   selectBackground=c["sel"], selectForeground=c["fg"])),
                     ("Listbox", dict(background=c["champ"], foreground=c["fg"], selectBackground=c["sel"],
                                      selectForeground=c["fg"])),
                     ("Canvas", dict(background=c["bg"])), ("Toplevel", dict(background=c["bg"])),
                     ("Frame", dict(background=c["bg"])), ("Label", dict(background=c["bg"]))):
        for o, v in opts.items():
            racine.option_add("*%s.%s" % (cl, o), v)
    _teindre(racine, c)


def _teindre(w, c):
    for x in w.winfo_children():
        try:
            cl = x.winfo_class()
            if cl in ("Text", "Listbox"):
                x.configure(bg=c["champ"], fg=c["fg"], selectbackground=c["sel"], selectforeground=c["fg"])
                if cl == "Text":
                    x.configure(insertbackground=c["fg"])
            elif cl == "Canvas":
                x.configure(bg=c["bg"])
            elif cl in ("Toplevel", "Frame", "Label"):
                x.configure(bg=c["bg"])
        except tk.TclError:
            pass
        _teindre(x, c)


class DialogueCouleurs(tk.Toplevel):
    """Fenêtre de choix manuel des couleurs ; chaque changement est appliqué tout de suite par rappel(couleurs)."""

    def __init__(self, parent, courant, rappel, langue="fr"):
        super().__init__(parent)
        self.L = LIBELLES.get(langue, LIBELLES["fr"])
        self.rappel = rappel
        self.c = complet(courant)
        self.title(self.L["titre"])
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        self.pastilles = {}
        for i, k in enumerate(CLES):
            ttk.Label(f, text=self.L[k]).grid(row=i, column=0, sticky="w", pady=3, padx=(0, 14))
            b = tk.Button(f, width=12, relief="solid", bd=1, command=lambda k=k: self.choisir(k))
            b.grid(row=i, column=1, pady=3)
            self.pastilles[k] = b
        ttk.Label(f, text=self.L["themes"]).grid(row=len(CLES), column=0, sticky="w", pady=(12, 3))
        self.cb = ttk.Combobox(f, state="readonly", width=22, values=list(THEMES))
        self.cb.grid(row=len(CLES), column=1, pady=(12, 3))
        self.cb.bind("<<ComboboxSelected>>", self.theme)
        bas = ttk.Frame(f)
        bas.grid(row=len(CLES) + 1, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(bas, text=self.L["reset"], command=lambda: self.poser(THEMES[DEFAUT])).pack(side="left", padx=4)
        ttk.Button(bas, text=self.L["fermer"], command=self.destroy).pack(side="left")
        self.maj()

    def maj(self):
        for k, b in self.pastilles.items():
            v = self.c[k]
            r, g, bl = (int(v[i:i + 2], 16) for i in (1, 3, 5))
            b.configure(bg=v, activebackground=v, text=v, fg="#000000" if (r * 299 + g * 587 + bl * 114) / 1000 > 140 else "#ffffff")

    def poser(self, c):
        self.c = complet(c)
        self.maj()
        self.rappel(dict(self.c))

    def theme(self, _e=None):
        self.poser(THEMES[self.cb.get()])

    def choisir(self, k):
        r = colorchooser.askcolor(color=self.c[k], title=self.L["choisir"], parent=self)
        if r and r[1]:
            self.c[k] = r[1].lower()
            self.maj()
            self.rappel(dict(self.c))
