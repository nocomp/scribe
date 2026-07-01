#!/usr/bin/env bash
# Lancement d'une instance SCRIBE (exemple générique).
# Adaptez le port et le fichier de configuration à votre établissement.
export SCRIBE_CONFIG_FILE="${SCRIBE_CONFIG_FILE:-config.xml}"
exec uvicorn main:app --host 0.0.0.0 --port "${SCRIBE_PORT:-8000}"
