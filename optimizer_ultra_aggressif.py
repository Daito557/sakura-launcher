"""Version ULTRA AGRESSIVE de _start_background_optimizer — pour PC faibles
qui lag fort. Ce fichier n'est PAS importé automatiquement par sakura.py :
c'est une variante à copier-coller manuellement à la place de la méthode
_start_background_optimizer dans sakura.py, uniquement sur les machines qui
en ont besoin (pas dans la version distribuée par défaut).

Reste scopée au seul process du launcher (jamais le jeu ni le système :
toujours pas de kill de process tiers, pas de purge système globale, pas de
service Windows touché) mais pousse le nettoyage mémoire au maximum :
- gc.collect() ET trim_own_memory() à CHAQUE cycle (3s), sans attendre un
  seuil de RAM système
- boucle 6-7x plus fréquente que la version normale (3s au lieu de 20s) :
  plus d'overhead CPU du nettoyage lui-même, mais sur un PC déjà saturé en
  RAM c'est ce qui compte le plus
- revérifie la priorité CPU "above normal" du jeu, jamais plus haut
  (HIGH/REALTIME peut geler tout le PC, déjà vu sur ce projet).

Pour l'utiliser : ouvre sakura.py, trouve la méthode
"def _start_background_optimizer(self):" dans la classe SakuraLauncher, et
remplace-la entièrement par celle ci-dessous (en gardant l'indentation des
méthodes de classe, 4 espaces).
"""

def _start_background_optimizer(self):
    def loop():
        while True:
            time.sleep(3)
            if not self.boost_active.get():
                continue
            try:
                import gc
                gc.collect()
                trim_own_memory()
            except Exception:
                pass
            pid = self._mc_pid
            if pid:
                try:
                    import psutil
                    p = psutil.Process(pid)
                    if not p.is_running():
                        self._mc_pid = None
                    elif sys.platform == "win32" and \
                            p.nice() != psutil.ABOVE_NORMAL_PRIORITY_CLASS:
                        boost_process_priority(pid, "above")
                        self._add_log("Priorité CPU du jeu rétablie (Sakura Mode)")
                except Exception:
                    self._mc_pid = None
    threading.Thread(target=loop, daemon=True).start()
