# AI-Vezérelt Parancsautomatizáló Rendszer

## A Rendszer Célja

Ez a projekt egy fejlett, AI-alapú parancsautomatizálási rendszert valósít meg, amely képes:
- AI asszisztensek (ChatGPT, Github Copilot) üzeneteiből parancsokat detektálni
- A parancsokat biztonságosan végrehajtani WebSocket kommunikáción keresztül
- Az eredményeket visszajuttatni az AI asszisztensnek
- A végrehajtást naplózni és újrajátszani

## Fő Modulok

### 1. AI Command Handler (`ai_command_handler.py`)
- AI üzenetek valósidejű figyelése
- Parancsok detektálása és validálása
- WebSocket kliens funkcionalitás
- Parancs előzmények és újrajátszás kezelése
- Selenium alapú böngésző automatizáció

### 2. Command Server (`command_server.py`) 
- WebSocket szerver implementáció
- Rendszerparancsok biztonságos végrehajtása
- Fájlműveletek kezelése
- Python kód végrehajtás
- Automatikus újrapróbálkozás hibák esetén

### 3. OpenAI Agent (`openai_agent.py`)
- OpenAI API integráció
- AI prompt kezelés és validáció
- Kontextus menedzsment
- Token optimalizáció

## Jelenlegi Működési Állapot

✅ Működő funkciók:
- Parancs detektálás és végrehajtás
- WebSocket kommunikáció
- Hibakezelés és újrapróbálkozás
- Parancs előzmények tárolása
- Alapvető fájlműveletek
- Naplózás

⚠️ Fejlesztés alatt:
- Parancs újrajátszás (REPLAY) funkció finomhangolása
- Hibakezelés további optimalizálása
- OpenAI integráció bővítése

## Tervezett Fejlesztési Irányok

1. **Biztonság Növelése**
   - Parancs végrehajtás további szigorítása
   - Fájlműveletek jogosultság kezelése
   - API kulcsok biztonságos tárolása

2. **Funkcionalitás Bővítése**
   - Több AI szolgáltató támogatása
   - Bővített parancs típusok
   - Aszinkron parancs végrehajtás
   - Docker konténerizáció

3. **Felhasználói Élmény**
   - Web alapú adminisztrációs felület
   - Részletesebb naplózás és monitorozás
   - Konfigurálható parancs szabályok

4. **Teljesítmény Optimalizálás**
   - Memória használat optimalizálása
   - WebSocket kapcsolat pooling
   - Parancs cache rendszer

## Telepítés és Használat

```bash
# Függőségek telepítése
pip install -r requirements.txt

# Command Server indítása
python command_server.py

# AI Command Handler indítása
python ai_command_handler.py
```

## Licensz
MIT License - lásd LICENSE fájl