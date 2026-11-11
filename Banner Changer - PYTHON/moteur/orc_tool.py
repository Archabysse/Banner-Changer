#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
orc_tool.py – lire, modifier et reconstruire Game.orc (Warhammer: Mark of Chaos)
================================================================================
Game.orc n'est PAS une archive : c'est un arbre de « chunks » (dossiers) contenant
des « blocks » (valeurs : textes, nombres...). Ce programme le convertit en un
fichier texte modifiable, puis reconstruit un Game.orc identique à l'octet près
quand vous n'avez rien changé (c'est vérifié par la commande « verifier »).

Format du fichier (d'après WMOC_Tools / ungame_orc de l'ancien projet de modding) :
  8 octets d'en-tête : ED FE 70 CF-style « CF70FEED » + version 1
  chunk  : octet de type (0x31/0x35/0x3D...), identifiant (1 à 4 octets),
           taille (u32) = octets qui suivent, fin 0x02 comprise, puis son contenu
           (blocks et chunks), puis l'octet 0x02.
  block  : octet de type (0x00, 0x04, 0x10, 0x14), identifiant (1 ou 2 octets),
           taille (1 ou 2 octets), puis les données.

Commandes :
  python orc_tool.py dump      Game.orc  Game.txt      -> texte modifiable
  python orc_tool.py build     Game.txt  Game_new.orc  -> reconstruit le .orc
  python orc_tool.py verifier  Game.orc                -> test aller-retour
  python orc_tool.py chercher  Game.orc  "Marauders"   -> où se trouve ce texte
  python orc_tool.py remplacer Game.orc  Game_new.orc "ancien" "nouveau" [...]
        remplace du texte dans toutes les chaînes (même longueur ou non)
  python orc_tool.py editer    Game.orc  Game_new.orc <chemin du chunk> <id du block> "nouveau texte"
        change EXACTEMENT le texte d'un seul block (contrairement à « remplacer », qui change
        toutes les chaînes contenant le motif). Ex. :
        editer Game.orc Game_new.orc 16777216#0/17301504#0/5000#1853/1000#0 2000 "Marauders TEST"
  python orc_tool.py cloner    Game.orc  Game_new.orc  <chemin> "ancien=nouveau" [...]
        duplique un chunk juste après lui, en remplaçant des textes dans la copie.
        Le chemin vient de « chercher », ex. 16777216#0/1500#0/2000#4 (le n de « #n » est
        le rang parmi les chunks frères de même identifiant ; sans « #n » = le premier)
  python orc_tool.py gui                               -> petite interface

Format du texte :
  chunk 12 t=31 {          <- chunk d'identifiant 12 (t = octet de type, ne pas toucher)
    block 2000 t=00 "Chaos_Marauders_Body"     <- texte (un 0 final est ajouté)
    block 5 t=00 x 00 00 80 3F   # u32=1065353216 f32=1.0   <- octets (hex) ; le # est un commentaire
  }
"""

import os
import re
import struct
import sys

sys.setrecursionlimit(100000)

MAGIC = bytes.fromhex("cf70feed01000000")


class OrcError(Exception):
    pass


# --------------------------------------------------------------------------
# Arbre en mémoire
#   chunk : ["c", type_byte, id, children(list), gtag]
#   block : ["b", type_byte, id, data(bytes)]
# --------------------------------------------------------------------------

def parse(data):
    if data[:8] != MAGIC:
        raise OrcError("En-tête inattendu : ce n'est pas un Game.orc (CF70FEED, version 1).")
    n = len(data)

    def block(p):
        z = data[p]
        if z & 4:
            bid = struct.unpack_from("<H", data, p + 1)[0]
            h = 4
        else:
            bid = data[p + 1]
            h = 3
        sz = data[p + h - 1]
        if z & 0x10:
            sz |= data[p + h] << 8
            h += 1
        end = p + h + sz
        if end > n:
            raise OrcError(f"Block tronqué à l'offset 0x{p:X}")
        return ["b", z, bid, data[p + h:end]], end

    def chunk(p):
        z = data[p]
        if z == 0x47:                                  # « Gxxx » (formats GOBJ)
            node = ["c", z, 0, [], bytes(data[p:p + 4])]
            q = p + 4
        elif (z & 0x31) == 0x31:
            k = ((z >> 2) & 3) + 1
            cid = int.from_bytes(data[p + 1:p + 1 + k], "little")
            sizef = struct.unpack_from("<I", data, p + 1 + k)[0]
            node = ["c", z, cid, [], None]
            q = p + 1 + k + 4
            if q + sizef > n:
                raise OrcError(f"Chunk dépasse le fichier (offset 0x{p:X})")
        else:
            raise OrcError(f"Type de chunk inconnu 0x{z:02X} à l'offset 0x{p:X}")
        kids = node[3]
        while True:
            if q >= n:
                raise OrcError("Fin de fichier inattendue (chunk non fermé)")
            b = data[q]
            if b == 2:
                q += 1
                break
            if b < 0x31:
                nd, q = block(q)
            else:
                nd, q = chunk(q)
            kids.append(nd)
        return node, q

    root, end = chunk(8)
    return root, bytes(data[end:])


def serialize(node):
    if node[0] == "b":
        _, z, bid, payload = node
        size = len(payload)
        if bid > 255:
            z |= 4
        if size > 255:
            z |= 0x10
        if size > 65535:
            raise OrcError(f"Block {bid} trop gros ({size} octets, maximum 65535).")
        head = bytearray([z])
        head += struct.pack("<H", bid) if z & 4 else bytes([bid])
        head.append(size & 0xFF)
        if z & 0x10:
            head.append(size >> 8)
        return bytes(head) + payload
    _, z, cid, kids, gtag = node
    body = b"".join(serialize(k) for k in kids) + b"\x02"
    if z == 0x47:
        return gtag + body
    k = ((z >> 2) & 3) + 1
    while cid >= (1 << (8 * k)) and k < 4:             # identifiant trop grand : on élargit
        k += 1
        z = (z & ~0x0C) | ((k - 1) << 2)
    return bytes([z]) + cid.to_bytes(k, "little") + struct.pack("<I", len(body)) + body


def build_file(root, tail):
    return MAGIC + serialize(root) + tail


# --------------------------------------------------------------------------
# Texte <-> arbre
# --------------------------------------------------------------------------

def _is_text(b):
    if len(b) < 2 or b[-1] != 0:
        return None
    body = b[:-1]
    if b"\x00" in body:
        return None
    try:
        s = body.decode("utf-8")
    except UnicodeDecodeError:
        return None
    for ch in s:
        if ch < " " and ch not in "\n\r\t":
            return None
        if "\x7f" <= ch <= "\x9f":
            return None
    return s


def _esc(s):
    out = []
    for ch in s:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        else:
            out.append(ch)
    return "".join(out)


_UNESC = re.compile(r'\\(["\\nrt]|x[0-9a-fA-F]{2})')


def _unesc(s):
    def r(m):
        g = m.group(1)
        return {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}.get(g) or chr(int(g[1:], 16))
    return _UNESC.sub(r, s)


def _hint(b):
    n = len(b)
    if n == 4:
        u = struct.unpack("<I", b)[0]
        i = struct.unpack("<i", b)[0]
        f = struct.unpack("<f", b)[0]
        t = f"u32={u}" + (f" i32={i}" if i != u else "")
        if f == f and (abs(f) > 1e-6 and abs(f) < 1e7):
            t += f" f32={f:.6g}"
        return t
    if n == 2:
        return f"u16={struct.unpack('<H', b)[0]}"
    if n == 1:
        return f"u8={b[0]}"
    if n == 8:
        return "f32x2=" + ",".join(f"{v:.6g}" for v in struct.unpack("<2f", b))
    if n == 12:
        return "f32x3=" + ",".join(f"{v:.6g}" for v in struct.unpack("<3f", b))
    return ""


def dump_text(root, tail, out):
    w = out.write
    w("# Game.orc en texte – modifiable puis reconstructible avec « orc_tool.py build »\n")
    if tail != b"\x02":
        w(f"tail x {tail.hex(' ')}\n")
    else:
        w("tail x 02\n")

    def rec(nd, lv):
        pad = "  " * lv
        if nd[0] == "c":
            if nd[1] == 0x47:
                w(f"{pad}gchunk x {nd[4].hex(' ')} {{\n")
            else:
                w(f"{pad}chunk {nd[2]} t={nd[1]:02x} {{\n")
            for k in nd[3]:
                rec(k, lv + 1)
            w(f"{pad}}}\n")
        else:
            _, z, bid, pl = nd
            s = _is_text(pl)
            if s is not None:
                w(f'{pad}block {bid} t={z:02x} "{_esc(s)}"\n')
            else:
                h = _hint(pl)
                w(f"{pad}block {bid} t={z:02x} x {pl.hex(' ')}" + (f"   # {h}" if h else "") + "\n")

    rec(root, 0)


_RE_CHUNK = re.compile(r"^chunk (\d+) t=([0-9a-fA-F]{2}) \{$")
_RE_GCHUNK = re.compile(r"^gchunk x ((?:[0-9a-fA-F]{2} ?)+) \{$")
_RE_BLOCK = re.compile(r'^block (\d+) t=([0-9a-fA-F]{2}) (.*)$')


def parse_text(lines):
    tail = b"\x02"
    stack = []
    root = None
    for no, raw in enumerate(lines, 1):
        ln = raw.strip()
        if not ln or ln.startswith("#"):
            continue
        try:
            if ln.startswith("tail x "):
                tail = bytes.fromhex(ln[7:].split("#")[0])
                continue
            if ln == "}":
                nd = stack.pop()
                if not stack:
                    root = nd
                continue
            m = _RE_CHUNK.match(ln)
            if m:
                nd = ["c", int(m.group(2), 16), int(m.group(1)), [], None]
            else:
                m = _RE_GCHUNK.match(ln)
                if m:
                    nd = ["c", 0x47, 0, [], bytes.fromhex(m.group(1).replace(" ", ""))]
                else:
                    m = _RE_BLOCK.match(ln)
                    if not m:
                        raise OrcError("ligne non reconnue")
                    rest = m.group(3)
                    if rest.startswith('"'):
                        j = len(rest) - 1
                        while j > 0 and rest[j] != '"':
                            j -= 1
                        if j <= 0:
                            raise OrcError("guillemet de fin manquant")
                        payload = _unesc(rest[1:j]).encode("utf-8") + b"\x00"
                    elif rest.startswith("x"):
                        payload = bytes.fromhex(rest[1:].split("#")[0])
                    else:
                        raise OrcError("valeur attendue : \"texte\" ou x <octets hex>")
                    nd = ["b", int(m.group(2), 16), int(m.group(1)), payload]
                    if not stack:
                        raise OrcError("block hors d'un chunk")
                    stack[-1][3].append(nd)
                    continue
            if stack:
                stack[-1][3].append(nd)
            stack.append(nd)
        except (ValueError, OrcError, IndexError) as ex:
            raise OrcError(f"ligne {no} : {ex}\n   {ln[:120]}")
    if stack or root is None:
        raise OrcError("accolades non équilibrées (il manque un « } »)")
    return root, tail


# --------------------------------------------------------------------------
# Opérations
# --------------------------------------------------------------------------

def load_orc(path):
    with open(path, "rb") as f:
        return parse(f.read())


def save_orc(path, root, tail):
    with open(path, "wb") as f:
        f.write(build_file(root, tail))


def walk(nd, path=()):
    """Génère (chemin, nœud). Le chemin est une suite d'éléments « id#n » où n est le rang
    (à partir de 0) du chunk parmi ses frères de même identifiant."""
    if nd[0] == "c":
        yield from _walk(nd, path + (f"{nd[2]}#0",))
    else:
        yield path, nd


def _walk(nd, path):
    yield path, nd
    seen = {}
    for k in nd[3]:
        if k[0] == "c":
            i = seen.get(k[2], 0)
            seen[k[2]] = i + 1
            yield from _walk(k, path + (f"{k[2]}#{i}",))
        else:
            yield path, k


def cmd_verifier(src, log=print):
    with open(src, "rb") as f:
        orig = f.read()
    root, tail = parse(orig)
    again = build_file(root, tail)
    log(f"Reconstruction directe de l'arbre : {'IDENTIQUE' if again == orig else 'DIFFÉRENTE'}")
    import io
    buf = io.StringIO()
    dump_text(root, tail, buf)
    buf.seek(0)
    root2, tail2 = parse_text(buf.read().splitlines())
    again2 = build_file(root2, tail2)
    ok = again2 == orig
    log(f"Aller-retour par le fichier texte : {'IDENTIQUE' if ok else 'DIFFÉRENT'} "
        f"({len(orig):,} octets)")
    return ok and again == orig


def cmd_chercher(src, motif, log=print, limit=200):
    root, tail = load_orc(src)
    rx = re.compile(re.escape(motif), re.I)
    n = 0
    for path, nd in walk(root):
        if nd[0] != "b":
            continue
        s = _is_text(nd[3])
        if s is not None and rx.search(s):
            n += 1
            if n <= limit:
                chemin = "/".join(path)
                log(f"chemin {chemin}  block {nd[2]}  : {s[:110]}")
    log(f"{n} résultat(s)" + (f" (affichage limité à {limit})" if n > limit else ""))


def _replace_in(nd, pairs):
    cnt = 0
    if nd[0] == "b":
        s = _is_text(nd[3])
        if s is not None:
            t = s
            for a, b in pairs:
                t = t.replace(a, b)
            if t != s:
                nd[3] = t.encode("utf-8") + b"\x00"
                return 1
        return 0
    for k in nd[3]:
        cnt += _replace_in(k, pairs)
    return cnt


def cmd_remplacer(src, dst, pairs, log=print):
    root, tail = load_orc(src)
    n = _replace_in(root, pairs)
    save_orc(dst, root, tail)
    log(f"{n} chaîne(s) modifiée(s) -> {dst}")


def _find_path(root, path):
    """Chemin « id#n/id#n/... » (le « #n » est facultatif : 0 par défaut)."""
    els = [e for e in path.strip("/").split("/") if e != ""]
    if not els:
        raise OrcError("Chemin vide.")

    def split(e):
        a, _, b = e.partition("#")
        return int(a), int(b or 0)
    try:
        ids = [split(e) for e in els]
    except ValueError:
        raise OrcError(f"Chemin invalide : {path}")
    if ids[0][0] != root[2]:
        raise OrcError(f"Le chemin doit commencer par l'identifiant du chunk racine ({root[2]}).")
    nd, parent = root, None
    for want, rank in ids[1:]:
        n = -1
        for k in nd[3]:
            if k[0] == "c" and k[2] == want:
                n += 1
                if n == rank:
                    parent, nd = nd, k
                    break
        else:
            raise OrcError(f"Chunk {want}#{rank} introuvable dans {nd[2]}.")
    return parent, nd


def _clone(nd):
    return nd[:2] + [nd[2]] + [[_clone(k) for k in nd[3]]] + [nd[4]] if nd[0] == "c" \
        else ["b", nd[1], nd[2], nd[3]]


def cmd_cloner(src, dst, path, pairs, log=print):
    root, tail = load_orc(src)
    parent, nd = _find_path(root, path)
    if parent is None:
        raise OrcError("Impossible de cloner la racine.")
    cp = _clone(nd)
    n = _replace_in(cp, pairs)
    i = next(i for i, k in enumerate(parent[3]) if k is nd)
    parent[3].insert(i + 1, cp)
    save_orc(dst, root, tail)
    log(f"Chunk {path} dupliqué ({n} chaîne(s) modifiée(s) dans la copie) -> {dst}")


def cmd_editer(src, dst, path, bid, texte, log=print):
    """Remplace EXACTEMENT le texte du block d'identifiant bid situé dans le chunk « path »."""
    root, tail = load_orc(src)
    parent, nd = _find_path(root, path)
    cible = [k for k in nd[3] if k[0] == "b" and k[2] == bid]
    if not cible:
        raise OrcError(f"Aucun block {bid} directement dans {path}.")
    k = cible[0]
    ancien = _is_text(k[3])
    if ancien is None:
        raise OrcError(f"Le block {bid} n'est pas un texte.")
    k[3] = texte.encode("utf-8") + b"\x00"
    save_orc(dst, root, tail)
    log(f"Block {bid} de {path} : « {ancien.strip(chr(0))} » -> « {texte} »  ({dst})")


def cmd_dump(src, dst, log=print):
    root, tail = load_orc(src)
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        dump_text(root, tail, f)
    log(f"Écrit : {dst}")


def cmd_build(src, dst, log=print):
    with open(src, "r", encoding="utf-8") as f:
        root, tail = parse_text(f.read().splitlines())
    save_orc(dst, root, tail)
    log(f"Écrit : {dst} ({os.path.getsize(dst):,} octets)")


# --------------------------------------------------------------------------
# Interface graphique minimale
# --------------------------------------------------------------------------

def gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext

    root = tk.Tk()
    root.title("Game.orc – texte <-> .orc")
    root.geometry("760x460")
    box = scrolledtext.ScrolledText(root, height=18)

    def log(m=""):
        box.insert("end", m + "\n")
        box.see("end")
        root.update_idletasks()

    def run(fn):
        try:
            fn()
        except Exception as ex:      # noqa
            messagebox.showerror("Erreur", str(ex))
            log("ERREUR : " + str(ex))

    def do_dump():
        s = filedialog.askopenfilename(title="Game.orc", filetypes=[("orc", "*.orc"), ("tous", "*")])
        if s:
            d = filedialog.asksaveasfilename(title="Texte de sortie", defaultextension=".txt",
                                             initialfile=os.path.splitext(os.path.basename(s))[0] + ".txt")
            if d:
                cmd_dump(s, d, log)

    def do_build():
        s = filedialog.askopenfilename(title="Fichier texte", filetypes=[("texte", "*.txt"), ("tous", "*")])
        if s:
            d = filedialog.asksaveasfilename(title="Game.orc à créer", defaultextension=".orc")
            if d:
                cmd_build(s, d, log)

    def do_verif():
        s = filedialog.askopenfilename(title="Game.orc", filetypes=[("orc", "*.orc"), ("tous", "*")])
        if s:
            cmd_verifier(s, log)

    fr = tk.Frame(root)
    fr.pack(fill="x", padx=8, pady=8)
    for t, fn in (("Game.orc -> texte", do_dump), ("Texte -> Game.orc", do_build),
                  ("Vérifier un .orc (aller-retour)", do_verif)):
        tk.Button(fr, text=t, command=lambda f=fn: run(f)).pack(side="left", padx=4)
    box.pack(fill="both", expand=True, padx=8, pady=8)
    root.mainloop()


def main(argv):
    if len(argv) < 2 or argv[1] in ("gui",):
        return gui()
    c = argv[1]
    try:
        if c == "dump" and len(argv) == 4:
            cmd_dump(argv[2], argv[3])
        elif c == "build" and len(argv) == 4:
            cmd_build(argv[2], argv[3])
        elif c in ("verifier", "verify") and len(argv) == 3:
            return 0 if cmd_verifier(argv[2]) else 1
        elif c == "chercher" and len(argv) == 4:
            cmd_chercher(argv[2], argv[3])
        elif c == "remplacer" and len(argv) >= 6 and (len(argv) - 4) % 2 == 0:
            cmd_remplacer(argv[2], argv[3], list(zip(argv[4::2], argv[5::2])))
        elif c == "editer" and len(argv) == 7:
            cmd_editer(argv[2], argv[3], argv[4], int(argv[5]), argv[6])
        elif c == "cloner" and len(argv) >= 6:
            pairs = []
            for a in argv[5:]:
                if "=" not in a:
                    raise OrcError(f"« {a} » : écrivez ancien=nouveau")
                x, y = a.split("=", 1)
                pairs.append((x, y))
            cmd_cloner(argv[2], argv[3], argv[4], pairs)
        else:
            print(__doc__)
            return 2
    except (OrcError, OSError) as ex:
        print("ERREUR :", ex)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
