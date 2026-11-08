from app import create_app

app = create_app()

if __name__ == '__main__':
    # load_dotenv=False: otherwise Flask also reads a .env from the folder it is started in.
    # The project-root .env is already loaded by app/__init__.py, and debug follows its FLASK_DEBUG.
    app.run(load_dotenv=False)