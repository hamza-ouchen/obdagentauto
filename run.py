"""Une commande : python run.py. L’environnement local est sélectionné si présent."""
import os
import sys
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
if __name__=='__main__':
    # Sur cette machine, python run.py utilise automatiquement les dépendances
    # déjà installées dans .venv ; aucun fichier batch ni activation manuelle.
    local_python=ROOT/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if local_python.exists() and Path(sys.prefix).resolve()!=(ROOT/'.venv').resolve():
        raise SystemExit(subprocess.call([str(local_python),str(Path(__file__).resolve())],cwd=str(ROOT)))
    import uvicorn
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env')
    uvicorn.run('app.main:app',host=os.getenv('HOST','127.0.0.1'),port=int(os.getenv('PORT','8765')))
