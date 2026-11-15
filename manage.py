#!/usr/bin/env python
import os
import sys
from lps.env import load_env

if __name__ == "__main__":
    load_env(".env")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lps.settings")
    if len(sys.argv) >= 2 and sys.argv[1] == "runserver":
        # El comando local publica los estáticos aunque DEBUG siga desactivado.
        os.environ.setdefault("SERVE_STATIC", "true")
        if len(sys.argv) == 2:
            sys.argv.append("0.0.0.0:" + os.getenv("PORT", "8080"))
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
