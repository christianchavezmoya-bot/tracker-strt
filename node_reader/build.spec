# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for HOLO MQTT Broker Windows .exe"""

block_cipher = None

a = Analysis(
    ['node_reader/app.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'paho.mqtt.client',
        'amqtt',
        'amqtt.broker',
        'amqtt.plugins.authentication',
        'node_reader.capture_plugin',
        'node_reader.pc_broker',
        'node_reader.mqtt_parse',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['bleak'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='HOLO-MQTT-Broker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
