"""Shared synthetic fixtures for tests — no real-person identifiers.

All names, handles, NIMs, and phones here are invented for CI/demo only.
"""

# Phone: 555-style demo number (not a claimed real subscriber)
PHONE_DISPLAY = "0812-5550-0100"
PHONE_DIGITS = "081255500100"
PHONE_E164 = "+6281255500100"
PHONE_SEED = f"phone:{PHONE_DISPLAY}"

# Dual-handle unknown-name path (invented doubled-letter usernames)
HANDLE_IG = "llaauurraa"  # morphs toward "laura"
HANDLE_TT = "zzfandomxx"
HANDLE_IG_URL = f"https://www.instagram.com/{HANDLE_IG}"
HANDLE_TT_URL = f"https://www.tiktok.com/@{HANDLE_TT}"
DISPLAY_NICK = "laura"

# Legal-name style seeds (placeholder personas)
NAME_ACADEMIC = "Jordan Sample Subject"
NAME_HITL = "Testa Personita"
NAME_HITL_NIM = "25081109901"
NAME_HITL_PT = "UNIVERSITAS CONTOH"

# Campus list extract (synthetic NIMs + names; CELIA hits cel-family grep)
CAMPUS_LIST_SAMPLE = """
1565 25011103193 CELIA SAMPLE PERSONA P FISIP ILMU KOMUNIKASI
1566 25011103619 RINA PLACEHOLDER DEMO P FISIP ILMU KOMUNIKASI
25011104828 SITI SAMPLE TESTROW P FISIP
25081109901 ANDI SAMPLE MAHASISWA P FK KEDOKTERAN
25011207721 NADYA SAMPLE PLACEHOLDER
"""

OTHER_ACADEMIC = "other:FK CONTOH"
OTHER_ORG = "other:ORG SAMPLE FK"
OTHER_GEO = "other:Kota Contoh"
OTHER_YEAR = "other:masuk 2025"
OTHER_ILKOM = "other:ilmu komunikasi contoh 2025"
OTHER_NAME_UNKNOWN = "other:legal name unknown at start"
