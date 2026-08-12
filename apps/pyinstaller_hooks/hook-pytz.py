"""Skip pytz's IANA zoneinfo data files in frozen builds.

ChilmAI never does timezone-aware datetime/pandas operations (only a
fixed JST offset via stdlib datetime.timezone), so pytz's ~600 tz
database files add dead weight and produce unfamiliar filenames like
"Egypt" when users unzip the release.

This replaces PyInstaller's built-in hook-pytz.py, so it must keep that
hook's excludedimports (pytz's pkg_resources fallback codepath) or it
silently regresses back in.
"""

datas = []
excludedimports = ["pkg_resources"]
