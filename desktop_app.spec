# -*- mode: python ; coding: utf-8 -*-
# Собирает desktop_app.py в exe: `pyinstaller desktop_app.spec`.
# one-dir режим (не one-file) — надёжнее для Selenium/webdriver-manager,
# которые сами качают/находят chromedriver рядом с процессом.
#
# PyInstaller не кросс-компилирует — собирать нужно на каждой
# целевой ОС отдельно (macOS-сборка даёт CrossJob-AI.app, Windows —
# CrossJob-AI.exe; результат появляется в dist/).

import sys

a = Analysis(
    ["desktop_app.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("src/webui/static", "src/webui/static"),
        ("data_folder_example", "data_folder_example"),
        # Всё, что ResumeFacade/StyleManager грузят по прямому пути
        # (importlib.util.spec_from_file_location для strings.py,
        # обычное чтение файлов для CSS) — PyInstaller не видит такую
        # динамическую загрузку при анализе импортов, поэтому эти
        # директории нужно бандлить явно как data-файлы.
        (
            "src/libs/resume_and_cover_builder/resume_style",
            "src/libs/resume_and_cover_builder/resume_style",
        ),
        (
            "src/libs/resume_and_cover_builder/resume_prompt",
            "src/libs/resume_and_cover_builder/resume_prompt",
        ),
        (
            "src/libs/resume_and_cover_builder/resume_job_description_prompt",
            "src/libs/resume_and_cover_builder/resume_job_description_prompt",
        ),
        (
            "src/libs/resume_and_cover_builder/cover_letter_prompt",
            "src/libs/resume_and_cover_builder/cover_letter_prompt",
        ),
    ],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CrossJob-AI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="CrossJob-AI",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="CrossJob-AI.app",
        icon=None,
        bundle_identifier="ru.crossjob-ai.desktop",
        info_plist={
            "NSHighResolutionCapable": True,
            "LSBackgroundOnly": False,
        },
    )
