"""
Загружает модуль по пути к файлу, а не по имени пакета: файлы
strings.py в разных подпапках (resume_prompt,
resume_job_description_prompt, cover_letter_prompt) называются
одинаково, и обычный import их бы перепутал.
"""

# app/libs/resume_and_cover_builder/module_loader.py
import importlib.util
import sys


def load_module(module_path: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
