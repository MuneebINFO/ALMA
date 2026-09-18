"""
Jouer une coroutine WinRT depuis un thread qui n a pas de boucle asyncio.

Les API Windows exposees par `winsdk` sont toutes asynchrones, et Alma les
appelle depuis le thread des commandes ou depuis le thread graphique --
aucun des deux n a de boucle. Ce module tient l unique facon correcte de
faire le pont, plutot qu une copie par appelant : dupliquer un utilitaire de
concurrence est precisement la ou les bugs s installent sans se voir.
"""

from __future__ import annotations

import asyncio


def executer(coroutine):
    """
    Joue la coroutine et rend son resultat.

    Si une boucle tourne deja dans ce thread, on en ouvre une dans un thread
    a part plutot que de s y greffer : s y greffer bloquerait l appelant, et
    depuis le thread graphique cela fige la fenetre.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coroutine).result()
