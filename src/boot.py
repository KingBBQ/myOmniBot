# boot.py - nur fuer Boards mit nativem USB (MakerPi RP2040).
#
# Schaltet einen zweiten CDC-Kanal frei: die REPL bleibt auf usb_cdc.console,
# der Companion Computer spricht ueber usb_cdc.data. Ohne diese Datei gibt es
# nur die REPL, und hardware.open_link() findet keinen Datenkanal.
#
# Auf dem klassischen ESP32 (RoboESP32) hat die Datei keine Wirkung - der hat
# kein natives USB. Dort laeuft die Verbindung ueber UART2, und boot.py muss
# gar nicht erst aufs Board.
#
# boot.py wird nur beim Hard-Reset ausgefuehrt, nicht beim Soft-Reboot durch
# tools/upload.py --run. Nach dem Aufspielen einmal den Reset-Knopf druecken.

try:
    import usb_cdc

    usb_cdc.enable(console=True, data=True)
except ImportError:
    pass  # Board ohne natives USB
