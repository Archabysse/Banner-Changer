# -*- coding: utf-8 -*-
"""Moteur de « Changer of Banners » : ajoute des emblèmes .gtex à toutes les armées d'un Data4.ork.
Indépendant de l'éditeur principal (n'importe aucun de ses modules)."""
import os
import struct
import tempfile
import zlib

import orc_tool as T
import ork_pack as P

PREFIXE_JEU = "Gui\\texture\\banners\\heraldics\\"


class BannersError(Exception):
    pass


# ----------------------------------------------------------------------------- accès à l'arbre de game.orc
def blk(c, t):
    return next((b for b in c[3] if b[0] == "b" and b[2] == t), None)


def chk(c, t):
    return next((x for x in c[3] if x[0] == "c" and x[2] == t), None)


def chks(c, t):
    return [x for x in c[3] if x[0] == "c" and x[2] == t]


def u(b):
    return struct.unpack("<I", bytes(b[3][:4]))[0]


def setu(b, v):
    b[3] = struct.pack("<I", v)


def sval(b):
    return bytes(b[3]).rstrip(b"\0").decode("utf-8", "replace")


def cstr(s):
    return s.encode("utf-8") + b"\0"


# ----------------------------------------------------------------------------- fichiers .gtex
def lister_gtex(dossier):
    """[(chemin complet, nom sans extension)] des .gtex du dossier (sous-dossiers compris), triés."""
    res = []
    if dossier and os.path.isdir(dossier):
        for r, _, fs in os.walk(dossier):
            for fn in sorted(fs):
                if fn.lower().endswith(".gtex"):
                    res.append((os.path.join(r, fn), os.path.splitext(fn)[0]))
    return res


def diagnostic(chemin):
    """(ok, code, détail) : code in 'ok', 'pas_gtex', 'pair', 'illisible' ; détail = « DXT3 128×128 1 »."""
    try:
        with open(chemin, "rb") as f:
            d = f.read(0x40)
        if d[:6] != b"GTEX00":
            return False, "pas_gtex", ""
        tag = d[6:10].decode("latin-1")
        niv = struct.unpack_from("<I", d, 0x0A)[0]
        w, h = struct.unpack_from("<2I", d, 0x2A)
        det = "%s  %d×%d  %d" % (tag, w, h, niv)
        if w < 2 or h < 2 or w % 2 or h % 2:
            return False, "pair", det
        return True, "ok", det
    except Exception as ex:                                  # noqa
        return False, "illisible", str(ex)


# ----------------------------------------------------------------------------- aperçu (décodage sans Pillow)
def _rgb565(v):
    return (((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31)


def _bloc_couleurs(b, quatre):
    c0, c1 = struct.unpack_from("<2H", b, 0)
    a, bb = _rgb565(c0), _rgb565(c1)
    if c0 > c1 or quatre:
        p = [a + (255,), bb + (255,),
             tuple((2 * a[i] + bb[i]) // 3 for i in range(3)) + (255,),
             tuple((a[i] + 2 * bb[i]) // 3 for i in range(3)) + (255,)]
    else:
        p = [a + (255,), bb + (255,), tuple((a[i] + bb[i]) // 2 for i in range(3)) + (255,), (0, 0, 0, 0)]
    idx = struct.unpack_from("<I", b, 4)[0]
    return [p[(idx >> (2 * k)) & 3] for k in range(16)]


def _bloc_dxt(typ, d, off):
    """16 pixels RGBA d'un bloc DXT1/3/5."""
    if typ == 1:
        return _bloc_couleurs(d[off:off + 8], False)
    col = _bloc_couleurs(d[off + 8:off + 16], True)
    if typ == 3:
        bits = struct.unpack_from("<Q", d, off)[0]
        al = [((bits >> (4 * k)) & 15) * 17 for k in range(16)]
    else:
        a0, a1 = d[off], d[off + 1]
        bits = int.from_bytes(d[off + 2:off + 8], "little")
        if a0 > a1:
            t = [a0, a1] + [((7 - i) * a0 + i * a1) // 7 for i in range(1, 7)]
        else:
            t = [a0, a1] + [((5 - i) * a0 + i * a1) // 5 for i in range(1, 5)] + [0, 255]
        al = [t[(bits >> (3 * k)) & 7] for k in range(16)]
    return [c[:3] + (a,) for c, a in zip(col, al)]


def _png(w, h, lignes):
    def ch(t, data):
        return struct.pack(">I", len(data)) + t + data + struct.pack(">I", zlib.crc32(t + data) & 0xFFFFFFFF)
    brut = b"".join(b"\0" + l for l in lignes)
    return (b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
            ch(b"IDAT", zlib.compress(brut, 6)) + ch(b"IEND", b""))


def apercu_png(chemin, maxi=256):
    """(octets PNG, largeur, hauteur d'origine, largeur affichée, hauteur affichée) du premier niveau d'un .gtex,
    composé sur un damier (transparence visible). Lève BannersError si illisible."""
    with open(chemin, "rb") as f:
        d = f.read()
    if d[:6] != b"GTEX00":
        raise BannersError("pas un .gtex")
    tag = d[6:10]
    w, h = struct.unpack_from("<2I", d, 0x2A)
    if w < 1 or h < 1 or w > 8192 or h > 8192:
        raise BannersError("dimensions invalides")
    typ = tag[3] - 0x30 if tag[:3] == b"DXT" else 0
    if typ not in (0, 1, 3, 5):
        raise BannersError("format non géré : " + tag.decode("latin-1"))
    corps = d[54:]
    pas = max(1, max(w, h) // maxi)
    ow, oh = w // pas, h // pas
    cache = {}
    lignes = []
    bw = (w + 3) // 4
    for y in range(oh):
        sy = y * pas
        ligne = bytearray()
        for x in range(ow):
            sx = x * pas
            if typ == 0:
                o = (sy * w + sx) * 4
                if o + 4 > len(corps):
                    raise BannersError("fichier tronqué")
                b_, g_, r_, a_ = corps[o], corps[o + 1], corps[o + 2], corps[o + 3]
            else:
                k = (sy // 4) * bw + sx // 4
                bl = cache.get(k)
                if bl is None:
                    taille = 8 if typ == 1 else 16
                    if (k + 1) * taille > len(corps):
                        raise BannersError("fichier tronqué")
                    bl = cache[k] = _bloc_dxt(typ, corps, k * taille)
                r_, g_, b_, a_ = bl[(sy % 4) * 4 + sx % 4]
            fond = 200 if ((x // 8) + (y // 8)) % 2 else 150
            ligne += bytes(((r_ * a_ + fond * (255 - a_)) // 255, (g_ * a_ + fond * (255 - a_)) // 255,
                            (b_ * a_ + fond * (255 - a_)) // 255))
        lignes.append(bytes(ligne))
    return _png(ow, oh, lignes), w, h, ow, oh


# ----------------------------------------------------------------------------- archives du jeu
def noms_dans_autres_archives(ork_base):
    """CRC des noms présents dans les AUTRES .ork du dossier (Data.ork, Data1.ork…), pas dans l'archive de base."""
    res = set()
    d = os.path.dirname(os.path.abspath(ork_base))
    base = os.path.abspath(ork_base).lower()
    for fn in os.listdir(d):
        p = os.path.join(d, fn)
        if fn.lower().endswith(".ork") and os.path.abspath(p).lower() != base:
            try:
                res.update(e.namecrc for e in P.Archive(p).entries)
            except Exception:                                  # noqa : archive illisible, ignorée
                pass
    return res


def crc_nom(nom):
    return P.name_crc(nom.lower().encode("latin-1", "ignore"))


def lire_game_orc(ork):
    a = P.Archive(ork)
    crc = P.name_crc(b"game.orc")
    for e in a.entries:
        if e.namecrc == crc:
            return a.read(e, b"game.orc")
    raise BannersError("game.orc introuvable dans " + ork)


def _source_remplissage(ork_base, emblemes, dossier_tmp):
    """Fichier .gtex servant aux entrées de remplissage : le plus petit emblème ajouté, sinon un emblème d'origine
    pris dans les archives du dossier de l'archive de base."""
    if emblemes:
        return min((c for _, c in emblemes), key=os.path.getsize)
    d = os.path.dirname(os.path.abspath(ork_base))
    for fn in sorted(os.listdir(d)):
        if not fn.lower().endswith(".ork"):
            continue
        try:
            arc = P.Archive(os.path.join(d, fn))
        except Exception:                                      # noqa
            continue
        for nom in ("heraldics_nuln", "heraldics_ostermark", "heraldics_elf4", "heraldics_darkelf1", "heraldics_orc5"):
            low = (PREFIXE_JEU + nom).lower()
            crc = P.name_crc(low.encode("latin-1"))
            for e in arc.entries:
                if e.namecrc == crc:
                    sortie = os.path.join(dossier_tmp, "remplissage.gtex")
                    with open(sortie, "wb") as f:
                        f.write(arc.read(e, low.encode("latin-1")))
                    return sortie
    return None


# ----------------------------------------------------------------------------- modification de game.orc
def _sous_factions(root):
    res = []
    c1500 = chk(root, 1500)
    if c1500 is None:
        return res
    for a in chks(c1500, 2000):
        for s in chks(a, 210):
            if chk(s, 30) is not None and chks(chk(s, 30), 20):
                res.append(s)
    return res


def _guids_pris(root):
    S = set()

    def w(n):
        for x in n[3]:
            if x[0] == "b":
                if len(x[3]) == 4 and x[2] in (45, 20, 1000, 5):
                    S.add(struct.unpack("<I", bytes(x[3]))[0])
            else:
                w(x)
    w(root)
    return S


def modifier_game_orc(root, emblemes, corriger, log):
    """emblemes : [(nom, chemin disque)]. Ajoute chaque emblème à la fin de la liste de CHAQUE sous-faction, puis (si
    corriger) intercale les entrées de remplissage qui réparent le défilement. Renvoie (ajouts, remplissages)."""
    sfs = _sous_factions(root)
    if not sfs:
        raise BannersError("structure inattendue : aucune liste d'emblèmes (1500 › 2000 › 210 › 30 › 20) dans game.orc.")
    pris = _guids_pris(root)
    prochain = [0x0EB00001]

    def guid():
        while prochain[0] in pris:
            prochain[0] += 1
        pris.add(prochain[0])
        return prochain[0]
    # 1) retire d'éventuelles entrées de remplissage d'un passage précédent (elles sont recréées proprement)
    anciens = 0
    for sf in sfs:
        c30 = chk(sf, 30)
        gardees = [x for x in c30[3] if not (x[0] == "c" and x[2] == 20 and blk(x, 10) is not None
                                              and "zremplissage" in sval(blk(x, 10)).lower())]
        anciens += len(c30[3]) - len(gardees)
        c30[3][:] = gardees
        setu(blk(c30, 10), len(chks(c30, 20)))
    if anciens:
        log("  %d ancienne(s) entrée(s) de remplissage retirée(s) avant recalcul" % anciens)
    # 2) ajout des emblèmes : la liste est commune à toutes les armées, chaque emblème n'est donc inscrit qu'UNE fois
    #    (à la fin de la dernière liste). Un emblème déjà présent est conservé tel quel (même identifiant) ;
    #    ses éventuels doublons (anciennes versions) sont retirés.
    n = 0
    doublons = 0
    for nom, chemin in emblemes:
        chemin_jeu = (PREFIXE_JEU + nom + ".gtex").lower()
        vu = False
        for sf in sfs:
            c30 = chk(sf, 30)
            gardees = []
            for x in c30[3]:
                if x[0] == "c" and x[2] == 20 and blk(x, 10) is not None and sval(blk(x, 10)).lower() == chemin_jeu:
                    if vu:
                        doublons += 1
                        continue
                    vu = True
                gardees.append(x)
            if len(gardees) != len(c30[3]):
                c30[3][:] = gardees
                setu(blk(c30, 10), len(chks(c30, 20)))
        if vu:
            continue
        c30 = chk(sfs[-1], 30)
        modeles = chks(c30, 20)
        tpl = next((x for x in modeles if blk(x, 20) is not None and len(blk(x, 20)[3]) <= 1), modeles[0])
        cp = T._clone(tpl)
        setu(blk(cp, 5), guid())
        blk(cp, 6)[3] = cstr(nom)
        blk(cp, 10)[3] = cstr(PREFIXE_JEU + nom + ".gtex")
        blk(cp, 30)[3] = cstr(PREFIXE_JEU + nom + ".gtex")
        dernier = next(i for i in range(len(c30[3]) - 1, -1, -1) if c30[3][i] is modeles[-1])
        c30[3].insert(dernier + 1, cp)
        setu(blk(c30, 10), len(modeles) + 1)
        n += 1
    log("  %d emblème(s) ajouté(s)" % n + ("  ·  %d doublon(s) retiré(s)" % doublons if doublons else ""))
    # 3) correction du défilement
    rempl = 0
    if corriger:
        vus = set()
        for sf in sfs:
            c30 = chk(sf, 30)
            ents = chks(c30, 20)
            sortie = []
            for e in ents:
                sortie.append(e)
                p = sval(blk(e, 10)).lower()
                if p in vus:
                    continue
                vus.add(p)
                rempl += 1
                f = T._clone(e)
                chemin = PREFIXE_JEU + "heraldics_zremplissage%03d.gtex" % rempl
                setu(blk(f, 5), guid())
                blk(f, 6)[3] = cstr(" ")
                blk(f, 10)[3] = cstr(chemin)
                blk(f, 30)[3] = cstr(chemin)
                if blk(f, 20) is not None:
                    blk(f, 20)[3] = b"\0"
                vus.add(chemin.lower())
                sortie.append(f)
            pos = c30[3].index(ents[0])
            c30[3][:] = [x for x in c30[3] if not (x[0] == "c" and x[2] == 20)]
            for k, e in enumerate(sortie):
                c30[3].insert(pos + k, e)
            setu(blk(c30, 10), len(sortie))
        log("  défilement corrigé : %d entrée(s) de remplissage" % rempl)
    return n, rempl


# ----------------------------------------------------------------------------- construction
def prochain_nom_sortie(dossier, base="Data4"):
    """(chemin, existait) : Data4.ork, ou Data4_1.ork, Data4_2.ork… si le nom est déjà pris."""
    p = os.path.join(dossier, base + ".ork")
    if not os.path.exists(p):
        return p, False
    i = 1
    while os.path.exists(os.path.join(dossier, "%s_%d.ork" % (base, i))):
        i += 1
    return os.path.join(dossier, "%s_%d.ork" % (base, i)), True


def construire(ork_base, dossier_sortie, fichiers, corriger, log=print):
    """fichiers : [(nom, chemin .gtex)] déjà contrôlés. Écrit le nouveau Data4.ork et renvoie
    (chemin écrit, liste d'avertissements, nombre d'emblèmes réellement ajoutés)."""
    if not os.path.isfile(ork_base):
        raise BannersError("Data4.ork introuvable : " + ork_base)
    if not dossier_sortie:
        raise BannersError("dossier de sortie non indiqué")
    os.makedirs(dossier_sortie, exist_ok=True)
    sortie, _ = prochain_nom_sortie(dossier_sortie)
    avert = []
    log("Lecture de game.orc…")
    root, tail = T.parse(lire_game_orc(ork_base))
    deja = noms_dans_autres_archives(ork_base)
    retenus = []
    vus = set()
    for nom, chemin in fichiers:
        if nom.lower() in vus:
            avert.append("doublon ignoré : " + nom)
            continue
        vus.add(nom.lower())
        if crc_nom(PREFIXE_JEU + nom) in deja:
            avert.append("« %s » : ce nom existe déjà dans une autre archive du jeu : ignoré (renommez le fichier)" % nom)
            continue
        retenus.append((nom, chemin))
    with tempfile.TemporaryDirectory() as tmp:
        n, rempl = modifier_game_orc(root, retenus, corriger, log)
        files = []
        gorc = os.path.join(tmp, "game.orc")
        with open(gorc, "wb") as f:
            f.write(T.build_file(root, tail))
        files.append(("game.orc", gorc))
        for nom, chemin in retenus:
            files.append(((PREFIXE_JEU + nom).lower(), chemin))
        if rempl:
            src = _source_remplissage(ork_base, retenus, tmp)
            if not src:
                raise BannersError("aucun fichier .gtex disponible pour les entrées de remplissage")
            for k in range(1, rempl + 1):
                nom = (PREFIXE_JEU + "heraldics_zremplissage%03d" % k).lower()
                if crc_nom(nom) in deja:
                    raise BannersError("un fichier de remplissage existe déjà dans le jeu : " + nom)
                files.append((nom, src))
        P.FILECRC.clear()
        log("Écriture de l'archive…")
        P.build(sortie, files, P.Archive(ork_base), None, lambda m: None)
        # contrôle de relecture : game.orc, les emblèmes et deux entrées de remplissage (toutes les autres sont identiques)
        a_verifier = [f for f in files if "zremplissage" not in f[0]] + [f for f in files if "zremplissage" in f[0]][:2]
        ok = P.check(sortie, a_verifier, lambda m: None)
        if not ok:
            raise BannersError("le contrôle de relecture de l'archive a échoué")
    log("Archive écrite : " + sortie)
    return sortie, avert, n
