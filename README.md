# Backup Test Data Generator

Ein Python-CLI zum Erzeugen und Verändern großer Testdatenbestände für Full-, Incremental- und Restore-Tests.

Das Tool kann:

- Testdaten von wenigen KB bis in den TB-Bereich erzeugen
- zufällige, komprimierbare, gemischte oder Sparse-Daten erstellen
- Fileserver-ähnliche Größenverteilungen simulieren
- vorhandene Dateien ändern und löschen
- neue Daten für Incremental-Backups hinzufügen
- SHA-256-Manifeste erstellen
- einen Restore bytegenau gegen ein Manifest prüfen
- fehlende, zusätzliche, beschädigte und falsch große Dateien erkennen
- einen maschinenlesbaren JSON-Prüfbericht erzeugen

## Voraussetzungen

- Python 3.10 oder neuer
- keine zusätzlichen Python-Pakete
- ausreichend freier Speicherplatz bei echten Zufallsdaten

Prüfen:

```bash
python --version
```

Je nach Betriebssystem kann der Befehl auch `python3` oder unter Windows `py` heißen.

## Installation

### Variante 1: Direkt verwenden

Lege diese Dateien in ein gemeinsames Projektverzeichnis:

```text
backup-testdata/
├── backup_testdata.py
├── README.md
└── .gitignore
```

Linux/macOS optional ausführbar machen:

```bash
chmod +x backup_testdata.py
```

Danach entweder so starten:

```bash
python3 backup_testdata.py --help
```

oder direkt:

```bash
./backup_testdata.py --help
```

Unter Windows:

```powershell
py backup_testdata.py --help
```

### Variante 2: Repository klonen

```bash
git clone <REPOSITORY-URL>
cd backup-testdata
python3 backup_testdata.py --help
```

Für das Skript ist kein `pip install` erforderlich, weil ausschließlich die Python-Standardbibliothek verwendet wird.

## Schnellstart

### 1. Baseline erzeugen

```bash
python3 backup_testdata.py create ./testdata \
  --size 10GB \
  --profile fileserver \
  --data mixed \
  --seed 42 \
  --label baseline
```

Das erzeugt:

- einen Datenbestand unter `./testdata`
- ein SHA-256-Manifest unter `./testdata/.backup_manifests/manifest_baseline.json`
- einen Zeiger auf das neueste Manifest unter `./testdata/.backup_manifests/latest.txt`

### 2. Full Backup durchführen

Sichere das vollständige Verzeichnis `./testdata`, einschließlich des versteckten Unterverzeichnisses `.backup_manifests`.

### 3. Daten für ein Incremental-Backup verändern

```bash
python3 backup_testdata.py mutate ./testdata \
  --change 5 \
  --delete 2 \
  --add 1GB \
  --label incremental_01
```

Der Befehl führt die Schritte in dieser Reihenfolge aus:

1. `--delete 2` löscht zufällig 2 Prozent der vorhandenen Dateien.
2. Die Dateiliste wird neu eingelesen.
3. `--change 5` verändert zufällig 5 Prozent der danach verbleibenden Dateien.
4. Pro ausgewählter Datei werden bis zu 1 MB an einer zufälligen Position überschrieben.
5. `--add 1GB` erzeugt insgesamt 1 GB neue Zufallsdaten unter `incremental_new/`.
6. Das Skript erstellt das neue Manifest `manifest_incremental_01.json`.

`--change` und `--delete` beziehen sich auf die **Anzahl der Dateien**, nicht auf den Anteil der Datenmenge.

Beispiel bei 10.000 Ausgangsdateien:

- 2 Prozent Löschung: 200 Dateien werden gelöscht
- verbleibend: 9.800 Dateien
- 5 Prozent Änderung: 490 der verbleibenden Dateien werden verändert
- zusätzlich: 1 GB neue Dateien

### 4. Incremental-Backup durchführen

Sichere den veränderten Datenbestand mit der zu testenden Backup-Lösung.

### 5. Restore prüfen

Angenommen, das Backup wurde nach `./restore-test` wiederhergestellt:

```bash
python3 backup_testdata.py verify ./restore-test
```

Ohne `--manifest` verwendet das Skript das neueste Manifest unter:

```text
./restore-test/.backup_manifests/
```

Einen bestimmten Sicherungsstand prüfst du explizit:

```bash
python3 backup_testdata.py verify ./restore-test \
  --manifest ./restore-test/.backup_manifests/manifest_incremental_01.json
```

Wenn das Manifest außerhalb des Restore-Verzeichnisses aufbewahrt wurde:

```bash
python3 backup_testdata.py verify ./restore-test \
  --manifest ./manifests/manifest_incremental_01.json
```

## Befehle

### `create`

Erzeugt einen neuen Datenbestand und anschließend automatisch ein SHA-256-Manifest.

```bash
python3 backup_testdata.py create TARGET --size SIZE [OPTIONEN]
```

Optionen:

- `--size`: gesamte logische Datenmenge, beispielsweise `500MB`, `10GB` oder `1TB`
- `--profile`: Verteilung der Dateigrößen, Standard ist `mixed`
- `--data`: Inhaltstyp, Standard ist `mixed`
- `--seed`: reproduzierbare Auswahl von Dateigrößen und Datentypen
- `--label`: Name des erzeugten Manifests, Standard ist `baseline`

Beispiele:

```bash
python3 backup_testdata.py create ./testdata --size 1GB
python3 backup_testdata.py create ./testdata --size 100GB --profile fileserver
python3 backup_testdata.py create ./testdata --size 1TB --profile large --data random
```

### `mutate`

Verändert einen vorhandenen Testdatenbestand und erstellt danach ein neues Manifest.

```bash
python3 backup_testdata.py mutate TARGET [OPTIONEN]
```

Optionen:

- `--change 5`: verändert 5 Prozent der nach der Löschung verbleibenden Dateien
- `--delete 2`: löscht 2 Prozent der vorhandenen Dateien
- `--add 1GB`: fügt insgesamt 1 GB neue Zufallsdaten hinzu
- `--seed`: macht die Dateiauswahl reproduzierbar
- `--label`: Bezeichnung des neuen Manifests

Ohne `--change`, `--delete` und `--add` gelten die Standardwerte:

```text
--change 5
--delete 1
--add 0
```

### `manifest`

Erstellt einen neuen SHA-256-Snapshot des aktuellen Datenbestands, ohne Dateien zu verändern.

```bash
python3 backup_testdata.py manifest ./testdata --label vor_backup
```

Das ist nützlich, wenn zwischen Datenänderung und Backup bewusst ein eigener Prüfsnapshot erstellt werden soll.

### `verify`

Prüft einen wiederhergestellten Datenbestand gegen ein Manifest.

```bash
python3 backup_testdata.py verify TARGET [--manifest DATEI]
```

Die Prüfung erkennt:

- fehlende Dateien
- falsche Dateigrößen
- abweichende SHA-256-Werte
- Lesefehler
- zusätzliche Dateien

Zusätzliche Dateien kannst du ignorieren:

```bash
python3 backup_testdata.py verify ./restore-test \
  --manifest ./manifest_incremental_01.json \
  --ignore-extra
```

Nach jeder Prüfung wird im Restore-Verzeichnis ein JSON-Bericht erzeugt:

```text
restore_verification_YYYYMMDD_HHMMSS.json
```

Exit-Codes:

- `0`: Restore-Prüfung bestanden
- `1`: Aufruf-, Datei-, Manifest- oder sonstiger Laufzeitfehler
- `2`: Restore-Prüfung durchgeführt, aber Abweichungen gefunden

Beispiel für Bash-Automatisierung:

```bash
python3 backup_testdata.py verify ./restore-test \
  --manifest ./manifest_incremental_01.json

case $? in
  0) echo "Restore ist vollständig und bytegenau korrekt" ;;
  1) echo "Prüfung konnte nicht korrekt ausgeführt werden" ;;
  2) echo "Restore enthält Abweichungen" ;;
esac
```

PowerShell:

```powershell
py backup_testdata.py verify .\restore-test `
  --manifest .\manifest_incremental_01.json

switch ($LASTEXITCODE) {
    0 { Write-Host "Restore ist vollständig und bytegenau korrekt" }
    1 { Write-Host "Prüfung konnte nicht korrekt ausgeführt werden" }
    2 { Write-Host "Restore enthält Abweichungen" }
}
```

### `clean`

Löscht einen Testdatenbestand nach ausdrücklicher Bestätigung:

```bash
python3 backup_testdata.py clean ./testdata
```

Zur Bestätigung muss exakt `DELETE` eingegeben werden.

## Profile

### `mixed`

Gemischte Dateigrößen von kleinen Dateien bis zu großen Dateien im GB-Bereich. Geeignet als allgemeiner Backup-Test.

```bash
python3 backup_testdata.py create ./testdata --size 100GB --profile mixed
```

### `fileserver`

Höherer Anteil kleiner und mittlerer Dateien. Geeignet, um typische Dateisystem- und Metadatenbelastung zu simulieren.

```bash
python3 backup_testdata.py create ./testdata --size 100GB --profile fileserver
```

### `large`

Große Dateien zwischen 1 GB und 10 GB. Geeignet für Durchsatztests mit wenigen großen Objekten.

```bash
python3 backup_testdata.py create ./testdata --size 1TB --profile large
```

## Datentypen

### `random`

Erzeugt echte Zufallsdaten über `os.urandom()`. Diese Daten sind praktisch nicht sinnvoll komprimierbar und eignen sich für Worst-Case-Tests von Kompression, Deduplizierung, Netzwerk und Storage.

```bash
python3 backup_testdata.py create ./testdata --size 100GB --data random
```

### `compressible`

Erzeugt sich wiederholende Datenmuster. Geeignet zum Testen von Kompression und Deduplizierung.

```bash
python3 backup_testdata.py create ./testdata --size 100GB --data compressible
```

### `mixed`

Mischt zufällige und komprimierbare Dateien. Dies ist der Standardmodus.

```bash
python3 backup_testdata.py create ./testdata --size 100GB --data mixed
```

### `sparse`

Erzeugt Dateien mit der gewünschten logischen Größe über `truncate()`. Abhängig von Dateisystem und Backupsoftware kann der physisch belegte beziehungsweise gesicherte Speicher deutlich kleiner sein.

```bash
python3 backup_testdata.py create ./testdata --size 1TB --data sparse
```

Sparse-Dateien sind deshalb kein Ersatz für echte 1-TB-Schreib- und Lesetests.

## Manifestformat

Ein Manifest ist eine JSON-Datei mit Metadaten zum vollständigen Datenbestand. Für jede Datei speichert es unter anderem:

```json
{
  "path": "set_0000/file_00000001.bin",
  "size": 1048576,
  "mtime_ns": 1792560000000000000,
  "sha256": "..."
}
```

Die Pfade werden relativ zur Wurzel des Testdatenverzeichnisses gespeichert. Dadurch kann der Restore an einem anderen absoluten Speicherort geprüft werden.

## Empfohlener Testablauf

1. Baseline mit `create` erzeugen.
2. Full Backup ausführen.
3. Baseline-Restore durchführen und gegen `manifest_baseline.json` prüfen.
4. Ausgangsdaten mit `mutate` verändern.
5. Incremental-Backup ausführen.
6. Restore bis zu diesem Sicherungsstand durchführen.
7. Gegen das passende Incremental-Manifest prüfen.
8. JSON-Prüfbericht zusammen mit den Backup-Job-Logs aufbewahren.

Verwende immer das Manifest, das exakt zum wiederhergestellten Sicherungsstand gehört. Ein Baseline-Manifest muss bei einem Restore nach späteren Änderungen erwartungsgemäß Abweichungen melden.

## Performance und Speicherbedarf

- `random`, `compressible` und `mixed` schreiben die eingestellte Datenmenge tatsächlich auf den Datenträger.
- `sparse` kann wesentlich weniger physischen Speicher belegen als seine logische Größe.
- Die Manifest-Erstellung liest jede Datei vollständig einmal ein.
- Die Restore-Prüfung liest jede wiederhergestellte Datei erneut vollständig ein.
- Bei 1 TB entstehen daher zusätzlich zum Erzeugen und Sichern mindestens zwei vollständige Lesevorgänge für die SHA-256-Erstellung und -Prüfung.
- SHA-256 erhöht die CPU- und I/O-Last. Das ist für eine vollständige Integritätsprüfung beabsichtigt.

Vor großen Tests freien Speicher prüfen:

Linux/macOS:

```bash
df -h
```

Windows PowerShell:

```powershell
Get-PSDrive -PSProvider FileSystem
```

## Sicherheitshinweise

- Verwende für Tests ein dediziertes Verzeichnis oder Volume.
- `mutate` löscht tatsächlich Dateien innerhalb des angegebenen Zielverzeichnisses.
- `clean` löscht das gesamte angegebene Zielverzeichnis rekursiv.
- Prüfe deshalb den Zielpfad vor jedem Aufruf sorgfältig.
- Erzeuge große Zufallsdaten nicht versehentlich auf produktiven Volumes.
- Die `.gitignore` schützt typische lokale Ausgabeordner, ersetzt aber keine sorgfältige Pfadwahl.

## Git-Hinweise

Die mitgelieferte `.gitignore` ignoriert unter anderem:

- `testdata/`
- `restore-test/`
- `backup-data/`
- `restore-data/`
- Verzeichnisse mit dem Präfix `generated-`
- `.backup_manifests/`
- Restore-Prüfberichte
- große generierte Binärdateien wie `*.bin`, `*.dat`, `*.img` und `*.sparse`

Bereits von Git versionierte Dateien werden durch eine spätere `.gitignore` nicht automatisch entfernt. Falls Testdaten versehentlich bereits im Git-Index liegen:

```bash
git rm -r --cached testdata restore-test backup-data restore-data
```

Danach den Git-Status kontrollieren:

```bash
git status
```

## Hilfe

```bash
python3 backup_testdata.py --help
python3 backup_testdata.py create --help
python3 backup_testdata.py mutate --help
python3 backup_testdata.py manifest --help
python3 backup_testdata.py verify --help
```
