#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ork_pack.py – créer ou compléter une archive .ork (Warhammer: Mark of Chaos)
============================================================================
Le contraire d'orkextract : met des fichiers dans une archive .ork lisible par le jeu.
Reprend l'algorithme d'orkdec de Luigi Auriemma (GPL v2+), dans le sens inverse.

Rappel du format :
  octets 0-3   : en-tête (copié d'une archive existante avec --modele, sinon 0)
  octets 4-7   : position de l'index − 8, XOR 0x0FBF6A67
  à partir de 8: les fichiers, chacun compressé (zlib) puis chiffré avec SON NOM
                 EN MINUSCULES comme mot de passe
  l'index      : nombre de fichiers, puis 5 entiers par fichier (crc fichier, empreinte du
                 nom, taille, taille compressée, position), le tout chiffré
  les 10 derniers octets : « Good luck! »

Commandes :
  python ork_pack.py creer  <dossier> <sortie.ork> [--modele Data4.ork] [--sans-ext .gtex,.dds]
        archive toute neuve contenant les fichiers du dossier
  python ork_pack.py ajouter <Data4.ork> <dossier> <sortie.ork> [--sans-ext ...]
        copie une archive existante telle quelle (aucun nom n'est nécessaire pour les
        fichiers existants : ils sont recopiés tels quels, même ceux dont on ignore le nom),
        puis ajoute ou REMPLACE les fichiers du dossier
  python ork_pack.py lister <archive.ork> [noms_trouves.txt]
  python ork_pack.py gui

Nom d'un fichier dans l'archive = son chemin relatif dans le dossier, avec des « \\ »
(ex. dossier/high/default/mon_modele.gobj -> « high\\default\\mon_modele.gobj »).
Si un fichier « noms_archive.csv » (créé par orkextract_NEW_6) est à la racine du dossier,
les noms exacts qu'il donne sont utilisés pour les fichiers qu'il cite : indispensable pour
les textures, que l'archive range SANS extension (« default\\orcboyz_diftext »).
--sans-ext retire l'extension indiquée aux nouveaux fichiers qui ne sont pas dans le fichier csv.
"""

import csv
import os
import struct
import sys
import zlib

M32 = 0xFFFFFFFF
ORK_SIGN = b"Good luck!"
ORK_OFFSET = 0x0FBF6A67
ENTRY_SIZE = 20

CRC_TABLE = []
for _i in range(256):
    _c = _i
    for _ in range(8):
        _c = ((_c >> 1) ^ 0xEDB88320) if (_c & 1) else (_c >> 1)
    CRC_TABLE.append(_c)

INDEX_KEYS = [
    (0x4A4908CD, 0xE621DBCB, 0xBFFCAE63),
    (0x8D9C42D5, 0xED3112CC, 0xF2FD696D),
    (0x86C179D2, 0x2281876E, 0xD3DFACCF),
]
FILE_KEYS = [
    (0x488BCEA3, 0xFB598BF2, 0xF89197A5),
    (0xD3F7454D, 0x7DA7B991, 0xC38E2892),
    (0xDD4F2048, 0x9189C8FB, 0x4A7CA962),
]


class OrkError(Exception):
    pass


def _step(k1, k2, k3, b):
    tab = CRC_TABLE
    k1 = tab[(b ^ k1) & 0xFF] ^ (k1 >> 8)
    k2 = ((k2 + (k1 & 0xFF)) * 0x114E230B + 1) & M32
    k3 = tab[((k2 >> 24) ^ k3) & 0xFF] ^ (k3 >> 8)
    return k1, k2, k3


def _feed(key, data):
    k1, k2, k3 = key
    for b in data:
        k1, k2, k3 = _step(k1, k2, k3, b)
    return (k1, k2, k3)


def _decrypt(key, data):
    k1, k2, k3 = key
    out = bytearray(len(data))
    for i, c in enumerate(data):
        t = k3 | 2
        b = c ^ (((t * (t ^ 1)) >> 8) & 0xFF)
        out[i] = b
        k1, k2, k3 = _step(k1, k2, k3, b)
    return bytes(out), (k1, k2, k3)


def _encrypt(key, data):
    k1, k2, k3 = key
    out = bytearray(len(data))
    for i, b in enumerate(data):
        t = k3 | 2
        out[i] = b ^ (((t * (t ^ 1)) >> 8) & 0xFF)
        k1, k2, k3 = _step(k1, k2, k3, b)
    return bytes(out), (k1, k2, k3)


def index_key(ks):
    buf = bytearray()
    k = 0
    for i in range(4):
        buf += b"Error!\0"
        k = (k + 1869628369) & M32
        if i < 3:
            buf += str(k).encode() + b"\0"
    return _feed(INDEX_KEYS[ks], bytes(buf))


def file_key(ks, name_lower):
    return _feed(FILE_KEYS[ks], name_lower)


def name_crc(name_bytes):
    crc, i = 0xA4D6CF31, 0
    for c in name_bytes.lower():
        i += 1
        crc = (c + CRC_TABLE[c] + ((crc ^ i) * 3)) & M32
    return crc


class Entry:
    __slots__ = ("filecrc", "namecrc", "size", "zipsize", "offset")


class Archive:
    """Lecture d'une archive existante : index + position des données."""

    def __init__(self, path):
        self.path = path
        self.size = os.path.getsize(path)
        self.entries = []
        self.keyset = 0
        self.header = b"\0\0\0\0"
        self.idx_pos = 0
        with open(path, "rb") as f:
            if self.size < 30:
                raise OrkError("Fichier trop petit pour être une archive ORK.")
            f.seek(self.size - len(ORK_SIGN))
            if f.read(len(ORK_SIGN)) != ORK_SIGN:
                raise OrkError(f"{path} : signature « Good luck! » absente.")
            f.seek(0)
            self.header = f.read(4)
            off = struct.unpack("<I", f.read(4))[0] ^ ORK_OFFSET
            self.idx_pos = 8 + off
            if self.idx_pos + 4 > self.size - len(ORK_SIGN):
                raise OrkError("Position de l'index invalide.")
            dec = None
            for ks in range(3):
                f.seek(self.idx_pos)
                cnt, key_after = _decrypt(index_key(ks), f.read(4))
                n = struct.unpack("<I", cnt)[0]
                if ((n * ENTRY_SIZE) & M32) == self.size - len(ORK_SIGN) - (self.idx_pos + 4):
                    dec, _ = _decrypt(key_after, f.read(n * ENTRY_SIZE))
                    self.keyset = ks
                    break
            if dec is None:
                raise OrkError("Index illisible avec les clés connues.")
        for i in range(n):
            fc, nc, sz, zs, of = struct.unpack_from("<5I", dec, i * ENTRY_SIZE)
            m = ((i * 733) + 0x48B18039) & M32
            e = Entry()
            e.filecrc, e.namecrc = fc, nc
            e.size, e.zipsize, e.offset = sz ^ m, zs ^ m, of ^ m
            self.entries.append(e)

    def read(self, e, name_lower):
        with open(self.path, "rb") as f:
            f.seek(8 + e.offset)
            raw = f.read(e.zipsize)
        plain, _ = _decrypt(file_key(self.keyset, name_lower), raw)
        return zlib.decompress(plain)


def write_index(out, entries, keyset):
    raw = bytearray()
    for i, e in enumerate(entries):
        m = ((i * 733) + 0x48B18039) & M32
        raw += struct.pack("<5I", e.filecrc & M32, e.namecrc & M32,
                           (e.size ^ m) & M32, (e.zipsize ^ m) & M32, (e.offset ^ m) & M32)
    head, key = _encrypt(index_key(keyset), struct.pack("<I", len(entries)))
    body, _ = _encrypt(key, bytes(raw))
    out.write(head)
    out.write(body)
    out.write(ORK_SIGN)


def name_hash31(low):
    """Second hash du nom (« filecrc » de l'index) : h = h*31 + c (mod 2^32) sur le nom en minuscules."""
    h = 0
    for c in low:
        h = (h * 31 + c) & M32
    return h


def make_blob(name, data, keyset):
    """Compresse puis chiffre un fichier avec son nom (minuscules) comme mot de passe."""
    low = name.encode("latin-1").lower()
    z = zlib.compress(data, 6)   # niveau 6 = celui des archives d'origine (taille identique vérifiée sur game.orc)
    enc, _ = _encrypt(file_key(keyset, low), z)
    e = Entry()
    e.filecrc = name_hash31(low)            # formule du jeu (trouvée dans l'exe) : h = h*31 + octet, sur le nom en minuscules
    e.namecrc = name_crc(low)
    e.size = len(data)
    e.zipsize = len(enc)
    return e, enc


# --------------------------------------------------------------------------

def _norm_ext_list(s):
    out = []
    for x in (s or "").replace(";", ",").split(","):
        x = x.strip().lower()
        if x:
            out.append(x if x.startswith(".") else "." + x)
    return tuple(out)


def collect(folder, sans_ext=()):
    """Liste (nom dans l'archive, chemin disque) pour tous les fichiers du dossier."""
    manifest = {}
    mp = os.path.join(folder, "noms_archive.csv")
    if os.path.isfile(mp):
        with open(mp, newline="", encoding="utf-8") as f:
            for row in csv.reader(f, delimiter=";"):
                if len(row) >= 2 and row[0] != "nom_archive":
                    manifest[os.path.normcase(row[1].replace("/", os.sep).replace("\\", os.sep))] = row[0]
    res, seen = [], {}
    for root, _, files in os.walk(folder):
        for fn in sorted(files):
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, folder)
            if rel.lower() in ("noms_archive.csv",) or fn.lower().endswith((".ork",)):
                continue
            key = os.path.normcase(rel)
            if key in manifest:
                name = manifest[key]
            else:
                name = rel.replace(os.sep, "\\")
                for ext in sans_ext:
                    if name.lower().endswith(ext):
                        name = name[:-len(ext)]
                        break
            low = name.lower()
            if low in seen:
                raise OrkError(f"Deux fichiers donnent le même nom d'archive « {name} » : "
                               f"{seen[low]} et {full}")
            seen[low] = full
            res.append((name, full))
    return res


FILECRC = {}      # {nom en minuscules : filecrc imposé} (formule du jeu inconnue ; voir LISEZMOI)


def build(out_path, files, base=None, header=None, log=print):
    """base = Archive existante à recopier (ou None). files = [(nom, chemin disque)]."""
    keyset = base.keyset if base else 0
    entries = [e for e in base.entries] if base else []
    pos_by_crc = {}
    for i, e in enumerate(entries):
        pos_by_crc.setdefault(e.namecrc, []).append(i)
    tmp = out_path + ".tmp"
    with open(tmp, "wb") as out:
        out.write((base.header if base else (header or b"\0\0\0\0")))
        out.write(b"\0\0\0\0")                       # position de l'index, complétée à la fin
        end = 8
        if base:
            with open(base.path, "rb") as src:
                src.seek(8)
                left = base.idx_pos - 8
                while left > 0:
                    chunk = src.read(min(left, 8 << 20))
                    if not chunk:
                        raise OrkError("Archive source tronquée.")
                    out.write(chunk)
                    left -= len(chunk)
            end = base.idx_pos
        added = replaced = 0
        for name, path in files:
            with open(path, "rb") as f:
                data = f.read()
            e, blob = make_blob(name, data, keyset)
            if name.lower() in FILECRC:
                e.filecrc = FILECRC[name.lower()] & M32
            e.offset = end - 8
            out.write(blob)
            end += len(blob)
            if e.namecrc in pos_by_crc:
                e.filecrc = entries[pos_by_crc[e.namecrc][0]].filecrc   # on garde le filecrc d'origine (lié au nom, pas au contenu)
                for j in pos_by_crc[e.namecrc]:
                    entries[j] = e
                replaced += 1
                log(f"  remplace : {name}  ({len(data):,} octets)")
            else:
                pos_by_crc[e.namecrc] = [len(entries)]
                entries.append(e)
                added += 1
                log(f"  ajoute   : {name}  ({len(data):,} octets)")
        idx_pos = end
        write_index(out, entries, keyset)
        out.seek(4)
        out.write(struct.pack("<I", ((idx_pos - 8) ^ ORK_OFFSET) & M32))
    os.replace(tmp, out_path)
    log(f"Archive écrite : {out_path} ({os.path.getsize(out_path):,} octets, "
        f"{len(entries):,} entrées : {added} ajoutée(s), {replaced} remplacée(s))")


def check(out_path, files, log=print):
    """Relit l'archive produite et compare chaque fichier ajouté avec l'original."""
    a = Archive(out_path)
    bad = 0
    for name, path in files:
        crc = name_crc(name.encode("latin-1").lower())
        ents = [e for e in a.entries if e.namecrc == crc]
        if not ents:
            log(f"  ÉCHEC : {name} absent de l'index")
            bad += 1
            continue
        try:
            got = a.read(ents[-1], name.encode("latin-1").lower())
        except Exception as ex:           # noqa
            log(f"  ÉCHEC : {name} illisible ({ex})")
            bad += 1
            continue
        with open(path, "rb") as f:
            if f.read() != got:
                log(f"  ÉCHEC : {name} différent après relecture")
                bad += 1
    log("Contrôle de relecture : " + ("OK" if not bad else f"{bad} problème(s)"))
    return bad == 0


def cmd_lister(path, names=None, log=print):
    a = Archive(path)
    known = {}
    if names:
        with open(names, encoding="utf-8", errors="ignore") as f:
            for ln in f:
                ln = ln.strip()
                if ln:
                    known[name_crc(ln.encode("latin-1", "ignore").lower())] = ln
    log(f"{path} : {len(a.entries):,} entrées, jeu de clés {a.keyset}, en-tête {a.header.hex()}")
    for i, e in enumerate(a.entries):
        log(f"{i:6d}  {e.namecrc:08x}  crc={e.filecrc:08x}  {e.size:>10,}  {e.zipsize:>10,}  "
            f"{known.get(e.namecrc, '')}")


# --------------------------------------------------------------------------

def gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext

    w = tk.Tk()
    w.title("Créer / compléter une archive .ork")
    w.geometry("780x520")
    vd, vb, vo, ve = (tk.StringVar() for _ in range(4))
    ve.set(".gtex,.dds")

    def row(r, label, var, cmd):
        tk.Label(w, text=label, anchor="w").grid(row=r, column=0, sticky="w", padx=8, pady=3)
        tk.Entry(w, textvariable=var, width=70).grid(row=r, column=1, padx=4)
        tk.Button(w, text="...", command=cmd).grid(row=r, column=2, padx=4)
    row(0, "Dossier des fichiers à ajouter", vd,
        lambda: vd.set(filedialog.askdirectory() or vd.get()))
    row(1, "Archive de départ (facultatif)", vb,
        lambda: vb.set(filedialog.askopenfilename(filetypes=[("ork", "*.ork")]) or vb.get()))
    row(2, "Archive à écrire", vo,
        lambda: vo.set(filedialog.asksaveasfilename(defaultextension=".ork") or vo.get()))
    tk.Label(w, text="Extensions à retirer des nouveaux noms", anchor="w").grid(
        row=3, column=0, sticky="w", padx=8)
    tk.Entry(w, textvariable=ve, width=70).grid(row=3, column=1, padx=4)
    box = scrolledtext.ScrolledText(w, height=20)
    box.grid(row=5, column=0, columnspan=3, sticky="nsew", padx=8, pady=8)
    w.grid_rowconfigure(5, weight=1)
    w.grid_columnconfigure(1, weight=1)

    def log(m=""):
        box.insert("end", m + "\n")
        box.see("end")
        w.update_idletasks()

    def go():
        try:
            if not vd.get() or not vo.get():
                raise OrkError("Choisissez le dossier et l'archive à écrire.")
            if os.path.abspath(vo.get()) == os.path.abspath(vb.get() or ""):
                raise OrkError("L'archive à écrire doit être un AUTRE fichier que l'archive de départ.")
            files = collect(vd.get(), _norm_ext_list(ve.get()))
            if not files:
                raise OrkError("Le dossier ne contient aucun fichier.")
            base = Archive(vb.get()) if vb.get() else None
            log(f"{len(files)} fichier(s) à écrire…")
            build(vo.get(), files, base, log=log)
            check(vo.get(), files, log)
        except Exception as ex:       # noqa
            messagebox.showerror("Erreur", str(ex))
            log("ERREUR : " + str(ex))
    tk.Button(w, text="Créer l'archive", command=go).grid(row=4, column=1, pady=6)
    w.mainloop()


def main(argv):
    if len(argv) < 2 or argv[1] == "gui":
        return gui()

    def opt(name, default=None):
        if name in argv:
            i = argv.index(name)
            v = argv[i + 1]
            del argv[i:i + 2]
            return v
        return default
    try:
        modele = opt("--modele")
        sans = _norm_ext_list(opt("--sans-ext", ""))
        c = argv[1]
        if c == "creer" and len(argv) == 4:
            files = collect(argv[2], sans)
            hdr = None
            if modele:
                hdr = Archive(modele).header
            build(argv[3], files, None, hdr)
            return 0 if check(argv[3], files) else 1
        if c == "ajouter" and len(argv) == 5:
            files = collect(argv[3], sans)
            build(argv[4], files, Archive(argv[2]))
            return 0 if check(argv[4], files) else 1
        if c == "lister" and len(argv) in (3, 4):
            cmd_lister(argv[2], argv[3] if len(argv) == 4 else None)
            return 0
        print(__doc__)
        return 2
    except (OrkError, OSError) as ex:
        print("ERREUR :", ex)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
