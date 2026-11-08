from app import create_app

app = create_app()

if __name__ == '__main__':
    # Local development only: gunicorn on Render imports `app` and never runs this block.
    # load_dotenv=False: otherwise Flask also reads a .env from the folder it is started in
    # (the project-root .env is already loaded by app/__init__.py).
    app.run(debug=True, load_dotenv=False)