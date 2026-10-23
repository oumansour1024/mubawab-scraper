@echo off
@REM  REM scripts\run_scraper.bat
@REM  cd /d C:\AllProjects\data-enginer\mubawab-scraper
@REM  call .venv\Scripts\activate

REM Créer dossier logs si absent
if not exist logs mkdir logs

REM Lancer avec log
mubawab-scraper-cli details ^
  --transaction all ^
  --city all ^
  --limit 0 ^
  --workers 4 ^
  >> logs\scraper_%date:~-4%%date:~3,2%%date:~0,2%.log 2>&1


REM mubawab-scraper-cli details   --transaction all --city all --limit 500 --workers 4