#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Changer of Banners : ajoute des emblèmes (.gtex) à toutes les armées de Warhammer: Mark of Chaos – Battle March.
Programme autonome : choisir le dossier des .gtex, le Data4.ork d'origine et un dossier de sortie, puis « Créer »."""
import base64
import json
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "moteur"))
import banners_core as B          # noqa: E402
import couleurs as CO             # noqa: E402


def dossier_programme():
    """Dossier du .exe (ou du script) : c'est là que sont enregistrés les réglages."""
    return os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, "frozen", False) else HERE


CONFIG = os.path.join(dossier_programme(), "saved_settings.json")
ANCIEN = os.path.join(dossier_programme(), "changer_of_banners.json")
CYAN = "#00bcd4"
VERT = "#2e9e4f"
ROUGE = "#d03a3a"

# ----------------------------------------------------------------------------- textes
TXT = {
    "fr": {
        "titre": "Changer of Banners",
        "dossier": "Dossier des emblèmes (.gtex)",
        "ork": "Data4.ork d'origine",
        "sortie": "Dossier de sortie",
        "parcourir": "Parcourir…",
        "actualiser": "Actualiser",
        "etoile": "Corriger le défilement des emblèmes",
        "tableau": "Emblèmes trouvés  (clic sur le rond : inclure / ignorer)",
        "col_inc": "Inclus", "col_fichier": "Fichier", "col_statut": "Contrôle du fichier",
        "apercu": "Aperçu", "aucun_apercu": "Sélectionnez un emblème",
        "creer": "Créer le nouveau Data4.ork",
        "langue": "Langue", "couleur": "Couleur…",
        "ok": "OK", "pas_gtex": "REFUSÉ · ce n'est pas un .gtex (convertissez-le avec gtexwrapper.exe)",
        "pair": "REFUSÉ · largeur et hauteur doivent être des nombres pairs", "illisible": "REFUSÉ · illisible",
        "ignore": "IGNORÉ · décoché",
        "etat": "{n} emblème(s) seront ajoutés   ·   {r} refusé(s) ou ignoré(s)",
        "err_champs": "Indiquez le Data4.ork d'origine, le dossier des emblèmes et le dossier de sortie.",
        "err_vide": "Aucun emblème valide à ajouter.",
        "avert_titre": "Avertissement",
        "avert_existe": "Un Data4.ork existe déjà dans le dossier de sortie.\nLe nouveau fichier sera nommé :\n{nom}",
        "travail": "Création en cours…",
        "fini": "Terminé : {chemin}\n{n} emblème(s) ajouté(s).",
        "fini_titre": "Terminé",
        "erreur": "Erreur",
        "apercu_err": "Aperçu impossible : {e}",
        "taille": "{w}×{h} pixels",
        "avert_liste": "Avertissements :\n{l}",
    },
    "en": {
        "titre": "Changer of Banners",
        "dossier": "Emblem folder (.gtex)",
        "ork": "Original Data4.ork",
        "sortie": "Output folder",
        "parcourir": "Browse…",
        "actualiser": "Refresh",
        "etoile": "Fix the emblem scrolling bug",
        "tableau": "Emblems found  (click the circle: include / ignore)",
        "col_inc": "Included", "col_fichier": "File", "col_statut": "File check",
        "apercu": "Preview", "aucun_apercu": "Select an emblem",
        "creer": "Create the new Data4.ork",
        "langue": "Language", "couleur": "Color…",
        "ok": "OK", "pas_gtex": "REFUSED · not a .gtex file (convert it with gtexwrapper.exe)",
        "pair": "REFUSED · width and height must be even numbers", "illisible": "REFUSED · unreadable",
        "ignore": "IGNORED · unchecked",
        "etat": "{n} emblem(s) will be added   ·   {r} refused or ignored",
        "err_champs": "Set the original Data4.ork, the emblem folder and the output folder.",
        "err_vide": "No valid emblem to add.",
        "avert_titre": "Warning",
        "avert_existe": "A Data4.ork already exists in the output folder.\nThe new file will be named:\n{nom}",
        "travail": "Working…",
        "fini": "Done: {chemin}\n{n} emblem(s) added.",
        "fini_titre": "Done",
        "erreur": "Error",
        "apercu_err": "Preview unavailable: {e}",
        "taille": "{w}×{h} pixels",
        "avert_liste": "Warnings:\n{l}",
    },
}

def lire_config():
    for p in (CONFIG, ANCIEN):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    return {}


def ecrire_config(c):
    try:
        with open(CONFIG, "w", encoding="utf-8") as f:
            json.dump(c, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.cfg = lire_config()
        self.lang = self.cfg.get("langue", "fr") if self.cfg.get("langue") in TXT else "fr"
        self.couleurs = CO.complet(self.cfg.get("couleurs"))
        self.fichiers = []                       # [{"chemin","nom","code","detail","actif"}]
        self.exclus = set(self.cfg.get("exclus", []))
        self.legendes = []                       # [(widget, clé, option)] pour le changement de langue
        self.file = queue.Queue()
        self.occupe = False
        self.geometry("1020x640")
        self.minsize(820, 520)
        self.preview_cache = {}
        self.icone_ok = self.rond(VERT)
        self.icone_non = self.rond(ROUGE)
        self.image_apercu = None
        self.construire()
        self.appliquer_theme()
        self.retexte()
        self.protocol("WM_DELETE_WINDOW", self.quitter)
        self.actualiser()

    # ---- utilitaires
    def t(self, k, **kw):
        s = TXT[self.lang][k]
        return s.format(**kw) if kw else s

    def rond(self, couleur, r=7):
        img = tk.PhotoImage(width=2 * r, height=2 * r)
        for y in range(2 * r):
            for x in range(2 * r):
                if (x - r + 0.5) ** 2 + (y - r + 0.5) ** 2 <= (r - 0.5) ** 2:
                    img.put(couleur, to=(x, y))
        return img

    def lg(self, widget, cle, option="text"):
        self.legendes.append((widget, cle, option))
        return widget

    # ---- interface
    def construire(self):
        f = ttk.Frame(self, padding=10)
        f.pack(fill="both", expand=True)
        self.cadre = f
        f.columnconfigure(1, weight=1)
        f.rowconfigure(6, weight=1)
        # barre du haut : langue et couleur
        haut = ttk.Frame(f)
        haut.grid(row=0, column=0, columnspan=4, sticky="e", pady=(0, 8))
        self.lg(ttk.Label(haut), "langue").pack(side="left", padx=(0, 4))
        self.cb_langue = ttk.Combobox(haut, state="readonly", width=10, values=["Français", "English"])
        self.cb_langue.set("Français" if self.lang == "fr" else "English")
        self.cb_langue.pack(side="left")
        self.cb_langue.bind("<<ComboboxSelected>>", self.changer_langue)
        self.lg(ttk.Button(haut, command=self.ouvrir_couleurs), "couleur").pack(side="left", padx=(12, 0))
        self.v_dossier = tk.StringVar(value=self.cfg.get("dossier", ""))
        self.v_ork = tk.StringVar(value=self.cfg.get("ork", ""))
        self.v_sortie = tk.StringVar(value=self.cfg.get("sortie", ""))
        self.v_dossier.trace_add("write", lambda *_: self.memoriser())
        self.v_ork.trace_add("write", lambda *_: self.memoriser())
        self.v_sortie.trace_add("write", lambda *_: self.memoriser())
        for i, (cle, var, cmd) in enumerate((("dossier", self.v_dossier, self.choisir_dossier),
                                             ("ork", self.v_ork, self.choisir_ork),
                                             ("sortie", self.v_sortie, self.choisir_sortie)), start=1):
            self.lg(ttk.Label(f), cle).grid(row=i, column=0, sticky="w", pady=3)
            ttk.Entry(f, textvariable=var).grid(row=i, column=1, sticky="ew", padx=6)
            self.lg(ttk.Button(f, command=cmd), "parcourir").grid(row=i, column=2)
        self.lg(ttk.Button(f, command=self.actualiser), "actualiser").grid(row=1, column=3, padx=(6, 0))
        # option « défilement » : étoile cyan + case
        ligne = ttk.Frame(f)
        ligne.grid(row=4, column=0, columnspan=4, sticky="w", pady=(8, 2))
        self.etoile = tk.Label(ligne, text="★", fg=CYAN, font=("TkDefaultFont", 13, "bold"))
        self.etoile.pack(side="left", padx=(0, 4))
        self.v_fix = tk.BooleanVar(value=self.cfg.get("corriger", True))
        self.lg(ttk.Checkbutton(ligne, variable=self.v_fix, command=self.memoriser), "etoile").pack(side="left")
        self.lg(ttk.Label(f, font=("TkDefaultFont", 9, "bold")), "tableau").grid(row=5, column=0, columnspan=4, sticky="w", pady=(6, 2))
        corps = ttk.Frame(f)
        corps.grid(row=6, column=0, columnspan=4, sticky="nsew")
        corps.columnconfigure(0, weight=1)
        corps.rowconfigure(0, weight=1)
        self.tv = ttk.Treeview(corps, columns=("fichier", "statut"), show="tree headings", selectmode="browse")
        self.tv.column("#0", width=70, minwidth=60, stretch=False, anchor="center")
        self.tv.column("fichier", width=220, minwidth=60, stretch=True, anchor="w")
        self.tv.column("statut", width=360, minwidth=60, stretch=True, anchor="w")
        sb = ttk.Scrollbar(corps, command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self.tv.bind("<Button-1>", self.clic)
        self.tv.bind("<<TreeviewSelect>>", lambda _e: self.montrer_apercu())
        # les colonnes ne peuvent pas dépasser la largeur du tableau (on les rattrape pendant et après le glissement)
        self.sep = None
        self.tv.bind("<B1-Motion>", lambda _e: (self.ajuster(), self.after_idle(self.ajuster)), add="+")
        self.tv.bind("<ButtonRelease-1>", lambda _e: (self.ajuster(), self.after_idle(self.ajuster)), add="+")
        self.tv.bind("<Configure>", lambda _e: self.after_idle(self.ajuster))
        # aperçu
        ap = ttk.Frame(corps, padding=(10, 0, 0, 0))
        ap.grid(row=0, column=2, sticky="ns")
        self.lg(ttk.Label(ap, font=("TkDefaultFont", 9, "bold")), "apercu").pack(anchor="w")
        self.zone = tk.Canvas(ap, width=260, height=260, highlightthickness=1)
        self.zone.pack(pady=4)
        self.info_apercu = ttk.Label(ap, wraplength=260, justify="left")
        self.info_apercu.pack(anchor="w")
        # bas
        bas = ttk.Frame(f)
        bas.grid(row=7, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        bas.columnconfigure(0, weight=1)
        self.etat = ttk.Label(bas)
        self.etat.grid(row=0, column=0, sticky="w")
        self.bouton = self.lg(ttk.Button(bas, command=self.creer), "creer")
        self.bouton.grid(row=0, column=1, padx=(14, 0))

    def ajuster(self):
        """Empêche les colonnes de sortir du tableau. La colonne qu'on est en train d'élargir est limitée la première
        (elle s'arrête au bord), l'excédent éventuel est ensuite retiré aux colonnes de droite."""
        larg = self.tv.winfo_width() - 4
        if larg < 100:
            return
        cols = ["#0", "fichier", "statut"]
        exces = sum(self.tv.column(c, "width") for c in cols) - larg
        ordre = []
        if self.sep in cols:
            ordre.append(self.sep)
        ordre += [c for c in ("statut", "fichier") if c not in ordre]
        for c in ordre:
            if exces <= 0:
                break
            w = self.tv.column(c, "width")
            r = min(exces, w - 60)
            if r > 0:
                self.tv.column(c, width=w - r)
                exces -= r
        self.tv.xview_moveto(0)

    def retexte(self):
        self.title(self.t("titre"))
        for w, cle, opt in self.legendes:
            w.configure(**{opt: self.t(cle)})
        self.tv.heading("#0", text=self.t("col_inc"))
        self.tv.heading("fichier", text=self.t("col_fichier"), anchor="w")
        self.tv.heading("statut", text=self.t("col_statut"), anchor="w")
        self.dessiner()
        self.montrer_apercu()

    def appliquer_theme(self):
        CO.appliquer(self, self.couleurs)
        c = self.couleurs
        self.etoile.configure(bg=c["bg"])
        self.zone.configure(bg=c["champ"], highlightbackground=c["bouton"])
        self.tv.configure(style="Treeview")
        ttk.Style(self).configure("Treeview", rowheight=24)

    def ouvrir_couleurs(self):
        def rappel(c):
            self.couleurs = c
            self.appliquer_theme()
            self.memoriser()
        CO.DialogueCouleurs(self, self.couleurs, rappel, self.lang)

    # ---- préférences
    def memoriser(self):
        self.cfg.update(dossier=self.v_dossier.get(), ork=self.v_ork.get(), sortie=self.v_sortie.get(),
                        corriger=bool(self.v_fix.get()), langue=self.lang, couleurs=self.couleurs,
                        exclus=sorted(self.exclus))
        ecrire_config(self.cfg)

    def changer_langue(self, _e=None):
        self.lang = "fr" if self.cb_langue.get() == "Français" else "en"
        self.retexte()
        self.maj_etat()
        self.memoriser()

    def quitter(self):
        self.memoriser()
        self.destroy()

    # ---- choix de fichiers
    def choisir_dossier(self):
        d = filedialog.askdirectory(initialdir=self.v_dossier.get() or HERE)
        if d:
            self.v_dossier.set(d)
            self.actualiser()

    def choisir_ork(self):
        p = filedialog.askopenfilename(initialdir=os.path.dirname(self.v_ork.get()) or HERE,
                                       filetypes=[("Data4.ork", "*.ork"), ("*", "*.*")])
        if p:
            self.v_ork.set(p)

    def choisir_sortie(self):
        d = filedialog.askdirectory(initialdir=self.v_sortie.get() or HERE)
        if d:
            self.v_sortie.set(d)

    # ---- tableau
    def actualiser(self):
        self.fichiers = []
        self.preview_cache = {}
        for p, nom in B.lister_gtex(self.v_dossier.get()):
            ok, code, det = B.diagnostic(p)
            self.fichiers.append({"chemin": p, "nom": nom, "code": code, "detail": det,
                                  "actif": ok and (nom not in self.exclus)})
        self.dessiner()
        self.montrer_apercu()

    def statut(self, e):
        if e["code"] != "ok":
            return self.t(e["code"]) + ("  (" + e["detail"] + ")" if e["code"] == "pair" and e["detail"] else "")
        if not e["actif"]:
            return self.t("ignore") + "  ·  " + e["detail"]
        return self.t("ok") + "  ·  " + e["detail"]

    def dessiner(self):
        sel = self.tv.selection()
        self.tv.delete(*self.tv.get_children())
        base = self.v_dossier.get()
        for i, e in enumerate(self.fichiers):
            nom = os.path.relpath(e["chemin"], base) if base else e["chemin"]
            self.tv.insert("", "end", iid=str(i), text="", image=self.icone_ok if e["actif"] else self.icone_non,
                           values=(nom, self.statut(e)))
        for i in sel:
            if self.tv.exists(i):
                self.tv.selection_set(i)
        self.maj_etat()

    def maj_etat(self):
        n = sum(1 for e in self.fichiers if e["actif"])
        self.etat.configure(text=self.t("etat", n=n, r=len(self.fichiers) - n))

    def clic(self, ev):
        col = self.tv.identify_column(ev.x)
        self.sep = None
        if self.tv.identify_region(ev.x, ev.y) == "separator":
            # séparateur d'en-tête : la colonne à sa gauche est celle qu'on élargit
            n = int(col[1:]) if col[1:].isdigit() else 0
            self.sep = {0: "#0", 1: "fichier", 2: "statut"}.get(n)
        i = self.tv.identify_row(ev.y)
        if i and self.tv.identify_column(ev.x) == "#0":
            e = self.fichiers[int(i)]
            if e["code"] == "ok":
                e["actif"] = not e["actif"]
                if e["actif"]:
                    self.exclus.discard(e["nom"])
                else:
                    self.exclus.add(e["nom"])
                # mise à jour de cette seule ligne (pas de reconstruction du tableau)
                self.tv.item(i, image=self.icone_ok if e["actif"] else self.icone_non,
                             values=(self.tv.set(i, "fichier"), self.statut(e)))
                self.maj_etat()
                self.after_idle(self.memoriser)
            if tuple(self.tv.selection()) != (i,):
                self.tv.selection_set(i)
            return "break"

    # ---- aperçu
    def montrer_apercu(self):
        self.zone.delete("all")
        self.image_apercu = None
        s = self.tv.selection()
        if not s or not self.fichiers:
            self.info_apercu.configure(text=self.t("aucun_apercu"))
            return
        e = self.fichiers[int(s[0])]
        try:
            r = self.preview_cache.get(e["chemin"])
            if r is None:
                r = self.preview_cache[e["chemin"]] = B.apercu_png(e["chemin"], 256)
            png, w, h, ow, oh = r
            img = tk.PhotoImage(data=base64.b64encode(png).decode("ascii"))
            k = max(1, min(256 // max(ow, 1), 256 // max(oh, 1)))
            if k > 1:
                img = img.zoom(k, k)
            self.image_apercu = img
            self.zone.create_image(130, 130, image=img)
            self.info_apercu.configure(text=e["nom"] + "\n" + self.t("taille", w=w, h=h))
        except Exception as ex:                                      # noqa
            self.info_apercu.configure(text=self.t("apercu_err", e=ex))

    # ---- création
    def log(self, msg):
        self.file.put(("log", msg))

    def ecrire_journal(self, msg):
        self.etat.configure(text=msg)

    def creer(self):
        if self.occupe:
            return
        ork, dossier, sortie = self.v_ork.get().strip(), self.v_dossier.get().strip(), self.v_sortie.get().strip()
        if not (ork and dossier and sortie):
            messagebox.showwarning(self.t("erreur"), self.t("err_champs"))
            return
        fichiers = [(e["nom"], e["chemin"]) for e in self.fichiers if e["actif"]]
        if not fichiers and not self.v_fix.get():
            messagebox.showwarning(self.t("erreur"), self.t("err_vide"))
            return
        cible, existait = B.prochain_nom_sortie(sortie)
        if existait:
            messagebox.showwarning(self.t("avert_titre"), self.t("avert_existe", nom=os.path.basename(cible)))
        self.occupe = True
        self.bouton.configure(state="disabled")
        self.ecrire_journal(self.t("travail"))
        corriger = bool(self.v_fix.get())

        def travail():
            try:
                r = B.construire(ork, sortie, fichiers, corriger, self.log)
                self.file.put(("fin", r))
            except Exception as ex:                                   # noqa
                self.file.put(("err", str(ex)))
        threading.Thread(target=travail, daemon=True).start()
        self.after(100, self.sonder)

    def sonder(self):
        try:
            while True:
                k, v = self.file.get_nowait()
                if k == "log":
                    self.ecrire_journal(v)
                elif k == "fin":
                    chemin, avert, n = v
                    self.occupe = False
                    self.bouton.configure(state="normal")
                    self.maj_etat()
                    msg = self.t("fini", chemin=chemin, n=n)
                    if avert:
                        msg += "\n\n" + self.t("avert_liste", l="\n".join(avert))
                    messagebox.showinfo(self.t("fini_titre"), msg)
                    return
                elif k == "err":
                    self.occupe = False
                    self.bouton.configure(state="normal")
                    self.maj_etat()
                    messagebox.showerror(self.t("erreur"), v)
                    return
        except queue.Empty:
            pass
        self.after(100, self.sonder)


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
