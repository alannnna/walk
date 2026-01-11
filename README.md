# to run
uv run python app.py

## prereqs before running
1. copy env_template.txt to .env and fill out the token and other fields

# deploy info
Running on Railway; redeploys automatically on push. All the .env vars need to be set in Railway variables. There is also DATABASE_PATH=/data/database.db and a Railway volume mounted at /data. The custom domain was configured both in Railway (Settings / Networking) and Spaceship (Advanced DNS / CNAME).
