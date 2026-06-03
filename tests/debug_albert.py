import os
#!/usr/bin/env python3
"""
tests/debug_albert.py — Diagnostic de la génération IA

Lance une série d'appels Albert avec différentes configurations pour
identifier ce qui cause les JSON cassés. Affiche le raw complet en cas
d'échec pour pouvoir diagnostiquer.

Usage :
    python3 tests/debug_albert.py

Pas besoin de lancer SCRIBE : le script appelle Albert directement.
"""
import asyncio, json, hashlib
import httpx
from datetime import datetime

ALBERT_URL   = "https://albert.api.etalab.gouv.fr/v1/chat/completions"
ALBERT_MODEL = "mistralai/Ministral-3-8B-Instruct-2512"
ALBERT_KEY   = os.getenv("ALBERT_API_KEY", "")  # Set via env var

SYSTEM_EXO = """Tu es expert en gestion de crise hospitalière française. Tu génères des scénarios d'exercice réalistes pour équipes GHT. Tu réponds UNIQUEMENT en JSON valide, sans texte autour."""

def build_prompt_full(nb_stimuli=8, complexite="MOYEN", type_crise="SANITAIRE",
                     sujet="Femme enceinte hémorragie au bloc + prématuré, saturation maternité DEMO1",
                     duree_min=60, duree_reel=240, ratio=4.0,
                     sites=None, nb_joueurs=4,
                     stimuli_externes="none", valeurs=None, services=None,
                     perturbations=""):
    """Prompt identique à celui de SCRIBE 2187/2192."""
    if sites is None: sites = ["DEMO1"]
    if valeurs is None: valeurs = []
    if services is None: services = []
    sid = datetime.now().strftime('%Y%m%d_%H%M')
    ports = {"DEMO1":8660,"DEMO2":8661,"DEMO5":8662,"DEMO6":8663,"DEMO7":8664,"DEMO5":8665,"DEMO6":8666}
    type_ctx = {
        "SANITAIRE":"Crise sanitaire hospitalière (hémorragie, accident, pandémie...)",
        "CYBER":"Crise cyber hospitalière. SIH, DPI, PACS potentiellement touchés. Inclure stimuli CERT Santé, isolation réseaux, continuité sans outils numériques.",
        "MIXTE":"Crise mixte sanitaire+cyber",
        "RH":"Crise RH / continuité de service",
        "TERTIAIRE":"Crise accueil / logistique / hôtellerie"
    }.get(type_crise, "Crise générique")
    ext_ctx = "aucun" if stimuli_externes == "none" else f"Inclure des stimuli externes provenant de : {stimuli_externes}"

    return f"""Génère un scénario d'exercice de crise hospitalière :
SUJET: {sujet}
SITES GHT: {', '.join(sites)} ({len(sites)} site(s))
DURÉE EXERCICE: {duree_min} minutes (ratio compression: {ratio}x → 1 min exercice = {ratio} min réelles)
DURÉE RÉELLE SIMULÉE: {duree_reel} minutes
TYPE DE CRISE: {type_crise} — {type_ctx}
COMPLEXITÉ: {complexite}
NOMBRE DE PARTICIPANTS: {nb_joueurs} personnes (générer un joueur avec rôle pour chacun)
NOMBRE DE STIMULI: {nb_stimuli} (espacés progressivement)
VALEURS MÉTIERS À TRAVAILLER: {', '.join(valeurs) if valeurs else 'aucune'}
SERVICES SUPPORTS IMPLIQUÉS: {', '.join(services) if services else 'aucun'}
STIMULI EXTERNES: {ext_ctx}
PERTURBATIONS FONCTIONNELLES: {perturbations if perturbations else "aucune panne/perturbation"}

Retourne UNIQUEMENT ce JSON valide (rien d'autre, pas de texte avant ou après):
{{"meta":{{"id":"exo_{sid}","titre":"<titre court et évocateur>","description":"<2-3 phrases>","duree_min":{duree_min},"duree_reel_min":{duree_reel},"ratio_compression":{ratio},"complexite":"{complexite}","type_crise":"{type_crise}","objectifs_pedagogiques":["<obj1>","<obj2>","<obj3>"]}},"acteurs":[{{"sigle":"{sites[0]}","nom_etablissement":"<nom complet>","role":"coordinateur","port":{ports.get(sites[0],8660)},"joueurs":[{{"username":"dircrise","display_name":"<prénom NOM — Directeur de Crise>","role_exercice":"<rôle précis dans l'exercice>","responsabilites":["<resp1>","<resp2>"]}}]}}],"stimuli":[{{"id":"S01","t_min":0,"cible":"{sites[0]}","type":"incident","titre":"<titre court>","description_animateur":"<contexte pour animateur — ce que les joueurs doivent faire>","payload":{{"fait":"<description précise pour les joueurs>","urgency":3,"type_crise":"{type_crise}","site_id":"<SIGLE>","unite_fonctionnelle":"<service>","declarant_nom":"<qui déclare>","analyse":"","jalons_labels":["<jalon1>","<jalon2>","<jalon3>"]}},"action_attendue":"<décision ou action attendue des joueurs>"}}],"decisions_attendues":[{{"t_min":5,"contenu":"<décision>","responsable":"Directeur de crise","obligatoire":true}}],"debriefing_guide":{{"points_cles":["<point1>","<point2>"],"questions_debriefing":["<question1>","<question2>"],"pieges_frequents":["<piège1>"]}}}}

RÈGLES STRICTES:
- EXACTEMENT {nb_stimuli} stimuli, espacés progressivement (T+0, T+5, T+10...)
- Types stimuli disponibles: incident, message, transfert, chat, decision
- Ports fixes: DEMO1=8660 DEMO2=8661 DEMO5=8662 DEMO6=8663 DEMO7=8664 DEMO5=8665 DEMO6=8666
- EXACTEMENT {nb_joueurs} joueurs répartis sur les sites
- JSON VALIDE UNIQUEMENT — pas de backtick, pas de commentaire, pas de texte hors JSON"""


async def call_albert(prompt, temperature=0.7, max_tokens=12000, label=""):
    """Un appel Albert brut. Retourne (ok, parsed_or_raw, error_info)."""
    print(f"\n{'='*70}")
    print(f"  TEST {label}")
    print(f"{'='*70}")
    print(f"  Prompt : {len(prompt)} chars (hash={hashlib.sha256(prompt.encode()).hexdigest()[:12]})")
    print(f"  Temp={temperature}, max_tokens={max_tokens}")

    t0 = datetime.now()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(ALBERT_URL,
                headers={"Authorization":f"Bearer {ALBERT_KEY}","Content-Type":"application/json"},
                json={
                    "model":ALBERT_MODEL,
                    "messages":[
                        {"role":"system","content":SYSTEM_EXO},
                        {"role":"user","content":prompt},
                    ],
                    "max_tokens":max_tokens,
                    "temperature":temperature,
                }
            )
    except Exception as e:
        print(f"  ❌ Exception réseau : {e}")
        return False, None, str(e)

    dt = (datetime.now()-t0).total_seconds()
    print(f"  HTTP {r.status_code} en {dt:.1f}s")
    if r.status_code != 200:
        print(f"  ❌ {r.text[:400]}")
        return False, None, f"HTTP {r.status_code}"

    payload = r.json()
    raw = payload["choices"][0]["message"]["content"].strip()
    usage = payload.get("usage",{})
    finish_reason = payload.get("choices",[{}])[0].get("finish_reason","?")
    print(f"  Tokens : input={usage.get('prompt_tokens','?')}, output={usage.get('completion_tokens','?')}")
    print(f"  Finish reason : {finish_reason}  {'⚠️  TRONQUÉ' if finish_reason == 'length' else ''}")
    print(f"  Raw : {len(raw)} chars")

    # Nettoyer markdown (comme 2187)
    cleaned = raw
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
        n_stimuli = len(parsed.get("stimuli",[]))
        print(f"  ✅ JSON valide — {n_stimuli} stimuli, titre='{parsed.get('meta',{}).get('titre','?')[:50]}'")
        return True, parsed, None
    except json.JSONDecodeError as e:
        print(f"  ❌ JSON invalide : {e}")
        # Afficher le contexte autour de l'erreur
        pos = e.pos if hasattr(e, 'pos') else 0
        ctx_start = max(0, pos-200)
        ctx_end = min(len(cleaned), pos+200)
        print(f"\n  --- Contexte autour du char {pos} (± 200) ---")
        print(f"  {cleaned[ctx_start:pos]}<<<ERREUR ICI>>>{cleaned[pos:ctx_end]}")
        print(f"  --- Fin contexte ---")
        return False, cleaned, str(e)


async def main():
    """Série de tests pour comprendre ce qui rend Albert instable."""
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║  SCRIBE — Diagnostic génération IA                                   ║")
    print(f"║  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                                                 ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")

    results = []

    # Test 1 : prompt minimal (peu de stimuli, sujet simple)
    p = build_prompt_full(nb_stimuli=5, complexite="FACILE",
                          sujet="Incendie cuisine centrale DEMO1")
    ok, _, err = await call_albert(p, temperature=0.7,
                                    label="1. Simple (5 stimuli, FACILE)")
    results.append(("simple_5stimuli", ok, err))

    # Test 2 : même sujet que le test 1, mais température basse
    ok, _, err = await call_albert(p, temperature=0.2,
                                    label="2. Simple mais temp=0.2")
    results.append(("simple_temp_basse", ok, err))

    # Test 3 : prompt complexe comme celui qui fait crasher (ton cas)
    p = build_prompt_full(nb_stimuli=10, complexite="DIFFICILE",
                          type_crise="CYBER",
                          sujet="Phishing cyber visant DPI, transferts patients multi-sites",
                          sites=["DEMO1", "DEMO2"], nb_joueurs=6,
                          stimuli_externes="samu,prefecture,cert_sante",
                          valeurs=["coordination","decision","cyber_response"],
                          services=["dsi","imagerie","labo","pharmacie"],
                          perturbations="DPI HS, PACS perturbé")
    ok, _, err = await call_albert(p, temperature=0.7,
                                    label="3. Complexe cyber (10 stimuli, DIFFICILE)")
    results.append(("complexe_10stimuli", ok, err))

    # Test 4 : même complexe, mais température basse (doit être plus stable)
    ok, _, err = await call_albert(p, temperature=0.2,
                                    label="4. Complexe mais temp=0.2")
    results.append(("complexe_temp_basse", ok, err))

    # Test 5 : très complexe (15 stimuli, tout activé)
    p = build_prompt_full(nb_stimuli=15, complexite="EXPERT",
                          type_crise="MIXTE",
                          sujet="Ransomware + afflux blessés + panne ascenseurs + grève infirmières",
                          sites=["DEMO1","DEMO2","DEMO5"], nb_joueurs=8,
                          stimuli_externes="samu,prefecture,medias,famille,cert_sante,ght_voisin",
                          valeurs=["coordination","communication","decision","transfert","capacite","continuite","cyber_response","rh","ethique"],
                          services=["imagerie","labo","pharmacie","bloc","sterilisation","dsi","biomed","securite","restauration","transport","lingerie","dechets"],
                          perturbations="DPI HS, PACS HS, SI hôtellerie KO, téléphonie IP partielle")
    ok, _, err = await call_albert(p, temperature=0.7,
                                    label="5. Très complexe (15 stimuli, EXPERT)")
    results.append(("tres_complexe", ok, err))

    # Récap
    print("\n")
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║  RÉCAPITULATIF                                                       ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")
    for name, ok, err in results:
        icon = "✅" if ok else "❌"
        print(f"  {icon} {name}: {'OK' if ok else err[:80] if err else 'KO'}")

    n_ok = sum(1 for _,ok,_ in results if ok)
    print(f"\n  Total : {n_ok}/{len(results)} réussis")

    # Conclusion automatique
    print("\n  Conclusion :")
    if n_ok == len(results):
        print("  → Albert fonctionne normalement pour tous les profils testés.")
        print("    Ton problème actuel doit être dans SCRIBE côté build, pas Albert.")
    elif n_ok == 0:
        print("  → Albert échoue sur TOUT. Problème côté etalab.gouv.fr (rate limit ?")
        print("    modèle HS ? clé bannie ?). Pas un problème SCRIBE.")
    else:
        simples_ok = results[0][1] and results[1][1]
        complexes_ok = results[2][1] and results[3][1]
        if simples_ok and not complexes_ok:
            print("  → Albert gère les prompts simples mais pas les complexes.")
            print("    Solution : réduire nb_stimuli, complexite, ou services activés.")
        elif not simples_ok:
            print("  → Albert échoue même sur des prompts simples. Service dégradé.")
        else:
            print("  → Pattern d'échec partiel — voir les erreurs individuelles.")


if __name__ == "__main__":
    asyncio.run(main())
