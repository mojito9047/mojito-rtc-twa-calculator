"""Mojito RTC TWA Calculator: server-side modules.

app.py (in the app folder) creates the Flask app and registers the blueprints
from instruments, course_data and race_officer. storage owns every file path.
"""

# The release shown on every page. Bump it with each tagged version (git tag
# vNN); tests/test_api.py checks it matches the newest README version heading.
VERSION = "v73"
